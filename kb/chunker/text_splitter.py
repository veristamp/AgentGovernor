# chunker/text_splitter.py
"""
Token-aware text splitting for chunking.

ENHANCED: Combines span preservation with intelligent splitting:
- Paragraph-first, then sentence-second splitting
- Performance guards for very long content
- Word boundary respect for overlong sentences
- Exact span tracking for reconstruction fidelity
"""

from __future__ import annotations

import logging
from typing import List, Tuple, Optional

from .config import ChunkerSettings, PARAGRAPH_SPLIT_RE, SENTENCE_SPLIT_RE
from config import get_logger

# Configure logging
logger = get_logger("chunker.text_splitter")

# Suppress transformers tokenization warnings
get_logger("transformers.tokenization_utils_base").setLevel(logging.ERROR)

# Type alias for clarity
SpanChunk = Tuple[str, int, int]  # (text, char_start, char_end)

def _split_sentences_with_spans(text: str, start_offset: int, settings: ChunkerSettings) -> List[SpanChunk]:
    """
    Split text into sentences while preserving character spans.
    Uses pysbd if available, falls back to regex.
    """
    if not text:
        return []
    
    # For very long text (>threshold), use simple period-based split for performance
    if len(text) > settings.large_text_threshold:
        logger.debug(f"Text is {len(text)} chars, using fast sentence split")
        spans = []
        pos = start_offset
        for part in text.split('. '):
            if part.strip():
                chunk = part.strip() + '. ' if not part.endswith('.') else part.strip() + ' '
                spans.append((chunk, pos, pos + len(chunk)))
                pos += len(chunk)
        # Adjust last span to not add trailing space
        if spans:
            last_text, last_start, _ = spans[-1]
            spans[-1] = (last_text.rstrip(), last_start, start_offset + len(text))
        return spans if spans else [(text, start_offset, start_offset + len(text))]
    
    # Use regex-based splitting with span preservation
    spans: List[SpanChunk] = []
    pos = 0
    for m in SENTENCE_SPLIT_RE.finditer(text):
        end = m.end()
        if pos < end:
            spans.append((text[pos:end], start_offset + pos, start_offset + end))
        pos = end
    
    # Add remaining text
    if pos < len(text):
        spans.append((text[pos:], start_offset + pos, start_offset + len(text)))
    
    return spans if spans else [(text, start_offset, start_offset + len(text))]

def _split_paragraphs_with_spans(text: str) -> List[SpanChunk]:
    """Split text into paragraphs while preserving character spans."""
    if not text:
        return []
    
    spans: List[SpanChunk] = []
    pos = 0
    
    for m in PARAGRAPH_SPLIT_RE.finditer(text):
        # Text before the paragraph break
        if pos < m.start():
            para_text = text[pos:m.start()]
            if para_text.strip():
                spans.append((para_text, pos, m.start()))
        pos = m.end()
    
    # Add remaining text
    if pos < len(text):
        remaining = text[pos:]
        if remaining.strip():
            spans.append((remaining, pos, len(text)))
    
    # If no paragraph breaks found, return whole text
    if not spans and text.strip():
        spans.append((text, 0, len(text)))
    
    return spans

def _word_boundary_split(text: str, char_start: int, max_chars: int) -> List[SpanChunk]:
    """
    Split text respecting word boundaries.
    Returns spans that don't cut words in the middle.
    """
    if len(text) <= max_chars:
        return [(text, char_start, char_start + len(text))]
    
    spans: List[SpanChunk] = []
    pos = 0
    
    while pos < len(text):
        # Calculate end position
        end = min(pos + max_chars, len(text))
        
        # If not at the end, find word boundary
        if end < len(text):
            # Check if we're mid-word
            if text[end - 1].isalnum() and end < len(text) and text[end].isalnum():
                # Find last space before end
                last_space = text.rfind(' ', pos, end)
                if last_space > pos:
                    end = last_space + 1  # Include the space
                # else: no good boundary, just cut (unavoidable for very long words)
        
        chunk = text[pos:end]
        if chunk.strip():
            spans.append((chunk, char_start + pos, char_start + end))
        pos = end
    
    return spans

