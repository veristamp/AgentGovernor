# chunker/code_parser/compat.py
"""
Compatibility layer for config imports.

Centralizes the ChunkKeys import with fallback to avoid duplication across modules.
"""
from __future__ import annotations

# Centralized ChunkKeys import with fallback
try:
    from config import ChunkKeys as K
except ImportError:
    # Fallback for standalone usage or testing
    class K:  # type: ignore
        """Fallback ChunkKeys when config module is not available."""
        # Core Identity
        ID = "id"
        INDEX = "index"
        TEXT = "text"
        TYPE = "type"
        FILE_PATH = "file_path"
        SOURCE_NAME = "source_name"
        ORIGINAL_TEXT = "original_text"
        
        # Hierarchy
        HEADING = "heading"
        H_LEVEL = "h_level"
        SECTION_PATH = "section_path"
        PARENT_ID = "parent_chunk_id"
        SECTION_ANCHOR = "section_anchor"
        SUMMARY = "summary"
        CHILD_IDS = "child_chunk_ids"
        
        # Physical Coordinates
        CHAR_START = "processed_char_start"
        CHAR_END = "processed_char_end"
        TOKEN_START = "token_start"
        TOKEN_COUNT = "token_count"
        LINE_START = "source_line_start"
        LINE_END = "source_line_end"
        
        # Metadata
        METADATA = "metadata"
        META_PAGES = "pages"
        META_BREADCRUMBS = "breadcrumbs"
        META_ROOT_TOPIC = "root_topic"
        META_HEADER_PREFIX = "header_prefix"
        META_LANGUAGE = "language"
        META_SYMBOLS = "symbols_defined"
        META_SYMBOLS_REF = "symbols_referenced"
        META_COMMENTS = "comments_text"


# Tree-sitter availability check (centralized)
try:
    from tree_sitter_language_pack import get_parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    get_parser = None  # type: ignore
    TREE_SITTER_AVAILABLE = False


# ID generation fallback
try:
    from config import generate_stable_id, generate_section_anchor
except ImportError:
    import hashlib
    
    def generate_stable_id(source: str, section_path: str, local_index: int) -> int:
        """Fallback stable ID generator."""
        key = f"{source}:{section_path}:{local_index}"
        return int(hashlib.md5(key.encode()).hexdigest()[:16], 16)
    
    def generate_section_anchor(source: str, section_path: str) -> str:
        """Fallback anchor generator."""
        return f"{source}#{section_path.lower().replace(' ', '-')}"


__all__ = [
    "K",
    "TREE_SITTER_AVAILABLE",
    "get_parser",
    "generate_stable_id",
    "generate_section_anchor",
]
