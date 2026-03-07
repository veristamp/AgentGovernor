# chunker/factories.py
"""Thread-safe factories for tokenizer and segmenter to enable multiprocessing."""

from __future__ import annotations

import threading
from typing import Optional, Any
from config import get_logger

# Configure logging
logger = get_logger("chunker.factories")

# Optional dependencies
try:
    from transformers import AutoTokenizer, PreTrainedTokenizerFast  # type: ignore
    TOKENIZER_AVAILABLE = True
except Exception:
    AutoTokenizer = None  # type: ignore
    PreTrainedTokenizerFast = None  # type: ignore
    TOKENIZER_AVAILABLE = False

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    tiktoken = None
    TIKTOKEN_AVAILABLE = False

try:
    from pysbd import Segmenter  # type: ignore
    PYSBD_AVAILABLE = True
except Exception:
    Segmenter = None  # type: ignore
    PYSBD_AVAILABLE = False

class TokenizerFactory:
    """
    Thread-safe singleton factory for tokenizers.
    
    This pattern allows worker processes in multiprocessing to initialize
    their own tokenizer instances without needing to pickle the tokenizer.
    """
    _instances: dict[str, Any] = {}
    _lock = threading.Lock()
    
    @classmethod
    def get_tokenizer(cls, tokenizer_name: str) -> Optional[Any]:
        """
        Get or create a tokenizer instance.
        
        Args:
            tokenizer_name: HuggingFace model name
            
        Returns:
            Tokenizer instance or None if unavailable
        """
        if not TOKENIZER_AVAILABLE or not tokenizer_name:
            return None
            
        # Check if already initialized (fast path, no lock)
        if tokenizer_name in cls._instances:
            return cls._instances[tokenizer_name]
        
        # Slow path: need to initialize
        with cls._lock:
            # Double-check after acquiring lock
            if tokenizer_name in cls._instances:
                return cls._instances[tokenizer_name]
            
            try:
                # Handle tiktoken (cl100k_base, etc.)
                if TIKTOKEN_AVAILABLE and (tokenizer_name.startswith("cl100k") or "tiktoken" in tokenizer_name):
                    logger.info(f"Initializing tiktoken encoder: {tokenizer_name}")
                    # If user passed "tiktoken/cl100k_base", extract the part after /
                    encoding_name = tokenizer_name.split("/")[-1] if "/" in tokenizer_name else tokenizer_name
                    # If it's literally "tiktoken", default to cl100k_base
                    if encoding_name == "tiktoken": encoding_name = "cl100k_base"
                    
                    encoder = tiktoken.get_encoding(encoding_name)
                    cls._instances[tokenizer_name] = encoder
                    return encoder

                if not TOKENIZER_AVAILABLE:
                    return None

                logger.info(f"Initializing transformers tokenizer: {tokenizer_name}")
                tokenizer = AutoTokenizer.from_pretrained(
                    tokenizer_name, 
                    use_fast=True
                )
                cls._instances[tokenizer_name] = tokenizer
                return tokenizer
            except Exception as e:
                logger.warning(
                    f"Failed to load tokenizer/encoder '{tokenizer_name}': {e}. "
                    "Falling back to character counts."
                )
                return None
    
    @classmethod
    def clear_cache(cls):
        """Clear all cached tokenizer instances (useful for testing)."""
        with cls._lock:
            cls._instances.clear()

class SegmenterFactory:
    """
    Thread-safe singleton factory for pysbd Segmenter.
    
    Similar to TokenizerFactory, this enables multiprocessing by allowing
    worker processes to initialize their own segmenter instances.
    
    Note: Caches by (language, clean) tuple to support multilingual use.
    """
    _instances: dict[str, Any] = {}  # Key: "language_clean"
    _lock = threading.Lock()
    
    @classmethod
    def get_segmenter(cls, language: str = "en", clean: bool = False) -> Optional[Any]:
        """
        Get or create a pysbd Segmenter instance.
        
        Args:
            language: Language code for sentence segmentation
            clean: Whether to clean sentences
            
        Returns:
            Segmenter instance or None if unavailable
        """
        if not PYSBD_AVAILABLE:
            return None
        
        # Cache key includes language and clean setting
        cache_key = f"{language}_{clean}"
        
        # Fast path
        if cache_key in cls._instances:
            return cls._instances[cache_key]
        
        # Slow path: initialize
        with cls._lock:
            # Double-check
            if cache_key in cls._instances:
                return cls._instances[cache_key]
            
            try:
                logger.info(f"Initializing pysbd Segmenter (language={language}, clean={clean})")
                segmenter = Segmenter(language=language, clean=clean)
                cls._instances[cache_key] = segmenter
                return segmenter
            except Exception as e:
                logger.warning(f"Failed to initialize pysbd Segmenter: {e}")
                return None
    
    @classmethod
    def clear_cache(cls):
        """Clear cached segmenter instances (useful for testing)."""
        with cls._lock:
            cls._instances.clear()
