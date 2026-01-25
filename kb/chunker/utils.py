
# chunker/utils.py
"""Utility functions for token counting, overlap, text processing, and document routing."""

from __future__ import annotations

import re
from typing import List, Dict, Any

from .config import ChunkerSettings, SENTENCE_SPLIT_RE
from .core import Chunk
from config import get_logger

# Configure logging
logger = get_logger("chunker.utils")

# Regex to find page markers like <!-- PAGE 4 -->
PAGE_MARKER_RE = re.compile(r'<!--\s*PAGE\s+(\d+)\s*-->', re.IGNORECASE)

def lookup_page_numbers(line_start: int, line_end: int, page_map: Dict[str, Any]) -> List[int]:
    """
    Finds pages based on line numbers using the pre-computed page map.
    
    Args:
        line_start: 1-indexed start line of the chunk
        line_end: 1-indexed end line of the chunk
        page_map: The page map dictionary from build_page_map
        
    Returns:
        List of page numbers this chunk overlaps with.
    """
    if line_start is None or not page_map or not page_map.get("has_pages"):
        return []

    # Default line_end if missing
    if line_end is None:
        line_end = line_start + 1 # Assume single line
        
    pages = set()
    ranges = page_map.get("page_ranges", [])
    
    for entry in ranges:
        # entry has line_start, line_end (0-indexed usually from split? need to check build_page_map)
        # build_page_map uses enumerate(lines), so 0-indexed.
        # parsers usually give 0-indexed or 1-indexed? MarkdownIt gives 0-indexed map.
        
        # Range overlap: max(start1, start2) < min(end1, end2)
        # Using 0-indexed half-open intervals [start, end)
        
        chunk_s = line_start
        chunk_e = line_end
        
        page_s = entry["line_start"]
        page_e = entry["line_end"]
        
        # Check overlap
        if max(chunk_s, page_s) < min(chunk_e, page_e):
             pages.add(entry["page"])
             
    return sorted(list(pages))

def clean_page_markers(text: str) -> str:
    """
    Removes <!-- PAGE X --> markers so they don't interfere with embeddings.
    """
    cleaned = PAGE_MARKER_RE.sub('', text)
    # Clean up any double spaces that might result from marker removal
    cleaned = re.sub(r'(?<=\S)  +', ' ', cleaned)
    return cleaned.strip()

def clean_markdown_for_breadcrumb(text: str) -> str:
    """
    Strips markdown links and images from text for clean breadcrumb display.
    """
    if not text:
        return text
    
    # Strip markdown images: ![alt text](url) -> alt text
    text = re.sub(r'!\[([^\]]*)\]\([^\)]*\)', r'\1', text)
    
    # Strip markdown links: [link text](url) -> link text
    text = re.sub(r'\[([^\]]*)\]\([^\)]*\)', r'\1', text)
    
    # Clean up any extra whitespace that may have been introduced
    text = ' '.join(text.split())
    
    return text.strip()

def token_count(text: str, settings: ChunkerSettings) -> int:
    """Estimates token count, using tokenizer if available."""
    if not text:
        return 0
    try:
        tokenizer = settings.get_tokenizer()
        if tokenizer:
            # Handle tiktoken vs transformers interface
            if hasattr(tokenizer, 'encode'):
                # Try tiktoken style (no add_special_tokens)
                try:
                    return len(tokenizer.encode(text))
                except TypeError:
                    # Fallback to transformers style
                    return len(tokenizer.encode(text, add_special_tokens=False))
    except Exception as e:
        logger.warning(f"Tokenizer failed, using char fallback: {e}")
    # Rough fallback if tokenizer is missing or fails (4 chars per token heuristic)
    return len(text) // 4

def truncate_to_embedding_limit(text: str, settings: ChunkerSettings) -> str:
    """Truncate text to the embedding token limit, preserving sentences when possible."""
    if not text:
        return text
    limit = getattr(settings, "embedding_max_tokens", None)
    if not limit:
        return text
    try:
        tokenizer = settings.get_tokenizer()
    except Exception:
        tokenizer = None
    if tokenizer:
        if token_count(text, settings) <= limit:
            return text
        sentences = split_sentences(text, settings)
        accumulated = []
        for sent in sentences:
            test_text = "".join(accumulated) + sent
            try:
                test_tokens = len(tokenizer.encode(test_text)) if hasattr(tokenizer, "encode") else len(test_text) // 4
            except Exception:
                test_tokens = len(test_text) // 4
            if test_tokens <= limit:
                accumulated.append(sent)
            else:
                break
        if accumulated:
            return "".join(accumulated)
        try:
            tokens = tokenizer.encode(text)[:limit]
            return tokenizer.decode(tokens)
        except Exception:
            return text[:limit * 4]
    # Fallback: approximate by chars
    if len(text) // 4 <= limit:
        return text
    return text[:limit * 4]

