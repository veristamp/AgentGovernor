# llm/__init__.py
"""
LLM Package - Unified AI Orchestration.

Simple usage:
    from llm import create_llm_manager
    
    llm = create_llm_manager(
        provider="openai",
        model="gpt-4o",
        pg_session=db
    )
    
    result = await llm.chat(session_id, query)
"""

from .manager import LLMManager, LLMConfig, create_llm_manager
from .client import LLMClient
from .kernel import LLMResponse, BaseLLM
from .cache_adapter import CacheStats, get_cache_adapter

__all__ = [
    # Manager
    "LLMManager",
    "LLMConfig",
    "create_llm_manager",
    # Client
    "LLMClient",
    # Caching
    "CacheStats",
    "get_cache_adapter",
    # Kernel (base classes)
    "LLMResponse",
    "BaseLLM",
]
