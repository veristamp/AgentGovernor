# services/chat/service.py
"""
Chat Service - Orchestrator.

Thin facade that coordinates persistence, ResponseFormatter, and LLMManager.
Provides multi-format response output (OpenAI, Anthropic, Gemini, raw).
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from llm import create_llm_manager, LLMManager
from services.chat.models import ChatConfig, ChatContext, SessionState
from services.chat.persistence import PostgresSessionStore
from services.chat.response_formatter import ResponseFormatter
from config import get_logger

logger = get_logger("ChatService")

class ChatService:
    """
    Refactored Chat completion service.
    Coordinates specialized components for a cleaner, maintainable architecture.
    """
    
    def __init__(self, **config_kwargs):
        """
        Initialize chat service with multi-layered architecture.
        """
        self.config = ChatConfig(**config_kwargs)
        self.formatter = ResponseFormatter(f"{self.config.provider}/{self.config.model}")
        
        # Shared Qdrant client for connection pooling across requests
        from qdrant_client import AsyncQdrantClient
        from config import DATABASE_CONFIG
        self._qdrant = AsyncQdrantClient(url=DATABASE_CONFIG.qdrant_url)
        
        logger.info(f"🚀 ChatService (v5) initialized: {self.config.provider}/{self.config.model}")

    @property
    def model_name(self) -> str:
        """Get the full model identifier."""
        return f"{self.config.provider}/{self.config.model}"

    async def complete(
        self,
        session: AsyncSession,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        # Session control
        session_id: Optional[str] = None,
        branch_from: Optional[str] = None,
        # History control
        include_history: bool = True,
        history_k: int = 10,
        # Memory control
        learn: bool = True,
        include_ltm: bool = True,
        # RAG control
        use_rag: bool = True,
        retrieval_limit: int = 5,
        use_rerank: bool = True,
        use_mmr: bool = True,
        mmr_lambda: float = 0.7,
        use_feedback_boost: bool = True,
        compress_chunks: bool = False,
        # Response format
        response_format: str = "openai",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Chat completion with full user control.
        
        Args:
            session: Database session
            messages: Conversation messages
            temperature: Sampling temperature
            max_tokens: Max response tokens
            session_id: None = ephemeral (no DB state), otherwise persisted
            branch_from: Fork history from this session
            include_history: Load conversation history from DB
            history_k: Number of history turns to include
            learn: Save this turn to memory
            include_ltm: Include long-term semantic memories
            use_rag: Enable RAG retrieval
            retrieval_limit: Number of chunks to retrieve
            response_format: Output format (openai, anthropic, gemini, raw)
            **kwargs: Provider-specific parameters
            
        Returns:
            Response in specified format with metadata
        """
        # 1. EPHEMERAL MODE: No session = stateless, no DB operations
        is_ephemeral = session_id is None
        
        # 2. Create LLMManager with current session
        llm = self._get_llm_manager(session)
        
        # 3. Extract user query from messages
        user_query = self._extract_user_query(messages)
        if not user_query:
            return self.formatter.format_empty(ChatContext(session_id=session_id or "ephemeral", user_query=""))
        
        try:
            # 4. BRANCHING: Copy history from source session if specified
            if branch_from and session_id and not is_ephemeral:
                await self._branch_session(session, branch_from, session_id)
            
            # 5. Call LLMManager with ALL user controls
            result = await llm.chat(
                session_id=session_id or f"ephemeral_{id(messages)}",  # Temp ID for internal use
                query=user_query,
                # RAG control
                use_rag=use_rag,
                retrieval_limit=retrieval_limit if use_rag else 0,
                use_rerank=use_rerank,
                use_mmr=use_mmr,
                mmr_lambda=mmr_lambda,
                use_feedback_boost=use_feedback_boost,
                compress_chunks=compress_chunks,
                # History control
                include_history=include_history and not is_ephemeral,
                history_k=history_k,
                # Memory control
                skip_learning=not learn or is_ephemeral,
                include_ltm=include_ltm and not is_ephemeral,
                # Generation params
                temperature=temperature or 0.7,
                max_tokens=max_tokens or 2048,
                **kwargs
            )
            
            # 6. Build response context
            context = ChatContext(
                session_id=session_id or "ephemeral",
                user_query=user_query,
                is_new_session=is_ephemeral
            )
            
            # 7. Load or create session state (for non-ephemeral)
            state = None
            if not is_ephemeral:
                store = PostgresSessionStore(session)
                state = await store.get_session_state(session_id)
                
            if state is None:
                state = SessionState(
                    session_id=session_id or "ephemeral",
                    request_count=0,
                    history_k=history_k
                )
            
            # Update state with results
            state.request_count += 1
            state.history_k = history_k
            state.enriched_chunks = result.get("chunks", [])
            
            # Accumulate cache stats
            cache_stats = result.get("cache_stats", {})
            if cache_stats.get("cached_tokens", 0) > 0:
                state.cache_hits += 1
                state.total_cached_tokens += cache_stats.get("cached_tokens", 0)
            
            # 8. Persist session state only if not ephemeral
            if not is_ephemeral:
                await store.save_session_state(session_id, state)
            
            # 9. Format response in requested format
            return self.formatter.format(result, context, state, response_format=response_format)

        except Exception as e:
            logger.exception("Chat completion failed")
            context = ChatContext(session_id=session_id or "ephemeral", user_query=user_query)
            return self.formatter.format_error(str(e), context, response_format=response_format)

    async def record_feedback(
        self,
        session: AsyncSession,
        chunk_ids: List[int],
        positive: bool,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Record user feedback with full analytics tracking."""
        llm = self._get_llm_manager(session)
        return await llm.feedback(
            chunk_ids=chunk_ids,
            positive=positive,
            user_id=user_id,
            session_id=session_id
        )

    async def get_session_stats(
        self, 
        session: AsyncSession, 
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get session state summary."""
        session_manager = SessionManager(session)
        state = await session_manager.load_state(session_id)
        return state.dict() if state else None

    async def clear_session(
        self, 
        session: AsyncSession, 
        session_id: str
    ) -> bool:
        """Clear session state from both store and memory."""
        session_manager = SessionManager(session)
        await session_manager.clear(session_id)
        
        # Also clear from LLM memory tiers
        llm = self._get_llm_manager(session)
        await llm.forget(session_id)
        return True

    async def _branch_session(
        self, 
        db_session: AsyncSession, 
        source_session_id: str, 
        target_session_id: str
    ):
        """
        Fork conversation history from source to target session.
        
        This enables branching: user can explore alternative paths
        without losing the original conversation.
        """
        from sqlalchemy import select, insert
        from db.schema import ConversationLog
        
        # Copy all turns from source to target with new session_id
        stmt = select(ConversationLog).where(
            ConversationLog.session_id == source_session_id
        ).order_by(ConversationLog.created_at)
        
        result = await db_session.execute(stmt)
        source_turns = result.scalars().all()
        
        if not source_turns:
            logger.warning(f"No history found in source session {source_session_id} for branching")
            return
        
        for turn in source_turns:
            # Create new turn in target session
            new_turn = ConversationLog(
                session_id=target_session_id,
                role=turn.role,
                content=turn.content,
                token_count=turn.token_count,
                model_used=turn.model_used,
                meta={
                    **(turn.meta or {}),
                    "branched_from": source_session_id,
                    "original_turn_id": turn.id
                }
            )
            db_session.add(new_turn)
        
        logger.info(f"🌿 Branched {len(source_turns)} turns from {source_session_id} to {target_session_id}")

    async def close(self):
        """Cleanup shared resources."""
        await self._qdrant.close()

    def _get_llm_manager(self, pg_session: AsyncSession) -> LLMManager:
        """Helper to create LLMManager with current config and shared client."""
        return LLMManager(
            pg_session=pg_session,
            qdrant_client=self._qdrant,
            config=self.config.to_llm_config()
        )

    def _extract_user_query(self, messages: List[Dict[str, str]]) -> str:
        """Extract the last user message."""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return msg.get("content", "")
        return ""


# =============================================================================
# FACTORY
# =============================================================================

_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    """Get or create the singleton ChatService instance."""
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service


def set_chat_service(service: ChatService):
    """Set the ChatService instance (for testing/DI)."""
    global _chat_service
    _chat_service = service
