# db/schema.py
"""
Database Schema for Dual-Graph Architecture
Postgres stores:
1. The Hard Graph (nodes, edges)
2. Global Metadata (concepts)
3. Orchestration & Management (documents, processing_queue)
"""

import os
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column, String, BigInteger, Integer, Float, Text, JSON, Index, ForeignKey, 
    DateTime, func, CheckConstraint
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship

from config import DATABASE_CONFIG, get_logger

Base = declarative_base()

# =============================================================================
# ORCHESTRATION & MANAGEMENT
# =============================================================================

class Document(Base):
    """
    Registry of all source documents in the knowledge base.
    Prevents redundant processing and tracks sync state.
    """
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True)
    file_path = Column(Text, unique=True, nullable=False, index=True)
    file_type = Column(String(20))  # md, py, tsx, etc.
    checksum = Column(String(64))   # SHA-256 to detect changes
    
    total_chunks = Column(Integer, default=0)
    
    # Lifecycle timestamps
    last_processed_at = Column(DateTime)
    last_harvested_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    
    # State: 'synced', 'stale', 'error'
    sync_status = Column(String(20), default='stale', index=True)
    
    # Relationship to nodes belonging to this doc
    nodes = relationship("Node", back_populates="document", cascade="all, delete-orphan")

class ProcessingJob(Base):
    """
    Queue and history of background processing tasks.
    Tracks both Chunking (Phase 1) and Graphing (Phase 2).
    """
    __tablename__ = "processing_queue"
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete="CASCADE"), nullable=False, index=True)
    
    # Phase 1: File -> Structured JSON
    chunking_status = Column(String(20), default='pending')
    chunking_error = Column(Text)
    json_path = Column(Text)
    
    # Phase 2: JSON -> Postgres/Qdrant
    graph_status = Column(String(20), default='pending')
    graph_error = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    __table_args__ = (
        CheckConstraint(chunking_status.in_(['pending', 'processing', 'completed', 'failed'])),
        CheckConstraint(graph_status.in_(['pending', 'processing', 'completed', 'failed'])),
    )

class Chunk(Base):
    """
    Parsed document chunks - Postgres is source of truth.
    
    This table stores chunks after the chunker phase, before embedding.
    Qdrant vectors are derived from this data.
    
    Lifecycle:
    1. Chunker parses document → writes to this table
    2. Embedder reads from here → generates vectors → writes to Qdrant
    3. Both Postgres and Qdrant have the same chunk ID for correlation
    """
    __tablename__ = "chunks"
    
    # Stable ID (same as Qdrant point ID)
    id = Column(BigInteger, primary_key=True, autoincrement=False)
    
    # Parent references
    doc_id = Column(Integer, ForeignKey('documents.id', ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey('processing_queue.id', ondelete="SET NULL"), nullable=True)
    
    # Core content
    chunk_type = Column(String(20), nullable=False, index=True)  # text, code, heading, table
    content = Column(Text, nullable=False)
    original_text = Column(Text)  # For byte-perfect reconstruction
    
    # Hierarchy
    section_path = Column(Text)
    parent_chunk_id = Column(BigInteger, ForeignKey('chunks.id'), nullable=True)
    chunk_index = Column(Integer, nullable=False)  # Order within document
    
    # Position tracking (for surgical editing)
    char_start = Column(Integer, default=0)
    char_end = Column(Integer, default=0)
    line_start = Column(Integer, default=0)
    line_end = Column(Integer, default=0)
    token_count = Column(Integer, default=0)
    
    # Extracted metadata (named 'meta' to avoid SQLAlchemy reserved 'metadata')
    meta = Column(JSON, default={})  # language, symbols, headers, etc.
    
    # Extracted concepts (denormalized for fast access)
    concepts = Column(JSON, default=[])  # [{name, type, score}, ...]
    
    # Embedding status
    embedding_status = Column(String(20), default='pending', index=True)  # pending, done, failed
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    embedded_at = Column(DateTime, nullable=True)
    
    # Relationships
    document = relationship("Document", backref="chunks")
    
    __table_args__ = (
        Index('idx_chunks_doc_type', 'doc_id', 'chunk_type'),
        Index('idx_chunks_embedding', 'embedding_status', 'created_at'),
        Index('idx_chunks_doc_order', 'doc_id', 'chunk_index'),
    )

class ConversationLog(Base):
    """
    Episodic Memory (STM) - The raw logs of interaction.
    Stores the raw chat history for the "Wrapper" to query.
    """
    __tablename__ = "conversation_logs"

    id = Column(Integer, primary_key=True)
    session_id = Column(String(64), index=True, nullable=False)
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    
    # Metadata for Caching/Optimization
    token_count = Column(Integer, default=0)
    model_used = Column(String(64))
    meta = Column(JSON, default={})  # Store citations, latency, tool_calls here
    
    created_at = Column(DateTime, server_default=func.now(), index=True)

class CompressedMemory(Base):
    """
    Semantic Memory (LTM) - Compressed summaries of old conversations.
    
    When episodic turns exceed the threshold, they are compressed
    using LLM summarization and stored here for long-term recall.
    
    Architecture:
    - Episodic (Tier 1): Full text, recent K turns → conversation_logs
    - Semantic (Tier 2): Compressed summaries → compressed_memories
    """
    __tablename__ = "compressed_memories"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(64), index=True, nullable=False)
    user_id = Column(String(64), index=True, nullable=True)  # For cross-session LTM
    
    # Compressed content
    summary = Column(Text, nullable=False)
    topics = Column(JSON, default=[])  # Extracted topic tags
    
    # Source tracking
    turn_ids = Column(JSON, default=[])  # Original conversation_logs IDs
    turn_range_start = Column(Integer)  # First turn ID compressed
    turn_range_end = Column(Integer)    # Last turn ID compressed
    
    # Token metrics
    original_token_count = Column(Integer, default=0)  # Before compression
    compressed_token_count = Column(Integer, default=0)  # After compression
    
    # Quality / Importance
    importance = Column(Float, default=0.5)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), index=True)
    
    __table_args__ = (
        Index('idx_memory_user_time', 'user_id', 'created_at'),
        Index('idx_memory_session', 'session_id', 'created_at'),
    )

