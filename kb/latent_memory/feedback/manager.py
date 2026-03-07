# latent_memory/feedback/manager.py
"""
Feedback Manager - Unified Interface for Two-Tier Learning.

Combines Soft (automatic) and Hard (user-confirmed) feedback loops
into a single manager with a clean API.

Architecture:
    ┌─────────────────────────────────────────────────┐
    │              FeedbackManager                     │
    │  ┌───────────────────┐  ┌───────────────────┐   │
    │  │  SoftFeedbackLoop │  │  HardFeedbackLoop │   │
    │  │  (LLM Citations)  │  │  (User 👍/👎)     │   │
    │  └───────────────────┘  └───────────────────┘   │
    └─────────────────────────────────────────────────┘

Usage:
    from latent_memory.feedback import FeedbackManager
    
    manager = FeedbackManager(qdrant_client=client, pg_session=session)
    
    # Automatic (Tier 1)
    await manager.process_turn(query, chunks, response)
    
    # User feedback (Tier 2)
    await manager.confirm_feedback([123], positive=True)
"""

from typing import List, Dict, Any, Optional

from .soft_loop import SoftFeedbackLoop
from .hard_loop import HardFeedbackLoop
from config import get_logger

logger = get_logger("latent_memory.feedback.manager")


class FeedbackManager:
    """
    Unified manager for two-tier feedback system.
    
    Tier 1 (Soft): Automatic LLM citation-driven learning
    Tier 2 (Hard): User-confirmed explicit feedback
    """
    
    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        qdrant_client: Optional[Any] = None,
        pg_session: Optional[Any] = None,
        collection_name: str = "kb_chunks",
        boost_weight: float = 0.3,
        decay_factor: float = 0.9,
        min_confidence: float = 0.2
    ):
        """
        Initialize the feedback manager.
        
        Args:
            qdrant_url: Qdrant server URL
            qdrant_client: Pre-configured Qdrant client
            pg_session: SQLAlchemy async session
            collection_name: Default Qdrant collection
            boost_weight: Soft signal boost weight
            decay_factor: Soft signal decay factor
            min_confidence: Minimum confidence for boosting
        """
        self._soft = SoftFeedbackLoop(
            pg_session=pg_session,
            boost_weight=boost_weight,
            decay_factor=decay_factor,
            min_confidence=min_confidence
        )
        
        self._hard = HardFeedbackLoop(
            qdrant_url=qdrant_url,
            qdrant_client=qdrant_client,
            pg_session=pg_session,
            collection_name=collection_name
        )
    
    # =========================================================================
    # SESSION MANAGEMENT
    # =========================================================================
    
    def set_pg_session(self, session):
        """Set Postgres session for both loops."""
        self._soft.set_pg_session(session)
        self._hard.set_pg_session(session)
    
    def set_qdrant_client(self, client):
        """Set Qdrant client for hard loop."""
        self._hard.set_qdrant_client(client)
    
    # =========================================================================
    # TIER 1: SOFT (AUTOMATIC)
    # =========================================================================
    
    async def process_turn(
        self,
        query: str,
        retrieved_chunks: List[Dict[str, Any]],
        llm_response: str,
        query_vector: Optional[List[float]] = None,
        query_concepts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Process a turn for automatic learning (SOFT signal).
        
        Call this after every LLM response.
        """
        return await self._soft.process_turn(
            query=query,
            retrieved_chunks=retrieved_chunks,
            llm_response=llm_response,
            query_vector=query_vector,
            query_concepts=query_concepts
        )
    
    def boost_results(
        self,
        query: str,
        base_results: List[Dict[str, Any]],
        score_key: str = "score"
    ) -> List[Dict[str, Any]]:
        """Apply soft signal boosting to search results."""
        return self._soft.boost_results(query, base_results, score_key)
    
    # =========================================================================
    # TIER 2: HARD (USER CONFIRMED)
    # =========================================================================
    
    async def confirm_feedback(
        self,
        chunk_ids: List[int],
        positive: bool,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        collection_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Record user-confirmed feedback (HARD signal).
        
        Call this when user clicks 👍 or 👎.
        """
        return await self._hard.confirm_feedback(
            chunk_ids=chunk_ids,
            positive=positive,
            user_id=user_id,
            session_id=session_id,
            collection_name=collection_name
        )
    
    async def get_recommendations(
        self,
        limit: int = 10,
        collection_name: Optional[str] = None,
        additional_positive: Optional[List[int]] = None,
        additional_negative: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """Get recommendations using Qdrant Recommend API with hard signals."""
        return await self._hard.get_recommendations(
            limit=limit,
            collection_name=collection_name,
            additional_positive=additional_positive,
            additional_negative=additional_negative
        )
    
    # =========================================================================
    # STATS & EXPORTS
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get combined statistics from both tiers."""
        return {
            "soft": self._soft.get_stats(),
            "hard": self._hard.get_stats()
        }
    
    def export_soft_edges(self) -> List[Dict[str, Any]]:
        """Export soft signal edges for knowledge graph."""
        return self._soft.export_graph_edges()

def create_feedback_manager(
    qdrant_url: str = "http://localhost:6333",
    **kwargs
) -> FeedbackManager:
    """Factory function for FeedbackManager."""
    return FeedbackManager(qdrant_url=qdrant_url, **kwargs)
