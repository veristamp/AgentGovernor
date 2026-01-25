# services/chat/persistence.py
"""
Persistence Layer - Session storage implementations.
Updated to use SessionState models.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.schema import Session as SessionModel
from config import get_logger
from services.chat.models import SessionState

logger = get_logger("ChatPersistence")

class BaseSessionStore(ABC):
    """Abstract base for session storage."""
    
    @abstractmethod
    async def get_session_state(self, session_id: str) -> Optional[SessionState]:
        pass
        
    @abstractmethod
    async def save_session_state(self, session_id: str, state: SessionState):
        pass
        
    @abstractmethod
    async def clear_session(self, session_id: str):
        pass

class PostgresSessionStore(BaseSessionStore):
    """
    Postgres-backed session store.
    """
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def get_session_state(self, session_id: str) -> Optional[SessionState]:
        """Retrieve session from database and convert to SessionState model."""
        stmt = select(SessionModel).where(SessionModel.session_id == session_id)
        result = await self.db.execute(stmt)
        sess = result.scalar_one_or_none()
        
        if not sess:
            return None
            
        # Check expiry
        if sess.expires_at and sess.expires_at < datetime.now():
            await self.clear_session(session_id)
            return None
            
        return SessionState(
            session_id=sess.session_id,
            last_query_topic=sess.last_query_topic,
            request_count=sess.request_count,
            cache_hits=sess.cache_hits,
            total_cached_tokens=sess.total_cached_tokens,
            history_k=sess.history_k or 10,
            enriched_chunks=sess.enriched_chunks or [],
            created_at=sess.created_at.timestamp() if sess.created_at else datetime.now().timestamp()
        )

    async def save_session_state(self, session_id: str, state: SessionState):
        """Upsert SessionState into database."""
        # Calculate expiry (24 hours)
        expires_at = datetime.now() + timedelta(hours=24)
        
        # Check if exists
        stmt = select(SessionModel.session_id).where(SessionModel.session_id == session_id)
        exists = (await self.db.execute(stmt)).scalar_one_or_none()
        
        if exists:
            # Update
            stmt = update(SessionModel).where(SessionModel.session_id == session_id).values(
                last_query_topic=state.last_query_topic,
                request_count=state.request_count,
                cache_hits=state.cache_hits,
                total_cached_tokens=state.total_cached_tokens,
                history_k=state.history_k,
                enriched_chunks=state.enriched_chunks,
                expires_at=expires_at
            )
            await self.db.execute(stmt)
        else:
            # Insert
            sess = SessionModel(
                session_id=session_id,
                last_query_topic=state.last_query_topic,
                request_count=state.request_count,
                cache_hits=state.cache_hits,
                total_cached_tokens=state.total_cached_tokens,
                history_k=state.history_k,
                enriched_chunks=state.enriched_chunks,
                expires_at=expires_at
            )
            self.db.add(sess)

    async def clear_session(self, session_id: str):
        """Delete session from database."""
        stmt = delete(SessionModel).where(SessionModel.session_id == session_id)
        await self.db.execute(stmt)

class MemorySessionStore(BaseSessionStore):
    """
    In-memory store for dev/testing.
    """
    def __init__(self):
        self._store: Dict[str, SessionState] = {}

    async def get_session_state(self, session_id: str) -> Optional[SessionState]:
        return self._store.get(session_id)

    async def save_session_state(self, session_id: str, state: SessionState):
        self._store[session_id] = state

    async def clear_session(self, session_id: str):
        if session_id in self._store:
            del self._store[session_id]