def add_overlap_to_chunk(out: List[str], new_chunk: str, settings: ChunkerSettings) -> str:
    """Adds overlap from previous chunk to maintain context continuity."""
    if not out or settings.overlap_tokens <= 0:
        return new_chunk
    last_chunk = out[-1]
    try:
        tokenizer = settings.get_tokenizer()
        if tokenizer:
            # Handle tiktoken vs transformers interface
            if hasattr(tokenizer, 'encode'):
                try:
                    tokens = tokenizer.encode(last_chunk)
                except TypeError:
                    tokens = tokenizer.encode(last_chunk, add_special_tokens=False)
            
            if len(tokens) > settings.overlap_tokens:
                # Decode the overlap tokens
                overlap_ids = tokens[-settings.overlap_tokens:]
                if hasattr(tokenizer, 'decode'):
                    try:
                        # tiktoken decode takes only tokens
                        overlap = tokenizer.decode(overlap_ids).strip()
                    except TypeError:
                        # transformers decode takes tokens and optional args
                        overlap = tokenizer.decode(overlap_ids, skip_special_tokens=True).strip()
                
                # SENTENCE BOUNDARY DETECTION
                sentences = split_sentences(overlap, settings)
                
                if len(sentences) > 1:
                    overlap = " ".join(sentences[1:])
                else:
                    # Only one sentence segment found. It might be a fragment.
                    if overlap and overlap[0].islower():
                        # Find first word boundary (space) in overlap
                        first_space = overlap.find(' ')
                        if first_space > 0:
                            overlap = overlap[first_space + 1:].strip()
                        elif first_space == -1:
                            overlap = ""
            else:
                overlap = last_chunk
        else:
            # Char fallback: last N sentences
            sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(last_chunk) if s.strip()]
            overlap = " ".join(sentences[-settings.overlap_sentences:]) if len(sentences) > settings.overlap_sentences else last_chunk
        
        # Only add overlap if it's non-empty
        if overlap:
            return f"{overlap} {new_chunk}".strip()
        else:
            return new_chunk
    except Exception as e:
        logger.warning(f"Error adding overlap, using chunk as-is: {e}")
        return new_chunk

def split_sentences(text: str, settings: ChunkerSettings) -> List[str]:
    """
    Split text into sentences using pysbd if available, otherwise use regex.
    """
    segmenter = settings.get_segmenter()
    if segmenter:  # Use factory-loaded instance
        try:
            sentences = segmenter.segment(text)
            return [s.strip() for s in sentences if s.strip()]
        except Exception as e:
            logger.warning(f"pysbd sentence splitting failed, using regex fallback: {e}")
            # Fall through to regex
    
    # Regex fallback
    return [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]

# ============================================================================
# DOCUMENT ROUTING
# ============================================================================

def build_page_map(content: str) -> Dict[str, Any]:
    """
    Build a map of text positions to page numbers before markdown parsing.
    """
    page_map: Dict[str, Any] = {"page_ranges": [], "has_pages": False}
    
    # Find all page markers with their positions
    lines = content.split('\n')
    page_starts = []  # [(line_idx, page_number), ...]
    
    for idx, line in enumerate(lines):
        match = PAGE_MARKER_RE.search(line)
        if match:
            page_num = int(match.group(1))
            page_starts.append((idx, page_num))
            page_map["has_pages"] = True
    
    if not page_starts:
        return page_map
    
    # Build ranges for each page
    for i, (start_idx, page_num) in enumerate(page_starts):
        # Determine end of this page (start of next page, or end of document)
        if i + 1 < len(page_starts):
            end_idx = page_starts[i + 1][0]
        else:
            end_idx = len(lines)
        
        # Collect substantial text from this page
        page_text_lines = []
        for line_idx in range(start_idx + 1, min(start_idx + 50, end_idx)):  # Look ahead max 50 lines
            clean_line = lines[line_idx].strip()
            # Skip headers, short lines, and markers
            if clean_line and not clean_line.startswith('#') and len(clean_line) > 20:
                page_text_lines.append(clean_line)
                if len(page_text_lines) >= 5:  # Collect ~5 good lines
                    break
        
        if page_text_lines:
            # Use first 100 chars as start marker
            start_text = ' '.join(page_text_lines[:2])[:100].strip()
            # Use last 100 chars as potential end marker (for spanning detection)
            end_text = ' '.join(page_text_lines[-2:])[:100].strip()
            
            page_map["page_ranges"].append({
                "page": page_num,
                "start_text": start_text,
                "end_text": end_text,
                "line_start": start_idx,
                "line_end": end_idx
            })
    
    return page_map

def chunk_document(content: str, url: str, settings: ChunkerSettings) -> List[Chunk]:
    """
    Main entry point for chunking. Correctly routes to markdown or code parsers.
    """
    # Import here to avoid circular imports (these modules import from utils)
    from .code_parser import EXTENSION_MAP, parse_raw_code
    from .ast_parser import markdown_ast_chunker
    
    # Build page map BEFORE parsing (markdown parser strips HTML comments)
    page_map = build_page_map(content)
    
    # Store page map in settings for chunk_factory to access
    settings._page_map = page_map
    
    # 1. Get extension
    ext = url.split('.')[-1].lower() if '.' in url else ""
    
    # 2. Check if it's a code file supported by our parser
    if ext in EXTENSION_MAP:
        # Use the Raw Code Parser (No fences, smart grouping)
        return parse_raw_code(content, url, settings)
    else:
        # Default to Markdown Parser (Handles .md, .txt, or unknown)
        return markdown_ast_chunker(content, url, settings)
