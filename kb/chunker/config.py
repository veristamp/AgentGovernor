# chunker/config.py
"""
Configuration settings and constants for the markdown chunker.

IMPORTANT: For token counting during chunking, we use tiktoken (cl100k_base) by default.
This is ~300x faster than HuggingFace tokenizers and good enough for chunking purposes
since we're just estimating, not doing exact billing.

Set CHUNKER_TOKENIZER env var to override:
- "cl100k_base" (default, fast) - GPT-4/ada-002 tokenizer
- "o200k_base" - GPT-4o tokenizer  
- Any HuggingFace model name for exact matching (slower)
"""

from __future__ import annotations

import os
import re

from typing import Dict, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass, field
from .core import ChunkType
from config import get_logger

# Prevent deadlocks when using multiprocessing with HuggingFace tokenizers
# Must be set BEFORE importing transformers
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# CHUNKER TOKENIZER: Use fast tiktoken by default
# This is separate from the embedding model - we just need fast token counting for chunking
_DEFAULT_TOKENIZER = os.getenv("CHUNKER_TOKENIZER", "cl100k_base")

# Import central config for max tokens (the embedding model's context window)
try:
    from config.embeddings import EMBEDDING_CONFIG
    _DEFAULT_MAX_TOKENS = EMBEDDING_CONFIG.max_tokens
except ImportError:
    _DEFAULT_MAX_TOKENS = 8192

if TYPE_CHECKING:
    # Import types only for type checking, not at runtime
    try:
        from transformers import PreTrainedTokenizerFast
    except ImportError:
        PreTrainedTokenizerFast = Any  # type: ignore
    try:
        from pysbd import Segmenter as PysbdSegmenter
    except ImportError:
        PysbdSegmenter = Any  # type: ignore

# Configure logging
logger = get_logger("chunker.config")

# --- Optional dependencies ---
try:
    from transformers import AutoTokenizer  # type: ignore
    TOKENIZER_AVAILABLE = True
except Exception:
    AutoTokenizer = None  # type: ignore
    TOKENIZER_AVAILABLE = False

# Optional: Robust sentence boundary detection
try:
    from pysbd import Segmenter  # type: ignore
    PYSBD_AVAILABLE = True
except Exception:
    Segmenter = None  # type: ignore
    PYSBD_AVAILABLE = False

# ==================== CONSTANTS ====================

# Configurable constants
EMBEDDING_MAX_TOKENS = 512  # Maximum tokens for lexical embedding approximation

# Sentence splitting (regex fallback, pysbd preferred)
# English-biased regex; for multilingual, use pysbd or spaCy (more accurate)
SENTENCE_SPLIT_RE = re.compile(
    r'(?<!\b[A-Z]\.)(?<!\b[A-Z][a-z]\.)(?<!\bet al)(?<=[.!?])["“”\']?\s+(?=[A-Z0-9(])'
)
PARAGRAPH_SPLIT_RE = re.compile(r'\n{2,}')

# Proposition/claim detection - removed re.M flag to only match at sentence start
CLAIM_PATTERNS = [
    r'^We\s+',
    r'^Our\s+',
    r'^The\s+company\s+',
    r'^Results?\s+shows?\s+',
    r'^Study\s+found\s+',
    r'^Research\s+indicates?\s+',
    r'^Figure\s+\d+',
    r'^Table\s+\d+',
    r'^Theorem\s+\d+',
    r'^Lemma\s+\d+',
    r'^Proposition\s+\d+',
]
CLAIM_RE = re.compile('|'.join(CLAIM_PATTERNS), re.I)

# ==================== SETTINGS CLASS ====================

