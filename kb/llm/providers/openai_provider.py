# llm/providers/openai_provider.py
"""
OpenAI Provider - Responses API Implementation.

Leverages the OpenAI Responses API for:
- Unified message handling via 'input' (supports both string and message array)
- Stateful conversations via 'previous_response_id'
- Prompt caching optimization via 'prompt_cache_key' / 'prompt_cache_retention'
- Background mode for long-running tasks
- Streaming with semantic events

Integration Notes:
- LLMClient normalizes all inputs to messages=[{role, content}] format
- This provider maps messages to Responses API 'input' field
- System prompts in messages are preserved (Responses API handles role:"system")

Reference: llm/doc/openai-api-format.md, caching.md, background.md, stream.md
"""

import sys
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field

from openai import AsyncOpenAI, AuthenticationError
from config import get_logger
from llm.kernel import BaseLLM, LLMResponse, get_or_request_key

log = get_logger("LLM.OpenAI")


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass  
class OpenAIConfig:
    """
    Advanced configuration for OpenAI Responses API.
    
    These settings are provider-specific and passed via kwargs
    through the LLMClient layer.
    """
    # Caching (improves hit rate by routing to same server)
    prompt_cache_key: Optional[str] = None
    prompt_cache_retention: str = "in_memory"  # "in_memory" or "24h"
    
    # Conversation chaining
    previous_response_id: Optional[str] = None
    
    # Storage & background
    store: bool = True  # Required for background mode
    background: bool = False  # Async long-running tasks
    
    # Output control  
    max_output_tokens: Optional[int] = None


# =============================================================================
# PROVIDER IMPLEMENTATION
# =============================================================================

