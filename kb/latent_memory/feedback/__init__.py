# latent_memory/feedback/__init__.py
"""
Feedback Subpackage - Two-Tier Learning System.

Tier 1 (Soft): Automatic LLM citation-driven learning
Tier 2 (Hard): User-confirmed explicit feedback (👍/👎)
"""

from .citation_extractor import (
    CITATION_PATTERN,
    FOOTNOTE_PATTERN,
    SOURCE_PATTERN,
    extract_citations,
    detect_text_overlap,
)

from .signal_tracker import ChunkSignal
from .soft_loop import SoftFeedbackLoop
from .hard_loop import HardFeedbackLoop
from .manager import FeedbackManager, create_feedback_manager

# Backwards compatibility alias
FeedbackLoop = FeedbackManager
create_feedback_loop = create_feedback_manager

__all__ = [
    # Utilities
    "CITATION_PATTERN",
    "FOOTNOTE_PATTERN", 
    "SOURCE_PATTERN",
    "extract_citations",
    "detect_text_overlap",
    "ChunkSignal",
    # Loops
    "SoftFeedbackLoop",
    "HardFeedbackLoop",
    # Manager
    "FeedbackManager",
    "create_feedback_manager",
    # Backwards compat
    "FeedbackLoop",
    "create_feedback_loop",
]
