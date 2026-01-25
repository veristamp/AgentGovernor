# services/chat/response_formatter.py
"""
Response Formatter - Multi-Format Output Adapter.

Translates internal LLM results into provider-specific response formats.
Supports OpenAI, Anthropic, Gemini, and raw internal formats.

Architecture:
    LLMManager returns → Internal format
        ↓
    ResponseFormatter → Provider-specific format
        ↓
    API response to client

Usage:
    formatter = ResponseFormatter(model_name="gpt-4o-mini")
    
    # OpenAI format (default, industry standard)
    response = formatter.format(result, format="openai")
    
    # Anthropic format
    response = formatter.format(result, format="anthropic")
    
    # Raw internal format (for debugging)
    response = formatter.format(result, format="raw")
"""

import time
import uuid
from typing import Dict, Any, List, Optional
from enum import Enum

from services.chat.models import SessionState, ChatContext


class ResponseFormat(str, Enum):
    """Supported response formats."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"  
    GEMINI = "gemini"
    RAW = "raw"


class ResponseFormatter:
    """
    Multi-format response adapter.
    
    Translates internal LLM results into provider-specific JSON responses.
    Maintains compatibility with different client expectations.
    """
    
    def __init__(self, model_name: str, provider: str = "openai"):
        self.model_name = model_name
        self.provider = provider
    
    def format(
        self,
        result: Dict[str, Any],
        context: ChatContext,
        session_state: SessionState,
        response_format: str = "openai"
    ) -> Dict[str, Any]:
        """
        Format internal result to specified output format.
        
        Args:
            result: Internal LLM result
            context: Chat context
            session_state: Session state
            response_format: Output format (openai, anthropic, gemini, raw)
            
        Returns:
            Formatted response dict
        """
        if response_format == ResponseFormat.ANTHROPIC:
            return self._format_anthropic(result, context, session_state)
        elif response_format == ResponseFormat.GEMINI:
            return self._format_gemini(result, context, session_state)
        elif response_format == ResponseFormat.RAW:
            return self._format_raw(result, context, session_state)
        else:
            # Default to OpenAI (industry standard)
            return self._format_openai(result, context, session_state)
    
    # =========================================================================
    # OPENAI FORMAT
    # =========================================================================
    
    def _format_openai(
        self,
        result: Dict[str, Any],
        context: ChatContext,
        session_state: SessionState
    ) -> Dict[str, Any]:
        """
        Format as OpenAI Chat Completion response.
        
        This is the de-facto industry standard format.
        """
        response_text = result.get("response", "")
        chunk_ids = result.get("chunk_ids", [])
        new_chunks = result.get("chunks", [])
        
        # Token usage
        prompt_tokens = result.get("input_tokens", 0)
        completion_tokens = result.get("output_tokens", 0)
        
        if prompt_tokens == 0:
            prompt_tokens = self._estimate_prompt_tokens(context.user_query, new_chunks, session_state)
        if completion_tokens == 0:
            completion_tokens = len(response_text) // 4

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.model_name,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text
                },
                "finish_reason": result.get("stop_reason") or "stop"
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "prompt_tokens_details": {
                    "cached_tokens": result.get("cached_tokens", 0)
                }
            },
            "system_fingerprint": f"kb-rag-v5-{context.get_latency_ms()}ms",
            
            # Internal metadata (prefixed with _)
            "_session": {
                "id": context.session_id,
                "is_new": context.is_new_session,
                "request_count": session_state.request_count,
                "history_k": session_state.history_k,
                "chunks_count": len(new_chunks),
                "chunk_refresh": context.need_refresh
            },
            # Full chunk data for frontend feedback operations
            "_chunks": self._format_chunks_for_frontend(new_chunks, chunk_ids),
            "_config": result.get("config_used", {}),
            "_feedback": result.get("feedback", {}),
            "_cache": result.get("cache_stats", {})
        }
    
    # =========================================================================
    # ANTHROPIC FORMAT
    # =========================================================================
    
    def _format_anthropic(
        self,
        result: Dict[str, Any],
        context: ChatContext,
        session_state: SessionState
    ) -> Dict[str, Any]:
        """
        Format as Anthropic Messages API response.
        
        Reference: https://docs.anthropic.com/en/api/messages
        """
        response_text = result.get("response", "")
        
        prompt_tokens = result.get("input_tokens", 0)
        completion_tokens = result.get("output_tokens", 0)
        
        if prompt_tokens == 0:
            prompt_tokens = self._estimate_prompt_tokens(
                context.user_query, result.get("chunks", []), session_state
            )
        if completion_tokens == 0:
            completion_tokens = len(response_text) // 4
        
        return {
            "id": f"msg_{uuid.uuid4().hex[:24]}",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": response_text
                }
            ],
            "model": self.model_name,
            "stop_reason": result.get("stop_reason") or "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": result.get("cached_tokens", 0)
            },
            
            # Internal metadata
            "_session": {
                "id": context.session_id,
                "is_new": context.is_new_session,
                "request_count": session_state.request_count
            },
            "_chunks": {
                "ids": result.get("chunk_ids", []),
                "count": len(result.get("chunks", []))
            },
            "_config": result.get("config_used", {}),
            "_latency_ms": context.get_latency_ms()
        }
    
    # =========================================================================
    # GEMINI FORMAT
    # =========================================================================
    
    def _format_gemini(
        self,
        result: Dict[str, Any],
        context: ChatContext,
        session_state: SessionState
    ) -> Dict[str, Any]:
        """
        Format as Google Gemini GenerateContent response.
        
        Reference: https://ai.google.dev/api/rest/v1/GenerateContentResponse
        """
        response_text = result.get("response", "")
        
        prompt_tokens = result.get("input_tokens", 0)
        completion_tokens = result.get("output_tokens", 0)
        
        if prompt_tokens == 0:
            prompt_tokens = self._estimate_prompt_tokens(
                context.user_query, result.get("chunks", []), session_state
            )
        if completion_tokens == 0:
            completion_tokens = len(response_text) // 4
        
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": response_text}
                        ],
                        "role": "model"
                    },
                    "finishReason": self._map_stop_reason_gemini(result.get("stop_reason")),
                    "index": 0,
                    "safetyRatings": []
                }
            ],
            "usageMetadata": {
                "promptTokenCount": prompt_tokens,
                "candidatesTokenCount": completion_tokens,
                "totalTokenCount": prompt_tokens + completion_tokens,
                "cachedContentTokenCount": result.get("cached_tokens", 0)
            },
            "modelVersion": self.model_name,
            
            # Internal metadata
            "_session": {
                "id": context.session_id,
                "is_new": context.is_new_session,
                "request_count": session_state.request_count
            },
            "_chunks": {
                "ids": result.get("chunk_ids", []),
                "count": len(result.get("chunks", []))
            },
            "_config": result.get("config_used", {}),
            "_latency_ms": context.get_latency_ms()
        }
    
    def _map_stop_reason_gemini(self, stop_reason: Optional[str]) -> str:
        """Map internal stop reason to Gemini format."""
        mapping = {
            "stop": "STOP",
            "end_turn": "STOP",
            "length": "MAX_TOKENS",
            "max_tokens": "MAX_TOKENS",
            "content_filter": "SAFETY",
        }
        return mapping.get(stop_reason or "stop", "STOP")
    
    # =========================================================================
    # RAW FORMAT (Internal/Debug)
    # =========================================================================
    
    def _format_raw(
        self,
        result: Dict[str, Any],
        context: ChatContext,
        session_state: SessionState
    ) -> Dict[str, Any]:
        """
        Return raw internal format with all metadata.
        
        Useful for debugging and internal consumption.
        """
        return {
            "response": result.get("response", ""),
            "model": self.model_name,
            "provider": self.provider,
            
            # Token usage
            "usage": {
                "input_tokens": result.get("input_tokens", 0),
                "output_tokens": result.get("output_tokens", 0),
                "cached_tokens": result.get("cached_tokens", 0),
                "total_tokens": result.get("input_tokens", 0) + result.get("output_tokens", 0)
            },
            
            # RAG info
            "chunks": result.get("chunks", []),
            "chunk_ids": result.get("chunk_ids", []),
            
            # Session info
            "session": {
                "id": context.session_id,
                "is_new": context.is_new_session,
                "request_count": session_state.request_count,
                "history_k": session_state.history_k
            },
            
            # Config applied
            "config": result.get("config_used", {}),
            
            # Performance
            "latency_ms": context.get_latency_ms(),
            "stop_reason": result.get("stop_reason"),
            
            # Cache stats
            "cache": result.get("cache_stats", {}),
            
            # Feedback
            "feedback": result.get("feedback", {})
        }
    
    # =========================================================================
    # ERROR FORMATTING
    # =========================================================================
    
    def format_error(
        self, 
        error: str, 
        context: Optional[ChatContext] = None,
        response_format: str = "openai"
    ) -> Dict[str, Any]:
        """Format error response in the specified format."""
        
        if response_format == ResponseFormat.ANTHROPIC:
            return {
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": error
                },
                "_latency_ms": context.get_latency_ms() if context else 0
            }
        elif response_format == ResponseFormat.GEMINI:
            return {
                "error": {
                    "code": 500,
                    "message": error,
                    "status": "INTERNAL"
                },
                "_latency_ms": context.get_latency_ms() if context else 0
            }
        else:
            # OpenAI / default
            return {
                "id": f"chatcmpl-error-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": self.model_name,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"I encountered an error: {error}"
                    },
                    "finish_reason": "error"
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "_error": error,
                "_latency_ms": context.get_latency_ms() if context else 0
            }

    def format_empty(
        self, 
        context: Optional[ChatContext] = None,
        response_format: str = "openai"
    ) -> Dict[str, Any]:
        """Format response for empty query."""
        empty_message = "I didn't receive a question. How can I help you?"
        
        if response_format == ResponseFormat.ANTHROPIC:
            return {
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": empty_message}],
                "model": self.model_name,
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 0, "output_tokens": 0}
            }
        elif response_format == ResponseFormat.GEMINI:
            return {
                "candidates": [{
                    "content": {
                        "parts": [{"text": empty_message}],
                        "role": "model"
                    },
                    "finishReason": "STOP",
                    "index": 0
                }],
                "usageMetadata": {"promptTokenCount": 0, "candidatesTokenCount": 0, "totalTokenCount": 0}
            }
        else:
            return {
                "id": f"chatcmpl-empty-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": self.model_name,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": empty_message},
                    "finish_reason": "stop"
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "_latency_ms": context.get_latency_ms() if context else 0
            }
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _estimate_prompt_tokens(self, query: str, chunks: List[Any], session: SessionState) -> int:
        """Heuristic token estimation if provider returns zero."""
        chunk_tokens = sum(c.get("token_count", len(str(c.get("text", ""))) // 4) for c in chunks)
        query_tokens = len(query) // 4
        history_tokens = session.history_k * 100
        return chunk_tokens + query_tokens + history_tokens + 500
    
    def _format_chunks_for_frontend(self, chunks: List[Any], chunk_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Format chunks for frontend consumption and feedback operations.
        
        Returns list of dicts with:
        - id: Qdrant point ID (used for feedback API)
        - content: Chunk text content
        - score: Relevance score
        - file_path: Source file path
        """
        formatted = []
        for i, chunk in enumerate(chunks):
            # Handle dict or EnrichedChunk objects
            if hasattr(chunk, 'chunk_id'):
                # EnrichedChunk object
                formatted.append({
                    "id": chunk.chunk_id,
                    "content": chunk.content[:500] if len(chunk.content) > 500 else chunk.content,
                    "score": getattr(chunk, 'score', 0.0),
                    "file_path": getattr(chunk, 'source', '')
                })
            elif isinstance(chunk, dict):
                # Dict format
                chunk_id = chunk.get("id") or chunk.get("chunk_id") or (chunk_ids[i] if i < len(chunk_ids) else 0)
                content = chunk.get("text") or chunk.get("content") or ""
                formatted.append({
                    "id": chunk_id,
                    "content": content[:500] if len(content) > 500 else content,
                    "score": chunk.get("score", 0.0),
                    "file_path": chunk.get("source") or chunk.get("file_path") or ""
                })
        return formatted

    # Legacy method for backward compatibility
    def format_completion(
        self,
        result: Dict[str, Any],
        context: ChatContext,
        session_state: SessionState
    ) -> Dict[str, Any]:
        """Legacy method - defaults to OpenAI format."""
        return self.format(result, context, session_state, response_format="openai")
