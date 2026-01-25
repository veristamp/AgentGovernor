# latent_memory/memory/models.py
"""
Memory Data Models.

Defines the core data structures for the 3-tier memory system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum


class TurnRole(str, Enum):
    """Valid roles for conversation turns."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ImportanceLevel(str, Enum):
    """Importance categories for prioritization."""
    CRITICAL = "critical"  # Must never evict (e.g., system instructions)
    HIGH = "high"          # Code changes, important decisions
    MEDIUM = "medium"      # Regular conversation with citations
    LOW = "low"            # Acknowledgments, "thanks", "ok"
    TRIVIAL = "trivial"    # Can evict immediately if needed


@dataclass
class Turn:
    """
    A single conversation turn with rich metadata.
    
    This is the atomic unit of conversation history.
    """
    id: Optional[int] = None
    session_id: str = ""
    role: str = "user"
    content: str = ""
    
    # Timestamps
    created_at: Optional[datetime] = None
    
    # Token metrics
    token_count: int = 0
    
    # Model info
    model_used: Optional[str] = None
    
    # Context (which chunks were in the prompt)
    chunk_ids: List[int] = field(default_factory=list)
    
    # Citations (which chunks were cited in response)
    citations: List[int] = field(default_factory=list)
    
    # User feedback
    feedback_score: Optional[float] = None  # -1.0 to 1.0
    
    # Importance (computed)
    importance: float = 0.5
    importance_reason: Optional[str] = None
    
    # Branching support
    parent_turn_id: Optional[int] = None
    branch_label: Optional[str] = None
    
    # Arbitrary metadata
    meta: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "token_count": self.token_count,
            "model_used": self.model_used,
            "chunk_ids": self.chunk_ids,
            "citations": self.citations,
            "feedback_score": self.feedback_score,
            "importance": self.importance,
            "parent_turn_id": self.parent_turn_id,
            "branch_label": self.branch_label,
            "meta": self.meta,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Turn":
        """Create from dictionary."""
        return cls(
            id=data.get("id"),
            session_id=data.get("session_id", ""),
            role=data.get("role", "user"),
            content=data.get("content", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            token_count=data.get("token_count", 0),
            model_used=data.get("model_used"),
            chunk_ids=data.get("chunk_ids", []),
            citations=data.get("citations", []),
            feedback_score=data.get("feedback_score"),
            importance=data.get("importance", 0.5),
            parent_turn_id=data.get("parent_turn_id"),
            branch_label=data.get("branch_label"),
            meta=data.get("meta", {}),
        )


@dataclass
class Memory:
    """
    A compressed memory from multiple turns.
    
    Created when episodic turns are summarized for long-term storage.
    """
    id: Optional[int] = None
    session_id: str = ""
    user_id: Optional[str] = None  # For cross-session LTM
    
    # Compressed content
    summary: str = ""
    turn_ids: List[int] = field(default_factory=list)  # Original turn IDs
    turn_range: Tuple[int, int] = (0, 0)  # (first_id, last_id)
    
    # Topics extracted
    topics: List[str] = field(default_factory=list)
    
    # Vector for semantic search
    embedding: Optional[List[float]] = None
    
    # Metadata
    created_at: Optional[datetime] = None
    importance: float = 0.5
    
    # Source tracking
    original_token_count: int = 0  # Tokens before compression
    compressed_token_count: int = 0  # Tokens after
    
    def compression_ratio(self) -> float:
        """Calculate compression efficiency."""
        if self.original_token_count == 0:
            return 0.0
        return 1.0 - (self.compressed_token_count / self.original_token_count)


@dataclass
class SessionStats:
    """Analytics for a conversation session."""
    session_id: str
    
    # Counts
    total_turns: int = 0
    user_turns: int = 0
    assistant_turns: int = 0
    
    # Token metrics
    total_tokens: int = 0
    active_tokens: int = 0  # Recent full-text turns
    compressed_tokens: int = 0  # In semantic memories
    
    # Memory tiers
    active_turns: int = 0  # Episodic (full text)
    compressed_memories: int = 0  # Semantic (summaries)
    
    # Topics
    top_topics: List[str] = field(default_factory=list)
    
    # Quality
    avg_importance: float = 0.5
    positive_feedback_rate: float = 0.0
    
    # Timestamps
    first_turn_at: Optional[datetime] = None
    last_turn_at: Optional[datetime] = None
    
    def duration_minutes(self) -> float:
        """Session duration in minutes."""
        if not self.first_turn_at or not self.last_turn_at:
            return 0.0
        delta = self.last_turn_at - self.first_turn_at
        return delta.total_seconds() / 60


@dataclass
class MemoryConfig:
    """
    Configuration for the memory system.
    
    Smart defaults - most users won't need to change these.
    """
    # Episodic tier
    episodic_k: int = 10  # Keep last K turns in full text
    
    # Compression triggers
    compress_threshold: int = 20  # Compress when session exceeds this
    compress_batch_size: int = 10  # Summarize N turns at a time
    
    # Importance scoring
    importance_code_change: float = 0.9
    importance_with_citations: float = 0.7
    importance_question: float = 0.6
    importance_acknowledgment: float = 0.2
    
    # Eviction
    evict_below_importance: float = 0.3
    always_keep_latest: int = 3  # Never evict last N turns
    
    # Cross-session (LTM)
    enable_ltm: bool = True
    ltm_retention_days: int = 30
    
    # Vector search
    enable_semantic_search: bool = True
    semantic_search_k: int = 5
    
    # Background processing
    async_compression: bool = True
    compression_delay_seconds: float = 5.0  # Wait before compressing
