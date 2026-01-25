# llm/kernel.py
"""
LLM Kernel - Shared Infrastructure for Providers.

Contains the base classes, utilities, and configuration needed by LLM providers.
"""

import os
import sys
import time
from pathlib import Path
from functools import wraps
from typing import Callable, Any, Type, Tuple, Optional
from abc import ABC, abstractmethod
from dotenv import load_dotenv, find_dotenv
from config import get_logger

logger = get_logger("LLMKernel")


# =============================================================================
# BASE CLASSES
# =============================================================================

class LLMResponse(str):
    """
    Response string that carries essential metadata from LLM providers.
    Inherits from str for backward compatibility.
    
    Focused on what matters:
    - Token usage (for cost tracking, especially reasoning tokens)
    - Caching info (to know if OpenAI's prompt cache hit)
    - Stop reason (to know if output was truncated)
    """
    
    # Token usage (for cost tracking)
    usage: dict              # Full usage dict from provider
    input_tokens: int        # Tokens in prompt
    output_tokens: int       # Tokens in response  
    reasoning_tokens: int    # Tokens used for reasoning (o-series models)
    cached_tokens: int       # Tokens served from cache (prompt caching)
    
    # Model info
    model: str               # Model identifier
    provider: str            # Provider name (openai, anthropic, etc.)
    
    # Caching (to know if prompt cache hit)
    cached: bool             # Whether prompt was cached
    
    # Generation info
    stop_reason: str         # "stop", "length", "tool_calls"

    def __new__(
        cls, 
        content: str, 
        usage: dict = None,
        model: str = None,
        provider: str = None,
        cached: bool = False,
        stop_reason: str = None,
        **kwargs  # Accept extra kwargs for forward compatibility
    ):
        obj = super().__new__(cls, content)
        
        # Parse usage dict
        obj.usage = usage or {}
        obj.input_tokens = obj.usage.get("prompt_tokens", 0) or obj.usage.get("input_tokens", 0)
        obj.output_tokens = obj.usage.get("completion_tokens", 0) or obj.usage.get("output_tokens", 0)
        obj.reasoning_tokens = obj.usage.get("reasoning_tokens", 0)
        obj.cached_tokens = (
            obj.usage.get("cached_tokens", 0) or 
            obj.usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
        )
        
        # Model info
        obj.model = model or ""
        obj.provider = provider or ""
        
        # Caching
        obj.cached = cached or obj.cached_tokens > 0
        
        # Generation
        obj.stop_reason = stop_reason or ""
        
        return obj


class BaseLLM(ABC):
    """Abstract base for all LLM providers."""
    
    @abstractmethod
    async def generate(
        self,
        model: str,
        prompt: str = None,
        messages: list = None,
        system: str = None,
        temperature: float = 0.7,
        max_tokens: int = None,
        stream: bool = False,
        **kwargs
    ) -> str:
        """
        Generate a response from the LLM.
        
        Args:
            model: Model identifier
            prompt: Simple text prompt
            messages: Conversation messages array
            system: System instructions
            temperature: Sampling temperature
            max_tokens: Maximum output tokens
            stream: Enable streaming
            **kwargs: Provider-specific parameters
            
        Returns:
            Generated text (or LLMResponse with metadata)
        """
        pass


# =============================================================================
# UTILITIES
# =============================================================================

def set_key(env_file: str, key: str, value: str):
    """Set a key in an env file."""
    env_path = Path(env_file)
    lines = []
    if env_path.exists():
        with env_path.open("r") as f:
            lines = f.readlines()

    key_found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            key_found = True
            break

    if not key_found:
        lines.append(f"{key}={value}\n")

    with env_path.open("w") as f:
        f.writelines(lines)


def get_or_request_key(env_var_name: str, prompt_message: str) -> str:
    """Fetch key from env, prompt if missing."""
    dotenv_path = find_dotenv()
    if dotenv_path:
        load_dotenv(dotenv_path)
    else:
        Path(".env").touch()
        load_dotenv()
    
    key = os.getenv(env_var_name)
    if not key:
        logger.warning(f"{env_var_name} not found in .env")
        try:
            new_key = input(f"{prompt_message} (will be saved in .env): ").strip()
            if not new_key:
                logger.error("No key provided.")
                sys.exit(1)
            env_file = dotenv_path or Path(".env")
            set_key(str(env_file), env_var_name, new_key)
            os.environ[env_var_name] = new_key
            key = new_key
        except EOFError:
            logger.error(f"Cannot request input in this terminal. Please set {env_var_name} in .env")
            sys.exit(1)
            
    return key


def get_key_silent(env_var_name: str):
    """Return env key if exists, else None. No prompts."""
    dotenv_path = find_dotenv()
    if dotenv_path:
        load_dotenv(dotenv_path)
    return os.getenv(env_var_name)


def with_retry(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    retriable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """
    Decorator to add retry logic with exponential backoff.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retriable_exceptions as e:
                    last_exception = e
                    if attempt >= max_retries:
                        logger.error(f"Max retries ({max_retries}) exceeded for {func.__name__}")
                        raise
                    logger.info(f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                    delay *= backoff_factor
                except Exception:
                    raise
            
            if last_exception:
                raise last_exception
        return wrapper
    return decorator
