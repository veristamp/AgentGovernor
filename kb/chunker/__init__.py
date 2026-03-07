# chunker/__init__.py
"""
Chunker Package - Modular document chunking for knowledge bases.

Simple usage:
    from chunker import create_chunker
    
    chunker = create_chunker()
    result = chunker.process_file("doc/example.md")
    
    print(f"Total chunks: {result.total_chunks}")
    for chunk in result.text:
        print(f"[{chunk['type']}] {chunk['text'][:50]}...")

Layer Structure:
┌─────────────────────────────────────────────────────────────────┐
│  ChunkerManager                 (High Level - Facade)           │
│    process_content() / process_file() / process_directory()    │
├─────────────────────────────────────────────────────────────────┤
│  Parsers                        (Mid Level - Document Parsing)  │
│    ast_parser.py    - Markdown documents                        │
│    code_parser/     - Code files (Python, JS, Go, etc.)        │
├─────────────────────────────────────────────────────────────────┤
│  Processors                     (Mid Level - Content Handling)  │
│    text_splitter.py   - Token-aware text chunking               │
│    block_handlers.py  - Code blocks, tables                     │
├─────────────────────────────────────────────────────────────────┤
│  Core                           (Low Level - Building Blocks)   │
│    core.py            - ChunkType, Chunk, ProcessingContext     │
│    chunk_factory.py   - merge_small_chunks                      │
│    utils.py           - token_count, split_sentences            │
│    factories.py       - Tokenizer/Segmenter factories           │
│    config.py          - ChunkerSettings                         │
└─────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

# =============================================================================
# CENTRAL CONFIG (The Canon)
# =============================================================================
from config import (
    ChunkKeys,
    generate_stable_id,
    generate_section_anchor,
    Language,
    get_language_from_extension,
    is_code_file,
)

# =============================================================================
# CORE (Low Level)
# =============================================================================

# Data structures
from .core import (
    ChunkType,
    Language,  # Re-exported for backwards compatibility
    Chunk,
    ProcessingContext,
    get_language_from_extension,  # Re-exported
    is_code_file,  # Re-exported
)


# Configuration
from .config import ChunkerSettings, CLAIM_RE, SENTENCE_SPLIT_RE, PARAGRAPH_SPLIT_RE

# Utilities
from .utils import (
    token_count,
    add_overlap_to_chunk,
    split_sentences,
    PAGE_MARKER_RE,
    build_page_map,
    chunk_document,
)

# Chunk creation
from .chunk_factory import merge_small_chunks

# =============================================================================
# PROCESSORS (Mid Level)
# =============================================================================

# Text processing
from .text_splitter import token_aware_text_chunks_with_spans

# Block handlers
from .block_handlers import split_code_block_to_chunks, extract_table_markdown

# =============================================================================
# PARSERS (Mid Level)
# =============================================================================

from .ast_parser import markdown_ast_chunker
from .code_parser import parse_raw_code, EXTENSION_MAP

# =============================================================================
# MANAGER (High Level)
# =============================================================================

from .manager import ChunkerManager, create_chunker, ChunkResult, ChunkStats, BatchResult


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Central Config
    "ChunkKeys",
    "generate_stable_id",
    "generate_section_anchor",
    
    # High Level - Manager (RECOMMENDED)
    "ChunkerManager",
    "create_chunker",
    "ChunkResult",
    "ChunkStats",
    "BatchResult",
    
    # Core - Data Types
    "ChunkType",
    "Language",
    "Chunk",
    "ProcessingContext",
    "ChunkerSettings",
    
    # Core - Utilities
    "token_count",
    "add_overlap_to_chunk",
    "split_sentences",
    
    # Core - Chunk Factory
    "merge_small_chunks",
    
    # Processors - Text
    "token_aware_text_chunks_with_spans",
    
    # Processors - Blocks
    "split_code_block_to_chunks",
    "extract_table_markdown",
    
    # Parsers
    "markdown_ast_chunker",
    "parse_raw_code",
    "chunk_document",  # Smart router
    
    # Constants
    "EXTENSION_MAP",
    "SENTENCE_SPLIT_RE",
    "PARAGRAPH_SPLIT_RE",
    "PAGE_MARKER_RE",
    "build_page_map",
]

__version__ = "2.2.1"
__author__ = "KB Team"
