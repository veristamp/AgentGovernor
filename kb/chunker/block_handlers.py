# chunker/block_handlers.py
"""Handlers for code blocks and table processing."""

from __future__ import annotations

from typing import List

from .config import ChunkerSettings
from .core import ChunkType
from .utils import token_count
from .code_parser import treesitter_chunk_code
from config import get_logger

# Configure logging
logger = get_logger("chunker.block_handlers")

def split_code_block_to_chunks(
    code_text: str, 
    fence: str, 
    info: str, 
    max_lines: int, 
    settings: ChunkerSettings,
    default_lang: str = ""
) -> List[str]:
    """Split long code blocks by semantics (Tree-sitter) or line count.
    
    Args:
        code_text: The raw code content (without fences)
        fence: The fence style (e.g., "```")
        info: The info string from the fence (e.g., "python" from ```python)
        max_lines: Maximum lines before splitting
        settings: Chunker configuration
        default_lang: Fallback language if info is empty (e.g., from file extension)
    """
    
    # 1. Try Tree-sitter first
    # Extract language from info string (e.g., "python" from "```python")
    # If empty, use default_lang (typically inferred from file extension)
    lang = info.split()[0].strip() if info else default_lang
    
    # Use lang for fence wrapping (more accurate than raw info which might be empty)
    fence_lang = lang if lang else info

    # 1. Check if code already fits in a single chunk (both line count AND token count)
    # If it fits, we return it AS-IS without any processing (Tree-sitter or line-based)
    # This is critical for document reconstruction fidelity.
    lines = code_text.splitlines()
    max_t = settings.max_tokens_by_type.get(ChunkType.CODE.value, settings.max_tokens_text)
    
    if len(lines) <= max_lines:
        full_chunk = f"{fence}{fence_lang}\n{code_text}\n{fence}"
        if token_count(full_chunk, settings) <= max_t:
            return [full_chunk]

    # 2. Try Tree-sitter for large blocks
    if lang and settings.use_treesitter:
        ts_chunks = treesitter_chunk_code(code_text, lang, settings)
        if ts_chunks:
            # Wrap chunks in fences and return
            return [f"{fence}{fence_lang}\n{chunk}\n{fence}" for chunk in ts_chunks]

    # 3. Line-Based Fallback for large blocks where Tree-sitter fails or is disabled
    # Indentation-aware splitting to avoid breaking mid-block
    parts: List[str] = []
    i = 0
    while i < len(lines):
        chunk_lines = []
        line_count = 0
        
        while i < len(lines) and line_count < max_lines:
            chunk_lines.append(lines[i])
            line_count += 1
            i += 1
            
            # If we're at max_lines, check if next line is indented
            # (likely continuation of a block). If so, include it.
            if line_count >= max_lines and i < len(lines):
                current_indent = len(lines[i]) - len(lines[i].lstrip())
                # If next line is indented, we might be mid-block
                if current_indent > 0 and i > 0:
                    prev_indent = len(lines[i-1]) - len(lines[i-1].lstrip())
                    # Continue if indentation suggests we're in a block
                    if current_indent >= prev_indent and prev_indent > 0:
                        continue  # Don't break yet
                break
        
        piece = "\n".join(chunk_lines)
        chunk_text = f"{fence}{fence_lang}\n{piece}\n{fence}"
        parts.append(chunk_text)

    # Check if any parts exceed token limits and fallback to token-based splitting if needed
    final_parts: List[str] = []
    for part in parts:
        if token_count(part, settings) <= max_t:
            final_parts.append(part)
        else:
            # Fallback to token-based splitting for this oversized part
            # Token-aware splitting that respects line boundaries to preserve syntax
            tokenizer = settings.get_tokenizer()
            current_chunk_lines = []
            current_tokens = 0
            
            # Split the oversized part into lines again
            inner_lines = part.strip(fence).strip().splitlines()
            
            for line in inner_lines:
                # Add newline to token count estimate if not first line
                line_with_newline = line + "\n"
                line_tokens = 0
                if tokenizer:
                    try:
                        # tiktoken style
                        line_tokens = len(tokenizer.encode(line_with_newline))
                    except TypeError:
                        # transformers style
                        line_tokens = len(tokenizer.encode(line_with_newline, add_special_tokens=False))
                else:
                    # Rough char fallback if no tokenizer
                    line_tokens = len(line_with_newline) // 4
                
                # If adding this line exceeds limit, flush buffer
                if current_tokens + line_tokens > max_t and current_chunk_lines:
                    piece_text = "\n".join(current_chunk_lines)
                    final_parts.append(f"{fence}{fence_lang}\n{piece_text}\n{fence}")
                    current_chunk_lines = []
                    current_tokens = 0
                
                # Check if single line is huge (rare edge case)
                if line_tokens > max_t:
                     # Hard split extremely long line
                     if tokenizer:
                         try:
                             # tiktoken style
                             long_tokens = tokenizer.encode(line)
                         except TypeError:
                             # transformers style
                             long_tokens = tokenizer.encode(line, add_special_tokens=False)
                         
                         for k in range(0, len(long_tokens), max_t):
                             chunk_tokens = long_tokens[k:k+max_t]
                             try:
                                 # tiktoken style
                                 chunk_text = tokenizer.decode(chunk_tokens)
                             except TypeError:
                                 # transformers style
                                 chunk_text = tokenizer.decode(chunk_tokens, skip_special_tokens=True)
                             final_parts.append(f"{fence}{fence_lang}\n{chunk_text}\n{fence}")
                     else:
                         for k in range(0, len(line), settings.max_chars_fallback):
                             final_parts.append(f"{fence}{fence_lang}\n{line[k:k+settings.max_chars_fallback]}\n{fence}")
                     current_chunk_lines = []
                     current_tokens = 0
                     continue

                current_chunk_lines.append(line)
                current_tokens += line_tokens
                
            # Flush remaining
            if current_chunk_lines:
                piece_text = "\n".join(current_chunk_lines)
                final_parts.append(f"{fence}{fence_lang}\n{piece_text}\n{fence}")

    return final_parts

