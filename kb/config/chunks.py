# config/chunks.py
"""
Central Chunk Schema Configuration.
Defines the 'Canon' for what a structured chunk looks like across the system.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

@dataclass(frozen=True)
class ChunkKeys:
    """The 'Canon' of keys for any chunk in the system."""
    
    # Core Identity
    ID = "id"
    INDEX = "index"
    TEXT = "text"
    TYPE = "type"
    FILE_PATH = "file_path"  # Absolute path on disk (optional)
    SOURCE_NAME = "source_name" # Clean display name (e.g., "database.py")
    ORIGINAL_TEXT = "original_text"

    # Hierarchy & Structure
    HEADING = "heading"
    H_LEVEL = "h_level"
    SECTION_PATH = "section_path"
    SECTION_ROOT_ID = "section_root_id"  # For Grouping API
    PARENT_ID = "parent_chunk_id"
    SECTION_ANCHOR = "section_anchor"
    SUMMARY = "summary"
    CHILD_IDS = "child_chunk_ids"

    # Search & Discovery (The Soft Graph)
    CONCEPT_TAGS = "concept_tags"
    CONTAINS_CODE = "contains_code"
    DOC_ID = "doc_id"

    # Physical Coordinates (Surgical Patching & Context Budgeting)
    CHAR_START = "processed_char_start"
    CHAR_END = "processed_char_end"
    TOKEN_START = "token_start"
    TOKEN_COUNT = "token_count"
    LINE_START = "source_line_start"
    LINE_END = "source_line_end"

    # Metadata Sub-dictionary
    METADATA = "metadata"
    META_PAGES = "pages"
    META_BREADCRUMBS = "breadcrumbs"
    META_ROOT_TOPIC = "root_topic"
    META_HEADER_PREFIX = "header_prefix"
    
    # Rich Metadata (Harvester & Logic)
    META_LANGUAGE = "language"
    META_SYMBOLS = "symbols_defined"
    META_SYMBOLS_REF = "symbols_referenced"
    META_COMMENTS = "comments_text"
    META_HEADERS = "headers"
    META_ROW_COUNT = "row_count"

    # Aliases
    SOURCE = "source"  # Document/source identifier in chunk payloads


def validate_chunk(chunk: Dict[str, Any]) -> bool:
    """Check if a chunk follows the mandatory schema for processing."""
    K = ChunkKeys
    required_keys = [
        K.ID, K.TEXT, K.SOURCE,
        K.CHAR_START, K.CHAR_END, K.TOKEN_COUNT
    ]
    return all(key in chunk for key in required_keys)
