# services/__init__.py
"""
Core Services Layer

Production-grade business logic, independent of HTTP/FastAPI.
Services can be used by:
- API endpoints (FastAPI)
- CLI tools
- Tests
- Background jobs

Architecture:
    ┌──────────────────────────────────────────────────────────────┐
    │                      API Layer (FastAPI)                      │
    │                            │                                  │
    │                            ▼                                  │
    │  ┌─────────────────────────────────────────────────────────┐ │
    │  │                   Services Layer                         │ │
    │  │                                                          │ │
    │  │  ChatService    IngestionService    PatchService         │ │
    │  │  GraphService   SessionStore                             │ │
    │  │                                                          │ │
    │  │  - Consistent response formatting                        │ │
    │  │  - Error handling                                        │ │
    │  │  - Config management                                     │ │
    │  │  - Lazy-load underlying managers                         │ │
    │  └─────────────────────────────────────────────────────────┘ │
    │                            │                                  │
    │                            ▼                                  │
    │  ┌─────────────────────────────────────────────────────────┐ │
    │  │                   Managers Layer                         │ │
    │  │                                                          │ │
    │  │  LLMManager   RAGManager   IngestionManager              │ │
    │  │  LatentMemoryManager   FilePatcherManager                │ │
    │  └─────────────────────────────────────────────────────────┘ │
    └──────────────────────────────────────────────────────────────┘
"""

from .chat.service import ChatService
from .graph_service import GraphService
from .patch_service import PatchService
from .ingestion_service import IngestionService, create_ingestion_service
from .watcher_service import WatcherService, create_watcher_service
from .pr_scanner import (
    PRService,
    PRScanner,
    PRVerdictReport,
    create_pr_service,
    create_pr_scanner,
)

__all__ = [
    "ChatService",
    "GraphService",
    "PatchService",
    "IngestionService",
    "create_ingestion_service",
    "WatcherService",
    "create_watcher_service",
    # PR Scanner
    "PRService",
    "PRScanner",
    "PRVerdictReport",
    "create_pr_service",
    "create_pr_scanner",
]

