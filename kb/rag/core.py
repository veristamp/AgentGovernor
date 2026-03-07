# rag/core.py
"""
Core Data Structures for RAG System.

Shared types and utilities used across RAG components.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class SearchMode(Enum):
    """Search modes for retrieval."""
    DENSE = "dense"        # Dense vector only
    SPARSE = "sparse"      # BM25 sparse only
    HYBRID = "hybrid"      # Dense + Sparse with RRF fusion


class FusionMethod(Enum):
    """Fusion methods for hybrid search."""
    RRF = "rrf"            # Reciprocal Rank Fusion
    WEIGHTED = "weighted"  # Weighted combination


# =============================================================================
# SEARCH CONFIG
# =============================================================================

@dataclass
class RAGConfig:
    """Configuration for RAG system."""
    
    # Search settings
    search_mode: SearchMode = SearchMode.HYBRID
    limit: int = 5
    rerank: bool = True
    use_mmr: bool = True
    mmr_lambda: float = 0.7
    
    # Enrichment
    include_flow: bool = True       # Include prev/next chunks
    include_concepts: bool = True   # Include related concepts
    max_concepts_per_chunk: int = 5
    
    # Feedback boosting
    apply_feedback_boost: bool = True
    
    # Formatting
    group_by: str = "source"


# =============================================================================
# SEARCH RESULT
# =============================================================================

@dataclass
class SearchHit:
    """A single search result from vector DB."""
    id: int
    score: float
    text: str
    source: str
    section_path: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "score": self.score,
            "text": self.text,
            "source": self.source,
            "section_path": self.section_path,
            "metadata": self.metadata
        }


@dataclass  
class RAGResult:
    """Complete RAG retrieval result."""
    query: str
    hits: List[SearchHit] = field(default_factory=list)
    enriched_context: str = ""
    sources: List[str] = field(default_factory=list)
    concepts: List[str] = field(default_factory=list)
    duration_ms: int = 0
    
    @property
    def hit_count(self) -> int:
        return len(self.hits)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "hit_count": self.hit_count,
            "sources": self.sources,
            "concepts": self.concepts,
            "duration_ms": self.duration_ms
        }


# =============================================================================
# UTILITIES
# =============================================================================

def get_token_count(chunk: Dict[str, Any]) -> int:
    """Get token count from chunk metadata (already computed by chunker)."""
    return chunk.get("token_count", 0)


def format_chunk_for_prompt(
    text: str,
    source: str,
    section_path: str = "",
    include_header: bool = True
) -> str:
    """Format a chunk for LLM prompt."""
    if include_header:
        header = f"[{source}]"
        if section_path:
            header += f" > {section_path}"
        return f"{header}\n{text}\n"
    return text
