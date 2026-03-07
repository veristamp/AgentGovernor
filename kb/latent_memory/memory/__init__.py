# latent_memory/memory/__init__.py
"""
Memory Subsystem - 3-Tier Automatic Memory Management.

Architecture:
┌─────────────────────────────────────────────────────────────────┐
│                    MemoryOrchestrator                           │
│  User API: remember() / recall() / forget()                     │
└─────────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
 ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
 │   Working   │      │  Episodic   │      │  Semantic   │
 │  Tier 0     │      │  Tier 1     │      │  Tier 2     │
 │  Current    │      │  Recent K   │      │  Compressed │
 │  in-memory  │      │  Postgres   │      │  Qdrant     │
 └─────────────┘      └─────────────┘      └─────────────┘

Features:
- Automatic importance scoring and eviction
- LLM-powered compression for long conversations
- Semantic search across history
- Cross-session user memory (LTM)
- Zero-config with smart defaults

Usage:
    from latent_memory.memory import create_orchestrator
    
    # Simple - all defaults
    memory = create_orchestrator(pg_session=db)
    
    # Remember (after each turn)
    await memory.remember(session_id, "user", "How do I chunk files?")
    
    # Recall (when building context)
    history = await memory.recall(session_id, query="chunking")
    
    # Forget (clear session)
    await memory.forget(session_id)
"""

# Data models
from .models import (
    Turn,
    Memory,
    SessionStats,
    MemoryConfig,
    TurnRole,
    ImportanceLevel,
)

# Memory tiers
from .episodic import EpisodicMemory
from .semantic import SemanticMemory

# Compression
from .compressor import MemoryCompressor

# Orchestrator (main entry point)
from .orchestrator import MemoryOrchestrator, create_orchestrator

__all__ = [
    # Models
    "Turn",
    "Memory",
    "SessionStats",
    "MemoryConfig",
    "TurnRole",
    "ImportanceLevel",
    # Tiers
    "EpisodicMemory",
    "SemanticMemory",
    # Compression
    "MemoryCompressor",
    # Orchestrator
    "MemoryOrchestrator",
    "create_orchestrator",
]
