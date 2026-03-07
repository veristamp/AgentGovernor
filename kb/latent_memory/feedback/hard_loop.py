# latent_memory/feedback/hard_loop.py
"""
Hard Feedback Loop - User-Confirmed Explicit Signals.

Unlike soft signals (inferred from LLM citations), hard signals are:
- Explicit user action (👍 thumbs up / 👎 thumbs down)
- Higher confidence (user confirmed)
- Permanent (updates Qdrant payload directly)
- Used for Qdrant Recommend API

The Two-Tier System:
- Tier 1 (Soft): Automatic LLM citation learning → soft_loop.py
- Tier 2 (Hard): User explicit feedback → THIS FILE

Usage:
    from latent_memory.feedback import HardFeedbackLoop
    
    loop = HardFeedbackLoop(qdrant_client=client)
    
    # User clicks 👍 on chunks 123, 456
    await loop.confirm_feedback(
        chunk_ids=[123, 456],
        positive=True,
        user_id="user_abc"
    )
    
    # Use Qdrant Recommend API with accumulated signals
    recommendations = await loop.get_recommendations(limit=10)
"""

from typing import List, Dict, Any, Optional
import time
from config import get_logger

logger = get_logger("latent_memory.feedback.hard_loop")


class HardFeedbackLoop:
    """
    Hard (User-Confirmed) Feedback Loop.
    
    Handles explicit user feedback (👍/👎):
    1. Updates Qdrant payload (quality_boost field)
    2. Persists to Postgres with CONFIRMED edge type
    3. Tracks globally for Qdrant Recommend API
    
    Hard signals have higher confidence than soft signals.
    """
    
    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        qdrant_client: Optional[Any] = None,
        pg_session: Optional[Any] = None,
        collection_name: str = "kb_chunks"
    ):
        """
        Initialize the hard feedback loop.
        
        Args:
            qdrant_url: Qdrant server URL
            qdrant_client: Optional pre-configured Qdrant client
            pg_session: SQLAlchemy async session for Postgres
            collection_name: Default Qdrant collection name
        """
        self.qdrant_url = qdrant_url
        self._client = qdrant_client
        self._pg_session = pg_session
        self.collection_name = collection_name
        
        # Global tracking for Recommend API
        self._global_positive: List[int] = []
        self._global_negative: List[int] = []
        
        # Stats
        self._total_positive = 0
        self._total_negative = 0
        self._qdrant_updates = 0
        self._postgres_edges = 0
    
    @property
    def client(self):
        """Lazy-load Qdrant client."""
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
                self._client = QdrantClient(url=self.qdrant_url)
            except ImportError:
                logger.warning("qdrant-client not installed")
                return None
        return self._client
    
    def set_qdrant_client(self, client):
        """Set Qdrant client."""
        self._client = client
    
    def set_pg_session(self, session):
        """Set Postgres session for edge persistence."""
        self._pg_session = session
    
    # =========================================================================
    # CORE: USER FEEDBACK
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
        User confirmed feedback - HARD SIGNAL.
        
        Updates:
        1. Qdrant payload (quality_boost field)
        2. Postgres edges (CONFIRMED type)
        3. Global tracking for Recommend API
        
        Args:
            chunk_ids: Chunk IDs the user is rating
            positive: True for 👍, False for 👎
            user_id: Optional user identifier
            session_id: Optional session for analytics/tracking
            collection_name: Override default collection
            
        Returns:
            Stats about the update
        """
        start_time = time.time()
        collection = collection_name or self.collection_name
        
        results = {
            "chunks_updated": 0,
            "qdrant_updated": False,
            "postgres_updated": False,
            "signal_type": "hard",
            "positive": positive,
            "session_id": session_id,
            "user_id": user_id,
            "latency_ms": 0
        }
        
        # 1. Update Qdrant payload
        if self.client:
            try:
                delta = 0.5 if positive else -0.5
                
                for chunk_id in chunk_ids:
                    # Get current payload
                    point = await self.client.retrieve(
                        collection_name=collection,
                        ids=[chunk_id],
                        with_payload=True
                    )
                    
                    if point:
                        current_boost = point[0].payload.get("quality_boost", 0.0)
                        feedback_count = point[0].payload.get("feedback_count", 0)
                        
                        # Update payload
                        await self.client.set_payload(
                            collection_name=collection,
                            payload={
                                "quality_boost": current_boost + delta,
                                "feedback_count": feedback_count + 1,
                                "last_feedback": time.time(),
                                "last_feedback_positive": positive
                            },
                            points=[chunk_id]
                        )
                        results["chunks_updated"] += 1
                        self._qdrant_updates += 1
                
                results["qdrant_updated"] = True
                logger.info(f"🎯 [HARD] Updated {results['chunks_updated']} chunks in Qdrant")
                
            except Exception as e:
                logger.error(f"Failed to update Qdrant payload: {e}")
        
        # 2. Persist to Postgres
        if self._pg_session:
            try:
                edges_written = await self._persist_to_postgres(
                    chunk_ids=chunk_ids,
                    positive=positive,
                    user_id=user_id,
                    session_id=session_id
                )
                results["postgres_updated"] = edges_written > 0
                results["postgres_edges"] = edges_written
                self._postgres_edges += edges_written
            except Exception as e:
                logger.error(f"Failed to persist hard feedback to Postgres: {e}")
        
        # 3. Track globally for Recommend API
        target_list = self._global_positive if positive else self._global_negative
        target_list.extend(chunk_ids)
        
        # Update stats
        if positive:
            self._total_positive += len(chunk_ids)
        else:
            self._total_negative += len(chunk_ids)
        
        # Keep lists bounded (last 100)
        if len(self._global_positive) > 100:
            self._global_positive = self._global_positive[-100:]
        if len(self._global_negative) > 100:
            self._global_negative = self._global_negative[-100:]
        
        # Calculate latency and finalize results
        results["latency_ms"] = int((time.time() - start_time) * 1000)
        
        # Structured log for analytics/monitoring
        emoji = "👍" if positive else "👎"
        logger.info(
            f"{emoji} [FEEDBACK] session={session_id or 'anon'}, "
            f"user={user_id or 'anon'}, chunks={len(chunk_ids)}, "
            f"qdrant={results['qdrant_updated']}, pg={results['postgres_updated']}, "
            f"{results['latency_ms']}ms"
        )
        
        return results
    
    async def _persist_to_postgres(
        self,
        chunk_ids: List[int],
        positive: bool,
        user_id: Optional[str],
        session_id: Optional[str] = None
    ) -> int:
        """Persist hard feedback to Postgres."""
        if not self._pg_session:
            return 0
        
        edges_written = 0
        edge_type = "HARD_POSITIVE" if positive else "HARD_NEGATIVE"
        
        try:
            if callable(self._pg_session):
                async with self._pg_session() as session:
                    from sqlalchemy import text
                    
                    for chunk_id in chunk_ids:
                        await session.execute(
                            text("""
                                INSERT INTO edges (source_id, target_id, edge_type, weight, properties)
                                VALUES (:source, :target, :edge_type, :weight, :props)
                                ON CONFLICT (source_id, target_id, edge_type) 
                                DO UPDATE SET weight = edges.weight + 0.5
                            """),
                            {
                                "source": chunk_id,
                                "target": 0,  # Global feedback node
                                "edge_type": edge_type,
                                "weight": 1.0 if positive else -1.0,
                                "props": f'{{"user_id": "{user_id or "anonymous"}", "session_id": "{session_id or "none"}", "timestamp": {time.time()}, "signal": "hard"}}'
                            }
                        )
                        edges_written += 1
                    
                    await session.commit()
        except Exception as e:
            logger.warning(f"Failed to persist hard feedback: {e}")
        
        return edges_written
    
    # =========================================================================
    # QDRANT RECOMMEND API
    # =========================================================================
    
    async def get_recommendations(
        self,
        limit: int = 10,
        collection_name: Optional[str] = None,
        additional_positive: Optional[List[int]] = None,
        additional_negative: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Use Qdrant Recommend API with accumulated hard signals.
        
        This uses the global positive/negative examples from user feedback
        to find similar chunks using Qdrant's native recommendation engine.
        
        Args:
            limit: Number of recommendations to return
            collection_name: Override default collection
            additional_positive: Extra positive IDs to include
            additional_negative: Extra negative IDs to include
            
        Returns:
            List of recommended chunks with scores
        """
        if not self.client:
            return []
        
        collection = collection_name or self.collection_name
        
        # Combine global signals with additional
        positive_ids = self._global_positive.copy()
        negative_ids = self._global_negative.copy()
        
        if additional_positive:
            positive_ids.extend(additional_positive)
        if additional_negative:
            negative_ids.extend(additional_negative)
        
        # Need at least some positive examples
        if not positive_ids:
            logger.debug("No positive examples for recommendation query")
            return []
        
        try:
            from qdrant_client.http import models
            
            result = await self.client.query_points(
                collection_name=collection,
                query=models.RecommendQuery(
                    recommend=models.RecommendInput(
                        positive=positive_ids[-20:],  # Last 20 positive
                        negative=negative_ids[-10:] if negative_ids else None,
                        strategy=models.RecommendStrategy.BEST_SCORE
                    )
                ),
                limit=limit,
                with_payload=True
            )
            
            logger.info(
                f"📊 [HARD] Recommend API: {len(result.points)} results "
                f"from {len(positive_ids)} positive, {len(negative_ids)} negative"
            )
            
            return [
                {
                    "id": p.id,
                    "score": p.score,
                    "payload": p.payload,
                    "source": "hard_recommend_api"
                }
                for p in result.points
            ]
            
        except Exception as e:
            logger.error(f"Qdrant Recommend API failed: {e}")
            return []
    
    # =========================================================================
    # UTILITIES
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get hard feedback statistics."""
        return {
            "signal_type": "hard",
            "total_positive": self._total_positive,
            "total_negative": self._total_negative,
            "global_positive_count": len(self._global_positive),
            "global_negative_count": len(self._global_negative),
            "qdrant_updates": self._qdrant_updates,
            "postgres_edges": self._postgres_edges,
            "recommend_ready": len(self._global_positive) >= 3
        }
    
    def clear_signals(self):
        """Clear all accumulated signals (use with caution)."""
        self._global_positive = []
        self._global_negative = []
        self._total_positive = 0
        self._total_negative = 0
        logger.warning("🗑️ [HARD] Cleared all hard signals")