class UserPreference(Base):
    """
    Long-Term User Preferences - Cross-session memory.
    
    Stores persistent facts about users that should be remembered
    across all sessions (coding style, preferred languages, etc.)
    """
    __tablename__ = "user_preferences"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), unique=True, nullable=False, index=True)
    
    # Preferences (JSON for flexibility)
    preferences = Column(JSON, default={})  # {coding_style: "concise", language: "python", ...}
    
    # Learned facts
    facts = Column(JSON, default=[])  # ["user prefers dark mode", "works on RAG systems", ...]
    
    # Stats
    total_sessions = Column(Integer, default=0)
    total_turns = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class Session(Base):
    """
    Shared Session State for Horizontal Scaling.
    Stores the "Hot" data needed to maintain prompt cache across servers.
    """
    __tablename__ = "sessions"
    
    session_id = Column(String(64), primary_key=True)
    
    # Cache Optimization State
    last_query_topic = Column(Text)
    request_count = Column(Integer, default=0)
    cache_hits = Column(Integer, default=0)
    total_cached_tokens = Column(BigInteger, default=0)
    history_k = Column(Integer, default=10)
    
    # Current active chunks (serialized EnrichedChunk data)
    enriched_chunks = Column(JSON, default=[])
    
    # Lifecycle
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime)
    
    __table_args__ = (
        Index('idx_sessions_updated', 'updated_at'),
    )

# =============================================================================
# THE HARD GRAPH (Skeleton)
# =============================================================================

class Node(Base):
    """
    Physical structure of the document (Topological Graph).
    """
    __tablename__ = "nodes"
    
    # Stable ID (Qdrant compatible)
    id = Column(BigInteger, primary_key=True, autoincrement=False)
    
    # Registry Link
    doc_id = Column(Integer, ForeignKey('documents.id', ondelete="CASCADE"), index=True)
    doc_url = Column(String(512), nullable=False, index=True)
    
    type = Column(String(20), nullable=False, index=True) # CHUNK, SECTION, CODE, TABLE
    content = Column(Text, nullable=True)
    
    # De-normalized Topology pointers
    parent_id = Column(BigInteger, ForeignKey('nodes.id'), nullable=True, index=True)
    prev_id = Column(BigInteger, ForeignKey('nodes.id'), nullable=True)
    next_id = Column(BigInteger, nullable=True)
    
    # Hierarchy Context
    page_idx = Column(Integer)
    section_path = Column(Text) 
    meta = Column(JSON)  # language, lines, etc.
    
    created_at = Column(DateTime, server_default=func.now())
    
    # Connectivity
    document = relationship("Document", back_populates="nodes")
    parent = relationship("Node", remote_side=[id], foreign_keys=[parent_id])
    
    __table_args__ = (
        Index('idx_nodes_doc_type', 'doc_url', 'type'),
        Index('idx_nodes_section_path_trgm', 'section_path'),
    )

# =============================================================================
# THE SOFT GRAPH (Nerves)
# =============================================================================

class GlobalConcept(Base):
    """
    Unified registry for conceptual nodes (Hubs).
    """
    __tablename__ = "global_concepts"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(256), unique=True, nullable=False, index=True)
    doc_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

