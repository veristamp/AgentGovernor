# llm/cache_adapter.py
"""
Provider Cache Adapter - Provider-Specific Caching Optimization.

Translates wrapper session state into provider-specific cache hints.
Each provider has different caching capabilities:

| Provider    | Auto-Cache | Explicit Cache | Strategy                    |
|-------------|------------|----------------|------------------------------|
| OpenAI      | Yes (≥1024)| prompt_cache_key| Use session_id for affinity |
| Anthropic   | No         | cache_control   | Mark static sections        |
| Gemini      | Yes        | Named caches    | TTL-based named caches      |
| Bedrock     | No         | Checkpoints     | Converse API checkpoints    |
| Groq        | Yes        | No              | Auto (no hints needed)      |
| Ollama      | Local KV   | No              | Local only (no API hints)   |
| Others      | Varies     | No              | NoOp adapter                |

Usage:
    from llm.cache_adapter import get_cache_adapter
    
    adapter = get_cache_adapter("openai")
    
    # Before request
    request_hints = adapter.prepare_request(messages, session_id)
    
    # After response
    cache_stats = adapter.parse_response(response)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from config import get_logger

logger = get_logger("CacheAdapter")


# =============================================================================
# CACHE STATISTICS
# =============================================================================

@dataclass
class CacheStats:
    """
    Unified cache statistics across all providers.
    
    This provides a common interface for tracking cache performance
    regardless of the underlying provider's caching mechanism.
    """
    # Token counts
    cached_tokens: int = 0          # Tokens served from cache
    total_prompt_tokens: int = 0    # Total prompt tokens
    
    # Derived metrics
    cache_hit_rate: float = 0.0     # cached_tokens / total_prompt_tokens
    
    # Provider-specific
    provider: str = ""              # Which provider
    cache_type: str = "auto"        # "auto", "explicit", "none"
    
    # Cost savings estimate (provider-dependent)
    estimated_savings_pct: float = 0.0  # % cost reduction from caching
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "cached_tokens": self.cached_tokens,
            "total_prompt_tokens": self.total_prompt_tokens,
            "cache_hit_rate": round(self.cache_hit_rate, 4),
            "provider": self.provider,
            "cache_type": self.cache_type,
            "estimated_savings_pct": round(self.estimated_savings_pct, 2),
            **self.metadata
        }


# =============================================================================
# BASE ADAPTER
# =============================================================================

class BaseCacheAdapter(ABC):
    """
    Abstract base for provider-specific cache adapters.
    
    Responsibilities:
    1. prepare_request(): Add provider-specific cache hints to requests
    2. parse_response(): Extract cache statistics from responses
    3. estimate_savings(): Calculate cost savings from caching
    """
    
    provider_name: str = "base"
    cache_type: str = "none"  # "auto", "explicit", "none"
    
    @abstractmethod
    def prepare_request(
        self, 
        messages: List[Dict[str, Any]], 
        session_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Add provider-specific cache hints to the request.
        
        Args:
            messages: The messages array to be sent
            session_id: Session identifier for cache affinity
            **kwargs: Additional context (system_prompt, etc.)
            
        Returns:
            Dict of provider-specific kwargs to merge into request
        """
        pass
    
    @abstractmethod
    def parse_response(self, response: Any) -> CacheStats:
        """
        Extract cache statistics from provider response.
        
        Args:
            response: Raw response from provider (or LLMResponse)
            
        Returns:
            Unified CacheStats object
        """
        pass
    
    def estimate_savings(self, stats: CacheStats) -> float:
        """
        Estimate cost savings percentage from caching.
        
        Default implementation - override for provider-specific logic.
        """
        if stats.total_prompt_tokens == 0:
            return 0.0
        
        # Most providers offer ~50-90% discount on cached tokens
        # Default to 50% savings on cached portion
        cached_ratio = stats.cached_tokens / stats.total_prompt_tokens
        return cached_ratio * 0.5 * 100  # Return as percentage


# =============================================================================
# OPENAI ADAPTER
# =============================================================================

