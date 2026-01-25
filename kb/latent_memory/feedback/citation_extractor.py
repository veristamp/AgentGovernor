# latent_memory/feedback/citation_extractor.py
"""
Citation Extraction Patterns and Utilities.

Detects which chunks the LLM actually used by looking for:
1. Explicit citations: [cite:123], [chunk:123], [ref:123]
2. Footnotes: [^1] mapped to chunk indices
3. Source references: (source: chunk_123)
4. Text overlap: Direct phrase matching as fallback
"""

import re
from typing import List, Dict, Any, Set


# =============================================================================
# CITATION EXTRACTION PATTERNS
# =============================================================================

# Matches: [cite:123] or [cite: 123] or [chunk:123]
CITATION_PATTERN = re.compile(r'\[(?:cite|chunk|ref):\s*(\d+)\]', re.IGNORECASE)

# Matches: [^1] style footnotes that might reference chunk indices
FOOTNOTE_PATTERN = re.compile(r'\[\^(\d+)\]')

# Matches: (Source: chunk_123) or (from: 123) or (1)
# Added (1) support for hallucinated simple refs
SOURCE_PATTERN = re.compile(r'\((?:source|from|chunk)?(?:\s*:)?\s*(?:chunk_)?(\d+)\)', re.IGNORECASE)

# Matches: [1], [15], [[15]] - looser bracket style
BRACKET_PATTERN = re.compile(r'\[\[?(\d+)\]?\]')


def extract_citations(
    response: str,
    retrieved_chunks: List[Dict[str, Any]] = None
) -> Set[int]:
    """
    Extract chunk IDs cited in the LLM response.
    
    Supports multiple citation formats:
    - [cite:123] or [chunk:123]
    - [^1] footnotes (matched to chunk index)
    - (source: chunk_123)
    - Direct text overlap detection (if chunks provided)
    
    Args:
        response: The LLM's response text
        retrieved_chunks: Optional list of retrieved chunks for validation
        
    Returns:
        Set of chunk IDs that were cited
    """
    cited_ids = set()
    
    # Build lookup maps if chunks provided
    id_to_chunk = {}
    index_to_id = {}
    if retrieved_chunks:
        id_to_chunk = {c.get("id"): c for c in retrieved_chunks}
        index_to_id = {c.get("index"): c.get("id") for c in retrieved_chunks}
    
    # Pattern 1: Explicit citations [cite:123]
    for match in CITATION_PATTERN.finditer(response):
        cited_id = int(match.group(1))
        if not retrieved_chunks or cited_id in id_to_chunk:
            cited_ids.add(cited_id)
        elif cited_id in index_to_id:
            cited_ids.add(index_to_id[cited_id])
    
    # Pattern 2: Footnotes [^1] mapped to chunk indices
    for match in FOOTNOTE_PATTERN.finditer(response):
        idx = int(match.group(1))
        if idx in index_to_id:
            cited_ids.add(index_to_id[idx])
    
    # Pattern 3: Source references (and simple parens)
    for match in SOURCE_PATTERN.finditer(response):
        cited_id = int(match.group(1))
        if not retrieved_chunks or cited_id in id_to_chunk:
            cited_ids.add(cited_id)
            
    # Pattern 5: Looser bracket matches [1], [[1]]
    for match in BRACKET_PATTERN.finditer(response):
        cited_id = int(match.group(1))
        # Be stricter here: only accept if it matches a known chunk ID or index
        if cited_id in id_to_chunk:
            cited_ids.add(cited_id)
        elif cited_id in index_to_id:
            cited_ids.add(index_to_id[cited_id])
    
    # Pattern 4: Text overlap detection (fallback)
    if not cited_ids and retrieved_chunks:
        cited_ids = detect_text_overlap(response, retrieved_chunks)
    
    return cited_ids


def detect_text_overlap(
    response: str,
    retrieved_chunks: List[Dict[str, Any]],
    min_overlap_words: int = 8
) -> Set[int]:
    """
    Detect which chunks were used based on text overlap.
    
    If the LLM's response contains a sequence of words from a chunk,
    that chunk was likely used.
    
    Args:
        response: The LLM's response text
        retrieved_chunks: List of chunks to check against
        min_overlap_words: Minimum consecutive words to count as overlap
        
    Returns:
        Set of chunk IDs that appear to have been used
    """
    cited_ids = set()
    response_lower = response.lower()
    
    for chunk in retrieved_chunks:
        chunk_text = chunk.get("text", "") or chunk.get("original_text", "")
        if not chunk_text:
            continue
        
        # Extract significant phrases (sequences of words)
        words = chunk_text.lower().split()
        
        # Check for n-gram overlaps
        for n in range(min_overlap_words, min(len(words), 15)):
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i + n])
                if phrase in response_lower:
                    cited_ids.add(chunk.get("id"))
                    break
            if chunk.get("id") in cited_ids:
                break
    
    return cited_ids