class Edge(Base):
    """
    Relationships between Graph elements.
    """
    __tablename__ = "edges"
    
    id = Column(BigInteger, primary_key=True)
    source_id = Column(BigInteger, ForeignKey('nodes.id', ondelete="CASCADE"), nullable=False, index=True)
    target_id = Column(BigInteger, nullable=False)  # Concept ID or Node ID
    edge_type = Column(String(20), nullable=False)  # MENTIONS, REFERS_TO, FOLLOWS, CHILD_OF
    weight = Column(Float, default=1.0)
    
    __table_args__ = (
        Index('idx_edges_source', 'source_id'),
        Index('idx_edges_target_type', 'target_id', 'edge_type'),
        Index('idx_edges_unique_link', 'source_id', 'target_id', 'edge_type', unique=True),
    )

# =============================================================================
# VERIFIED PATCH CONTRACT (VPC) - Audit Log for Code Mutations
# =============================================================================

class PatchHistory(Base):
    """
    Verified Patch Contract - First-class audit log for all patch operations.
    
    Every patch attempt (whether applied or rejected) is recorded here.
    This enables:
    - Traceability: What changed, when, and why
    - Rollback: Reconstruct previous states
    - Learning: What kinds of patches get rejected?
    - Compliance: Prove the agent didn't make unauthorized changes
    """
    __tablename__ = "patch_history"
    
    # Primary Key
    id = Column(BigInteger, primary_key=True)
    patch_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID
    
    # Target Information
    file_path = Column(Text, nullable=False, index=True)
    chunk_id = Column(BigInteger, nullable=True)  # Qdrant chunk ID
    chunk_index = Column(Integer, nullable=True)
    
    # Content Hashes (for verification)
    old_content_hash = Column(String(64))  # SHA-256
    new_content_hash = Column(String(64))
    
    # Character Offsets
    char_start = Column(Integer)
    char_end = Column(Integer)
    bytes_changed = Column(Integer, default=0)
    lines_changed = Column(Integer, default=0)
    
    # Diff (truncated if too large)
    diff_summary = Column(Text)  # First 2000 chars of unified diff
    
    # Gate Results (JSON for flexibility)
    validator_result = Column(JSON)  # {valid, error, error_line, language, node_count}
    critic_result = Column(JSON)    # {approved, score, violations[], stats{}}
    oracle_result = Column(JSON)    # {risk_level, caller_count, importers, warnings[]}
    immune_result = Column(JSON)    # {status, passed, test_count, failed_tests[], duration_ms}
    
    # Symbols Changed
    symbols_changed = Column(JSON)  # List of function/class names affected
    
    # Final Decision
    decision = Column(String(20), nullable=False, index=True)  # 'applied', 'rejected', 'dry_run'
    decision_reason = Column(Text)
    rejected_by_gate = Column(String(20))  # 'validator', 'critic', 'oracle', 'immune', null
    
    # Git Integration (filled post-commit)
    git_commit_sha = Column(String(40), nullable=True)
    git_branch = Column(String(128), nullable=True)
    
    # Provenance
    agent_session_id = Column(String(64), nullable=True, index=True)
    request_id = Column(String(64), nullable=True)  # For tracing back to user request
    
    # Timing
    created_at = Column(DateTime, server_default=func.now(), index=True)
    duration_ms = Column(Integer, default=0)  # Total time for all gates + patch
    
    __table_args__ = (
        Index('idx_patch_file_time', 'file_path', 'created_at'),
        Index('idx_patch_decision', 'decision', 'created_at'),
        Index('idx_patch_session', 'agent_session_id', 'created_at'),
    )

class FileLock(Base):
    """
    Distributed lock for concurrent file mutations.
    Enables horizontal scaling of agents by coordinating via Postgres.
    """
    __tablename__ = "file_locks"
    
    file_path = Column(Text, primary_key=True)
    owner_id = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())

# =============================================================================
# ENGINE & INITIALIZATION
# =============================================================================

def get_async_engine(database_url: str = None):
    if not database_url:
        database_url = DATABASE_CONFIG.postgres_url
    
    return create_async_engine(
        database_url,
        echo=False,
        pool_size=DATABASE_CONFIG.postgres_pool_size,
        max_overflow=DATABASE_CONFIG.postgres_max_overflow,
        pool_pre_ping=True,
    )

def get_session_maker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_database(engine, install_functions: bool = True):
    """
    Initialize full database schema from Python models.
    
    Args:
        engine: SQLAlchemy async engine
        install_functions: Also install Postgres RPC functions (default: True)
    """
    async with engine.begin() as conn:
        # Note: In production, use Alembic. For now, create_all is fine.
        await conn.run_sync(Base.metadata.create_all)
    
    # Install retrieval functions (N+1 killer)
    if install_functions:
        try:
            from rag.retrieval_functions import create_retrieval_functions
            SessionMaker = get_session_maker(engine)
            async with SessionMaker() as session:
                await create_retrieval_functions(session)
        except ImportError:
            pass  # RAG module not available
        except Exception as e:
            import logging
            get_logger("db.schema").warning(f"Could not install retrieval functions: {e}")
