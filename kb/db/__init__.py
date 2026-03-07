# db/__init__.py
"""
Database Module - Dual-Graph Data Layer (Postgres + Qdrant).

This module contains ONLY database-related code:
- Schema (ORM models)
- Manager (connection handling)
- CLI utilities (init, drop)

Business logic like ingestion is in separate modules:
- ingestion/ - Document ingestion pipeline
- concept_harvester/ - Concept extraction and graph building
- rag/ - Retrieval and search

Architecture:
    ┌──────────────────────────────────────────────────────────────────┐
    │                      DatabaseManager                              │
    │                  (Connection Façade)                              │
    │                                                                   │
    │   pg_session()      qdrant       init_postgres()    drop_all()   │
    ├───────────────────────────────────────────────────────────────────┤
    │                                                                   │
    │     ┌──────────────────────┐    ┌──────────────────────────┐     │
    │     │   POSTGRES (schema)  │    │   QDRANT (collections)   │     │
    │     │                      │    │                          │     │
    │     │ • documents          │    │ • kb_chunks (vectors)    │     │
    │     │ • chunks             │    │ • kb_concepts (concepts) │     │
    │     │ • nodes / edges      │    │                          │     │
    │     │ • global_concepts    │    │                          │     │
    │     │ • processing_queue   │    │                          │     │
    │     │ • conversation_logs  │    │                          │     │
    │     │ • patch_history      │    │                          │     │
    │     └──────────────────────┘    └──────────────────────────┘     │
    └──────────────────────────────────────────────────────────────────┘

Usage:
    from db import create_db_manager
    
    async with create_db_manager() as db:
        async with db.pg_session() as session:
            # Use Postgres
            pass
        # Use Qdrant
        await db.qdrant.search(...)
"""

from .manager import (
    DatabaseManager,
    create_db_manager,
    get_pg_session,
    get_qdrant_client,
)

from .schema import (
    # Base
    Base,
    # Orchestration
    Document,
    ProcessingJob,
    Chunk,
    # Graph
    Node,
    Edge,
    GlobalConcept,
    # Memory
    ConversationLog,
    CompressedMemory,
    UserPreference,
    Session,
    # Audit
    PatchHistory,
    FileLock,
    # Utilities
    get_async_engine,
    get_session_maker,
    init_database,
)

__all__ = [
    # Manager
    "DatabaseManager",
    "create_db_manager",
    "get_pg_session",
    "get_qdrant_client",
    # Base
    "Base",
    # Orchestration & Ingestion
    "Document",
    "ProcessingJob",
    "Chunk",
    # Graph
    "Node",
    "Edge",
    "GlobalConcept",
    # Memory
    "ConversationLog",
    "CompressedMemory",
    "UserPreference",
    "Session",
    # Audit
    "PatchHistory",
    "FileLock",
    # Utilities
    "get_async_engine",
    "get_session_maker",
    "init_database",
]
