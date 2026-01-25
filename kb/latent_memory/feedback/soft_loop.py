# latent_memory/feedback/soft_loop.py
"""
Soft Feedback Loop - Automatic Citation-Driven Learning.

Implements the "Generator teaches Retriever" principle from CLaRa,
but mechanically via explicit graph edges instead of backpropagation.

The Key Insight:
- If the LLM CITES a chunk in its response → that chunk was USEFUL
- If the LLM IGNORES a chunk → that chunk was NOISE for this query
- No user feedback needed! The generator IS the feedback signal.

This creates a Data Flywheel:
1. Every interaction refines the retrieval graph
2. Good chunks get boosted
3. Noisy chunks get decayed
4. Retrieval improves automatically

Usage:
    from latent_memory.feedback import SoftFeedbackLoop
    
    loop = SoftFeedbackLoop()
    
    # After every turn (AUTOMATIC - no user interaction)
    await loop.process_turn(
        query="How do I run the chunker?",
        retrieved_chunks=chunks_from_qdrant,
        llm_response="To run the chunker, use `uv run` [cite:123]..."
    )
    
    # Future retrieval is automatically boosted
    boosted = loop.boost_results(query, base_results)
"""

from typing import List, Dict, Any, Optional
from collections import defaultdict
import hashlib
import time

from .citation_extractor import extract_citations
from .signal_tracker import ChunkSignal
from config import get_logger

logger = get_logger("latent_memory.feedback.soft_loop")


