# latent_memory/kv_cache.py
"""
KV Cache Manager - Structure-Invariant Prompt Builder.

Builds prompts in a cache-optimal order to maximize LLM KV Cache hits.
By sorting chunks by stable ID (content hash), the context prefix remains
identical across turns, allowing the LLM to skip re-computation.

Key Insight:
- LLM KV Caches work on the PREFIX of the prompt
- If first N tokens are identical, they're fetched from cache (0ms)
- We sort by STABLE ID (not token_start) because IDs don't change on edit

Prompt Anatomy (Cache Contract):
┌─────────────────────────────────────────────────────────────────┐
│  [STATIC]   System Prompt          ← Always cached              │
├─────────────────────────────────────────────────────────────────┤
│  [STABLE]   Context Chunks          ← Cached until content edit │
│             (sorted by stable ID)                               │
├─────────────────────────────────────────────────────────────────┤
│  [EPISODIC] Conversation History    ← Cached while prefix stable│
├─────────────────────────────────────────────────────────────────┤
│  [DYNAMIC]  User Query              ← Always recomputed (small) │
│             Session Metadata                                    │
└─────────────────────────────────────────────────────────────────┘
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import hashlib

from functools import lru_cache
from config import get_logger

logger = get_logger("latent_memory.kv_cache")

# OPTIONAL: tiktoken for high-fidelity sync token counting
try:
    import tiktoken
    _ENCODING = tiktoken.get_encoding("cl100k_base") # Default for GPT-4o family
except ImportError:
    _ENCODING = None

@dataclass
class PrefixMetadata:
    """Logical tracking of what is currently in the LLM context prefix."""
    cached_chunk_ids: List[str] = field(default_factory=list)
    cached_tokens: int = 0
    prefix_hash: str = ""
    
    def calculate_hit_rate(self, current_ids: List[str]) -> float:
        """Calculate logical hit rate for current chunks."""
        if not current_ids:
            return 0.0
        
        cached_set = set(self.cached_chunk_ids)
        current_set = set(current_ids)
        overlap = cached_set & current_set
        
        return len(overlap) / len(current_set)

class KVCacheManager:
    """
    Builds cache-optimal prompts.
    
    Responsibilities:
    1. Assemble prompt in cache-friendly order
    2. Sort chunks by stable ID for prefix stability
    3. Track what's intended for cache (Logical Cache)
    """
    
    def __init__(self, system_prompt: str = ""):
        self.system_prompt = system_prompt
        self._prefix_meta = PrefixMetadata()
        self._last_prefix = ""

    def _count_tokens(self, text: str) -> int:
        """Helper to get high-fidelity token counts synchronously."""
        if not text:
            return 0
        if _ENCODING:
            return len(_ENCODING.encode(text))
        return len(text) // 4 # Fallback heuristic

    
    def build(
        self,
        chunks: List[Dict[str, Any]],
        query: str,
        history: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Build a cache-optimal prompt.
        
        Args:
            chunks: Context chunks (will be sorted by stable ID)
            query: User's current question
            history: Previous conversation turns
            metadata: Optional session metadata (placed at the end)
            
        Returns:
            Complete prompt string
        """
        parts = []
        
        # 1. System Prompt (STATIC)
        if self.system_prompt:
            parts.append(self.system_prompt)
            parts.append("\n\n")
        
        # 2. Stable Metadata (STATIC - e.g. user profile, strict rules)
        # Promoted to prefix to extend cache lifetime for same-user sessions
        if metadata and metadata.get("stable"):
            parts.append("<session_context>\n")
            for k, v in metadata["stable"].items():
                parts.append(f"{k}: {v}\n")
            parts.append("</session_context>\n\n")

        # 3. Context Chunks (STABLE - sorted by ID)
        if chunks:
            parts.append("<context>\n")
            
            # Sort by stable ID for consistent ordering (Numeric ID Jitter Fix)
            def _stable_id_key(c):
                cid = c.get("id", "")
                # Handle numeric IDs naturally (1, 2, 10 instead of 1, 10, 2)
                if isinstance(cid, int):
                    return (0, cid)
                if isinstance(cid, str) and cid.isdigit():
                    return (0, int(cid))
                # Fallback to string sort for non-numeric
                return (1, str(cid))

            sorted_chunks = sorted(chunks, key=_stable_id_key)
            
            for chunk in sorted_chunks:
                chunk_id = chunk.get("id", "")
                source = chunk.get("source", "")
                text = chunk.get("text", chunk.get("content", chunk.get("original_text", "")))
                
                parts.append(f'<chunk id="{chunk_id}" source="{source}">\n')
                parts.append(text)
                parts.append('\n</chunk>\n\n')
            
            parts.append("</context>\n\n")
        
        # 4. Conversation History (EPISODIC)
        if history:
            parts.append("<conversation_history>\n")
            
            for turn in history:
                role = turn.get("role", "user")
                content = turn.get("content", "")
                
                parts.append(f'<message role="{role}">\n{content}\n</message>\n')
            
            parts.append("</conversation_history>\n\n")
        
        # Store prefix (everything before dynamic content)
        self._last_prefix = "".join(parts)
        
        # 5. User Query (DYNAMIC)
        parts.append("<user_query>\n")
        parts.append(query)
        parts.append("\n</user_query>")
        
        # Note: Dynamic metadata (session_id, timestamps) intentionally NOT added here
        # to avoid polluting the cache boundary. Session tracking should happen
        # at the application layer, not in the prompt.
        
        return "".join(parts)
    
    def mark_cached(self, chunks: List[Dict[str, Any]]):
        """
        Mark chunks as cached after successful LLM call.
        """
        # Sort by stable ID for consistent ordering
        def _stable_id_key(c):
            cid = c.get("id", "")
            if isinstance(cid, int):
                return (0, cid)
            if isinstance(cid, str) and cid.isdigit():
                return (0, int(cid))
            return (1, str(cid))

        sorted_chunks = sorted(chunks, key=_stable_id_key)
        
        self._prefix_meta.cached_chunk_ids = [
            str(c.get("id", "")) for c in sorted_chunks
        ]
        
        # Priority: 1. Pre-calculated token_count from chunker, 2. Live tiktoken count
        self._prefix_meta.cached_tokens = sum(
            c.get("token_count") or self._count_tokens(str(c.get("text", "")))
            for c in sorted_chunks
        )
        
        self._prefix_meta.prefix_hash = hashlib.md5(
            self._last_prefix.encode()
        ).hexdigest()[:12]
    
    def get_cache_hit_ratio(self, chunks: List[Dict[str, Any]]) -> float:
        """Estimate logical hit rate for given chunks."""
        current_ids = [str(c.get("id", "")) for c in chunks]
        return self._prefix_meta.calculate_hit_rate(current_ids)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get logical cache statistics."""
        return {
            "cached_chunks": len(self._prefix_meta.cached_chunk_ids),
            "cached_tokens": self._prefix_meta.cached_tokens,
            "prefix_hash": self._prefix_meta.prefix_hash or "none"
        }
    
    def invalidate(self):
        """Invalidate logical cache (call after file edits)."""
        self._prefix_meta = PrefixMetadata()
        self._last_prefix = ""

# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def build_prompt(
    system_prompt: str,
    chunks: List[Dict[str, Any]],
    query: str,
    history: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    One-shot prompt building.
    
    For simple cases where you don't need to track cache state.
    """
    manager = KVCacheManager(system_prompt)
    return manager.build(chunks, query, history)

def estimate_cache_savings(
    old_chunks: List[Dict[str, Any]],
    new_chunks: List[Dict[str, Any]],
    ms_per_token: float = 0.5
) -> Dict[str, Any]:
    """
    Estimate compute savings from cache reuse.
    
    Args:
        old_chunks: Previously processed chunks
        new_chunks: Current chunks
        ms_per_token: Estimated prefill time per token
        
    Returns:
        Savings analysis
    """
    old_ids = set(str(c.get("id", "")) for c in old_chunks)
    new_ids = set(str(c.get("id", "")) for c in new_chunks)
    
    overlap = old_ids & new_ids
    overlap_chunks = [c for c in new_chunks if str(c.get("id", "")) in overlap]
    
    total_tokens = sum(c.get("token_count", 0) for c in new_chunks)
    cached_tokens = sum(c.get("token_count", 0) for c in overlap_chunks)
    new_tokens = total_tokens - cached_tokens
    
    return {
        "cache_hit_ratio": cached_tokens / total_tokens if total_tokens else 0,
        "cached_tokens": cached_tokens,
        "new_tokens": new_tokens,
        "estimated_saved_ms": cached_tokens * ms_per_token,
        "speedup": total_tokens / new_tokens if new_tokens else float("inf")
    }
