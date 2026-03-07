# llm/client.py
"""
Multi-provider LLM Client.

Unified interface for multiple LLM providers with integrated cache optimization.

Features:
- Provider-agnostic API
- Automatic cache hint injection via CacheAdapter
- Session affinity for better cache hit rates
- Unified cache statistics

Usage:
    client = LLMClient("openai")
    
    # With session_id for cache affinity
    response = await client.generate(
        model="gpt-4o",
        user="How does chunking work?",
        session_id="user_123"
    )
    
    # Get cache stats
    stats = client.get_cache_stats(response)
"""

from typing import Optional, List, Dict, Any, Union
from config import get_logger

logger = get_logger("LLMClient")


def _get_provider_class(name: str):
    """Lazy-load provider classes to handle missing dependencies gracefully."""
    name = name.lower()
    try:
        if name == "anthropic":
            from llm.providers.anthropic_provider import AnthropicProvider
            return AnthropicProvider
        elif name == "azure":
            from llm.providers.azure_provider import AzureProvider
            return AzureProvider
        elif name == "openai":
            from llm.providers.openai_provider import OpenAIProvider
            return OpenAIProvider
        elif name == "ollama":
            from llm.providers.ollama_provider import OllamaProvider
            return OllamaProvider
        elif name == "groq":
            from llm.providers.groq_provider import GroqProvider
            return GroqProvider
        elif name == "bedrock":
            from llm.providers.bedrock_provider import BedrockProvider
            return BedrockProvider
        elif name == "openrouter":
            from llm.providers.openrouter_provider import OpenRouterProvider
            return OpenRouterProvider
        elif name == "gemini":
            from llm.providers.gemini_provider import GeminiProvider
            return GeminiProvider
        elif name == "xai":
            from llm.providers.xai_provider import XAIProvider
            return XAIProvider
        elif name == "mistral":
            from llm.providers.mistral_provider import MistralProvider
            return MistralProvider
        elif name == "huggingface":
            from llm.providers.huggingface_provider import HuggingFaceProvider
            return HuggingFaceProvider
        elif name in ("gcp", "vertex", "vertexai"):
            from llm.providers.gcp_provider import GCPProvider
            return GCPProvider
        else:
            raise ValueError(f"Unsupported provider: {name}")
    except ImportError as e:
        logger.error(f"Failed to load provider '{name}': {e}")
        raise ImportError(f"Missing dependency for provider '{name}'. Error: {e}")


class LLMClient:
    """
    Standardized Client for interacting with any LLM provider.
    
    Integrates with CacheAdapter for provider-specific cache optimization.
    Use session_id parameter for cache affinity across requests.
    """
    
    def __init__(self, provider: str, **kwargs):
        """
        Initialize client.
        
        Args:
            provider: Provider name (openai, ollama, etc.)
            **kwargs: Config passed to the provider implementation.
        """
        ProviderClass = _get_provider_class(provider)
        self.impl = ProviderClass(**kwargs)
        self.name = provider.lower()
        
        # Initialize cache adapter for this provider
        self._cache_adapter = None
        self._last_cache_stats = None
    
    @property
    def cache_adapter(self):
        """Lazy-load cache adapter."""
        if self._cache_adapter is None:
            from llm.cache_adapter import get_cache_adapter
            self._cache_adapter = get_cache_adapter(self.name)
        return self._cache_adapter
        
    async def generate(
        self,
        model: str,
        prompt: Optional[str] = None,
        user: Optional[str] = None,
        system: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        stream: bool = False,
        session_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Unified async generation interface.
        
        Args:
            model: Model identifier
            prompt: Simple text prompt (legacy)
            user: User message content
            system: System prompt
            messages: Full messages array (overrides prompt/user/system)
            temperature: Sampling temperature
            max_tokens: Maximum output tokens
            stream: Enable streaming
            session_id: Session ID for cache affinity (improves cache hit rate)
            **kwargs: Provider-specific parameters
            
        Returns:
            Generated text (LLMResponse if provider supports metadata)
        """
        # 1. Normalize Messages
        if messages is None:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            elif hasattr(self.impl, "default_system_prompt"):
                messages.append({"role": "system", "content": self.impl.default_system_prompt})
            
            content = user or prompt
            if content:
                messages.append({"role": "user", "content": content})

        # 2. Apply cache adapter hints
        cache_hints = self.cache_adapter.prepare_request(
            messages=messages,
            session_id=session_id,
            system=system
        )
        
        # Merge cache hints into kwargs (cache hints take precedence for their specific keys)
        merged_kwargs = {**kwargs, **cache_hints}
        
        # Handle Anthropic's special message modification
        if "messages" in cache_hints:
            messages = cache_hints.pop("messages")
            merged_kwargs.pop("messages", None)

        # 3. Call Implementation (async)
        response = await self.impl.generate(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            **merged_kwargs
        )
        
        # 4. Parse cache stats from response
        self._last_cache_stats = self.cache_adapter.parse_response(response)
        
        return response
    
    def get_cache_stats(self, response: Any = None) -> Dict[str, Any]:
        """
        Get cache statistics from the last (or specified) response.
        
        Args:
            response: Optional response to parse (uses last response if None)
            
        Returns:
            Cache statistics dictionary
        """
        if response is not None:
            stats = self.cache_adapter.parse_response(response)
            return stats.to_dict()
        
        if self._last_cache_stats:
            return self._last_cache_stats.to_dict()
        
        return {
            "cached_tokens": 0,
            "total_prompt_tokens": 0,
            "cache_hit_rate": 0,
            "provider": self.name,
            "cache_type": self.cache_adapter.cache_type,
            "estimated_savings_pct": 0
        }

    def list_models(self) -> List[str]:
        """Fetch available models."""
        if hasattr(self.impl, "list_models"):
            return self.impl.list_models()
        return []
