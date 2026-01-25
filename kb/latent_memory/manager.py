# latent_memory/manager.py
"""
Latent Memory Manager - Unified AI Memory Interface.

A single, clean API that handles everything:
- Memory: Remember conversations, recall relevant context
- Context: Build cache-optimal prompts automatically
- Feedback: Learn from LLM citations and user reactions

Philosophy:
- User provides: system_prompt, session_id, chunks, query
- System handles: token limits, eviction, compression, caching, feedback

Usage:
    from latent_memory import LatentMemoryManager
    
    # Initialize once
    llm = LatentMemoryManager(
        system_prompt="You are a helpful assistant.",
        pg_session=db,
        qdrant_client=qdrant
    )
    
    # Build prompt (does everything automatically)
    prompt = await llm.prepare(
        session_id="user_123",
        query="How does chunking work?",
        chunks=retrieved_chunks
    )
    
    # After LLM response
    await llm.learn(
        session_id="user_123",
        query="How does chunking work?",
        chunks=retrieved_chunks,
        response="Based on [cite:1]..."
    )
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from config import get_logger

logger = get_logger("LatentMemory")


@dataclass
class LatentConfig:
    """
    Configuration with smart defaults.
    
    Users typically don't need to change any of these.
    """
    # Context limits
    max_tokens: int = 128000
    reserve_for_output: int = 4000
    
    # History
    history_k: int = 10
    
    # Formatting (internal - users shouldn't care)
    context_header: str = "## Context\n\n"
    query_header: str = "\n---\n\n## Your Question\n\n"
    history_header: str = "\n---\n\n## Conversation History\n\n"
    
    # Features
    enable_feedback: bool = True
    enable_compression: bool = True
    enable_ltm: bool = True  # Long-term memory across sessions


class LatentMemoryManager:
    """
    Unified AI Memory Manager.
    
    Single interface for:
    - Conversation memory (short-term + long-term)
    - Context assembly (cache-optimal)
    - Feedback learning (automatic + user-confirmed)
    
    Architecture (internal - users don't need to know):
    ┌──────────────────────────────────────────────────────────────┐
    │                   LatentMemoryManager                         │
    │                                                               │
    │  prepare()      learn()       feedback()       forget()       │
    │      │             │              │               │           │
    │      └─────────────┼──────────────┼───────────────┘           │
    │                    ▼                                          │
    │  ┌─────────────────────────────────────────────────────────┐  │
    │  │              Internal Components (Hidden)               │  │
    │  │  MemoryOrchestrator │ FeedbackManager │ PromptBuilder   │  │
    │  └─────────────────────────────────────────────────────────┘  │
    └──────────────────────────────────────────────────────────────┘
    """
    
    def __init__(
        self,
        system_prompt: str = "",
        pg_session: Optional[Any] = None,
        qdrant_client: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        embedder: Optional[Any] = None,
        config: Optional[LatentConfig] = None
    ):
        """
        Initialize the memory manager.
        
        Args:
            system_prompt: System instructions for the LLM
            pg_session: Database session/factory for persistence
            qdrant_client: Vector store for semantic operations
            llm_client: Optional LLM for compression
            embedder: Optional embedder for semantic search
            config: Optional configuration (uses smart defaults)
        """
        self.system_prompt = system_prompt
        self.config = config or LatentConfig()
        
        # Store clients for lazy initialization
        self._pg_session = pg_session
        self._qdrant = qdrant_client
        self._llm = llm_client
        self._embedder = embedder
        
        # Lazy-loaded internal components
        self._memory = None
        self._feedback = None
        self._prompt_builder = None
        self._rotator = None
    
    # =========================================================================
    # MAIN PUBLIC API (4 methods - that's it!)
    # =========================================================================
    
    async def prepare(
        self,
        session_id: str,
        query: str,
        chunks: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        # User controls
        include_history: bool = True,
        history_k: int = 10,
        include_ltm: bool = True
    ) -> str:
        """
        Prepare a complete prompt for the LLM with USER CONTROL.
        
        Args:
            session_id: Conversation session identifier
            query: Current user question
            chunks: Retrieved context chunks
            user_id: Optional user ID for cross-session memory
            include_history: Whether to load conversation history
            history_k: Number of history turns to include
            include_ltm: Whether to include long-term memories
            
        Returns:
            Complete prompt string ready for LLM
        """
        # 1. Get conversation history (respecting user controls)
        history = []
        if include_history and history_k > 0:
            history = await self._recall_history(
                session_id, 
                query, 
                user_id,
                k=history_k,
                include_ltm=include_ltm
            )
        
        # 2. Apply feedback boost to chunks
        if self._get_feedback():
            chunks = self._get_feedback().boost_results(query, chunks)
        
        # 3. Build the prompt
        metadata = {
            "stable": {"user_id": user_id} if user_id else {},
            "dynamic": {"session_id": session_id}
        }
        
        prompt = self._build_prompt(
            chunks=chunks,
            query=query,
            history=history,
            metadata=metadata
        )
        
        history_info = f"{len(history)} turns" if include_history else "disabled"
        logger.info(
            f"📝 Prompt: session={session_id[:8]}..., history={history_info}, chunks={len(chunks)}"
        )
        
        return prompt
    
    async def learn(
        self,
        session_id: str,
        query: str,
        chunks: List[Dict[str, Any]],
        response: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Learn from an LLM response.
        
        Call this after every successful LLM response. It:
        1. Saves the turn to memory
        2. Extracts citations and updates feedback
        3. Triggers background compression if needed
        
        Args:
            session_id: Conversation session
            query: User's question
            chunks: Chunks that were in context
            response: LLM's response
            user_id: Optional user for cross-session learning
            
        Returns:
            Learning statistics
        """
        stats = {"session_id": session_id, "learned": True}
        
        # 1. Remember the conversation turn
        memory = self._get_memory()
        if memory:
            chunk_ids = [c.get("id") for c in chunks]
            
            # Remember user turn
            await memory.remember(
                session_id=session_id,
                role="user",
                content=query,
                user_id=user_id,
                chunk_ids=chunk_ids
            )
            
            # Remember assistant turn with citations
            from .feedback import extract_citations
            citations = list(extract_citations(response, chunks))
            
            await memory.remember(
                session_id=session_id,
                role="assistant",
                content=response,
                user_id=user_id,
                citations=citations
            )
            
            stats["turns_saved"] = 2
        
        # 2. Process feedback (soft signals from citations)
        feedback = self._get_feedback()
        if feedback and self.config.enable_feedback:
            feedback_stats = await feedback.process_turn(
                query=query,
                retrieved_chunks=chunks,
                llm_response=response
            )
            stats["feedback"] = feedback_stats
        
        logger.info(f"🧠 Learned from turn in session {session_id[:8]}...")
        
        return stats
    
    async def feedback(
        self,
        chunk_ids: List[int],
        positive: bool,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Record explicit user feedback.
        
        Call when user clicks 👍 or 👎 on a response.
        
        Args:
            chunk_ids: Chunks being rated
            positive: True for 👍, False for 👎
            user_id: Optional user identifier
            session_id: Optional session for analytics tracking
            
        Returns:
            Feedback recording stats
        """
        fb = self._get_feedback()
        if not fb:
            return {"recorded": False, "reason": "feedback not enabled"}
        
        result = await fb.confirm_feedback(
            chunk_ids=chunk_ids,
            positive=positive,
            user_id=user_id,
            session_id=session_id
        )
        
        return result
    
    async def forget(
        self,
        session_id: str,
        keep_ltm: bool = True
    ):
        """
        Forget a conversation session.
        
        Args:
            session_id: Session to forget
            keep_ltm: Keep compressed long-term memories (default True)
        """
        memory = self._get_memory()
        if memory:
            await memory.forget(session_id, keep_ltm=keep_ltm)
        
        logger.info(f"🗑️ Forgot session {session_id[:8]}... (LTM kept: {keep_ltm})")
    
    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================
    
    async def get_stats(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Get memory and feedback statistics."""
        stats = {}
        
        memory = self._get_memory()
        if memory and session_id:
            stats["memory"] = await memory.get_stats(session_id)
        
        feedback = self._get_feedback()
        if feedback:
            stats["feedback"] = feedback.get_stats()
        
        return stats
    
    def invalidate(self):
        """Invalidate all caches (use after document changes)."""
        if self._prompt_builder:
            self._prompt_builder.invalidate()
        logger.info("🔄 Cache invalidated")
    
    # =========================================================================
    # INTERNAL (Hidden from users)
    # =========================================================================
    
    def _get_memory(self):
        """Lazy-load memory orchestrator."""
        if self._memory is None and self._pg_session:
            from .memory import MemoryOrchestrator
            self._memory = MemoryOrchestrator(
                pg_session=self._pg_session,
                qdrant_client=self._qdrant,
                llm_client=self._llm,
                embedder=self._embedder
            )
        return self._memory
    
    def _get_feedback(self):
        """Lazy-load feedback manager."""
        if self._feedback is None and self.config.enable_feedback:
            from .feedback import FeedbackManager
            self._feedback = FeedbackManager(
                qdrant_client=self._qdrant,
                pg_session=self._pg_session
            )
        return self._feedback
    
    def _get_prompt_builder(self):
        """Lazy-load prompt builder (KVCacheManager)."""
        if self._prompt_builder is None:
            from .kv_cache import KVCacheManager
            self._prompt_builder = KVCacheManager(system_prompt=self.system_prompt)
        return self._prompt_builder
    
    def _get_rotator(self):
        """Lazy-load context rotator for token budgeting."""
        if self._rotator is None:
            from .context_rotator import ContextRotator
            self._rotator = ContextRotator(
                max_tokens=self.config.max_tokens,
                reserve_for_output=self.config.reserve_for_output,
                system_prompt_tokens=len(self.system_prompt) // 4
            )
        return self._rotator
    
    async def _recall_history(
        self,
        session_id: str,
        query: str,
        user_id: Optional[str],
        k: int = 10,
        include_ltm: bool = True
    ) -> List[Dict[str, Any]]:
        """Get relevant conversation history with user controls."""
        memory = self._get_memory()
        if not memory:
            return []
        
        turns = await memory.recall(
            session_id=session_id,
            query=query,
            k=k,
            include_ltm=include_ltm,
            user_id=user_id
        )
        
        return [{"role": t.role, "content": t.content} for t in turns]
    
    def _build_prompt(
        self,
        chunks: List[Dict[str, Any]],
        query: str,
        history: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build cache-optimal prompt with token budgeting."""
        # Normalize chunks
        normalized = []
        for chunk in chunks:
            normalized.append({
                "id": chunk.get("id", chunk.get("chunk_id", "")),
                "text": chunk.get("text", chunk.get("content", chunk.get("original_text", ""))),
                "source": chunk.get("source", ""),
                "score": chunk.get("score", chunk.get("relevance", 0.5)),
                "token_count": chunk.get("token_count", len(str(chunk.get("text", ""))) // 4)
            })
        
        # Apply token budgeting - evict low-score chunks if needed
        rotator = self._get_rotator()
        history_tokens = sum(len(h.get("content", "")) // 4 for h in history)
        query_tokens = len(query) // 4
        
        fitted_chunks, budget = rotator.fit_chunks(
            chunks=normalized,
            history_tokens=history_tokens,
            query_tokens=query_tokens
        )
        
        if len(fitted_chunks) < len(normalized):
            logger.info(
                f"📉 Evicted {len(normalized) - len(fitted_chunks)} chunks "
                f"(budget: {budget.utilization})"
            )
        
        # Build prompt with cache-optimal ordering
        builder = self._get_prompt_builder()
        return builder.build(
            chunks=fitted_chunks,
            query=query,
            history=history,
            metadata=metadata
        )


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_memory_manager(
    system_prompt: str = "",
    pg_session: Optional[Any] = None,
    qdrant_client: Optional[Any] = None,
    **kwargs
) -> LatentMemoryManager:
    """
    Create a LatentMemoryManager with sensible defaults.
    
    Example:
        llm = create_memory_manager(
            system_prompt="You are a helpful assistant.",
            pg_session=db_session
        )
        
        prompt = await llm.prepare(session_id, query, chunks)
        # ... call LLM ...
        await llm.learn(session_id, query, chunks, response)
    """
    config = LatentConfig(**{
        k: v for k, v in kwargs.items() 
        if hasattr(LatentConfig, k)
    })
    
    return LatentMemoryManager(
        system_prompt=system_prompt,
        pg_session=pg_session,
        qdrant_client=qdrant_client,
        config=config,
        **{k: v for k, v in kwargs.items() if k in ['llm_client', 'embedder']}
    )
