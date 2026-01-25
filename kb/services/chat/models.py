# services/chat/models.py
"""
Chat Service Models - All data structures for the chat service layer.

Contains:
- Session models (SessionState, ChatContext, ChatConfig)
- Persona models (PersonaDefinition, LLMConfig, RAGConfig, etc.)

These live in the services layer to avoid circular imports.
API layer can import from here for request/response shaping.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field
from pydantic import BaseModel, Field


# =============================================================================
# SESSION MODELS
# =============================================================================

class SessionState(BaseModel):
    """
    Current state of a chat session.
    Used for persistence and context management.
    """
    session_id: str
    last_query_topic: Optional[str] = None
    request_count: int = 0
    cache_hits: int = 0
    total_cached_tokens: int = 0
    history_k: int = 10
    enriched_chunks: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    
    @property
    def is_new(self) -> bool:
        return self.request_count == 0


@dataclass
class ChatContext:
    """
    Context for a single chat request.
    """
    session_id: str
    user_query: str
    is_new_session: bool = False
    need_refresh: bool = False
    start_time: float = field(default_factory=datetime.now().timestamp)
    
    def get_latency_ms(self) -> int:
        return int((datetime.now().timestamp() - self.start_time) * 1000)


@dataclass
class ChatConfig:
    """
    Configuration for the Chat Service.
    """
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    base_url: Optional[str] = None
    qdrant_url: Optional[str] = None
    collection_name: Optional[str] = None
    system_prompt: Optional[str] = None
    max_context_tokens: int = 128000
    history_k: int = 10
    max_chunks: int = 5
    use_rerank: bool = True
    compress_context: bool = False
    
    # Embedding configuration
    embedding_provider: Optional[str] = None
    embedding_base_url: Optional[str] = None
    dense_model: Optional[str] = None
    sparse_model: Optional[str] = None
    reranker_model: Optional[str] = None
    reranker_provider: Optional[str] = None
    reranker_base_url: Optional[str] = None
    
    def to_llm_config(self) -> Any:
        # Avoid circular import
        from llm import LLMConfig
        
        # Build kwargs, excluding None values to use LLMConfig defaults
        kwargs = {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "qdrant_url": self.qdrant_url,
            "collection_name": self.collection_name,
            "max_context_tokens": self.max_context_tokens,
            "history_k": self.history_k,
            "max_chunks": self.max_chunks,
            "use_rerank": self.use_rerank,
            "compress_context": self.compress_context,
            "embedding_provider": self.embedding_provider,
            "embedding_base_url": self.embedding_base_url,
            "dense_model": self.dense_model,
            "sparse_model": self.sparse_model,
            "reranker_model": self.reranker_model,
            "reranker_provider": self.reranker_provider,
            "reranker_base_url": self.reranker_base_url,
        }
        
        # Only include system_prompt if explicitly set (not None)
        # This lets LLMConfig use its own default
        if self.system_prompt is not None:
            kwargs["system_prompt"] = self.system_prompt
        
        return LLMConfig(**kwargs)


# =============================================================================
# PERSONA CONFIG MODELS
# =============================================================================

class MemoryConfig(BaseModel):
    """Memory tier configuration."""
    include_history: bool = Field(True, description="Include conversation history")
    history_k: int = Field(10, ge=0, le=100, description="Number of history turns")
    include_ltm: bool = Field(True, description="Include long-term memories")
    auto_compress: bool = Field(True, description="Auto-compress old turns")
    compression_threshold: int = Field(20, description="Turns before compression")


class RAGConfig(BaseModel):
    """RAG pipeline configuration."""
    enabled: bool = Field(True, description="Enable RAG retrieval")
    retrieval_limit: int = Field(5, ge=0, le=50, description="Chunks to retrieve")
    use_rerank: bool = Field(True, description="Apply cross-encoder reranking")
    use_mmr: bool = Field(True, description="Apply MMR diversification")
    mmr_lambda: float = Field(0.7, ge=0.0, le=1.0, description="MMR diversity")
    use_feedback_boost: bool = Field(True, description="Boost by feedback signals")
    compress_chunks: bool = Field(False, description="Semantic chunk compression")
    collection_name: Optional[str] = Field(None, description="Override collection")


class LLMConfig(BaseModel):
    """LLM provider configuration for personas."""
    provider: str = Field("openai", description="LLM provider")
    model: str = Field("gpt-4o-mini", description="Model name")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Temperature")
    max_tokens: int = Field(2048, ge=1, le=128000, description="Max tokens")
    system_prompt: Optional[str] = Field(None, description="Override system prompt")


class FeedbackConfig(BaseModel):
    """Feedback system configuration."""
    auto_learn: bool = Field(True, description="Auto-save turns to memory")
    extract_citations: bool = Field(True, description="Extract LLM citations")
    enable_hard_feedback: bool = Field(True, description="Accept thumbs up/down")


# =============================================================================
# PERSONA MODELS
# =============================================================================

class PersonaDefinition(BaseModel):
    """
    Complete persona definition.
    
    A persona is a named configuration bundle that defines how the
    system behaves.
    """
    id: str = Field(..., description="Unique persona identifier")
    name: str = Field(..., description="Human-readable name")
    description: Optional[str] = Field(None, description="What this persona does")
    
    # System behavior
    system_prompt: str = Field(
        "You are a helpful AI assistant.",
        description="System prompt for this persona"
    )
    
    # Component configs
    llm: LLMConfig = Field(default_factory=LLMConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    feedback: FeedbackConfig = Field(default_factory=FeedbackConfig)
    
    # Metadata
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    owner: Optional[str] = Field(None, description="Owner/creator ID")
    is_public: bool = Field(True, description="Available to all users")
    
    class Config:
        extra = "allow"


class PersonaOverrides(BaseModel):
    """Per-request persona overrides."""
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=128000)
    use_rag: Optional[bool] = None
    retrieval_limit: Optional[int] = Field(None, ge=0, le=50)
    use_rerank: Optional[bool] = None
    use_mmr: Optional[bool] = None
    mmr_lambda: Optional[float] = Field(None, ge=0.0, le=1.0)
    include_history: Optional[bool] = None
    history_k: Optional[int] = Field(None, ge=0, le=100)
    include_ltm: Optional[bool] = None
    learn: Optional[bool] = None
    extra: Optional[Dict[str, Any]] = Field(default_factory=dict)
