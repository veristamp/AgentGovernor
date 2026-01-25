# chunker/chunk_factory.py
"""
Chunk Factory - Post-processing utilities for chunks.

This module provides:
- merge_small_chunks: Combines small adjacent text chunks to reduce noise
"""

from __future__ import annotations

from typing import List

from .config import ChunkerSettings
from .core import Chunk, ChunkType
from .utils import token_count
from config import get_logger

# Safe import with fallback
try:
    from config import ChunkKeys as K
except ImportError:
    class K:
        META_HEADER_PREFIX = "header_prefix"

# Configure logging
logger = get_logger("chunker.chunk_factory")

def merge_small_chunks(chunks: List[Chunk], settings: ChunkerSettings) -> List[Chunk]:
    """
    Merges small text chunks to reduce noise while preserving structure.
    
    Strategy: "Adjacency Merging with Barriers"
    - Only TEXT chunks can be merged
    - Non-text chunks (HEADING, CODE, TABLE) act as barriers that break the merge chain
    - Chunks must be in the same section (same section_path)
    - At least one chunk must be "small" (below min_merge_tokens)
    - Combined chunk must fit within max_tokens limit
    
    This prevents:
    - Merging across section boundaries
    - Reordering content (e.g., merging text from after a code block into before it)
    
    Returns:
        List of merged chunks with updated indices
    """
    if not chunks:
        return chunks

    merged: List[Chunk] = []
    last_text_idx = -1  # Index of last TEXT chunk in 'merged' list
    
    for chunk in chunks:
        # 1. Non-text chunks pass through and break merge chain
        if chunk.chunk_type != ChunkType.TEXT:
            merged.append(chunk)
            last_text_idx = -1  # Break merge chain
            continue
            
        # 2. First text chunk - just add it
        if last_text_idx == -1:
            merged.append(chunk)
            last_text_idx = len(merged) - 1
            continue
            
        # 3. Evaluate merge conditions
        last_chunk = merged[last_text_idx]
        
        # Condition A: Same section
        same_section = (last_chunk.section_path == chunk.section_path)
        
        # Condition B: At least one is small
        is_last_small = last_chunk.token_count < settings.min_merge_tokens
        is_curr_small = chunk.token_count < settings.min_merge_tokens
        either_small = is_last_small or is_curr_small
        
        # Condition C: Combined fits in limit
        # Strip duplicate header prefixes before combining
        chunk_text = chunk.text
        header_prefix = chunk.metadata.get(K.META_HEADER_PREFIX)
        if header_prefix and chunk_text.startswith(header_prefix):
            chunk_text = chunk_text[len(header_prefix):].lstrip("\n")

        combined_text = last_chunk.text + "\n\n" + chunk_text
        max_tokens = settings.max_tokens_by_type.get(ChunkType.TEXT.value, settings.max_tokens_text)
        fits_in_limit = token_count(combined_text, settings) <= max_tokens
        
        # Execute merge if all conditions met
        if same_section and either_small and fits_in_limit:
            # Merge into last_chunk
            last_chunk.text = combined_text
            last_chunk.original_text = (last_chunk.original_text or "") + (chunk.original_text or "")
            last_chunk.char_end = chunk.char_end
            last_chunk.line_end = chunk.line_end
            last_chunk.token_count = token_count(combined_text, settings)
            logger.debug(f"Merged chunks in section '{chunk.section_path}'")
        else:
            # No merge - add chunk and update tracker
            merged.append(chunk)
            last_text_idx = len(merged) - 1

    # Re-index chunks sequentially for consistency
    for i, chunk in enumerate(merged):
        chunk.index = i
        
    return merged