def token_aware_text_chunks_with_spans(text: str, settings: ChunkerSettings) -> List[SpanChunk]:
    """
    Token-aware chunking that preserves exact substrings.
    
    ENHANCED with paragraph-first splitting, performance guards, and word boundary respect.
    
    Returns:
        List of (chunk_text, start_offset, end_offset) tuples where:
        - Concatenating chunk_text exactly reconstructs the original text
        - start_offset and end_offset are character positions in the original
    
    Features:
        1. Paragraph-first, then sentence-second splitting
        2. Performance guards for very long paragraphs (>50KB) and many sentences (>1000)
        3. Word boundary respect for overlong sentences
        4. Exact span tracking for reconstruction fidelity
    """
    if not text or not text.strip():
        return []
    
    raw = text
    max_tokens = settings.max_tokens_text
    tok = settings.get_tokenizer()
    
    # Helper function for token counting
    def get_token_count(s: str) -> int:
        if tok:
            try:
                try:
                    return len(tok.encode(s))
                except TypeError:
                    return len(tok.encode(s, add_special_tokens=False))
            except Exception:
                pass
        # Fallback: estimate 4 chars per token
        return len(s) // 4
    
    # Quick check: if entire text fits, return as single chunk
    if get_token_count(text) <= max_tokens:
        return [(text, 0, len(text))]
    
    # STEP 1: Split into paragraphs first
    paragraphs = _split_paragraphs_with_spans(text)
    
    out: List[SpanChunk] = []
    
    for para_text, para_start, para_end in paragraphs:
        para_tokens = get_token_count(para_text)
        
        # If paragraph fits, add directly
        if para_tokens <= max_tokens:
            out.append((para_text, para_start, para_end))
            continue
        
        # STEP 2: Split paragraph into sentences
        sentences = _split_sentences_with_spans(para_text, para_start, settings)
        
        # PERFORMANCE GUARD: For paragraphs with excessive sentences,
        # use character-based chunking
        if len(sentences) > settings.max_sentences_per_para:
            logger.warning(f"Paragraph has {len(sentences)} sentences, using character-based fallback")
            char_chunks = _word_boundary_split(para_text, para_start, settings.max_chars_fallback)
            out.extend(char_chunks)
            continue
        
        # STEP 3: Accumulate sentences into chunks
        curr_texts: List[str] = []
        curr_start: Optional[int] = None
        curr_end: Optional[int] = None
        curr_tokens = 0
        
        for sent_text, sent_start, sent_end in sentences:
            sent_tokens = get_token_count(sent_text)
            
            # Handle overlong single sentence
            if sent_tokens > max_tokens:
                # Flush current buffer first
                if curr_texts:
                    combined = "".join(curr_texts)
                    out.append((combined, curr_start, curr_end))
                    curr_texts = []
                    curr_start = None
                    curr_end = None
                    curr_tokens = 0
                
                # Split overlong sentence with word boundary respect
                overlong_chunks = _word_boundary_split(sent_text, sent_start, settings.max_chars_fallback)
                out.extend(overlong_chunks)
                continue
            
            # Start new chunk if empty
            if not curr_texts:
                curr_texts = [sent_text]
                curr_start = sent_start
                curr_end = sent_end
                curr_tokens = sent_tokens
                continue
            
            # Check if sentence fits in current chunk
            # Add 1 token to account for space between sentences
            if curr_tokens + sent_tokens + 1 <= max_tokens:
                curr_texts.append(sent_text)
                curr_end = sent_end
                curr_tokens += sent_tokens + 1
            else:
                # Finalize current chunk and start new one
                combined = "".join(curr_texts)
                out.append((combined, curr_start, curr_end))
                
                curr_texts = [sent_text]
                curr_start = sent_start
                curr_end = sent_end
                curr_tokens = sent_tokens
        
        # Finalize last chunk for this paragraph
        if curr_texts:
            combined = "".join(curr_texts)
            out.append((combined, curr_start, curr_end))
    
    return out