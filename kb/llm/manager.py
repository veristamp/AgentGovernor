# llm/manager.py
"""
LLM Manager - Unified AI Orchestrator.

The highest-level interface that combines:
- Multi-provider LLM Clients
- RAG Retrieval
- Latent Memory (history, feedback, caching)

Philosophy:
- User provides: query, session_id
- System handles: retrieval, memory, caching, feedback, prompt building

Layer Structure:
┌─────────────────────────────────────────────────────────────────────────┐
│                          LLMManager                                      │
│   User-facing: chat(), feedback(), get_history()                         │
├─────────────────────────────────────────────────────────────────────────┤
│             RAGManager              │      LatentMemoryManager           │
│   retrieve(), enrich()              │   prepare(), learn(), feedback()   │
├─────────────────────────────────────────────────────────────────────────┤
│  LLMClient (OpenAI, Ollama, Groq, etc.)                                 │
└─────────────────────────────────────────────────────────────────────────┘

Usage:
    from llm.manager import create_llm_manager
    
    llm = create_llm_manager(
        provider="openai",
        model="gpt-4o",
        pg_session=db,
        qdrant_client=qdrant
    )
    
    # Simple chat - everything automatic
    result = await llm.chat(
        session_id="user_123",
        query="How does chunking work?"
    )
    
    # Optional: User feedback
    await llm.feedback(result["chunk_ids"], positive=True)
"""

import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from config import get_logger, DATABASE_CONFIG

logger = get_logger("LLMManager")


@dataclass
class LLMConfig:
    """LLM Manager configuration with smart defaults."""
    # LLM
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_output_tokens: int = 2048
    
    # RAG
    qdrant_url: Optional[str] = None
    collection_name: Optional[str] = None
    max_chunks: int = 5
    use_rerank: bool = True
    
    # Embedding Models (None = use defaults from config/embeddings.py)
    embedding_provider: Optional[str] = None  # fastembed, ollama, openai, infinity
    embedding_base_url: Optional[str] = None
    dense_model: Optional[str] = None
    sparse_model: Optional[str] = None
    reranker_model: Optional[str] = None
    reranker_provider: Optional[str] = None
    reranker_base_url: Optional[str] = None
    
    # Memory
    max_context_tokens: int = 128000
    history_k: int = 10
    enable_feedback: bool = True
    compress_context: bool = False  # Use semantic compressor to reduce noise
    
    # Prompt Caching (OpenAI-specific, passed to provider)
    prompt_cache_key: Optional[str] = None  # Influences cache routing for better hit rates
    prompt_cache_retention: str = "in_memory"  # "in_memory" or "24h" (extended)
    
    # System
    system_prompt: str = (
        "You are a helpful assistant for technical documentation. "
        "Use the provided context to answer. Always cite your sources "
        "using the [cite:ID] format when referencing specific chunks."
    )