@dataclass
class ChunkerSettings:
    """
    Configuration for the chunker, allowing per-corpus tuning.
    
    Defaults are read from EMBEDDING_CONFIG (set via environment variables).
    """
    tokenizer_name: str = None  # Set in __post_init__ from EMBEDDING_CONFIG
    max_tokens_text: int = 2000  # ~25% of context window for chunks
    # IMPORTANT: min_keep_tokens filters out "fluff" but can be dangerous for dense content
    # (e.g., glossaries, FAQs). Set to 1 to preserve all content.
    min_keep_tokens: int = 1              # Lowered to 1 to ensure 100% content fidelity
    
    # Merge threshold: chunks below this size will merge with neighbors if possible
    # This prevents "orphaned header intros" - transitional text between sections  
    # that's big enough to survive garbage collection but too small to be useful alone
    min_merge_tokens: int = 50            # Merge chunks smaller than this with neighbors
    
    # SAFETY: Lowered from 7200 to prevent silent truncation by embedding models
    # 2000 chars ≈ 500 tokens (safe for 512-token BERT models if tokenizer fails)
    max_chars_fallback: int = 2000       # Safe fallback for char-based splitting
    emit_heading_chunks: bool = True

    # Oversized atomic block splitting
    split_code_max_lines: int = 200
    split_table_rows: int = 100

    # Smart overlap for context continuity (scaled up for large context)
    overlap_tokens: int = 300  # ~20% of max_tokens_text
    overlap_sentences: int = 5  # Fallback for char mode

    # Content-type-specific token limits (scaled up for large context)
    max_tokens_by_type: Dict[str, int] = field(default_factory=lambda: {
        ChunkType.TEXT.value: 2000, 
        ChunkType.CODE.value: 2000, 
        ChunkType.TABLE.value: 2000
    })
    embedding_model: Optional[str] = None  
    # Proposition detection thresholds
    prop_token_thresh: int = 200  # Min tokens before splitting on claims
    prop_char_thresh: int = 500   # Min chars before splitting on claims

    # Header injection for better retrieval context
    inject_headers: bool = True  # Prepend section path to chunk text

    # Sentence windowing (late-chunking pattern)
    sentence_window_size: int = 0  # Sentences to add as context (0 = disabled)

    # Internal state (not intended for manual initialization)
    _page_map: Dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    # Use pysbd for sentence splitting if available
    use_pysbd: bool = True  # Use pysbd if available (more accurate than regex)
    
    # Enable Tree-sitter parsing
    use_treesitter: bool = True
    
    # Code chunking thresholds (for code_parser)
    code_group_limit: int = 400      # Max tokens for grouping small non-atomic nodes
    code_tiny_threshold: int = 100   # Threshold to merge tiny preamble with next node

    # Text splitting performance thresholds
    large_text_threshold: int = 50000     # Chars before using fast sentence split
    max_sentences_per_para: int = 1000    # Sentences before char-based fallback
    token_safety_margin: float = 0.85     # Safety margin for token limit checks (85%)

    # Embedding model token limit (separate from chunking limit)
    # Many embedding models have hard limits (e.g., 512 for BERT-based models)
    # Set to None to use max_tokens_text, or specify a hard limit for your embedding model
    embedding_max_tokens: Optional[int] = None  # Set in __post_init__ from EMBEDDING_CONFIG

    # Note: tokenizer and segmenter are NOT stored in this dataclass to enable
    # multiprocessing/serialization. Use get_tokenizer() and get_segmenter() instead.
    
    def __post_init__(self):
        """Apply defaults from central config after initialization."""
        if self.tokenizer_name is None:
            self.tokenizer_name = _DEFAULT_TOKENIZER
        if self.embedding_max_tokens is None:
            self.embedding_max_tokens = _DEFAULT_MAX_TOKENS
    
    def get_tokenizer(self) -> 'Optional[PreTrainedTokenizerFast]':
        """
        Get tokenizer instance via factory pattern.
        
        This method allows the chunker to work with multiprocessing by avoiding
        storing non-serializable tokenizer objects in the settings.
        """
        from .factories import TokenizerFactory
        return TokenizerFactory.get_tokenizer(self.tokenizer_name)  # type: ignore
    
    def get_segmenter(self) -> 'Optional[PysbdSegmenter]':
        """
        Get segmenter instance via factory pattern.
        
        This method allows the chunker to work with multiprocessing by avoiding
        storing non-serializable segmenter objects in the settings.
        """
        if not self.use_pysbd:
            return None
        from .factories import SegmenterFactory
        return SegmenterFactory.get_segmenter(language="en", clean=False)  # type: ignore
