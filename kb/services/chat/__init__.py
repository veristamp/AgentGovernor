# services/chat/__init__.py
"""
Chat Services Package.

Provides service-layer abstractions for chat, sessions, memory, and personas.

Architecture:
    ┌────────────────────────────────────────────┐
    │  API Layer (api/routes/)                   │
    │  - Request validation only                  │
    ├────────────────────────────────────────────┤
    │  Service Layer (this package)              │
    │  - Business logic                           │
    │  - ChatService, SessionService, etc.        │
    ├────────────────────────────────────────────┤
    │  Data Layer (latent_memory/, db/)          │
    │  - Persistence, vector stores               │
    └────────────────────────────────────────────┘

Services:
    ChatService     - Chat completion orchestration
    SessionService  - Session management (history, branching, export)
    MemoryService   - Long-term memory operations  
    PersonaService  - Agent persona management

Internal:
    models.py         - All data models (session, persona, config)
    persistence.py    - Session state storage (Postgres)
    response_formatter.py - Multi-format response output
"""

from .service import ChatService, get_chat_service
from .session_service import SessionService, get_session_service
from .memory_service import MemoryService, get_memory_service
from .persona_service import PersonaService, get_persona_service
from .response_formatter import ResponseFormatter, ResponseFormat

# All models from consolidated models.py
from .models import (
    # Session models
    SessionState,
    ChatContext,
    ChatConfig,
    # Persona models
    PersonaDefinition,
    PersonaOverrides,
    LLMConfig,
    RAGConfig,
    MemoryConfig,
    FeedbackConfig,
)

__all__ = [
    # Services
    "ChatService",
    "SessionService", 
    "MemoryService",
    "PersonaService",
    # Factories
    "get_chat_service",
    "get_session_service",
    "get_memory_service",
    "get_persona_service",
    # Session Models
    "SessionState",
    "ChatContext",
    "ChatConfig",
    # Persona Models
    "PersonaDefinition",
    "PersonaOverrides",
    "LLMConfig",
    "RAGConfig",
    "MemoryConfig",
    "FeedbackConfig",
    # Utils
    "ResponseFormatter",
    "ResponseFormat",
]