class OpenAIProvider(BaseLLM):
    """
    OpenAI LLM Provider using the Responses API.
    
    This provider is instantiated by LLMClient and receives normalized
    messages from it. It maps those to the OpenAI Responses API format.
    
    Features:
    - Automatic prompt caching (1024+ tokens prefix)
    - Conversation chaining via previous_response_id
    - Background mode for long-running generations
    - Full usage statistics including cache metrics
    """
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """
        Initialize OpenAI provider.
        
        Args:
            api_key: Optional API key (defaults to env or interactive prompt)
            **kwargs: Additional configuration (passed by LLMClient)
        """
        self.api_key = api_key or get_or_request_key(
            "OPENAI_API_KEY", 
            "Please enter your OpenAI API Key"
        )
        self.client = AsyncOpenAI(api_key=self.api_key)
        self._last_response_id: Optional[str] = None
    
    # =========================================================================
    # CORE GENERATION (Called by LLMClient)
    # =========================================================================
    
    async def generate(
        self,
        model: str,
        prompt: str = None,
        messages: List[Dict[str, str]] = None,
        system: str = None,
        temperature: float = 0.7,
        max_tokens: int = None,
        stream: bool = False,
        **kwargs
    ) -> Union[LLMResponse, str]:
        """
        Generate text using OpenAI Responses API.
        
        This method is called by LLMClient.generate() which has already
        normalized inputs to the messages format.
        
        Args:
            model: Model ID (e.g., "gpt-4o-mini", "gpt-5")
            prompt: Simple text prompt (fallback if no messages)
            messages: Normalized message array from LLMClient
            system: System instructions (used if not in messages)
            temperature: Sampling temperature  
            max_tokens: Max output tokens
            stream: Enable streaming
            **kwargs: Provider-specific config (OpenAIConfig fields)
            
        Returns:
            LLMResponse with content and usage metadata
        """
        # Extract provider-specific config from kwargs
        config = self._extract_config(kwargs)
        
        # Build API parameters
        params = self._build_params(
            model=model,
            prompt=prompt,
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            config=config,
            extra=kwargs
        )
        
        # Execute request
        if stream:
            return await self._stream(params, model)
        else:
            return await self._generate(params, model)
    
    # =========================================================================
    # PARAMETER BUILDING
    # =========================================================================
    
    def _extract_config(self, kwargs: Dict) -> OpenAIConfig:
        """Extract OpenAI-specific config from kwargs."""
        config = OpenAIConfig()
        
        # Pop known config keys
        for field_name in [
            "prompt_cache_key", "prompt_cache_retention",
            "previous_response_id", "store", "background", 
            "max_output_tokens"
        ]:
            if field_name in kwargs:
                setattr(config, field_name, kwargs.pop(field_name))
        
        return config
    
    def _build_params(
        self,
        model: str,
        prompt: str,
        messages: List[Dict],
        system: str,
        temperature: float,
        max_tokens: int,
        stream: bool,
        config: OpenAIConfig,
        extra: Dict
    ) -> Dict[str, Any]:
        """
        Build Responses API request parameters.
        
        Maps from LLMClient's normalized format to Responses API format.
        """
        params = {"model": model}
        
        # === INPUT ===
        # Priority: messages > prompt > empty
        # LLMClient already builds messages with system inside
        if messages:
            params["input"] = messages
        elif prompt:
            params["input"] = prompt
        else:
            params["input"] = ""
        
        # === INSTRUCTIONS ===
        # Only set if explicit system provided and NOT already in messages
        # (LLMClient typically embeds system in messages, but this is a fallback)
        if system and not messages:
            params["instructions"] = system
        
        # === GENERATION PARAMS ===
        if temperature is not None:
            params["temperature"] = temperature
        
        if max_tokens or config.max_output_tokens:
            params["max_output_tokens"] = max_tokens or config.max_output_tokens
        
        # === STREAMING ===
        if stream:
            params["stream"] = True
        
        # === CACHING OPTIMIZATION ===
        if config.prompt_cache_key:
            params["prompt_cache_key"] = config.prompt_cache_key
        if config.prompt_cache_retention != "in_memory":
            params["prompt_cache_retention"] = config.prompt_cache_retention
        
        # === CONVERSATION CHAINING ===  
        if config.previous_response_id:
            params["previous_response_id"] = config.previous_response_id
        
        # === STORAGE & BACKGROUND ===
        params["store"] = config.store
        if config.background:
            params["background"] = True
        
        # === EXTRA PARAMS ===
        # Pass through remaining kwargs (tools, reasoning, etc.)
        params.update(extra)
        
        return params
    
    # =========================================================================
    # REQUEST EXECUTION  
    # =========================================================================
    
    async def _generate(self, params: Dict, model: str) -> LLMResponse:
        """Execute non-streaming generation."""
        response = await self.client.responses.create(**params)
        
        # Store response ID for chaining
        self._last_response_id = getattr(response, "id", None)
        
        # Extract content and usage
        content = self._extract_content(response)
        usage = self._extract_usage(response)
        
        # Extract stop reason
        stop_reason = ""
        if hasattr(response, "output") and response.output:
            last_item = response.output[-1]
            stop_reason = getattr(last_item, "stop_reason", "") or ""
        
        return LLMResponse(
            content=content,
            usage=usage,
            model=model,
            provider="openai",  # Added: explicitly pass provider
            cached=usage.get("cached_tokens", 0) > 0,
            stop_reason=stop_reason
        )
    
    async def _stream(self, params: Dict, model: str) -> str:
        """Execute streaming generation."""
        output_parts = []
        
        stream = await self.client.responses.create(**params)
        
        async for event in stream:
            event_type = getattr(event, "type", "")
            
            # Text delta events (as per stream.md)
            if event_type == "response.output_text.delta":
                text = getattr(event, "delta", "")
                if text:
                    sys.stdout.write(text)
                    sys.stdout.flush()
                    output_parts.append(text)
            
            # Capture response ID from completion
            elif event_type == "response.completed":
                resp = getattr(event, "response", None)
                if resp:
                    self._last_response_id = getattr(resp, "id", None)
        
        return "".join(output_parts).strip()
    
    # =========================================================================
    # RESPONSE PARSING
    # =========================================================================
    
    def _extract_content(self, response) -> str:
        """Extract text content from response object."""
        # Primary: output_text helper (most common)
        content = getattr(response, "output_text", None)
        if content:
            return content
        
        # Fallback: iterate output items
        if hasattr(response, "output") and response.output:
            parts = []
            for item in response.output:
                # Direct text
                if hasattr(item, "text"):
                    parts.append(item.text)
                # Message content items  
                elif hasattr(item, "content"):
                    for part in getattr(item, "content", []):
                        if hasattr(part, "text"):
                            parts.append(part.text)
            return "".join(parts)
        
        return ""
    
    def _extract_usage(self, response) -> Dict[str, int]:
        """
        Extract usage statistics with proper field mapping.
        
        Responses API uses:
        - input_tokens / input_tokens_details.cached_tokens
        - output_tokens / output_tokens_details.reasoning_tokens
        
        We map to standard names for LLMResponse compatibility
        (prompt_tokens, completion_tokens, etc.)
        """
        usage = getattr(response, "usage", None)
        if not usage:
            return {}
        
        result = {
            "prompt_tokens": getattr(usage, "input_tokens", 0),
            "completion_tokens": getattr(usage, "output_tokens", 0),
            "total_tokens": getattr(usage, "total_tokens", 0),
        }
        
        # Cache details (key metric for optimization)
        input_details = getattr(usage, "input_tokens_details", None)
        if input_details:
            cached = getattr(input_details, "cached_tokens", 0)
            if cached:
                result["cached_tokens"] = cached
        
        # Reasoning tokens (for o1, gpt-5, etc.)
        output_details = getattr(usage, "output_tokens_details", None)
        if output_details:
            reasoning = getattr(output_details, "reasoning_tokens", 0)
            if reasoning:
                result["reasoning_tokens"] = reasoning
        
        return result
    
    # =========================================================================
    # UTILITIES
    # =========================================================================
    
    @property
    def last_response_id(self) -> Optional[str]:
        """Get the last response ID for conversation chaining."""
        return self._last_response_id
    
    def list_models(self) -> List[str]:
        """List available models (synchronous)."""
        from openai import OpenAI
        try:
            sync_client = OpenAI(api_key=self.api_key)
            models = sync_client.models.list()
            return sorted([m.id for m in models.data])
        except AuthenticationError:
            raise RuntimeError("Invalid API key. Please check .env file.")
    
    # =========================================================================
    # BACKGROUND MODE HELPERS
    # =========================================================================
    
    async def poll_background(
        self, 
        response_id: str, 
        interval: float = 2.0
    ) -> LLMResponse:
        """
        Poll a background response until completion.
        
        Usage:
            response = await provider.generate(..., background=True)
            # Returns immediately with status="queued"
            final = await provider.poll_background(response.id)
        """
        import asyncio
        
        while True:
            response = await self.client.responses.retrieve(response_id)
            status = getattr(response, "status", "")
            
            if status not in ("queued", "in_progress"):
                break
            
            log.debug(f"Background response {response_id}: {status}")
            await asyncio.sleep(interval)
        
        if status == "completed":
            return LLMResponse(
                content=self._extract_content(response),
                usage=self._extract_usage(response),
                model=getattr(response, "model", ""),
                cached=False
            )
        else:
            raise RuntimeError(f"Background response failed with status: {status}")
    
    async def cancel_background(self, response_id: str) -> bool:
        """Cancel an in-flight background response."""
        try:
            await self.client.responses.cancel(response_id)
            return True
        except Exception as e:
            log.error(f"Failed to cancel response {response_id}: {e}")
            return False