class LLMManager:
    """
    Unified LLM Orchestrator.
    
    Handles the complete cycle:
    1. RETRIEVE - Get relevant chunks from RAG
    2. PREPARE - Build cache-optimal prompt with memory
    3. GENERATE - Call LLM provider
    4. LEARN - Extract citations, update feedback
    
    The user only calls chat() - everything else is automatic.
    """
    
    def __init__(
        self,
        pg_session: Optional[Any] = None,
        qdrant_client: Optional[Any] = None,
        config: Optional[LLMConfig] = None,
        **kwargs
    ):
        """
        Initialize the LLM Manager.
        
        Args:
            pg_session: Database session/factory for persistence
            qdrant_client: Qdrant client for vector operations
            config: Optional configuration (uses smart defaults)
            **kwargs: Override config values
        """
        # Merge config
        self.config = config or LLMConfig()
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        
        # Store clients
        self._pg_session = pg_session
        self._qdrant = qdrant_client
        
        # Lazy-loaded components
        self._llm_client = None
        self._rag = None
        self._memory = None
        
        logger.info(f"🚀 LLMManager initialized: {self.config.provider}/{self.config.model}")
    
    # =========================================================================
    # MAIN PUBLIC API
    # =========================================================================
    
    async def chat(
        self,
        session_id: str,
        query: str,
        user_id: Optional[str] = None,
        # RAG control
        use_rag: bool = True,
        retrieval_limit: int = 5,
        use_rerank: bool = True,
        use_mmr: bool = True,
        mmr_lambda: float = 0.7,
        use_feedback_boost: bool = True,
        compress_chunks: bool = False,
        pre_retrieved_chunks: Optional[List[Any]] = None,
        # History control
        include_history: bool = True,
        history_k: int = 10,
        # Memory control
        skip_learning: bool = False,
        include_ltm: bool = True,
        # Generation control
        stream: bool = False,
        **generation_kwargs
    ) -> Dict[str, Any]:
        """
        Complete RAG + Memory chat cycle with FULL user control.
        
        Args:
            session_id: Conversation session identifier
            query: User's question
            user_id: Optional user ID for cross-session memory
            
            # RAG Control
            use_rag: Enable RAG retrieval (False = pure LLM)
            retrieval_limit: Number of chunks to retrieve
            use_rerank: Apply cross-encoder reranking
            use_mmr: Apply MMR diversification
            mmr_lambda: MMR diversity (0=diverse, 1=relevant)
            use_feedback_boost: Boost by citation signals
            compress_chunks: Apply semantic compression
            pre_retrieved_chunks: Optional pre-fetched chunks (bypass retrieval)
            
            # History Control  
            include_history: Load conversation history from DB
            history_k: Number of recent turns to include
            
            # Memory Control
            skip_learning: If True, don't save turn to memory
            include_ltm: Include long-term semantic memories
            
            # Generation Control
            stream: Whether to stream the response
            **generation_kwargs: Override temperature, max_tokens, etc.
            
        Returns:
            Dict with response, chunks, session info, and metadata
        """
        start_time = time.time()
        chunks = []
        
        # 1. RETRIEVE (respecting user's RAG settings)
        if pre_retrieved_chunks is not None:
            chunks = self._normalize_chunks(pre_retrieved_chunks)
        elif use_rag and retrieval_limit > 0:
            rag = self._get_rag()
            enriched = await rag.retrieve(
                query=query,
                limit=retrieval_limit,
                rerank=use_rerank,
                use_mmr=use_mmr,
                mmr_lambda=mmr_lambda,
                apply_feedback_boost=use_feedback_boost,
                compress=compress_chunks
            )
            chunks = self._normalize_chunks(enriched)
        
        chunk_ids = [c.get("id") for c in chunks]
        
        # 2. PREPARE (Memory builds prompt with user-controlled history)
        memory = self._get_memory()
        prompt = await memory.prepare(
            session_id=session_id,
            query=query,
            chunks=chunks,
            user_id=user_id,
            # Pass user controls to memory
            include_history=include_history,
            history_k=history_k,
            include_ltm=include_ltm
        )
        
        # 3. GENERATE
        llm = self._get_llm_client()
        
        temperature = generation_kwargs.get("temperature", self.config.temperature)
        max_tokens = generation_kwargs.get("max_tokens", self.config.max_output_tokens)
        
        # Build provider-specific kwargs for caching optimization
        provider_kwargs = dict(generation_kwargs)
        
        # Remove standard params from provider_kwargs to avoid "multiple values" errors
        # during llm.generate() call (since we pass temperature/max_tokens explicitly)
        provider_kwargs.pop("temperature", None)
        provider_kwargs.pop("max_tokens", None)
        
        if self.config.prompt_cache_key:
            provider_kwargs["prompt_cache_key"] = self.config.prompt_cache_key
        if self.config.prompt_cache_retention != "in_memory":
            provider_kwargs["prompt_cache_retention"] = self.config.prompt_cache_retention
        
        # Track response metadata for cost tracking
        response_meta = {}
        
        try:
            response = await llm.generate(
                model=self.config.model,
                user=prompt,
                system=self.config.system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                session_id=session_id,  # ADDED: Pass session_id for cache affinity
                **provider_kwargs
            )
            
            # Handle streaming
            if stream and hasattr(response, '__iter__'):
                response = "".join(list(response))
            
            # Extract metadata from LLMResponse (for cost tracking & debugging)
            if hasattr(response, 'cached'):
                response_meta = {
                    "cached": response.cached,
                    "cached_tokens": response.cached_tokens,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "reasoning_tokens": response.reasoning_tokens,
                    "stop_reason": response.stop_reason,
                    # Add detailed cache statistics if available from client
                    "cache_stats": llm.get_cache_stats(response)
                }
                    
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            response = f"I encountered an error: {str(e)}"
        
        # 4. LEARN (save turn + extract citations)
        feedback_stats = {}
        if self.config.enable_feedback and not skip_learning and not str(response).startswith("I encountered"):
            feedback_stats = await memory.learn(
                session_id=session_id,
                query=query,
                chunks=chunks,
                response=str(response),
                user_id=user_id
            )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Log with details about what was used
        rag_info = f"RAG: {len(chunks)} chunks" if use_rag else "RAG: off"
        history_info = f"history: {history_k}t" if include_history else "history: off"
        cached_info = f", cached={response_meta.get('cached', False)}" if response_meta else ""
        logger.info(f"💬 Chat: {rag_info}, {history_info}, {latency_ms}ms{cached_info}")
        
        return {
            "response": str(response),
            "session_id": session_id,
            "chunk_ids": chunk_ids,
            "chunks": chunks,
            "latency_ms": latency_ms,
            "feedback": feedback_stats,
            # Config metadata - what was actually used
            "config_used": {
                "use_rag": use_rag,
                "retrieval_limit": retrieval_limit,
                "use_rerank": use_rerank,
                "use_mmr": use_mmr,
                "mmr_lambda": mmr_lambda,
                "use_feedback_boost": use_feedback_boost,
                "compress_chunks": compress_chunks,
                "include_history": include_history,
                "history_k": history_k,
                "include_ltm": include_ltm,
                "learned": not skip_learning
            },
            # Token/cache metadata for cost tracking
            **response_meta
        }

    async def learn(
        self,
        session_id: str,
        query: str,
        chunks: List[Dict[str, Any]],
        response: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Learn from a conversation turn (save & feedback).
        
        Args:
            session_id: Conversation session
            query: User's question
            chunks: Chunks that were in context
            response: LLM's response
            user_id: Optional user ID
            
        Returns:
            Learning stats
        """
        memory = self._get_memory()
        return await memory.learn(
            session_id=session_id,
            query=query,
            chunks=chunks,
            response=response,
            user_id=user_id
        )
    
    async def feedback(
        self,
        chunk_ids: List[int],
        positive: bool,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Record explicit user feedback (👍/👎).
        
        Args:
            chunk_ids: Chunks being rated
            positive: True for 👍, False for 👎
            user_id: Optional user identifier
            session_id: Optional session for analytics
            
        Returns:
            Feedback recording stats
        """
        memory = self._get_memory()
        return await memory.feedback(
            chunk_ids=chunk_ids,
            positive=positive,
            user_id=user_id,
            session_id=session_id
        )
    
    async def get_stats(
        self,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get memory and session statistics."""
        stats = {
            "provider": self.config.provider,
            "model": self.config.model
        }
        
        memory = self._get_memory()
        if memory:
            stats["memory"] = await memory.get_stats(session_id)
        
        return stats
    
    async def forget(self, session_id: str, keep_ltm: bool = True):
        """Clear a conversation session."""
        memory = self._get_memory()
        await memory.forget(session_id, keep_ltm=keep_ltm)
    
    # =========================================================================
    # INTERNAL
    # =========================================================================
    
    def _get_llm_client(self):
        """Lazy-load LLM client."""
        if self._llm_client is None:
            from llm.client import LLMClient
            
            kwargs = {}
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            
            self._llm_client = LLMClient(self.config.provider, **kwargs)
        
        return self._llm_client
    
    def _get_rag(self):
        """Lazy-load RAG manager."""
        if self._rag is None:
            from rag import create_rag_manager
            
            # Get feedback manager from memory for boosting
            memory = self._get_memory()
            feedback_loop = memory._get_feedback() if memory else None
            
            self._rag = create_rag_manager(
                qdrant_url=self.config.qdrant_url or DATABASE_CONFIG.qdrant_url,
                collection_name=self.config.collection_name or DATABASE_CONFIG.qdrant_collection_chunks,
                pg_session=self._pg_session,
                lazy_load=True,
                feedback_loop=feedback_loop,
                # Embedding configuration
                provider=self.config.embedding_provider,
                base_url=self.config.embedding_base_url,
                dense_model=self.config.dense_model,
                sparse_model=self.config.sparse_model,
                reranker_model=self.config.reranker_model,
                reranker_provider=self.config.reranker_provider,
                reranker_base_url=self.config.reranker_base_url,
                qdrant_client=self._qdrant
            )
        
        return self._rag
    
    def _get_memory(self):
        """Lazy-load memory manager."""
        if self._memory is None:
            from latent_memory import LatentMemoryManager, LatentConfig
            
            config = LatentConfig(
                max_tokens=self.config.max_context_tokens,
                history_k=self.config.history_k,
                enable_feedback=self.config.enable_feedback
            )
            
            self._memory = LatentMemoryManager(
                system_prompt=self.config.system_prompt,
                pg_session=self._pg_session,
                qdrant_client=self._qdrant,
                config=config
            )
        
        return self._memory
    
    def _normalize_chunks(self, chunks: List[Any]) -> List[Dict[str, Any]]:
        """Normalize chunks to dict format."""
        normalized = []
        
        for chunk in chunks:
            if hasattr(chunk, "chunk_id"):
                # EnrichedChunk object
                normalized.append({
                    "id": chunk.chunk_id,
                    "text": chunk.content,
                    "source": chunk.source,
                    "score": getattr(chunk, "score", 0.5),
                    "token_count": getattr(chunk, "token_count", 0) or len(chunk.content) // 4
                })
            elif isinstance(chunk, dict):
                # Already a dict
                normalized.append({
                    "id": chunk.get("id", chunk.get("chunk_id", "")),
                    "text": chunk.get("text", chunk.get("content", "")),
                    "source": chunk.get("source", ""),
                    "score": chunk.get("score", 0.5),
                    "token_count": chunk.get("token_count", len(str(chunk.get("text", ""))) // 4)
                })
            else:
                logger.warning(f"Unknown chunk type: {type(chunk)}")
        
        return normalized

    def set_pg_session(self, session: Any):
        """Update the database session for all sub-managers."""
        self._pg_session = session
        if self._rag:
            self._rag.set_pg_session(session)
        if self._memory:
            self._memory._pg_session = session

    def set_qdrant_client(self, client: Any):
        """Update the Qdrant client for all sub-managers."""
        self._qdrant = client
        if self._rag:
            self._rag._qdrant = client
        if self._memory:
            self._memory._qdrant = client

    async def close(self):
        """Cleanup resources."""
        if self._rag:
            await self._rag.close()


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_llm_manager(
    provider: str = "openai",
    model: str = "gpt-4o-mini",
    pg_session: Optional[Any] = None,
    qdrant_client: Optional[Any] = None,
    **kwargs
) -> LLMManager:
    """
    Create an LLMManager with sensible defaults.
    
    Example:
        llm = create_llm_manager(
            provider="openai",
            model="gpt-4o",
            pg_session=db_session
        )
        
        result = await llm.chat(
            session_id="user_123",
            query="How does chunking work?"
        )
    """
    config = LLMConfig(provider=provider, model=model, **{
        k: v for k, v in kwargs.items() if hasattr(LLMConfig, k)
    })
    
    return LLMManager(
        pg_session=pg_session,
        qdrant_client=qdrant_client,
        config=config
    )
