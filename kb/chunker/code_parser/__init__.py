# chunker/code_parser/__init__.py
"""
Code Parser Package - Tree-sitter based code chunking.

Structure:
- constants.py   : Type definitions, language mappings (~120 lines)
- symbol_extraction.py : AST symbol/comment/ref extraction (~200 lines)
- helpers.py     : Utility functions for span/naming/metadata (~180 lines)
- emitters.py    : Chunk emission functions (~200 lines)
- chunker.py     : CodeChunker class (~280 lines)
- api.py         : Standalone functions for markdown (~120 lines)

Usage:
    from chunker.code_parser import parse_raw_code, EXTENSION_MAP
    
    # Or use the class directly
    from chunker.code_parser import CodeChunker
    chunker = CodeChunker(code, "file.py", settings)
    chunks = chunker.chunk()
"""
from __future__ import annotations

# Constants
from .constants import (
    EXTENSION_MAP,
    ATOMIC_TYPES,
    BRACE_LANGUAGES,
    Symbol,
    SYMBOL_NODE_TYPES,
    COMMENT_NODE_TYPES,
    REFERENCE_NODE_TYPES,
)

# Symbol extraction
from .symbol_extraction import (
    extract_symbols_from_node,
    extract_comments_from_node,
    extract_references_from_node,
)

# Compatibility layer
from .compat import TREE_SITTER_AVAILABLE, K

# Main class
from .chunker import CodeChunker, parse_raw_code

# Standalone API
from .api import treesitter_chunk_code, extract_code_block_metadata


__all__ = [
    # Main class
    "CodeChunker",
    
    # Entry points
    "parse_raw_code",
    "treesitter_chunk_code",
    "extract_code_block_metadata",
    
    # Constants
    "EXTENSION_MAP",
    "ATOMIC_TYPES", 
    "BRACE_LANGUAGES",
    "TREE_SITTER_AVAILABLE",
    
    # Symbol types
    "Symbol",
    "SYMBOL_NODE_TYPES",
    "COMMENT_NODE_TYPES",
    "REFERENCE_NODE_TYPES",
    
    # Extraction functions
    "extract_symbols_from_node",
    "extract_comments_from_node",
    "extract_references_from_node",
]
