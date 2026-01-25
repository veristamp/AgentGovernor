# services/chat/memory_service.py
"""
Memory Service - Business Logic for Long-Term Memory Operations.

Follows the same layered pattern as ChatService:
- API Layer (routes/memory.py) → This Service → LatentMemoryManager/Orchestrator

Provides:
- Cross-session memory queries
- Memory CRUD operations
- Semantic search over memories
- GDPR compliance (export, delete)
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import logging

from latent_memory import LatentMemoryManager
from config import EMBEDDING_CONFIG, get_logger

logger = get_logger("MemoryService")

class MemoryService:
    """
    Service layer for long-term memory operations.
    
    Architecture:
        API (routes/memory.py)
            ↓
        MemoryService (this file) - Business logic
            ↓
        LatentMemoryManager - Memory tier orchestration
            ↓
        SemanticMemory / EpisodicMemory - Storage
    """
    
    def __init__(self, qdrant_client=None, embedder=None):
        """
        Initialize the memory service.
        
        Args:
            qdrant_client: Shared Qdrant client for vector ops
            embedder: Shared embedder for semantic search
        """
        self._qdrant = qdrant_client
        self._embedder = embedder
    
    # =========================================================================
    # MEMORY LISTING & RETRIEVAL
    # =========================================================================
    
    async def list_memories(
        self,
        session: AsyncSession,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        topic: Optional[str] = None,
        min_importance: float = 0.0,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        List long-term memories with filtering.
        
        Args:
            session: Database session
            user_id: Filter by user
            session_id: Filter by originating session
            topic: Filter by topic (fuzzy match)
            min_importance: Minimum importance threshold
            limit: Max results
            
        Returns:
            Dict with memories list and total count
        """
        conditions = ["1=1"]
        params = {"limit": limit}
        
        if user_id:
            conditions.append("user_id = :user_id")
            params["user_id"] = user_id
        
        if session_id:
            conditions.append("session_id = :session_id")
            params["session_id"] = session_id
        
        if topic:
            conditions.append("topic ILIKE :topic")
            params["topic"] = f"%{topic}%"
        
        if min_importance > 0:
            conditions.append("importance >= :min_importance")
            params["min_importance"] = min_importance
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT id, summary, session_id, user_id, created_at, 
                   topic, turn_count, importance
            FROM compressed_memories
            WHERE {where_clause}
            ORDER BY importance DESC, created_at DESC
            LIMIT :limit
        """
        
        count_query = f"""
            SELECT COUNT(*) FROM compressed_memories
            WHERE {where_clause}
        """
        
        try:
            result = await session.execute(text(query), params)
            rows = result.fetchall()
            
            count_result = await session.execute(text(count_query), params)
            total = count_result.scalar() or 0
            
            memories = [
                {
                    "id": row[0],
                    "summary": row[1],
                    "session_id": row[2],
                    "user_id": row[3],
                    "created_at": row[4].isoformat() if row[4] else None,
                    "topic": row[5],
                    "turn_count": row[6] or 0,
                    "importance": row[7] or 0.5
                }
                for row in rows
            ]
            
            logger.info(f"📚 Listed {len(memories)}/{total} memories")
            return {"memories": memories, "total": total}
            
        except Exception as e:
            logger.error(f"Error listing memories: {e}")
            return {"memories": [], "total": 0, "error": str(e)}
    
    async def get_memory(
        self,
        session: AsyncSession,
        memory_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get details of a specific memory.
        
        Args:
            session: Database session
            memory_id: Memory ID
            
        Returns:
            Memory dict or None if not found
        """
        query = """
            SELECT id, summary, session_id, user_id, created_at, topic, 
                   turn_count, importance, metadata, embedding IS NOT NULL as has_embedding
            FROM compressed_memories
            WHERE id = :memory_id
        """
        
        try:
            result = await session.execute(text(query), {"memory_id": memory_id})
            row = result.fetchone()
            
            if not row:
                return None
            
            return {
                "id": row[0],
                "summary": row[1],
                "session_id": row[2],
                "user_id": row[3],
                "created_at": row[4].isoformat() if row[4] else None,
                "topic": row[5],
                "turn_count": row[6],
                "importance": row[7],
                "metadata": row[8],
                "has_embedding": row[9]
            }
            
        except Exception as e:
            logger.error(f"Error getting memory {memory_id}: {e}")
            return None
    
    # =========================================================================
    # MEMORY SEARCH
    # =========================================================================
    
    async def search_memories(
        self,
        session: AsyncSession,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 10,
        use_vector: bool = False
    ) -> Dict[str, Any]:
        """
        Search long-term memories.
        
        Args:
            session: Database session
            query: Search query
            user_id: Filter by user
            limit: Max results
            use_vector: Use vector similarity (requires Qdrant)
            
        Returns:
            Search results with scores
        """
        if use_vector and self._qdrant and self._embedder:
            return await self._vector_search(query, user_id, limit)
        
        # Fallback to text search
        return await self._text_search(session, query, user_id, limit)
    
    async def _text_search(
        self,
        session: AsyncSession,
        query: str,
        user_id: Optional[str],
        limit: int
    ) -> Dict[str, Any]:
        """Text-based memory search."""
        conditions = ["summary ILIKE :query"]
        params = {"query": f"%{query}%", "limit": limit}
        
        if user_id:
            conditions.append("user_id = :user_id")
            params["user_id"] = user_id
        
        where_clause = " AND ".join(conditions)
        
        search_query = f"""
            SELECT id, summary, session_id, user_id, topic, importance
            FROM compressed_memories
            WHERE {where_clause}
            ORDER BY importance DESC
            LIMIT :limit
        """
        
        try:
            result = await session.execute(text(search_query), params)
            rows = result.fetchall()
            
            results = [
                {
                    "id": row[0],
                    "summary": row[1],
                    "session_id": row[2],
                    "user_id": row[3],
                    "topic": row[4],
                    "importance": row[5],
                    "score": row[5]  # Use importance as score for text search
                }
                for row in rows
            ]
            
            logger.info(f"🔍 Text search '{query[:30]}...' found {len(results)} memories")
            return {"query": query, "results": results, "count": len(results), "method": "text"}
            
        except Exception as e:
            logger.error(f"Memory text search failed: {e}")
            return {"query": query, "results": [], "count": 0, "error": str(e)}
    
    async def _vector_search(
        self,
        query: str,
        user_id: Optional[str],
        limit: int
    ) -> Dict[str, Any]:
        """Vector-based semantic memory search."""
        try:
            # Embed query
            query_vector = await self._embedder.embed_query(query)
            
            # Search in Qdrant memories collection
            from qdrant_client.http import models
            
            filter_conditions = []
            if user_id:
                filter_conditions.append(
                    models.FieldCondition(
                        key="user_id",
                        match=models.MatchValue(value=user_id)
                    )
                )
            
            search_filter = models.Filter(must=filter_conditions) if filter_conditions else None
            
            results = await self._qdrant.search(
                collection_name="kb_memories",
                query_vector=query_vector,
                query_filter=search_filter,
                limit=limit,
                with_payload=True
            )
            
            memories = [
                {
                    "id": hit.id,
                    "summary": hit.payload.get("summary", ""),
                    "session_id": hit.payload.get("session_id"),
                    "user_id": hit.payload.get("user_id"),
                    "topic": hit.payload.get("topic"),
                    "importance": hit.payload.get("importance", 0.5),
                    "score": hit.score
                }
                for hit in results
            ]
            
            logger.info(f"🔍 Vector search '{query[:30]}...' found {len(memories)} memories")
            return {"query": query, "results": memories, "count": len(memories), "method": "vector"}
            
        except Exception as e:
            logger.error(f"Memory vector search failed: {e}")
            return {"query": query, "results": [], "count": 0, "error": str(e)}
    
    # =========================================================================
    # MEMORY CRUD
    # =========================================================================
    
    async def delete_memory(
        self,
        session: AsyncSession,
        memory_id: int
    ) -> Dict[str, Any]:
        """
        Delete a specific memory (GDPR compliance).
        
        Args:
            session: Database session
            memory_id: Memory to delete
            
        Returns:
            Status dict
        """
        # Check exists
        check_query = "SELECT id FROM compressed_memories WHERE id = :memory_id"
        result = await session.execute(text(check_query), {"memory_id": memory_id})
        
        if not result.fetchone():
            return {"status": "not_found", "memory_id": memory_id}
        
        # Delete from Postgres
        await session.execute(
            text("DELETE FROM compressed_memories WHERE id = :memory_id"),
            {"memory_id": memory_id}
        )
        
        # Delete from Qdrant if available
        if self._qdrant:
            try:
                await self._qdrant.delete(
                    collection_name="kb_memories",
                    points_selector=[memory_id]
                )
            except Exception as e:
                logger.warning(f"Could not delete from Qdrant: {e}")
        
        await session.commit()
        
        logger.info(f"🗑️ Deleted memory {memory_id}")
        return {"status": "deleted", "memory_id": memory_id}
    
    async def delete_user_memories(
        self,
        session: AsyncSession,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Delete all memories for a user (GDPR compliance).
        
        Args:
            session: Database session
            user_id: User whose memories to delete
            
        Returns:
            Status with count
        """
        # Count first
        count_result = await session.execute(
            text("SELECT COUNT(*) FROM compressed_memories WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        count = count_result.scalar() or 0
        
        # Delete from Postgres
        await session.execute(
            text("DELETE FROM compressed_memories WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        
        # Delete from Qdrant if available
        if self._qdrant:
            try:
                from qdrant_client.http import models
                await self._qdrant.delete(
                    collection_name="kb_memories",
                    points_selector=models.FilterSelector(
                        filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="user_id",
                                    match=models.MatchValue(value=user_id)
                                )
                            ]
                        )
                    )
                )
            except Exception as e:
                logger.warning(f"Could not delete from Qdrant: {e}")
        
        await session.commit()
        
        logger.info(f"🗑️ Deleted {count} memories for user {user_id}")
        return {"status": "deleted", "user_id": user_id, "count": count}
    
    # =========================================================================
    # STATS
    # =========================================================================
    
    async def get_stats(
        self,
        session: AsyncSession,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get memory statistics.
        
        Args:
            session: Database session
            user_id: Optional user filter
            
        Returns:
            Memory statistics
        """
        conditions = ["1=1"]
        params = {}
        
        if user_id:
            conditions.append("user_id = :user_id")
            params["user_id"] = user_id
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT 
                COUNT(*) as total_memories,
                COUNT(DISTINCT session_id) as unique_sessions,
                COUNT(DISTINCT user_id) as unique_users,
                SUM(turn_count) as total_turns_compressed,
                AVG(importance) as avg_importance,
                MIN(created_at) as oldest_memory,
                MAX(created_at) as newest_memory
            FROM compressed_memories
            WHERE {where_clause}
        """
        
        try:
            result = await session.execute(text(query), params)
            row = result.fetchone()
            
            return {
                "total_memories": row[0] or 0,
                "unique_sessions": row[1] or 0,
                "unique_users": row[2] or 0,
                "total_turns_compressed": row[3] or 0,
                "avg_importance": float(row[4]) if row[4] else 0.0,
                "oldest_memory": row[5].isoformat() if row[5] else None,
                "newest_memory": row[6].isoformat() if row[6] else None
            }
            
        except Exception as e:
            logger.error(f"Error getting memory stats: {e}")
            return {"error": str(e)}

# =============================================================================
# FACTORY
# =============================================================================

_memory_service: Optional[MemoryService] = None

def get_memory_service() -> MemoryService:
    """Get or create the singleton MemoryService instance."""
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service

def set_memory_service(service: MemoryService):
    """Set the MemoryService instance (for testing/DI)."""
    global _memory_service
    _memory_service = service
