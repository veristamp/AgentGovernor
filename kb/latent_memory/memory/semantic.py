# latent_memory/memory/semantic.py
"""
Semantic Memory - Tier 2: Compressed Long-Term Memories.

Stores compressed summaries of old conversations for:
- Cross-session recall ("Last time we discussed...")
- Semantic search across history
- User preference learning
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from .models import Memory, MemoryConfig
from config import get_logger

logger = get_logger("latent_memory.memory.semantic")

class SemanticMemory:
    """
    Long-term memory storage with vector search.
    
    Features:
    - Store compressed memories from EpisodicMemory
    - Vector-based semantic search
    - Cross-session user memory (LTM)
    - Automatic cleanup of old memories
    """
    
    def __init__(
        self,
        pg_session=None,
        qdrant_client=None,
        config: Optional[MemoryConfig] = None,
        collection_name: str = "memories",
        embedder=None
    ):
        """
        Initialize semantic memory.
        
        Args:
            pg_session: SQLAlchemy async session for metadata
            qdrant_client: Qdrant client for vector storage
            config: Memory configuration
            collection_name: Qdrant collection for memories
            embedder: Embedding model for vectorization
        """
        self.pg_session = pg_session
        self.qdrant = qdrant_client
        self.config = config or MemoryConfig()
        self.collection_name = collection_name
        self.embedder = embedder
        
        # In-memory cache for fast access
        self._cache: Dict[str, List[Memory]] = {}
    
    async def store(self, memory: Memory) -> int:
        """
        Store a compressed memory.
        
        Args:
            memory: Memory object to store
            
        Returns:
            Memory ID
        """
        # Generate embedding if embedder available
        if self.embedder and not memory.embedding:
            embeddings = await self.embedder.encode([memory.summary])
            memory.embedding = embeddings[0]
        
        # Store in Qdrant if available
        if self.qdrant and memory.embedding:
            await self._store_in_qdrant(memory)
        
        # Store metadata in Postgres
        memory_id = await self._store_metadata(memory)
        memory.id = memory_id
        
        # Update cache
        if memory.session_id not in self._cache:
            self._cache[memory.session_id] = []
        self._cache[memory.session_id].append(memory)
        
        logger.info(f"💾 Stored memory {memory_id}: {memory.summary[:50]}...")
        
        return memory_id
    
    async def search(
        self,
        query: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        k: int = 5,
        min_importance: float = 0.0
    ) -> List[Memory]:
        """
        Search memories semantically.
        
        Args:
            query: Search query
            session_id: Limit to specific session (None = all sessions)
            user_id: Limit to specific user (for cross-session LTM)
            k: Max results
            min_importance: Filter by importance
            
        Returns:
            List of relevant memories
        """
        if not self.embedder:
            logger.warning("No embedder configured, using fallback search")
            return await self._fallback_search(query, session_id, user_id, k)
        
        # Get query embedding
        query_embeddings = await self.embedder.encode([query])
        query_vector = query_embeddings[0]
        
        # Search Qdrant
        if self.qdrant:
            return await self._qdrant_search(
                query_vector, session_id, user_id, k, min_importance
            )
        
        # Fallback to in-memory search
        return await self._cache_search(
            query_vector, session_id, user_id, k
        )
    
    async def get_user_context(
        self,
        user_id: str,
        topics: Optional[List[str]] = None,
        k: int = 3
    ) -> List[Memory]:
        """
        Get relevant context for a user across all their sessions.
        
        This enables "Remember when we discussed X?" functionality.
        
        Args:
            user_id: User to get context for
            topics: Optional topic filter
            k: Max memories
            
        Returns:
            Relevant memories from previous sessions
        """
        if not self.config.enable_ltm:
            return []
        
        # If topics provided, search for them
        if topics:
            query = " ".join(topics)
            return await self.search(query, user_id=user_id, k=k)
        
        # Otherwise, get most recent high-importance memories
        return await self._get_recent_user_memories(user_id, k)
    
    async def cleanup_old(self, days: Optional[int] = None):
        """
        Remove memories older than retention period.
        
        Args:
            days: Override config.ltm_retention_days
        """
        retention_days = days or self.config.ltm_retention_days
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        
        deleted_count = await self._delete_before(cutoff)
        
        logger.info(f"🧹 Cleaned up {deleted_count} old memories (>{retention_days} days)")
        
        return deleted_count
    
    async def get_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get memory storage statistics."""
        stats = {
            "total_memories": 0,
            "user_memories": 0,
            "total_tokens_saved": 0,
            "avg_compression_ratio": 0.0,
            "top_topics": []
        }
        
        # Collect from cache first
        topic_counts: Dict[str, int] = {}
        total_original = 0
        total_compressed = 0
        
        for memories in self._cache.values():
            for memory in memories:
                stats["total_memories"] += 1
                
                if user_id and memory.user_id == user_id:
                    stats["user_memories"] += 1
                
                total_original += memory.original_token_count or 0
                total_compressed += memory.compressed_token_count or 0
                
                for topic in (memory.topics or []):
                    topic_counts[topic] = topic_counts.get(topic, 0) + 1
        
        # Try to get from Postgres
        if self.pg_session:
            try:
                if callable(self.pg_session):
                    async with self.pg_session() as session:
                        db_stats = await self._query_pg_stats(session, user_id)
                else:
                    db_stats = await self._query_pg_stats(self.pg_session, user_id)
                
                # Merge DB stats (DB is source of truth)
                stats["total_memories"] = db_stats.get("total", stats["total_memories"])
                stats["user_memories"] = db_stats.get("user_count", stats["user_memories"])
                total_original = db_stats.get("total_original", total_original)
                total_compressed = db_stats.get("total_compressed", total_compressed)
            except Exception as e:
                logger.warning(f"Could not query Postgres stats: {e}")
        
        # Calculate tokens saved and compression ratio
        stats["total_tokens_saved"] = total_original - total_compressed
        if total_original > 0:
            stats["avg_compression_ratio"] = round(total_compressed / total_original, 3)
        
        # Sort topics by count
        stats["top_topics"] = sorted(
            topic_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return stats
    
    async def _query_pg_stats(self, session, user_id: Optional[str]) -> Dict[str, Any]:
        """Query statistics from Postgres."""
        from sqlalchemy import select, func
        from db.schema import CompressedMemory as CM
        
        # Total count
        total_query = select(func.count()).select_from(CM)
        total_result = await session.execute(total_query)
        total = total_result.scalar() or 0
        
        # User count
        user_count = 0
        if user_id:
            user_query = select(func.count()).select_from(CM).where(CM.user_id == user_id)
            user_result = await session.execute(user_query)
            user_count = user_result.scalar() or 0
        
        # Token sums
        token_query = select(
            func.sum(CM.original_token_count),
            func.sum(CM.compressed_token_count)
        ).select_from(CM)
        token_result = await session.execute(token_query)
        row = token_result.one()
        
        return {
            "total": total,
            "user_count": user_count,
            "total_original": row[0] or 0,
            "total_compressed": row[1] or 0
        }
    
    # =========================================================================
    # STORAGE BACKENDS
    # =========================================================================
    
    async def _store_in_qdrant(self, memory: Memory):
        """Store memory vector in Qdrant."""
        if not self.qdrant or not memory.embedding:
            return
        
        from qdrant_client.http import models
        
        point = models.PointStruct(
            id=hash(f"{memory.session_id}:{memory.created_at}") % (2**63),
            vector=memory.embedding,
            payload={
                "session_id": memory.session_id,
                "user_id": memory.user_id,
                "summary": memory.summary,
                "topics": memory.topics,
                "importance": memory.importance,
                "turn_ids": memory.turn_ids,
                "created_at": memory.created_at.isoformat() if memory.created_at else None
            }
        )
        
        await self.qdrant.upsert(
            collection_name=self.collection_name,
            points=[point]
        )
    
    async def _store_metadata(self, memory: Memory) -> int:
        """Store memory metadata in Postgres."""
        if not self.pg_session:
            return hash(f"{memory.session_id}:{memory.created_at}") % (2**31)
        
        try:
            if callable(self.pg_session):
                async with self.pg_session() as session:
                    from db.schema import CompressedMemory as CM
                    
                    record = CM(
                        session_id=memory.session_id,
                        user_id=memory.user_id,
                        summary=memory.summary,
                        topics=memory.topics,
                        turn_ids=memory.turn_ids,
                        turn_range_start=memory.turn_range[0] if memory.turn_range else None,
                        turn_range_end=memory.turn_range[1] if memory.turn_range else None,
                        original_token_count=memory.original_token_count,
                        compressed_token_count=memory.compressed_token_count,
                        importance=memory.importance
                    )
                    
                    session.add(record)
                    await session.commit()
                    await session.refresh(record)
                    
                    return record.id
            else:
                # Direct session
                from db.schema import CompressedMemory as CM
                
                record = CM(
                    session_id=memory.session_id,
                    user_id=memory.user_id,
                    summary=memory.summary,
                    topics=memory.topics,
                    turn_ids=memory.turn_ids,
                    turn_range_start=memory.turn_range[0] if memory.turn_range else None,
                    turn_range_end=memory.turn_range[1] if memory.turn_range else None,
                    original_token_count=memory.original_token_count,
                    compressed_token_count=memory.compressed_token_count,
                    importance=memory.importance
                )
                
                self.pg_session.add(record)
                await self.pg_session.commit()
                await self.pg_session.refresh(record)
                
                return record.id
        
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            return hash(f"{memory.session_id}:{memory.created_at}") % (2**31)

    
    async def _qdrant_search(
        self,
        query_vector: List[float],
        session_id: Optional[str],
        user_id: Optional[str],
        k: int,
        min_importance: float
    ) -> List[Memory]:
        """Search memories in Qdrant."""
        from qdrant_client.http import models
        
        # Build filter
        must_conditions = []
        
        if session_id:
            must_conditions.append(
                models.FieldCondition(
                    key="session_id",
                    match=models.MatchValue(value=session_id)
                )
            )
        
        if user_id:
            must_conditions.append(
                models.FieldCondition(
                    key="user_id",
                    match=models.MatchValue(value=user_id)
                )
            )
        
        if min_importance > 0:
            must_conditions.append(
                models.FieldCondition(
                    key="importance",
                    range=models.Range(gte=min_importance)
                )
            )
        
        query_filter = models.Filter(must=must_conditions) if must_conditions else None
        
        # Search
        results = await self.qdrant.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=k
        )
        
        # Convert to Memory objects
        memories = []
        for result in results:
            payload = result.payload
            memories.append(Memory(
                id=result.id,
                session_id=payload.get("session_id", ""),
                user_id=payload.get("user_id"),
                summary=payload.get("summary", ""),
                topics=payload.get("topics", []),
                importance=payload.get("importance", 0.5),
                turn_ids=payload.get("turn_ids", []),
                created_at=datetime.fromisoformat(payload["created_at"]) if payload.get("created_at") else None
            ))
        
        return memories
    
    async def _fallback_search(
        self,
        query: str,
        session_id: Optional[str],
        user_id: Optional[str],
        k: int
    ) -> List[Memory]:
        """Keyword-based fallback search."""
        # Search in cache
        query_words = set(query.lower().split())
        
        candidates = []
        for sess_id, memories in self._cache.items():
            if session_id and sess_id != session_id:
                continue
            
            for memory in memories:
                if user_id and memory.user_id != user_id:
                    continue
                
                # Score by keyword overlap
                memory_words = set(memory.summary.lower().split())
                memory_words.update(t.lower() for t in memory.topics)
                
                overlap = len(query_words & memory_words)
                if overlap > 0:
                    candidates.append((memory, overlap))
        
        # Sort by overlap
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        return [m for m, _ in candidates[:k]]
    
    async def _cache_search(
        self,
        query_vector: List[float],
        session_id: Optional[str],
        user_id: Optional[str],
        k: int
    ) -> List[Memory]:
        """Search in-memory cache using cosine similarity."""
        import numpy as np
        
        query_vec = np.array(query_vector)
        
        candidates = []
        for sess_id, memories in self._cache.items():
            if session_id and sess_id != session_id:
                continue
            
            for memory in memories:
                if user_id and memory.user_id != user_id:
                    continue
                
                if memory.embedding:
                    mem_vec = np.array(memory.embedding)
                    # Cosine similarity
                    similarity = np.dot(query_vec, mem_vec) / (
                        np.linalg.norm(query_vec) * np.linalg.norm(mem_vec)
                    )
                    candidates.append((memory, similarity))
        
        # Sort by similarity
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        return [m for m, _ in candidates[:k]]
    
    async def _get_recent_user_memories(
        self,
        user_id: str,
        k: int
    ) -> List[Memory]:
        """Get most recent memories for a user."""
        candidates = []
        
        for memories in self._cache.values():
            for memory in memories:
                if memory.user_id == user_id:
                    candidates.append(memory)
        
        # Sort by recency
        candidates.sort(
            key=lambda m: m.created_at or datetime.min,
            reverse=True
        )
        
        return candidates[:k]
    
    async def _delete_before(self, cutoff: datetime) -> int:
        """Delete memories before cutoff date."""
        deleted = 0
        
        # Clean cache
        for sess_id in list(self._cache.keys()):
            original_count = len(self._cache[sess_id])
            self._cache[sess_id] = [
                m for m in self._cache[sess_id]
                if m.created_at and m.created_at > cutoff
            ]
            deleted += original_count - len(self._cache[sess_id])
        
        # Clean Postgres
        if self.pg_session:
            try:
                pg_deleted = await self._delete_pg_before(cutoff)
                deleted += pg_deleted
                logger.debug(f"Deleted {pg_deleted} memories from Postgres")
            except Exception as e:
                logger.error(f"Failed to clean Postgres memories: {e}")
        
        # Clean Qdrant
        if self.qdrant:
            try:
                qdrant_deleted = await self._delete_qdrant_before(cutoff)
                deleted += qdrant_deleted
                logger.debug(f"Deleted {qdrant_deleted} memories from Qdrant")
            except Exception as e:
                logger.error(f"Failed to clean Qdrant memories: {e}")
        
        return deleted
    
    async def _delete_pg_before(self, cutoff: datetime) -> int:
        """Delete old memories from Postgres."""
        from sqlalchemy import delete
        from db.schema import CompressedMemory as CM
        
        if callable(self.pg_session):
            async with self.pg_session() as session:
                stmt = delete(CM).where(CM.created_at < cutoff)
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount or 0
        else:
            stmt = delete(CM).where(CM.created_at < cutoff)
            result = await self.pg_session.execute(stmt)
            await self.pg_session.commit()
            return result.rowcount or 0
    
    async def _delete_qdrant_before(self, cutoff: datetime) -> int:
        """Delete old memories from Qdrant."""
        from qdrant_client.http import models
        
        # Qdrant doesn't return count directly, so we estimate
        # by counting before delete
        try:
            # Get count of old memories (scroll with limit 0 doesn't work, so estimate)
            filter_condition = models.Filter(
                must=[
                    models.FieldCondition(
                        key="created_at",
                        range=models.Range(lt=cutoff.isoformat())
                    )
                ]
            )
            
            # Delete by filter
            await self.qdrant.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(filter=filter_condition)
            )
            
            # Return estimate (we don't have exact count)
            return 0  # Qdrant delete doesn't return count
            
        except Exception as e:
            logger.warning(f"Qdrant cleanup failed: {e}")
            return 0

