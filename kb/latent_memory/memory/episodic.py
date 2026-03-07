# latent_memory/memory/episodic.py
"""
Episodic Memory - Tier 1: Recent Full-Text Turns.

This is the upgraded version of history.py with:
- Rich metadata storage (chunk_ids, citations, feedback)
- Importance scoring for smart eviction
- Semantic search capability
- Branching support
"""

import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import select, delete, desc, func, update

from .models import Turn, SessionStats, MemoryConfig, ImportanceLevel
from config import get_logger

logger = get_logger("latent_memory.memory.episodic")

class EpisodicMemory:
    """
    Manages recent conversation turns with full text.
    
    Features:
    - Store turns with rich metadata
    - Importance-based retrieval and eviction
    - Semantic search (when embedder provided)
    - Session analytics
    """
    
    def __init__(
        self,
        pg_session,
        config: Optional[MemoryConfig] = None,
        embedder=None  # Optional: for semantic search
    ):
        """
        Initialize episodic memory.
        
        Args:
            pg_session: SQLAlchemy async session or session factory
            config: Memory configuration (uses defaults if not provided)
            embedder: Optional embedder for semantic search
        """
        self.pg_session = pg_session
        self.config = config or MemoryConfig()
        self.embedder = embedder
        self._importance_cache: Dict[int, float] = {}
    
    # =========================================================================
    # CORE OPERATIONS
    # =========================================================================
    
    async def add_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        token_count: int = 0,
        model_used: Optional[str] = None,
        chunk_ids: Optional[List[int]] = None,
        citations: Optional[List[int]] = None,
        feedback_score: Optional[float] = None,
        parent_turn_id: Optional[int] = None,
        branch_label: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None
    ) -> Turn:
        """
        Add a conversation turn with rich metadata.
        
        Returns:
            The created Turn object with computed importance.
        """
        # Create turn object
        turn = Turn(
            session_id=session_id,
            role=role,
            content=content,
            token_count=token_count or self._estimate_tokens(content),
            model_used=model_used,
            chunk_ids=chunk_ids or [],
            citations=citations or [],
            feedback_score=feedback_score,
            parent_turn_id=parent_turn_id,
            branch_label=branch_label,
            meta=meta or {},
            created_at=datetime.utcnow()
        )
        
        # Compute importance
        turn.importance, turn.importance_reason = self._compute_importance(turn)
        
        # Persist to database
        turn.id = await self._persist_turn(turn)
        
        logger.debug(
            f"📝 Added turn {turn.id}: {role} ({turn.importance:.2f} importance)"
        )
        
        return turn
    
    async def get_recent(
        self,
        session_id: str,
        k: Optional[int] = None,
        min_importance: float = 0.0
    ) -> List[Turn]:
        """
        Get recent turns, optionally filtered by importance.
        
        Args:
            session_id: Session to query
            k: Max turns to return (defaults to config.episodic_k)
            min_importance: Only return turns above this importance
            
        Returns:
            List of turns, oldest first (for cache stability)
        """
        k = k or self.config.episodic_k
        
        async with self._get_session() as session:
            from db.schema import ConversationLog
            
            # Build query
            stmt = (
                select(ConversationLog)
                .where(ConversationLog.session_id == session_id)
                .order_by(desc(ConversationLog.created_at))
                .limit(k * 2)  # Get more, then filter by importance
            )
            
            result = await session.execute(stmt)
            rows = result.scalars().all()
            
            # Convert to Turn objects
            turns = [self._row_to_turn(row) for row in rows]
            
            # Filter by importance
            if min_importance > 0:
                turns = [t for t in turns if t.importance >= min_importance]
            
            # Take top K and reverse for chronological order
            turns = turns[:k]
            turns.reverse()
            
            return turns
    
    async def search_relevant(
        self,
        session_id: str,
        query: str,
        k: int = 5
    ) -> List[Turn]:
        """
        Search for turns semantically relevant to query.
        
        Requires embedder to be configured.
        Falls back to keyword search if no embedder.
        """
        if self.embedder:
            return await self._semantic_search(session_id, query, k)
        else:
            return await self._keyword_search(session_id, query, k)
    
    async def update_feedback(
        self,
        turn_id: int,
        feedback_score: float
    ):
        """
        Update feedback score for a turn.
        
        Args:
            turn_id: Turn to update
            feedback_score: -1.0 (👎) to 1.0 (👍)
        """
        async with self._get_session() as session:
            from db.schema import ConversationLog
            
            # Update the turn
            stmt = (
                update(ConversationLog)
                .where(ConversationLog.id == turn_id)
                .values(
                    meta=func.jsonb_set(
                        ConversationLog.meta,
                        ['feedback_score'],
                        str(feedback_score)
                    )
                )
            )
            await session.execute(stmt)
            await session.commit()
            
            logger.info(f"👍 Updated feedback for turn {turn_id}: {feedback_score}")
    
    async def get_session_stats(self, session_id: str) -> SessionStats:
        """Get comprehensive stats for a session."""
        async with self._get_session() as session:
            from db.schema import ConversationLog
            
            # Get all turns
            stmt = (
                select(ConversationLog)
                .where(ConversationLog.session_id == session_id)
                .order_by(ConversationLog.created_at)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            
            if not rows:
                return SessionStats(session_id=session_id)
            
            turns = [self._row_to_turn(row) for row in rows]
            
            # Calculate stats
            user_turns = [t for t in turns if t.role == "user"]
            assistant_turns = [t for t in turns if t.role == "assistant"]
            
            positive_feedback = [
                t for t in turns 
                if t.feedback_score is not None and t.feedback_score > 0
            ]
            total_with_feedback = [
                t for t in turns if t.feedback_score is not None
            ]
            
            return SessionStats(
                session_id=session_id,
                total_turns=len(turns),
                user_turns=len(user_turns),
                assistant_turns=len(assistant_turns),
                total_tokens=sum(t.token_count for t in turns),
                active_turns=len(turns),  # All episodic turns are "active"
                avg_importance=sum(t.importance for t in turns) / len(turns),
                positive_feedback_rate=(
                    len(positive_feedback) / len(total_with_feedback)
                    if total_with_feedback else 0.0
                ),
                first_turn_at=turns[0].created_at,
                last_turn_at=turns[-1].created_at
            )
    
    async def clear_session(self, session_id: str):
        """Delete all turns for a session."""
        async with self._get_session() as session:
            from db.schema import ConversationLog
            
            stmt = delete(ConversationLog).where(
                ConversationLog.session_id == session_id
            )
            await session.execute(stmt)
            await session.commit()
            
            logger.info(f"🗑️ Cleared session: {session_id}")
    
    async def get_turns_for_compression(
        self,
        session_id: str,
        keep_recent: int = 5
    ) -> List[Turn]:
        """
        Get turns that should be compressed.
        
        Returns turns that are:
        - Not in the most recent `keep_recent`
        - Below the importance threshold for preservation
        """
        all_turns = await self.get_recent(session_id, k=100)
        
        if len(all_turns) <= keep_recent:
            return []
        
        # The oldest turns, excluding the most recent
        candidates = all_turns[:-keep_recent]
        
        # Filter out high-importance turns that shouldn't be compressed
        compressible = [
            t for t in candidates
            if t.importance < self.config.importance_code_change
        ]
        
        return compressible
    
    async def delete_turns(self, turn_ids: List[int]) -> int:
        """
        Delete specific turns by ID.
        
        Used after compression to remove turns that have been
        compressed into semantic memory.
        
        Args:
            turn_ids: List of turn IDs to delete
            
        Returns:
            Number of turns deleted
        """
        if not turn_ids:
            return 0
        
        async with self._get_session() as session:
            from db.schema import ConversationLog
            
            stmt = delete(ConversationLog).where(
                ConversationLog.id.in_(turn_ids)
            )
            result = await session.execute(stmt)
            await session.commit()
            
            deleted_count = result.rowcount or 0
            logger.info(f"🗑️ Deleted {deleted_count} compressed turns")
            
            return deleted_count
    
    # =========================================================================
    # IMPORTANCE SCORING
    # =========================================================================
    
    def _compute_importance(self, turn: Turn) -> tuple[float, str]:
        """
        Compute importance score for a turn.
        
        Returns:
            (score, reason) tuple
        """
        score = 0.5  # Default
        reason = "default"
        
        content_lower = turn.content.lower()
        
        # High importance indicators
        if turn.citations:
            score = max(score, self.config.importance_with_citations)
            reason = f"cited {len(turn.citations)} chunks"
        
        if self._has_code_content(turn.content):
            score = max(score, self.config.importance_code_change)
            reason = "contains code"
        
        if turn.role == "user" and "?" in turn.content:
            score = max(score, self.config.importance_question)
            reason = "question"
        
        # Low importance indicators
        acknowledgments = ["thanks", "thank you", "ok", "okay", "got it", "i see"]
        if any(ack in content_lower for ack in acknowledgments):
            if len(turn.content) < 50:  # Short acknowledgment
                score = min(score, self.config.importance_acknowledgment)
                reason = "acknowledgment"
        
        # Boost if user provided explicit feedback
        if turn.feedback_score is not None:
            if turn.feedback_score > 0:
                score = min(1.0, score + 0.2)
                reason = f"{reason}, positive feedback"
            elif turn.feedback_score < 0:
                score = max(0.1, score - 0.1)
                reason = f"{reason}, negative feedback"
        
        return score, reason
    
    def _has_code_content(self, content: str) -> bool:
        """Check if content contains code."""
        # Code block markers
        if "```" in content:
            return True
        
        # Common code patterns
        code_patterns = [
            r"def \w+\(",
            r"class \w+[:\(]",
            r"import \w+",
            r"from \w+ import",
            r"async def",
            r"await \w+",
            r"\w+\.\w+\(",
        ]
        
        for pattern in code_patterns:
            if re.search(pattern, content):
                return True
        
        return False
    
    # =========================================================================
    # SEARCH
    # =========================================================================
    
    async def _semantic_search(
        self,
        session_id: str,
        query: str,
        k: int
    ) -> List[Turn]:
        """
        Search using embeddings with in-memory cosine similarity.
        
        For episodic memory (recent turns), we compute embeddings on-the-fly
        rather than storing in Qdrant - this is efficient for small turn sets.
        """
        import numpy as np
        
        # Get all recent turns
        all_turns = await self.get_recent(session_id, k=50)
        if not all_turns:
            return []
        
        # Get query embedding
        query_embeddings = await self.embedder.encode([query])
        query_vec = np.array(query_embeddings[0])
        
        # Get embeddings for all turns
        turn_texts = [t.content for t in all_turns]
        turn_embeddings = await self.embedder.encode(turn_texts)
        turn_vecs = np.array(turn_embeddings)
        
        # Compute cosine similarities
        # Normalize vectors
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        turn_norms = turn_vecs / (np.linalg.norm(turn_vecs, axis=1, keepdims=True) + 1e-8)
        
        # Dot product = cosine similarity for normalized vectors
        similarities = np.dot(turn_norms, query_norm)
        
        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:k]
        
        # Return turns in order of similarity
        return [all_turns[i] for i in top_indices if similarities[i] > 0.1]
    
    async def _keyword_search(
        self,
        session_id: str,
        query: str,
        k: int
    ) -> List[Turn]:
        """Simple keyword-based search fallback."""
        # Get all turns
        all_turns = await self.get_recent(session_id, k=50)
        
        # Score by keyword overlap
        query_words = set(query.lower().split())
        
        scored = []
        for turn in all_turns:
            turn_words = set(turn.content.lower().split())
            overlap = len(query_words & turn_words)
            if overlap > 0:
                scored.append((turn, overlap))
        
        # Sort by overlap score
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return [turn for turn, _ in scored[:k]]
    
    # =========================================================================
    # PERSISTENCE HELPERS
    # =========================================================================
    
    async def _persist_turn(self, turn: Turn) -> int:
        """Persist turn to database."""
        async with self._get_session() as session:
            from db.schema import ConversationLog
            
            log = ConversationLog(
                session_id=turn.session_id,
                role=turn.role,
                content=turn.content,
                token_count=turn.token_count,
                model_used=turn.model_used,
                meta={
                    "chunk_ids": turn.chunk_ids,
                    "citations": turn.citations,
                    "feedback_score": turn.feedback_score,
                    "importance": turn.importance,
                    "importance_reason": turn.importance_reason,
                    "parent_turn_id": turn.parent_turn_id,
                    "branch_label": turn.branch_label,
                    **(turn.meta or {})
                }
            )
            
            session.add(log)
            await session.commit()
            await session.refresh(log)
            
            return log.id
    
    def _row_to_turn(self, row) -> Turn:
        """Convert database row to Turn object."""
        meta = row.meta or {}
        
        return Turn(
            id=row.id,
            session_id=row.session_id,
            role=row.role,
            content=row.content,
            token_count=row.token_count,
            model_used=row.model_used,
            created_at=row.created_at,
            chunk_ids=meta.get("chunk_ids", []),
            citations=meta.get("citations", []),
            feedback_score=meta.get("feedback_score"),
            importance=meta.get("importance", 0.5),
            importance_reason=meta.get("importance_reason"),
            parent_turn_id=meta.get("parent_turn_id"),
            branch_label=meta.get("branch_label"),
            meta={k: v for k, v in meta.items() if k not in [
                "chunk_ids", "citations", "feedback_score", 
                "importance", "importance_reason",
                "parent_turn_id", "branch_label"
            ]}
        )
    
    def _get_session(self):
        """Get async session context manager."""
        if callable(self.pg_session):
            return self.pg_session()
        else:
            # Assume it's already a session
            from contextlib import asynccontextmanager
            
            @asynccontextmanager
            async def wrapper():
                yield self.pg_session
            
            return wrapper()
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate (4 chars per token)."""
        return len(text) // 4
