# latent_memory/context_rotator.py
"""
Context Rotator - Token Budget Manager for Chunks.

Manages the token budget for context chunks within the LLM's context window.
Handles eviction when chunks exceed available space.

NOTE: History management is now handled by MemoryOrchestrator.
      This component focuses ONLY on chunk token budgeting.

Architecture:
┌─────────────────────────────────────────────────────────────────┐
│                    Token Budget                                  │
│                                                                  │
│  ┌─────────────┐  ┌─────────────────┐  ┌───────────────────┐    │
│  │   System    │ +│    Chunks       │ +│     History       │    │
│  │   Prompt    │  │  (This class)   │  │ (MemoryOrchestrator) │  │
│  │   LOCKED    │  │  MANAGED        │  │    MANAGED        │    │
│  └─────────────┘  └─────────────────┘  └───────────────────┘    │
│                                                                  │
│  Total must be < max_tokens - reserve_for_output                 │
└─────────────────────────────────────────────────────────────────┘
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from config import get_logger

logger = get_logger("latent_memory.context_rotator")

@dataclass
class TokenBudget:
    """Token allocation summary."""
    max_tokens: int
    system_tokens: int
    chunk_tokens: int
    history_tokens: int
    query_tokens: int
    reserve_tokens: int
    
    @property
    def total_used(self) -> int:
        return self.system_tokens + self.chunk_tokens + self.history_tokens + self.query_tokens
    
    @property
    def available(self) -> int:
        return self.max_tokens - self.total_used - self.reserve_tokens
    
    @property
    def utilization(self) -> float:
        return self.total_used / self.max_tokens if self.max_tokens > 0 else 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "system_tokens": self.system_tokens,
            "chunk_tokens": self.chunk_tokens,
            "history_tokens": self.history_tokens,
            "query_tokens": self.query_tokens,
            "reserve_tokens": self.reserve_tokens,
            "total_used": self.total_used,
            "available": self.available,
            "utilization": f"{self.utilization:.1%}"
        }

class ContextRotator:
    """
    Manages token budget for context chunks.
    
    Responsibilities:
    1. Track available token space
    2. Evict low-priority chunks when budget exceeded
    3. Report budget utilization
    
    NOT responsible for:
    - Prompt building (see KVCacheManager)
    - History management (see MemoryOrchestrator)
    """
    
    def __init__(
        self,
        max_tokens: int = 128000,
        reserve_for_output: int = 4000,
        system_prompt_tokens: int = 0
    ):
        """
        Initialize the context rotator.
        
        Args:
            max_tokens: Total context window size
            reserve_for_output: Tokens to reserve for LLM generation
            system_prompt_tokens: Tokens used by system prompt (locked)
        """
        self.max_tokens = max_tokens
        self.reserve_for_output = reserve_for_output
        self.system_prompt_tokens = system_prompt_tokens
        
        # Pinned chunks (never evicted)
        self._pinned: List[Dict[str, Any]] = []
        self._pinned_tokens = 0
    
    def pin_chunk(self, chunk: Dict[str, Any]):
        """
        Pin a chunk so it's never evicted.
        
        Use for critical context that must always be present.
        """
        self._pinned.append(chunk)
        self._pinned_tokens += self._get_tokens(chunk)
    
    def clear_pinned(self):
        """Remove all pinned chunks."""
        self._pinned.clear()
        self._pinned_tokens = 0
    
    def fit_chunks(
        self,
        chunks: List[Dict[str, Any]],
        history_tokens: int = 0,
        query_tokens: int = 0
    ) -> Tuple[List[Dict[str, Any]], TokenBudget]:
        """
        Fit chunks within available token budget.
        
        Evicts lowest-scoring chunks if budget exceeded.
        
        Args:
            chunks: Candidate chunks (will be filtered if too many)
            history_tokens: Tokens already allocated for history
            query_tokens: Tokens for the user query
            
        Returns:
            (fitted_chunks, budget) - Chunks that fit + budget breakdown
        """
        # Calculate available space for chunks
        fixed_tokens = (
            self.system_prompt_tokens +
            self._pinned_tokens +
            history_tokens +
            query_tokens
        )
        
        available_for_chunks = self.max_tokens - fixed_tokens - self.reserve_for_output
        
        if available_for_chunks <= 0:
            logger.warning(
                f"⚠️ No space for chunks! Fixed tokens ({fixed_tokens}) + "
                f"reserve ({self.reserve_for_output}) >= max ({self.max_tokens})"
            )
            return self._pinned.copy(), self._make_budget(0, history_tokens, query_tokens)
        
        # Sort chunks by score (highest first) to keep best ones
        scored_chunks = sorted(
            chunks,
            key=lambda c: c.get("score", c.get("relevance", 0.5)),
            reverse=True
        )
        
        # Greedily add chunks until budget exhausted
        fitted = list(self._pinned)  # Start with pinned
        chunk_tokens = self._pinned_tokens
        evicted_count = 0
        
        for chunk in scored_chunks:
            tokens = self._get_tokens(chunk)
            
            if chunk_tokens + tokens <= available_for_chunks:
                fitted.append(chunk)
                chunk_tokens += tokens
            else:
                evicted_count += 1
        
        if evicted_count > 0:
            logger.info(f"📉 Evicted {evicted_count} chunks to fit token budget")
        
        budget = self._make_budget(chunk_tokens, history_tokens, query_tokens)
        
        return fitted, budget
    
    def calculate_budget(
        self,
        chunks: List[Dict[str, Any]],
        history_tokens: int = 0,
        query_tokens: int = 0
    ) -> TokenBudget:
        """
        Calculate token budget without modifying chunks.
        
        Useful for previewing budget before fitting.
        """
        chunk_tokens = sum(self._get_tokens(c) for c in chunks) + self._pinned_tokens
        return self._make_budget(chunk_tokens, history_tokens, query_tokens)
    
    def get_available_for_history(
        self,
        chunks: List[Dict[str, Any]],
        query_tokens: int = 0
    ) -> int:
        """
        Calculate how many tokens are available for history.
        
        Useful for MemoryOrchestrator to know how much history to fetch.
        """
        chunk_tokens = sum(self._get_tokens(c) for c in chunks) + self._pinned_tokens
        
        used = self.system_prompt_tokens + chunk_tokens + query_tokens
        return self.max_tokens - used - self.reserve_for_output
    
    def _get_tokens(self, chunk: Dict[str, Any]) -> int:
        """Get token count for a chunk."""
        if "token_count" in chunk:
            return chunk["token_count"]
        
        # Estimate from text length
        text = chunk.get("text", chunk.get("content", chunk.get("original_text", "")))
        return len(text) // 4  # Rough estimate
    
    def _make_budget(
        self,
        chunk_tokens: int,
        history_tokens: int,
        query_tokens: int
    ) -> TokenBudget:
        """Create a TokenBudget object."""
        return TokenBudget(
            max_tokens=self.max_tokens,
            system_tokens=self.system_prompt_tokens,
            chunk_tokens=chunk_tokens,
            history_tokens=history_tokens,
            query_tokens=query_tokens,
            reserve_tokens=self.reserve_for_output
        )

# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def fit_to_context(
    chunks: List[Dict[str, Any]],
    max_tokens: int = 128000,
    reserved_tokens: int = 10000,  # For history + query + output
    system_tokens: int = 500
) -> List[Dict[str, Any]]:
    """
    Simple function to fit chunks within a token budget.
    
    Args:
        chunks: Chunks with scores and token_count
        max_tokens: Context window size
        reserved_tokens: Tokens to reserve for other content
        system_tokens: System prompt tokens
        
    Returns:
        Chunks that fit within budget
    """
    rotator = ContextRotator(
        max_tokens=max_tokens,
        reserve_for_output=reserved_tokens,
        system_prompt_tokens=system_tokens
    )
    
    fitted, _ = rotator.fit_chunks(chunks)
    return fitted