def extract_table_markdown(
    md_lines: List[str], 
    start: int, 
    end: int, 
    split_rows: int, 
    settings: ChunkerSettings
) -> List[str]:
    """Extract table markdown and split into smaller tables by row count with token limit checks."""
    table_md = "\n".join(md_lines[start:end]).strip()
    rows = [r for r in table_md.splitlines() if r.strip()]
    if len(rows) <= split_rows or split_rows <= 0:
        return [table_md]

    # Use content-type-specific token limits
    max_t = settings.max_tokens_by_type.get(ChunkType.TABLE.value, settings.max_tokens_text)

    # Try to keep the header and delimiter with each slice
    # IMPROVED: More robust delimiter detection using multiple heuristics
    # (handles messy markdown with blank lines/comments before table header)
    header = []
    delimiter_row = None
    body_start_idx = 0
    
    def is_table_delimiter(row: str) -> bool:
        """
        Robust table delimiter detection using multiple heuristics.
        Handles various edge cases like pipes inside cells, missing outer pipes, etc.
        """
        stripped = row.strip()
        if not stripped:
            return False
        
        # Remove outer pipes if present
        if stripped.startswith('|'):
            stripped = stripped[1:]
        if stripped.endswith('|'):
            stripped = stripped[:-1]
        
        # Split by pipes to check each cell
        cells = [c.strip() for c in stripped.split('|')]
        
        # Heuristic 1: At least one cell should be mostly dashes
        has_dash_cell = False
        for cell in cells:
            if not cell:
                continue
            # Count dashes and colons (alignment markers)
            dash_colon_count = sum(1 for c in cell if c in '-:')
            # If > 70% of characters are dashes/colons, likely a delimiter
            if len(cell) > 0 and dash_colon_count / len(cell) > 0.7:
                has_dash_cell = True
                break
        
        if not has_dash_cell:
            return False
        
        # Heuristic 2: All cells should only contain -, :, and spaces
        for cell in cells:
            if not cell:
                continue
            # Check if cell only contains delimiter characters
            if not all(c in '-: ' for c in cell):
                return False
        
        # Heuristic 3: At least one cell must have consecutive dashes
        has_consecutive_dashes = False
        for cell in cells:
            if '--' in cell or '---' in cell:
                has_consecutive_dashes = True
                break
        
        return has_consecutive_dashes
    
    for i, r in enumerate(rows):  # Search through ALL rows
        if is_table_delimiter(r):
            # Found delimiter! Header is everything before it
            delimiter_row = r
            header = rows[:i] if i > 0 else []  # lines before delimiter are header
            # Include delimiter in header for reconstruction
            if delimiter_row:
                header.append(delimiter_row)
            body_start_idx = i + 1
            break
    
    # Fallback: If no delimiter found, try to intelligently detect table structure
    if delimiter_row is None:
        logger.warning("No table delimiter found using heuristics, trying fallback detection")
        # Look for rows with pipes as potential table rows
        table_rows = [r for r in rows if '|' in r]
        if table_rows:
            # Assume first row is header, create synthetic delimiter
            header = [table_rows[0]]
            # Count pipes to determine column count
            pipe_count = table_rows[0].count('|')
            # Create a basic delimiter row
            delimiter_row = '|' + '---|' * (pipe_count - 1) if pipe_count > 1 else '|---|'
            header.append(delimiter_row)
            body_start_idx = 1
        else:
            # Last resort: treat everything as one chunk
            logger.warning("Could not parse table structure, returning as single chunk")
            return [table_md]

    body = rows[body_start_idx:]
    parts = []
    for i in range(0, len(body), split_rows):
        chunk_rows = header + body[i:i + split_rows]
        parts.append("\n".join(chunk_rows))

    # Check token limits and apply fallback if needed
    final_parts: List[str] = []
    for part in parts:
        if token_count(part, settings) <= max_t:
            final_parts.append(part)
        else:
            # Fallback to row-by-row splitting for oversized tables
            current_table = []
            current_tokens_estimate = 0  # Use estimate for fast path
            
            for row in header + body:
                # OPTIMIZATION: Use fast character-based estimation first
                # Only call expensive tokenizer when close to limit
                row_chars = len(row)
                row_est_tokens = row_chars // 4  # ~4 chars per token heuristic
                
                # Fast path: If we're nowhere near the limit, use estimation
                safety_margin = getattr(settings, 'token_safety_margin', 0.85)
                if current_tokens_estimate + row_est_tokens <= max_t * safety_margin:
                    current_table.append(row)
                    current_tokens_estimate += row_est_tokens
                else:
                    # Slow path: Getting close to limit, need exact count
                    row_text = "\n".join(current_table + [row])
                    exact_tokens = token_count(row_text, settings)
                    
                    if exact_tokens <= max_t:
                        current_table.append(row)
                        current_tokens_estimate = exact_tokens  # Update with exact count
                    else:
                        # Flush current table and start new one
                        if current_table:
                            final_parts.append("\n".join(current_table))
                        
                        # Check if single row is too large
                        single_row_tokens = token_count(row, settings)
                        if single_row_tokens > max_t:
                            # Single row exceeds limit, split it
                            tokenizer = settings.get_tokenizer()
                            if tokenizer:
                                try:
                                    try:
                                        # tiktoken style
                                        row_tokens_encoded = tokenizer.encode(row)
                                    except TypeError:
                                        # transformers style
                                        row_tokens_encoded = tokenizer.encode(row, add_special_tokens=False)

                                    for j in range(0, len(row_tokens_encoded), max_t):
                                        row_chunk_tokens = row_tokens_encoded[j:j + max_t]
                                        try:
                                            # tiktoken style
                                            piece = tokenizer.decode(row_chunk_tokens)
                                        except TypeError:
                                            # transformers style
                                            piece = tokenizer.decode(row_chunk_tokens, skip_special_tokens=True)
                                        final_parts.append(piece)
                                except Exception as e:
                                    logger.warning(f"Token-based row splitting failed, using char fallback: {e}")
                                    for j in range(0, len(row), settings.max_chars_fallback):
                                        final_parts.append(row[j:j + settings.max_chars_fallback])
                            else:
                                for j in range(0, len(row), settings.max_chars_fallback):
                                    final_parts.append(row[j:j + settings.max_chars_fallback])
                            current_table = []
                            current_tokens_estimate = 0
                        else:
                            # Start new table with this row
                            current_table = [row]
                            current_tokens_estimate = single_row_tokens
            
            if current_table:
                final_parts.append("\n".join(current_table))

    return final_parts
