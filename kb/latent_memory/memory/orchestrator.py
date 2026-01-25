# latent_memory/memory/orchestrator.py
"""
Memory Orchestrator - The Brain of the Memory System.

Provides a zero-config interface that automatically:
- Routes to appropriate memory tier (working/episodic/semantic)
- Handles compression when needed
- Manages cross-session context
- Optimizes for cache stability
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from .models import Turn, Memory, SessionStats, MemoryConfig
from .episodic import EpisodicMemory
from .semantic import SemanticMemory
from .compressor import MemoryCompressor
from config import get_logger

logger = get_logger("latent_memory.memory.orchestrator")

class MemoryOrchestrator:
    """
    Zero-config memory management.
    
    Users just call `remember()` and `recall()`.
    System handles compression, search, and cross-session context.
    
    Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    MemoryOrchestrator                        │
    │                                                              │
    │  User API: remember() / recall() / forget()                  │
    │                         │                                    │
    │           ┌─────────────┼─────────────┐                      │
    │           ▼             ▼             ▼                      │
    │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐             │
    │  │   Working   │ │  Episodic   │ │  Semantic   │             │
    │  │  (current)  │ │  (recent)   │ │   (LTM)     │             │
    │  │  in-memory  │ │  Postgres   │ │  Qdrant     │             │
    │  └─────────────┘ └─────────────┘ └─────────────┘             │
    │                         │                                    │
    │                         ▼                                    │
    │                  ┌─────────────┐                             │
    │                  │ Compressor  │                             │
    │                  │  (LLM)      │                             │
    │                  └─────────────┘                             │
    └─────────────────────────────────────────────────────────────┘
    """
    
    def __init__(
        self,
        pg_session=None,
        qdrant_client=None,
        llm_client=None,
        embedder=None,
        config: Optional[MemoryConfig] = None
    ):
        """
        Initialize the memory orchestrator.
        
        Args:
            pg_session: SQLAlchemy async session for persistence
            qdrant_client: Qdrant client for vector storage
            llm_client: LLM client for compression (optional)
            embedder: Embedding model for semantic search
            config: Memory configuration (uses smart defaults if not provided)
        """
        self.config = config or MemoryConfig()
        
        # Initialize sub-components
        self.episodic = EpisodicMemory(
            pg_session=pg_session,
            config=self.config,
            embedder=embedder
        )
        
        self.semantic = SemanticMemory(
            pg_session=pg_session,
            qdrant_client=qdrant_client,
            config=self.config,
            embedder=embedder
        )
        
        self.compressor = MemoryCompressor(
            llm_client=llm_client,
            config=self.config
        )
        
        # Working memory (current turn, in-memory only)
        self._working: Dict[str, List[Turn]] = {}
        
        # Background tasks
        self._compression_tasks: Dict[str, asyncio.Task] = {}
    
    # =========================================================================
    # SIMPLE USER API
    # =========================================================================
    
    async def remember(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: Optional[str] = None,
        chunk_ids: Optional[List[int]] = None,
        citations: Optional[List[int]] = None,
        **meta
    ) -> Turn:
        """
        Remember a conversation turn.
        
        This is THE main entry point. Just call this after each turn.
        System handles everything else (storage, importance, compression).
        
        Args:
            session_id: Session identifier
            role: "user" or "assistant"
            content: Turn content
            user_id: Optional user ID for cross-session memory
            chunk_ids: Chunks that were in context
            citations: Chunks that were cited
            **meta: Additional metadata
            
        Returns:
            The stored Turn with computed importance
        """
        # Add to episodic memory
        turn = await self.episodic.add_turn(
            session_id=session_id,
            role=role,
            content=content,
            chunk_ids=chunk_ids,
            citations=citations,
            meta={"user_id": user_id, **meta}
        )
        
        # Add to working memory
        if session_id not in self._working:
            self._working[session_id] = []
        self._working[session_id].append(turn)
        
        # Trim working memory (keep last few turns only)
        if len(self._working[session_id]) > 5:
            self._working[session_id] = self._working[session_id][-5:]
        
        # Schedule background compression if needed
        if self.config.async_compression:
            await self._maybe_schedule_compression(session_id, user_id)
        
        return turn
    
    async def recall(
        self,
        session_id: str,
        query: Optional[str] = None,
        k: Optional[int] = None,
        include_ltm: bool = True,
        user_id: Optional[str] = None
    ) -> List[Turn]:
        """
        Recall relevant conversation context.
        
        Args:
            session_id: Session to recall from
            query: Optional query for semantic filtering
            k: Number of turns to return
            include_ltm: Whether to include long-term memories
            user_id: For cross-session context
            
        Returns:
            List of relevant turns, oldest first (for cache stability)
        """
        k = k or self.config.episodic_k
        
        # Get recent episodic turns
        recent_turns = await self.episodic.get_recent(session_id, k=k)
        
        # If query provided, also search for relevant turns
        if query:
            relevant = await self.episodic.search_relevant(session_id, query, k=3)
            
            # Merge, avoiding duplicates
            seen_ids = {t.id for t in recent_turns}
            for turn in relevant:
                if turn.id not in seen_ids:
                    recent_turns.append(turn)
        
        # Include long-term memories if enabled
        if include_ltm and self.config.enable_ltm and user_id:
            ltm_context = await self._get_ltm_context(user_id, query)
            if ltm_context:
                # Prepend LTM as system context
                ltm_summary = "\n".join([m.summary for m in ltm_context])
                ltm_turn = Turn(
                    role="system",
                    content=f"[Previous context]: {ltm_summary}",
                    importance=0.6
                )
                recent_turns.insert(0, ltm_turn)
        
        # Sort by time for cache stability
        recent_turns.sort(key=lambda t: t.created_at or datetime.min)
        
        return recent_turns
    
    async def forget(self, session_id: str, keep_ltm: bool = True):
        """
        Clear session memory.
        
        Args:
            session_id: Session to clear
            keep_ltm: Whether to preserve compressed long-term memories
        """
        # Clear working memory
        if session_id in self._working:
            del self._working[session_id]
        
        # Clear episodic
        await self.episodic.clear_session(session_id)
        
        logger.info(f"🗑️ Forgot session: {session_id} (LTM preserved: {keep_ltm})")
    
    async def feedback(
        self,
        turn_id: int,
        positive: bool
    ):
        """
        Record user feedback for a turn.
        
        Args:
            turn_id: Turn to rate
            positive: True for 👍, False for 👎
        """
        score = 1.0 if positive else -1.0
        await self.episodic.update_feedback(turn_id, score)
    
    # =========================================================================
    # CONTEXT BUILDING
    # =========================================================================
    
    async def build_context(
        self,
        session_id: str,
        query: str,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Build optimized context for LLM prompt.
        
        Returns turns in the format expected by LLM APIs:
        [{"role": "user", "content": "..."}, ...]
        """
        turns = await self.recall(
            session_id=session_id,
            query=query,
            user_id=user_id,
            include_ltm=True
        )
        
        return [
            {"role": t.role, "content": t.content}
            for t in turns
        ]
    
    # =========================================================================
    # COMPRESSION
    # =========================================================================
    
    async def _maybe_schedule_compression(
        self,
        session_id: str,
        user_id: Optional[str]
    ):
        """Schedule compression if session exceeds threshold."""
        # Check if already scheduled
        if session_id in self._compression_tasks:
            task = self._compression_tasks[session_id]
            if not task.done():
                return
        
        # Get turn count
        stats = await self.episodic.get_session_stats(session_id)
        
        if stats.total_turns > self.config.compress_threshold:
            # Schedule with delay
            task = asyncio.create_task(
                self._delayed_compression(session_id, user_id)
            )
            self._compression_tasks[session_id] = task
    
    async def _delayed_compression(
        self,
        session_id: str,
        user_id: Optional[str]
    ):
        """Run compression after delay."""
        await asyncio.sleep(self.config.compression_delay_seconds)
        await self.compress_session(session_id, user_id)
    
    async def compress_session(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        keep_recent: int = 5
    ) -> Optional[Memory]:
        """
        Compress old turns into semantic memory.
        
        Args:
            session_id: Session to compress
            user_id: For cross-session LTM
            keep_recent: Number of recent turns to keep full
            
        Returns:
            Created memory, or None if nothing to compress
        """
        # Get turns eligible for compression
        turns = await self.episodic.get_turns_for_compression(
            session_id, keep_recent
        )
        
        if len(turns) < self.config.compress_batch_size:
            return None
        
        # Compress
        compressed_turns = turns[:self.config.compress_batch_size]
        memory = await self.compressor.compress(
            turns=compressed_turns,
            session_id=session_id,
            user_id=user_id
        )
        
        # Store in semantic memory
        await self.semantic.store(memory)
        
        # Delete compressed turns from episodic memory
        turn_ids = [t.id for t in compressed_turns if t.id]
        if turn_ids:
            deleted_count = await self.episodic.delete_turns(turn_ids)
            logger.info(f"🗜️ Compressed {len(compressed_turns)} turns -> 1 memory, deleted {deleted_count} from episodic")
        
        return memory
    
    async def _get_ltm_context(
        self,
        user_id: str,
        query: Optional[str]
    ) -> List[Memory]:
        """Get relevant long-term memories for user."""
        if not query:
            return await self.semantic.get_user_context(user_id, k=2)
        
        return await self.semantic.search(
            query=query,
            user_id=user_id,
            k=self.config.semantic_search_k
        )
    
    # =========================================================================
    # STATS & MONITORING
    # =========================================================================
    
    async def get_stats(self, session_id: str) -> SessionStats:
        """Get comprehensive session statistics."""
        return await self.episodic.get_session_stats(session_id)
    
    def get_working_memory(self, session_id: str) -> List[Turn]:
        """Get current working memory (volatile)."""
        return self._working.get(session_id, [])
    
    async def estimate_compression_savings(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """Estimate potential savings from compression."""
        turns = await self.episodic.get_turns_for_compression(session_id)
        return self.compressor.estimate_compression(turns)

# =============================================================================
# CONVENIENCE FACTORY
# =============================================================================

def create_orchestrator(
    pg_session=None,
    qdrant_client=None,
    llm_client=None,
    embedder=None,
    **config_kwargs
) -> MemoryOrchestrator:
    """
    Factory function to create a MemoryOrchestrator.
    
    Example:
        memory = create_orchestrator(pg_session=session)
        await memory.remember(session_id, "user", "Hello!")
    """
    config = MemoryConfig(**config_kwargs) if config_kwargs else None
    
    return MemoryOrchestrator(
        pg_session=pg_session,
        qdrant_client=qdrant_client,
        llm_client=llm_client,
        embedder=embedder,
        config=config
    )
