# services/chat/session_service.py
"""
Session Service - Business Logic for Session Operations.

Follows the same layered pattern as ChatService:
- API Layer (routes/sessions.py) → This Service → DB

Provides:
- Session listing and retrieval
- Conversation history access
- Session branching/forking
- Compression control
- GDPR compliance (export, delete)
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import logging

from .persistence import PostgresSessionStore
from config import get_logger

logger = get_logger("SessionService")


class SessionService:
    """
    Service layer for session operations.
    
    Architecture:
        API (routes/sessions.py)
            ↓
        SessionService (this file) - Business logic
            ↓
        SessionManager - State management
            ↓
        PostgreSQL - Persistence
    """
    
    def __init__(self):
        """Initialize the session service."""
        pass
    
    # =========================================================================
    # SESSION LISTING
    # =========================================================================
    
    async def list_sessions(
        self,
        session: AsyncSession,
        user_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "last_active",
        order: str = "desc"
    ) -> Dict[str, Any]:
        """
        List sessions with pagination.
        
        Args:
            session: Database session
            user_id: Filter by user
            page: Page number (1-indexed)
            page_size: Items per page
            sort_by: Sort field (created_at, last_active)
            order: Sort order (asc, desc)
            
        Returns:
            Paginated session list
        """
        offset = (page - 1) * page_size
        order_clause = "DESC" if order == "desc" else "ASC"
        
        # Build query
        conditions = ["1=1"]
        params = {"limit": page_size, "offset": offset}
        
        if user_id:
            conditions.append("user_id = :user_id")
            params["user_id"] = user_id
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT 
                session_id,
                created_at,
                updated_at as last_active,
                request_count as message_count,
                total_cached_tokens as total_tokens,
                cache_hits
            FROM sessions
            WHERE {where_clause}
            ORDER BY {sort_by} {order_clause}
            LIMIT :limit OFFSET :offset
        """
        
        count_query = f"""
            SELECT COUNT(*) FROM sessions
            WHERE {where_clause}
        """
        
        try:
            result = await session.execute(text(query), params)
            rows = result.fetchall()
            
            count_result = await session.execute(text(count_query), params)
            total = count_result.scalar() or 0
            
            sessions_list = [
                {
                    "session_id": row[0],
                    "created_at": row[1].isoformat() if row[1] else None,
                    "last_active": row[2].isoformat() if row[2] else None,
                    "message_count": row[3] or 0,
                    "total_tokens": row[4] or 0,
                    "cache_hits": row[5] or 0
                }
                for row in rows
            ]
            
            logger.info(f"📋 Listed {len(sessions_list)}/{total} sessions (page {page})")
            
            return {
                "sessions": sessions_list,
                "total": total,
                "page": page,
                "page_size": page_size,
                "has_more": (offset + page_size) < total
            }
            
        except Exception as e:
            logger.warning(f"Error listing sessions: {e}")
            return {
                "sessions": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "has_more": False,
                "error": str(e)
            }
    
    async def get_session(
        self,
        session: AsyncSession,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get session stats.
        
        Args:
            session: Database session
            session_id: Session ID
            
        Returns:
            Session state dict or None
        """
        store = PostgresSessionStore(session)
        state = await store.get_session_state(session_id)
        return state.dict() if state else None
    
    # =========================================================================
    # CONVERSATION HISTORY
    # =========================================================================
    
    async def get_history(
        self,
        session: AsyncSession,
        session_id: str,
        page: int = 1,
        page_size: int = 50,
        role: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        min_importance: Optional[float] = None,
        include_compressed: bool = False
    ) -> Dict[str, Any]:
        """
        Get paginated conversation history.
        
        Args:
            session: Database session
            session_id: Session ID
            page: Page number
            page_size: Items per page
            role: Filter by role (user/assistant)
            from_date: Filter from date
            to_date: Filter to date
            min_importance: Minimum importance
            include_compressed: Include compressed turns
            
        Returns:
            Paginated history
        """
        offset = (page - 1) * page_size
        
        # Build dynamic query
        conditions = ["session_id = :session_id"]
        params = {"session_id": session_id, "limit": page_size, "offset": offset}
        
        if role:
            conditions.append("role = :role")
            params["role"] = role
        
        if from_date:
            conditions.append("created_at >= :from_date")
            params["from_date"] = from_date
        
        if to_date:
            conditions.append("created_at <= :to_date")
            params["to_date"] = to_date
        
        if min_importance is not None:
            conditions.append("(meta->>'importance')::float >= :min_importance")
            params["min_importance"] = min_importance
        
        if not include_compressed:
            conditions.append("(meta->>'is_compressed')::boolean IS NOT TRUE")
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT 
                id, role, content, created_at, 
                (meta->>'importance')::float as importance, 
                meta->'chunk_ids' as chunk_ids,
                (meta->>'is_compressed')::boolean as is_compressed
            FROM conversation_logs
            WHERE {where_clause}
            ORDER BY created_at ASC
            LIMIT :limit OFFSET :offset
        """
        
        count_query = f"""
            SELECT COUNT(*) FROM conversation_logs
            WHERE {where_clause}
        """
        
        try:
            result = await session.execute(text(query), params)
            rows = result.fetchall()
            
            count_result = await session.execute(text(count_query), params)
            total = count_result.scalar() or 0
            
            turns = [
                {
                    "id": row[0],
                    "role": row[1],
                    "content": row[2],
                    "timestamp": row[3].isoformat() if row[3] else None,
                    "importance": row[4] or 0.5,
                    "chunk_ids": row[5] if row[5] else None,
                    "compressed": row[6] or False
                }
                for row in rows
            ]
            
            return {
                "session_id": session_id,
                "turns": turns,
                "total": total,
                "page": page,
                "page_size": page_size,
                "has_more": (offset + page_size) < total
            }
            
        except Exception as e:
            logger.error(f"Error fetching history: {e}")
            return {
                "session_id": session_id,
                "turns": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "has_more": False,
                "error": str(e)
            }
    
    # =========================================================================
    # EXPORT (GDPR)
    # =========================================================================
    
    async def export_session(
        self,
        session: AsyncSession,
        session_id: str,
        include_memories: bool = True,
        include_feedback: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Export all session data (GDPR compliance).
        
        Args:
            session: Database session
            session_id: Session ID
            include_memories: Include LTM memories
            include_feedback: Include feedback history
            
        Returns:
            Complete export or None if not found
        """
        # Get session state
        state = await self.get_session(session, session_id)
        if not state:
            return None
        
        # Get full history (no pagination)
        history_query = """
            SELECT 
                id, role, content, created_at, 
                (meta->>'importance')::float as importance, 
                meta->'chunk_ids' as chunk_ids,
                (meta->>'is_compressed')::boolean as is_compressed,
                meta
            FROM conversation_logs
            WHERE session_id = :session_id
            ORDER BY created_at ASC
        """
        
        result = await session.execute(text(history_query), {"session_id": session_id})
        history_rows = result.fetchall()
        
        history = [
            {
                "id": row[0],
                "role": row[1],
                "content": row[2],
                "timestamp": row[3].isoformat() if row[3] else None,
                "importance": row[4],
                "chunk_ids": row[5],
                "compressed": row[6],
                "metadata": row[7]
            }
            for row in history_rows
        ]
        
        export_data = {
            "session": state,
            "history": history,
            "turn_count": len(history),
            "exported_at": datetime.utcnow().isoformat()
        }
        
        # Get memories if requested
        if include_memories:
            memories_query = """
                SELECT id, summary, topic, created_at, turn_count, importance
                FROM compressed_memories
                WHERE session_id = :session_id
                ORDER BY created_at DESC
            """
            mem_result = await session.execute(text(memories_query), {"session_id": session_id})
            mem_rows = mem_result.fetchall()
            
            export_data["memories"] = [
                {
                    "id": row[0],
                    "summary": row[1],
                    "topic": row[2],
                    "created_at": row[3].isoformat() if row[3] else None,
                    "turn_count": row[4],
                    "importance": row[5]
                }
                for row in mem_rows
            ]
        
        # Get feedback if requested
        if include_feedback:
            try:
                feedback_query = """
                    SELECT source_id, edge_type, weight, properties, created_at
                    FROM edges
                    WHERE properties::text LIKE :session_pattern
                    AND edge_type IN ('HARD_POSITIVE', 'HARD_NEGATIVE', 'SOFT_CITE')
                    ORDER BY created_at DESC
                """
                fb_result = await session.execute(
                    text(feedback_query), 
                    {"session_pattern": f'%"{session_id}"%'}
                )
                fb_rows = fb_result.fetchall()
                
                export_data["feedback"] = [
                    {
                        "chunk_id": row[0],
                        "type": row[1],
                        "weight": row[2],
                        "properties": row[3],
                        "created_at": row[4].isoformat() if row[4] else None
                    }
                    for row in fb_rows
                ]
            except Exception:
                export_data["feedback"] = []
        
        logger.info(f"📦 Exported session {session_id}: {len(history)} turns")
        return export_data
    
    # =========================================================================
    # DELETE (GDPR)
    # =========================================================================
    
    async def delete_session(
        self,
        session: AsyncSession,
        session_id: str,
        keep_ltm: bool = False
    ) -> Dict[str, Any]:
        """
        Delete session and all associated data.
        
        Args:
            session: Database session
            session_id: Session ID
            keep_ltm: Preserve long-term memories
            
        Returns:
            Status dict
        """
        # Delete session record
        result = await session.execute(
            text("DELETE FROM sessions WHERE session_id = :session_id"),
            {"session_id": session_id}
        )
        session_deleted = result.rowcount > 0
        
        # Delete history
        history_result = await session.execute(
            text("DELETE FROM conversation_logs WHERE session_id = :session_id"),
            {"session_id": session_id}
        )
        history_deleted = history_result.rowcount
        
        # Delete LTM if not keeping
        ltm_deleted = 0
        if not keep_ltm:
            ltm_result = await session.execute(
                text("DELETE FROM compressed_memories WHERE session_id = :session_id"),
                {"session_id": session_id}
            )
            ltm_deleted = ltm_result.rowcount
        
        await session.commit()
        
        logger.info(f"🗑️ Deleted session {session_id} (history={history_deleted}, ltm={ltm_deleted})")
        
        return {
            "status": "deleted",
            "session_id": session_id,
            "history_deleted": history_deleted,
            "ltm_deleted": ltm_deleted,
            "ltm_preserved": keep_ltm
        }
    
    # =========================================================================
    # BRANCHING
    # =========================================================================
    
    async def branch_session(
        self,
        session: AsyncSession,
        source_session_id: str,
        new_session_id: str,
        from_turn_id: Optional[int] = None,
        label: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a branch/fork of a session.
        
        Args:
            session: Database session
            source_session_id: Source session
            new_session_id: New session ID
            from_turn_id: Branch from this turn (None = copy all)
            label: Optional branch label
            
        Returns:
            Status dict
        """
        # Check source exists
        source_check = await session.execute(
            text("SELECT 1 FROM sessions WHERE session_id = :session_id"),
            {"session_id": source_session_id}
        )
        if not source_check.fetchone():
            return {"status": "error", "error": f"Source session not found: {source_session_id}"}
        
        # Check target doesn't exist
        target_check = await session.execute(
            text("SELECT 1 FROM sessions WHERE session_id = :session_id"),
            {"session_id": new_session_id}
        )
        if target_check.fetchone():
            return {"status": "error", "error": f"Target session already exists: {new_session_id}"}
        
        # Copy history
        if from_turn_id:
            copy_query = """
                INSERT INTO conversation_logs 
                    (session_id, role, content, created_at, meta)
                SELECT 
                    :new_session_id, role, content, NOW(), meta
                FROM conversation_logs
                WHERE session_id = :source_session_id AND id <= :from_turn_id
                ORDER BY created_at ASC
            """
            params = {
                "new_session_id": new_session_id,
                "source_session_id": source_session_id,
                "from_turn_id": from_turn_id
            }
        else:
            copy_query = """
                INSERT INTO conversation_logs 
                    (session_id, role, content, created_at, meta)
                SELECT 
                    :new_session_id, role, content, NOW(), meta
                FROM conversation_logs
                WHERE session_id = :source_session_id
                ORDER BY created_at ASC
            """
            params = {
                "new_session_id": new_session_id,
                "source_session_id": source_session_id
            }
        
        result = await session.execute(text(copy_query), params)
        turns_copied = result.rowcount
        
        await session.commit()
        
        logger.info(f"🌿 Branched {source_session_id} → {new_session_id} ({turns_copied} turns)")
        
        return {
            "status": "branched",
            "source_session_id": source_session_id,
            "new_session_id": new_session_id,
            "turns_copied": turns_copied,
            "from_turn_id": from_turn_id,
            "label": label
        }
    
    # =========================================================================
    # COMPRESSION
    # =========================================================================
    
    async def compress_session(
        self,
        session: AsyncSession,
        session_id: str,
        llm_manager,
        keep_recent: int = 5
    ) -> Dict[str, Any]:
        """
        Manually trigger session compression.
        
        Args:
            session: Database session
            session_id: Session ID
            llm_manager: LLM manager for compression
            keep_recent: Recent turns to keep
            
        Returns:
            Compression result
        """
        try:
            memory = llm_manager._get_memory()
            if not memory:
                return {"status": "error", "error": "Memory system not available"}
            
            orchestrator = memory._get_memory()
            if not orchestrator:
                return {"status": "error", "error": "Memory orchestrator not available"}
            
            result = await orchestrator.compress_session(
                session_id=session_id,
                keep_recent=keep_recent
            )
            
            if result:
                logger.info(f"🗜️ Compressed session {session_id}")
                return {
                    "status": "compressed",
                    "session_id": session_id,
                    "turns_compressed": getattr(result, 'turn_count', 0),
                    "memories_created": 1
                }
            else:
                return {
                    "status": "no_action",
                    "session_id": session_id,
                    "reason": "Not enough turns to compress"
                }
                
        except Exception as e:
            logger.error(f"Compression failed: {e}")
            return {"status": "error", "error": str(e)}


# =============================================================================
# FACTORY
# =============================================================================

_session_service: Optional[SessionService] = None


def get_session_service() -> SessionService:
    """Get or create the singleton SessionService instance."""
    global _session_service
    if _session_service is None:
        _session_service = SessionService()
    return _session_service


def set_session_service(service: SessionService):
    """Set the SessionService instance (for testing/DI)."""
    global _session_service
    _session_service = service
