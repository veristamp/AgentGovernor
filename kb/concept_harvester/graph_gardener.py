"""
Graph Gardener - Async Maintenance for the Dual-Graph.

Periodic cleanup tasks:
1. Synonym Compaction: Merge similar concepts via Qdrant recommend
2. Island Pruning: Remove orphaned concepts (degree=1, age>X days)
3. Supernode Demotion: Reduce weights for overconnected nodes

Usage:
    uv run -m concept_harvester.graph_gardener --threshold 0.92
"""

import asyncio
import argparse
import os
from typing import Dict, List

from sqlalchemy import text

from config import get_logger

logger = get_logger("Gardener")


class DatabaseGardener:
    """
    Async maintenance agent for the Dual-Graph.
    
    Operates on Postgres (Hard Graph) and Qdrant (Soft Graph).
    """
    
    def __init__(
        self,
        pg_session,
        qdrant_client=None,
        collection_name: str = "kb_concepts",
        synonym_threshold: float = 0.92,
        island_min_age_days: int = 7,
        supernode_threshold_percent: float = 0.10
    ):
        self.pg_session = pg_session
        self.qdrant_client = qdrant_client
        self.collection_name = collection_name
        self.synonym_threshold = synonym_threshold
        self.island_min_age_days = island_min_age_days
        self.supernode_threshold_percent = supernode_threshold_percent
        self._stats = {"synonyms_merged": 0, "islands_pruned": 0, "supernodes_demoted": 0, "edges_processed": 0}
    
    async def run(self) -> Dict[str, int]:
        """Run all maintenance tasks."""
        logger.info("🌱 Starting maintenance cycle...")
        self._stats = {k: 0 for k in self._stats}
        
        await self.compact_synonyms()
        await self.prune_islands()
        await self.demote_supernodes()
        
        logger.info(f"✨ Maintenance complete: {self._stats}")
        return self._stats
    
    async def _qdrant_call(self, method: str, **kwargs):
        """Universal async/sync Qdrant caller."""
        if not self.qdrant_client:
            return None
        fn = getattr(self.qdrant_client, method, None)
        if not fn:
            return None
        if asyncio.iscoroutinefunction(fn):
            return await fn(**kwargs)
        return fn(**kwargs)
    
    async def compact_synonyms(self):
        """Merge concepts with high vector similarity."""
        if not self.qdrant_client:
            logger.warning("No Qdrant client - skipping synonym compaction")
            return
        
        logger.info(f"🔍 Compacting synonyms (threshold > {self.synonym_threshold})...")
        
        result = await self.pg_session.execute(text("SELECT id, name FROM global_concepts ORDER BY id"))
        concepts = result.fetchall()
        
        if len(concepts) < 2:
            return
        
        merged = 0
        processed = set()
        
        for cid, name in concepts:
            if cid in processed:
                continue
            
            try:
                similar = await self._qdrant_call(
                    'recommend',
                    collection_name=self.collection_name,
                    positive=[cid],
                    limit=5,
                    score_threshold=self.synonym_threshold
                )
                
                if not similar:
                    continue
                
                for hit in similar:
                    if hit.id == cid or hit.id in processed:
                        continue
                    
                    if await self._merge_concepts(cid, hit.id, name):
                        processed.add(hit.id)
                        merged += 1
                        logger.info(f"   🔗 Merged: '{hit.payload.get('canonical_name', hit.id)}' → '{name}'")
                        
            except Exception as e:
                logger.debug(f"Recommend skipped for {name}: {e}")
        
        self._stats["synonyms_merged"] = merged
    
    async def prune_islands(self):
        """Remove orphaned concepts (degree=1, old)."""
        logger.info(f"🧹 Pruning islands (degree=1, age > {self.island_min_age_days}d)...")
        
        result = await self.pg_session.execute(text("""
            WITH edge_counts AS (
                SELECT target_id, COUNT(*) as cnt FROM edges WHERE edge_type = 'MENTIONS' GROUP BY target_id
            )
            SELECT gc.id, gc.name FROM global_concepts gc
            JOIN edge_counts ec ON gc.id = ec.target_id
            WHERE ec.cnt = 1 AND gc.created_at < NOW() - (:days * INTERVAL '1 day')
        """), {"days": self.island_min_age_days})
        
        islands = result.fetchall()
        
        if not islands:
            logger.info("   ✅ No islands to prune")
            return
        
        ids = [i[0] for i in islands]
        
        await self.pg_session.execute(text("DELETE FROM edges WHERE target_id = ANY(:ids) OR source_id = ANY(:ids)"), {"ids": ids})
        await self.pg_session.execute(text("DELETE FROM global_concepts WHERE id = ANY(:ids)"), {"ids": ids})
        
        try:
            await self._qdrant_call('delete', collection_name=self.collection_name, points_selector=ids)
        except:
            pass
        
        await self.pg_session.commit()
        self._stats["islands_pruned"] = len(islands)
        logger.info(f"   🗑️ Pruned {len(islands)} island concepts")
    
    async def demote_supernodes(self):
        """Reduce weights for overconnected concepts."""
        logger.info(f"📉 Demoting supernodes (threshold > {self.supernode_threshold_percent*100}%)...")
        
        count_result = await self.pg_session.execute(text("SELECT COUNT(*) FROM nodes WHERE type = 'CHUNK'"))
        total = count_result.scalar() or 1
        
        threshold = max(int(total * self.supernode_threshold_percent), 10)
        
        result = await self.pg_session.execute(text("""
            SELECT target_id, COUNT(*) as cnt FROM edges
            WHERE edge_type = 'MENTIONS' GROUP BY target_id HAVING COUNT(*) > :t
        """), {"t": threshold})
        
        supernodes = result.fetchall()
        
        if not supernodes:
            logger.info("   ✅ No supernodes to demote")
            return
        
        for cid, edge_count in supernodes:
            factor = min(0.1, threshold / edge_count)
            await self.pg_session.execute(text("""
                UPDATE edges SET weight = weight * :f, edge_type = 'BELONGS_TO_DOMAIN'
                WHERE target_id = :id AND edge_type = 'MENTIONS'
            """), {"f": factor, "id": cid})
            self._stats["edges_processed"] += edge_count
        
        await self.pg_session.commit()
        self._stats["supernodes_demoted"] = len(supernodes)
        logger.info(f"   📉 Demoted {len(supernodes)} supernodes ({self._stats['edges_processed']} edges)")
    
    async def _merge_concepts(self, canonical_id: int, victim_id: int, canonical_name: str) -> bool:
        """Merge victim concept into canonical."""
        try:
            # Rewire edges
            await self.pg_session.execute(text("""
                INSERT INTO edges (source_id, target_id, edge_type, weight)
                SELECT source_id, :cid, edge_type, weight FROM edges WHERE target_id = :vid
                ON CONFLICT (source_id, target_id, edge_type) DO NOTHING
            """), {"cid": canonical_id, "vid": victim_id})
            
            await self.pg_session.execute(text("DELETE FROM edges WHERE target_id = :vid"), {"vid": victim_id})
            
            # Transfer doc_count & delete
            await self.pg_session.execute(text("""
                UPDATE global_concepts SET doc_count = doc_count + 
                    (SELECT doc_count FROM global_concepts WHERE id = :vid)
                WHERE id = :cid
            """), {"cid": canonical_id, "vid": victim_id})
            await self.pg_session.execute(text("DELETE FROM global_concepts WHERE id = :vid"), {"vid": victim_id})
            
            try:
                await self._qdrant_call('delete', collection_name=self.collection_name, points_selector=[victim_id])
            except:
                pass
            
            await self.pg_session.commit()
            return True
        except Exception as e:
            logger.error(f"Merge failed {victim_id} → {canonical_id}: {e}")
            await self.pg_session.rollback()
            return False


async def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Graph Gardener: Automated Maintenance")
    parser.add_argument("--threshold", type=float, default=0.92, help="Synonym threshold")
    parser.add_argument("--age", type=int, default=7, help="Island min age (days)")
    parser.add_argument("--super-pct", type=float, default=0.10, help="Supernode threshold %")
    args = parser.parse_args()
    
    from dotenv import load_dotenv
    load_dotenv()
    
    from db.schema import get_async_engine, get_session_maker
    from qdrant_client import AsyncQdrantClient
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("No DATABASE_URL")
        return
    
    engine = get_async_engine(db_url)
    qdrant = AsyncQdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))
    
    async with get_session_maker(engine)() as session:
        gardener = DatabaseGardener(
            pg_session=session,
            qdrant_client=qdrant,
            synonym_threshold=args.threshold,
            island_min_age_days=args.age,
            supernode_threshold_percent=args.super_pct
        )
        await gardener.run()
    
    await qdrant.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
