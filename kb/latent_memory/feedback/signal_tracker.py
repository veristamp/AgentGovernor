# latent_memory/feedback/signal_tracker.py
"""
Signal Tracker - Query-Chunk Edge Scoring.

Tracks the learned signal for query-chunk pairs:
- boost_score: Positive = useful, Negative = noise
- citation_count: How many times this chunk was cited for this query
- ignore_count: How many times it was retrieved but ignored
- signal_type: "soft" (LLM inferred) or "hard" (user confirmed)
"""

from dataclasses import dataclass


@dataclass
class ChunkSignal:
    """Tracks the learned signal for a query-chunk pair."""
    
    chunk_id: int
    boost_score: float = 0.0  # Positive = useful, Negative = noise
    citation_count: int = 0
    ignore_count: int = 0
    last_updated: float = 0.0
    signal_type: str = "soft"  # "soft" (LLM inferred) or "hard" (user confirmed)
    
    @property
    def confidence(self) -> float:
        """
        Calculate confidence in this signal using Wilson score.
        
        Hard signals (user confirmed) get higher confidence.
        
        Returns:
            Float between 0.0 and 1.0
        """
        total = self.citation_count + self.ignore_count
        if total == 0:
            return 0.0
        
        # Wilson score lower bound for 95% confidence
        n = total
        p = self.citation_count / n
        z = 1.96  # 95% confidence
        
        denominator = 1 + z * z / n
        center = p + z * z / (2 * n)
        spread = z * ((p * (1 - p) + z * z / (4 * n)) / n) ** 0.5
        
        base_confidence = (center - spread) / denominator
        
        # Hard signals (user confirmed) get higher confidence
        if self.signal_type == "hard":
            return min(1.0, base_confidence + 0.4)
        
        return base_confidence
    
    @property
    def is_positive(self) -> bool:
        """Whether this signal indicates the chunk is useful."""
        return self.boost_score > 0
    
    @property
    def is_significant(self) -> bool:
        """Whether this signal has enough data to be meaningful."""
        return (self.citation_count + self.ignore_count) >= 3