class SoftFeedbackLoop:
    """
    Soft (Automatic) Feedback Loop.
    
    Learns from LLM behavior without user interaction:
    - Cited chunks get BOOSTED
    - Ignored chunks get DECAYED
    - All signals are "soft" (inferred, not confirmed)
    
    Integration with Dual-Graph:
    - Creates ANSWERED_BY edges in Postgres for cited chunks
    - Enables "Hub-Hop" pattern: Query → Concept → Chunk
    """
    
    def __init__(
        self,
        pg_session: Optional[Any] = None,
        boost_weight: float = 0.3,
        decay_factor: float = 0.9,
        min_confidence: float = 0.2,
        persist_to_postgres: bool = True
    ):
        """
        Initialize the soft feedback loop.
        
        Args:
            pg_session: SQLAlchemy async session for Postgres (Dual-Graph)
            boost_weight: How much to boost cited chunks (0-1)
            decay_factor: Factor to decay ignored chunk edges (0-1)
            min_confidence: Minimum confidence to apply boost
            persist_to_postgres: Whether to write edges to Postgres
        """
        self._pg_session = pg_session
        self.boost_weight = boost_weight
        self.decay_factor = decay_factor
        self.min_confidence = min_confidence
        self.persist_to_postgres = persist_to_postgres
        
        # Graph edges: query_hash -> chunk_id -> ChunkSignal
        self._graph: Dict[str, Dict[int, ChunkSignal]] = defaultdict(dict)
        
        # Query text cache for Postgres inserts
        self._query_cache: Dict[str, str] = {}
        
        # Stats
        self._total_turns = 0
        self._total_citations = 0
        self._total_ignores = 0
        self._postgres_edges_written = 0
    
    def set_pg_session(self, session):
        """Set Postgres session for edge persistence."""
        self._pg_session = session
    
    # =========================================================================
    # CORE: AUTOMATIC FEEDBACK
    # =========================================================================
    
    async def process_turn(
        self,
        query: str,
        retrieved_chunks: List[Dict[str, Any]],
        llm_response: str,
        query_vector: Optional[List[float]] = None,
        query_concepts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Process a complete turn. AUTOMATIC - runs after every LLM response.
        
        This is the "Joint Optimization" step:
        - Cited chunks get BOOSTED
        - Ignored chunks get DECAYED
        - Edges are persisted to Postgres (Dual-Graph)
        
        Args:
            query: The user's query
            retrieved_chunks: Chunks that were retrieved for this query
            llm_response: The LLM's final response (may contain citations)
            query_vector: Optional query embedding
            query_concepts: Optional concepts for Hub-Hop
            
        Returns:
            Processing stats
        """
        self._total_turns += 1
        query_hash = self._hash_query(query)
        now = time.time()
        
        # Cache query text for Postgres
        self._query_cache[query_hash] = query
        
        # 1. Extract citations from the response
        cited_ids = extract_citations(llm_response, retrieved_chunks)
        retrieved_ids = {c.get("id") for c in retrieved_chunks}
        ignored_ids = retrieved_ids - cited_ids
        
        # 2. Update in-memory graph edges
        for chunk_id in cited_ids:
            self._boost_edge(query_hash, chunk_id, now)
            self._total_citations += 1
        
        for chunk_id in ignored_ids:
            self._decay_edge(query_hash, chunk_id, now)
            self._total_ignores += 1
        
        # 3. Persist to Postgres (Dual-Graph integration)
        pg_edges_written = 0
        if self.persist_to_postgres and self._pg_session and cited_ids:
            pg_edges_written = await self._persist_edges_to_postgres(
                query_hash=query_hash,
                query_text=query,
                cited_chunk_ids=list(cited_ids),
                query_concepts=query_concepts or [],
                timestamp=now
            )
            self._postgres_edges_written += pg_edges_written
        
        result = {
            "query_hash": query_hash,
            "retrieved": len(retrieved_ids),
            "cited": len(cited_ids),
            "ignored": len(ignored_ids),
            "cited_ids": list(cited_ids),
            "ignored_ids": list(ignored_ids),
            "postgres_edges": pg_edges_written,
            "signal_type": "soft"
        }
        
        logger.info(
            f"📊 [SOFT] Turn processed: {len(cited_ids)} cited, {len(ignored_ids)} ignored "
            f"(Total: {self._total_turns} turns)"
        )
        
        return result
    
    async def _persist_edges_to_postgres(
        self,
        query_hash: str,
        query_text: str,
        cited_chunk_ids: List[int],
        query_concepts: List[str],
        timestamp: float
    ) -> int:
        """Write ANSWERED_BY edges to Postgres for the Dual-Graph."""
        if not self._pg_session:
            return 0
        
        edges_written = 0
        query_int = int(query_hash[:15], 16) % (2**63)
        
        try:
            if callable(self._pg_session):
                async with self._pg_session() as session:
                    from sqlalchemy import text
                    
                    for chunk_id in cited_chunk_ids:
                        await session.execute(
                            text("""
                                INSERT INTO edges (source_id, target_id, edge_type, weight, properties)
                                VALUES (:source, :target, :edge_type, :weight, :props)
                                ON CONFLICT (source_id, target_id, edge_type) 
                                DO UPDATE SET weight = edges.weight + 0.1
                            """),
                            {
                                "source": chunk_id,
                                "target": query_int,
                                "edge_type": "SOFT_CITED",
                                "weight": 1.0,
                                "props": f'{{"query": "{query_text[:100]}", "signal": "soft"}}'
                            }
                        )
                        edges_written += 1
                    
                    await session.commit()
        
        except Exception as e:
            logger.warning(f"Failed to persist soft edges: {e}")
        
        return edges_written
    
    def _boost_edge(self, query_hash: str, chunk_id: int, timestamp: float):
        """Strengthen the edge between query and chunk."""
        if chunk_id not in self._graph[query_hash]:
            self._graph[query_hash][chunk_id] = ChunkSignal(chunk_id=chunk_id, signal_type="soft")
        
        signal = self._graph[query_hash][chunk_id]
        signal.citation_count += 1
        signal.boost_score = min(1.0, signal.boost_score + 0.2)
        signal.last_updated = timestamp
    
    def _decay_edge(self, query_hash: str, chunk_id: int, timestamp: float):
        """Weaken the edge between query and chunk."""
        if chunk_id not in self._graph[query_hash]:
            self._graph[query_hash][chunk_id] = ChunkSignal(chunk_id=chunk_id, signal_type="soft")
        
        signal = self._graph[query_hash][chunk_id]
        signal.ignore_count += 1
        signal.boost_score = max(-0.5, signal.boost_score * self.decay_factor - 0.05)
        signal.last_updated = timestamp
    
    # =========================================================================
    # RETRIEVAL BOOSTING
    # =========================================================================
    
    def boost_results(
        self,
        query: str,
        base_results: List[Dict[str, Any]],
        score_key: str = "score"
    ) -> List[Dict[str, Any]]:
        """
        Boost retrieval results based on learned associations.
        
        Args:
            query: Current user query
            base_results: Results from vector search
            score_key: Key containing the similarity score
            
        Returns:
            Re-ranked results with feedback boost applied
        """
        query_hash = self._hash_query(query)
        
        # Get boosts from direct matches
        direct_boosts = {}
        if query_hash in self._graph:
            for chunk_id, signal in self._graph[query_hash].items():
                if signal.confidence >= self.min_confidence:
                    direct_boosts[chunk_id] = signal.boost_score
        
        # Apply boosts
        boosted = []
        boost_count = 0
        penalty_count = 0
        
        for result in base_results:
            result = result.copy()
            chunk_id = result.get("id")
            boost = direct_boosts.get(chunk_id, 0.0)
            
            if boost != 0.0:
                original_score = result.get(score_key, 0.0)
                boosted_score = original_score + (boost * self.boost_weight)
                
                result[score_key] = boosted_score
                result["_feedback_boost"] = boost
                result["_original_score"] = original_score
                result["_signal_type"] = "soft"
                
                if boost > 0:
                    boost_count += 1
                else:
                    penalty_count += 1
            
            boosted.append(result)
        
        # Re-sort
        boosted.sort(key=lambda x: x.get(score_key, 0), reverse=True)
        
        if boost_count or penalty_count:
            logger.info(f"🎯 [SOFT] Applied: +{boost_count} boosted, -{penalty_count} penalized")
        
        return boosted
    
    # =========================================================================
    # UTILITIES
    # =========================================================================
    
    def _hash_query(self, query: str) -> str:
        """Create a normalized hash for a query."""
        normalized = " ".join(query.lower().strip().split())
        return hashlib.md5(normalized.encode()).hexdigest()[:16]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get soft feedback statistics."""
        total_edges = sum(len(signals) for signals in self._graph.values())
        positive_edges = sum(
            1 for signals in self._graph.values()
            for s in signals.values() if s.boost_score > 0
        )
        
        return {
            "signal_type": "soft",
            "total_turns": self._total_turns,
            "total_citations": self._total_citations,
            "total_ignores": self._total_ignores,
            "unique_queries": len(self._graph),
            "total_edges": total_edges,
            "positive_edges": positive_edges,
            "negative_edges": total_edges - positive_edges,
            "citation_rate": self._total_citations / max(1, self._total_citations + self._total_ignores),
            "postgres_edges_written": self._postgres_edges_written
        }
    
    def export_graph_edges(self) -> List[Dict[str, Any]]:
        """Export feedback as graph edges for the Knowledge Graph."""
        edges = []
        
        for query_hash, signals in self._graph.items():
            for chunk_id, signal in signals.items():
                if abs(signal.boost_score) >= 0.1:
                    edge_type = "SOFT_CITED" if signal.boost_score > 0 else "SOFT_IGNORED"
                    
                    edges.append({
                        "source_type": "QUERY",
                        "source_id": query_hash,
                        "target_type": "CHUNK",
                        "target_id": chunk_id,
                        "edge_type": edge_type,
                        "signal_type": "soft",
                        "properties": {
                            "boost_score": signal.boost_score,
                            "confidence": signal.confidence,
                            "citation_count": signal.citation_count,
                            "ignore_count": signal.ignore_count,
                            "last_updated": signal.last_updated
                        }
                    })
        
        return edges