class OpenAICacheAdapter(BaseCacheAdapter):
    """
    OpenAI Cache Adapter.
    
    OpenAI auto-caches prefixes ≥1024 tokens with ~75% discount.
    We can influence routing with prompt_cache_key for better hit rates.
    
    Strategy:
    - Use session_id prefix as prompt_cache_key for affinity
    - Keep requests with same session routed to same cache node
    - Extended retention (24h) for long-lived sessions
    """
    
    provider_name = "openai"
    cache_type = "auto"
    
    def __init__(self, use_extended_retention: bool = False):
        """
        Args:
            use_extended_retention: Use 24h cache retention (for GPT-5+ models)
        """
        self.use_extended_retention = use_extended_retention
    
    def prepare_request(
        self, 
        messages: List[Dict[str, Any]], 
        session_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Add OpenAI-specific cache hints."""
        hints = {}
        
        # Use session_id for cache routing affinity
        if session_id:
            # First 16 chars for routing (combine with prefix hash)
            hints["prompt_cache_key"] = session_id[:16]
        
        # Extended retention for long-running sessions
        if self.use_extended_retention:
            hints["prompt_cache_retention"] = "24h"
        
        return hints
    
    def parse_response(self, response: Any) -> CacheStats:
        """Extract cache stats from OpenAI response."""
        # Handle dict response (raw API)
        if isinstance(response, dict):
            usage = response.get("usage", {})
            details = usage.get("prompt_tokens_details", {})
            cached = details.get("cached_tokens", 0)
            total = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
        
        # Handle LLMResponse object
        elif hasattr(response, "cached_tokens"):
            cached = response.cached_tokens or 0
            total = response.input_tokens or 0
        
        else:
            return CacheStats(provider=self.provider_name)
        
        hit_rate = cached / max(1, total)
        
        # OpenAI gives 75% discount on cached tokens (50% for some tiers)
        savings = hit_rate * 75
        
        return CacheStats(
            cached_tokens=cached,
            total_prompt_tokens=total,
            cache_hit_rate=hit_rate,
            provider=self.provider_name,
            cache_type=self.cache_type,
            estimated_savings_pct=savings,
            metadata={
                "openai_cache_type": "auto" if cached > 0 else "miss"
            }
        )


# =============================================================================
# ANTHROPIC ADAPTER
# =============================================================================

class AnthropicCacheAdapter(BaseCacheAdapter):
    """
    Anthropic Cache Adapter.
    
    Anthropic requires explicit cache_control markers on messages.
    90% discount on cached reads, but you pay for cache writes.
    
    Strategy:
    - Mark system prompt as cacheable (ephemeral)
    - Mark stable context chunks as cacheable
    - Leave dynamic content (query, recent history) unmarked
    """
    
    provider_name = "anthropic"
    cache_type = "explicit"
    
    def __init__(self, cache_breakpoints: int = 2):
        """
        Args:
            cache_breakpoints: Max number of cache_control markers (Anthropic limits to 4)
        """
        self.cache_breakpoints = min(cache_breakpoints, 4)
    
    def prepare_request(
        self, 
        messages: List[Dict[str, Any]], 
        session_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Add Anthropic cache_control markers.
        
        Anthropic format:
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "...",
                    "cache_control": {"type": "ephemeral"}
                }
            ]
        }
        """
        modified_messages = []
        cache_marks_used = 0
        
        for i, msg in enumerate(messages):
            new_msg = dict(msg)
            
            # Mark system prompt (always cache if present)
            if msg.get("role") == "system" and cache_marks_used < self.cache_breakpoints:
                new_msg["content"] = self._wrap_with_cache_control(msg["content"])
                cache_marks_used += 1
            
            # Mark first user message (usually contains stable context)
            elif msg.get("role") == "user" and i <= 2 and cache_marks_used < self.cache_breakpoints:
                # Only cache if content is substantial (>500 chars suggests context)
                content = msg.get("content", "")
                if len(content) > 500:
                    new_msg["content"] = self._wrap_with_cache_control(content)
                    cache_marks_used += 1
            
            modified_messages.append(new_msg)
        
        return {"messages": modified_messages}
    
    def _wrap_with_cache_control(self, content: str) -> List[Dict[str, Any]]:
        """Wrap content with cache_control for Anthropic."""
        return [{
            "type": "text",
            "text": content,
            "cache_control": {"type": "ephemeral"}
        }]
    
    def parse_response(self, response: Any) -> CacheStats:
        """Extract cache stats from Anthropic response."""
        # Anthropic returns cache_creation_input_tokens and cache_read_input_tokens
        if isinstance(response, dict):
            usage = response.get("usage", {})
            cache_read = usage.get("cache_read_input_tokens", 0)
            cache_write = usage.get("cache_creation_input_tokens", 0)
            total = usage.get("input_tokens", 0)
        
        elif hasattr(response, "usage"):
            usage = response.usage if isinstance(response.usage, dict) else {}
            cache_read = usage.get("cache_read_input_tokens", 0)
            cache_write = usage.get("cache_creation_input_tokens", 0)
            total = usage.get("input_tokens", 0)
        
        else:
            return CacheStats(provider=self.provider_name, cache_type=self.cache_type)
        
        # For Anthropic, cached tokens are the ones READ from cache
        cached = cache_read
        hit_rate = cached / max(1, total) if total > 0 else 0
        
        # Anthropic: 90% discount on cache reads
        savings = hit_rate * 90
        
        return CacheStats(
            cached_tokens=cached,
            total_prompt_tokens=total,
            cache_hit_rate=hit_rate,
            provider=self.provider_name,
            cache_type=self.cache_type,
            estimated_savings_pct=savings,
            metadata={
                "cache_read_tokens": cache_read,
                "cache_write_tokens": cache_write,
                "cache_status": "hit" if cache_read > 0 else ("write" if cache_write > 0 else "miss")
            }
        )


# =============================================================================
# GEMINI ADAPTER
# =============================================================================

class GeminiCacheAdapter(BaseCacheAdapter):
    """
    Gemini Cache Adapter.
    
    Gemini supports both auto-caching and explicit named caches with TTL.
    75-90% discount on cached content.
    
    Strategy:
    - Use auto-caching for most cases (implicit prefix caching)
    - Named caches for long-running sessions with stable context
    """
    
    provider_name = "gemini"
    cache_type = "auto"  # Can also be "explicit" with named caches
    
    def __init__(self, use_named_cache: bool = False, cache_ttl_seconds: int = 3600):
        self.use_named_cache = use_named_cache
        self.cache_ttl_seconds = cache_ttl_seconds
    
    def prepare_request(
        self, 
        messages: List[Dict[str, Any]], 
        session_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Prepare Gemini-specific hints."""
        hints = {}
        
        if self.use_named_cache and session_id:
            # Named cache format for Gemini
            hints["cached_content"] = {
                "name": f"session-{session_id[:16]}",
                "ttl": f"{self.cache_ttl_seconds}s"
            }
        
        # Gemini auto-caches, so no special hints needed for basic usage
        return hints
    
    def parse_response(self, response: Any) -> CacheStats:
        """Extract cache stats from Gemini response."""
        if isinstance(response, dict):
            usage = response.get("usageMetadata", {})
            cached = usage.get("cachedContentTokenCount", 0)
            total = usage.get("promptTokenCount", 0)
        elif hasattr(response, "cached_tokens"):
            cached = response.cached_tokens or 0
            total = response.input_tokens or 0
        else:
            return CacheStats(provider=self.provider_name, cache_type=self.cache_type)
        
        hit_rate = cached / max(1, total)
        savings = hit_rate * 75  # 75% discount
        
        return CacheStats(
            cached_tokens=cached,
            total_prompt_tokens=total,
            cache_hit_rate=hit_rate,
            provider=self.provider_name,
            cache_type=self.cache_type,
            estimated_savings_pct=savings
        )


# =============================================================================
# GROQ ADAPTER
# =============================================================================

class GroqCacheAdapter(BaseCacheAdapter):
    """
    Groq Cache Adapter.
    
    Groq auto-caches common prefixes with ~50% discount.
    No explicit cache control available.
    """
    
    provider_name = "groq"
    cache_type = "auto"
    
    def prepare_request(
        self, 
        messages: List[Dict[str, Any]], 
        session_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """No hints needed - Groq handles caching automatically."""
        return {}
    
    def parse_response(self, response: Any) -> CacheStats:
        """Extract cache stats from Groq response."""
        # Groq doesn't expose cache stats in response
        # We can only track token usage
        if isinstance(response, dict):
            usage = response.get("usage", {})
            total = usage.get("prompt_tokens", 0)
        elif hasattr(response, "input_tokens"):
            total = response.input_tokens or 0
        else:
            total = 0
        
        return CacheStats(
            cached_tokens=0,  # Not exposed by Groq
            total_prompt_tokens=total,
            cache_hit_rate=0,  # Unknown
            provider=self.provider_name,
            cache_type=self.cache_type,
            estimated_savings_pct=0,  # Can't calculate without cache info
            metadata={"note": "Groq auto-caches but doesn't expose stats"}
        )


# =============================================================================
# NOOP ADAPTER
# =============================================================================

class NoOpCacheAdapter(BaseCacheAdapter):
    """
    No-Op Cache Adapter.
    
    For providers without API-level caching:
    - Ollama (local KV cache only)
    - Mistral (KV cache in inference libs)
    - HuggingFace (local Transformers cache)
    - OpenRouter (provider-dependent, handled by underlying provider)
    """
    
    provider_name = "noop"
    cache_type = "none"
    
    def __init__(self, provider_name: str = "unknown"):
        self.provider_name = provider_name
    
    def prepare_request(
        self, 
        messages: List[Dict[str, Any]], 
        session_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """No cache hints for this provider."""
        return {}
    
    def parse_response(self, response: Any) -> CacheStats:
        """No cache stats available."""
        total = 0
        if isinstance(response, dict):
            usage = response.get("usage", {})
            total = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
        elif hasattr(response, "input_tokens"):
            total = response.input_tokens or 0
        
        return CacheStats(
            cached_tokens=0,
            total_prompt_tokens=total,
            cache_hit_rate=0,
            provider=self.provider_name,
            cache_type=self.cache_type,
            estimated_savings_pct=0
        )


# =============================================================================
# FACTORY
# =============================================================================

# Provider to adapter mapping
_ADAPTER_MAP: Dict[str, type] = {
    "openai": OpenAICacheAdapter,
    "anthropic": AnthropicCacheAdapter,
    "gemini": GeminiCacheAdapter,
    "groq": GroqCacheAdapter,
    "azure": OpenAICacheAdapter,  # Azure uses OpenAI API
    "xai": OpenAICacheAdapter,    # xAI has similar caching to OpenAI
}


def get_cache_adapter(provider: str, **kwargs) -> BaseCacheAdapter:
    """
    Get the appropriate cache adapter for a provider.
    
    Args:
        provider: Provider name (openai, anthropic, etc.)
        **kwargs: Provider-specific configuration
        
    Returns:
        Cache adapter instance
        
    Example:
        adapter = get_cache_adapter("openai", use_extended_retention=True)
        hints = adapter.prepare_request(messages, session_id="user_123")
    """
    provider_lower = provider.lower()
    
    if provider_lower in _ADAPTER_MAP:
        adapter_class = _ADAPTER_MAP[provider_lower]
        return adapter_class(**kwargs)
    
    # Default to NoOp for unknown providers
    logger.debug(f"No cache adapter for '{provider}', using NoOp")
    return NoOpCacheAdapter(provider_name=provider_lower)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Base
    "BaseCacheAdapter",
    "CacheStats",
    # Adapters
    "OpenAICacheAdapter",
    "AnthropicCacheAdapter",
    "GeminiCacheAdapter", 
    "GroqCacheAdapter",
    "NoOpCacheAdapter",
    # Factory
    "get_cache_adapter",
]
