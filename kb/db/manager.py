# db/manager.py
"""
Database Manager - Unified interface for Postgres + Qdrant connections.

Provides factory functions and context managers for database access.
All configuration comes from config.DATABASE_CONFIG.

Usage:
    from db import create_db_manager
    
    async with create_db_manager() as db:
        async with db.pg_session() as session:
            # Use Postgres session
            pass
        
        # Use Qdrant client directly
        await db.qdrant.search(...)
"""

import asyncio
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine

from config import DATABASE_CONFIG, EMBEDDING_CONFIG


class DatabaseManager:
    """
    Unified manager for Postgres and Qdrant connections.
    
    Handles connection lifecycle and provides convenient accessors.
    """
    
    def __init__(
        self,
        postgres_url: Optional[str] = None,
        qdrant_url: Optional[str] = None,
        auto_init: bool = False
    ):
        """
        Initialize database manager.
        
        Args:
            postgres_url: Override Postgres URL (defaults to DATABASE_CONFIG)
            qdrant_url: Override Qdrant URL (defaults to DATABASE_CONFIG)
            auto_init: If True, create tables/collections on connect
        """
        self._postgres_url = postgres_url or DATABASE_CONFIG.postgres_url
        self._qdrant_url = qdrant_url or DATABASE_CONFIG.qdrant_url
        self._auto_init = auto_init
        
        self._engine: Optional[AsyncEngine] = None
        self._session_maker = None
        self._qdrant: Optional[AsyncQdrantClient] = None
    
    @property
    def engine(self) -> AsyncEngine:
        """Get SQLAlchemy async engine."""
        if self._engine is None:
            from db.schema import get_async_engine
            self._engine = get_async_engine(self._postgres_url)
        return self._engine
    
    @property
    def session_maker(self):
        """Get async session maker."""
        if self._session_maker is None:
            from db.schema import get_session_maker
            self._session_maker = get_session_maker(self.engine)
        return self._session_maker
    
    @property
    def qdrant(self) -> AsyncQdrantClient:
        """Get Qdrant async client."""
        if self._qdrant is None:
            self._qdrant = AsyncQdrantClient(url=self._qdrant_url)
        return self._qdrant
    
    @asynccontextmanager
    async def pg_session(self):
        """Context manager for Postgres session."""
        async with self.session_maker() as session:
            yield session
    
    async def init_postgres(self):
        """Create all Postgres tables."""
        from db.schema import init_database
        await init_database(self.engine)
    
    async def init_qdrant_collection(
        self, 
        collection_name: Optional[str] = None,
        vector_size: Optional[int] = None,
        recreate: bool = False
    ):
        """
        Initialize a Qdrant collection with hybrid vectors.
        
        Args:
            collection_name: Collection name (defaults to DATABASE_CONFIG)
            vector_size: Vector dimension (defaults to EMBEDDING_CONFIG)
            recreate: If True, delete and recreate collection
        """
        from qdrant_client.models import VectorParams, Distance, SparseVectorParams
        
        name = collection_name or DATABASE_CONFIG.qdrant_collection_chunks
        size = vector_size or EMBEDDING_CONFIG.dim
        
        if recreate:
            try:
                await self.qdrant.delete_collection(name)
            except:
                pass
        
        try:
            await self.qdrant.get_collection(name)
        except:
            await self.qdrant.create_collection(
                collection_name=name,
                vectors_config={
                    "dense": VectorParams(size=size, distance=Distance.COSINE)
                },
                sparse_vectors_config={
                    "bm25": SparseVectorParams()
                }
            )
    
    async def drop_all_postgres(self):
        """Drop all Postgres tables."""
        from db.schema import Base
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    
    async def drop_all_qdrant(self) -> List[str]:
        """Delete all Qdrant collections. Returns list of deleted collection names."""
        deleted = []
        collections = await self.qdrant.get_collections()
        for col in collections.collections:
            await self.qdrant.delete_collection(col.name)
            deleted.append(col.name)
        return deleted
    
    async def drop_all(self) -> Dict[str, Any]:
        """
        Drop ALL data from both Postgres and Qdrant.
        
        Returns:
            Dict with stats about what was dropped
        """
        # Qdrant first (no foreign key constraints)
        qdrant_deleted = await self.drop_all_qdrant()
        
        # Then Postgres
        await self.drop_all_postgres()
        
        return {
            "postgres_tables_dropped": True,
            "qdrant_collections_deleted": qdrant_deleted
        }
    
    async def close(self):
        """Close all connections."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_maker = None
        
        if self._qdrant:
            await self._qdrant.close()
            self._qdrant = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        if self._auto_init:
            await self.init_postgres()
            await self.init_qdrant_collection()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


def create_db_manager(
    postgres_url: Optional[str] = None,
    qdrant_url: Optional[str] = None,
    auto_init: bool = False
) -> DatabaseManager:
    """
    Factory function for DatabaseManager.
    
    Args:
        postgres_url: Override Postgres URL
        qdrant_url: Override Qdrant URL
        auto_init: If True, initialize tables/collections on context entry
        
    Returns:
        DatabaseManager instance
        
    Usage:
        async with create_db_manager() as db:
            async with db.pg_session() as session:
                ...
    """
    return DatabaseManager(
        postgres_url=postgres_url,
        qdrant_url=qdrant_url,
        auto_init=auto_init
    )


# Convenience functions for quick access
async def get_pg_session():
    """Get a quick Postgres session (caller must close)."""
    manager = create_db_manager()
    return manager.session_maker()


async def get_qdrant_client() -> AsyncQdrantClient:
    """Get a quick Qdrant client (caller must close)."""
    return AsyncQdrantClient(url=DATABASE_CONFIG.qdrant_url)
