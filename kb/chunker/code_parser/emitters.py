# chunker/code_parser/emitters.py
"""
Chunk emission functions for code parsing.
Handles creating chunks from AST nodes with proper span tracking.
"""
from __future__ import annotations

import textwrap
from typing import List, Dict, Optional

from ..config import ChunkerSettings
from ..core import ChunkType, ProcessingContext, Chunk
from ..utils import token_count

from .constants import BRACE_LANGUAGES
from .compat import K
from .helpers import (
    get_span,
    get_node_name,
    infer_group_name,
    get_child_text_with_indent,
    get_footer,
    extract_metadata_from_node,
    extract_metadata_from_nodes,
    add_code_metadata,
)


def emit_group(nodes, code_bytes: bytes, byte_to_char: Dict, out_chunks: List[Chunk],
               lang: str, settings: ChunkerSettings, ctx: ProcessingContext):
    """Emit a group of small nodes as one chunk."""
    if not nodes:
        return
    
    text = code_bytes[nodes[0].start_byte:nodes[-1].end_byte].decode("utf8", errors="replace")
    name = infer_group_name(nodes, ctx)
    symbols, comments, refs = extract_metadata_from_nodes(nodes, code_bytes)
    original_text, char_start, char_end = get_span(ctx, code_bytes, byte_to_char, 
                                                    nodes[0].start_byte, nodes[-1].end_byte)
    
    ctx.push_heading(1, name)
    chunk = ctx.create_chunk(
        text=text,
        chunk_type=ChunkType.CODE,
        line_start=nodes[0].start_point[0],
        line_end=nodes[-1].end_point[0] + 1,
        original_text=original_text,
        char_start=char_start,
        char_end=char_end,
    )
    
    if chunk:
        add_code_metadata(chunk, lang, symbols, refs, comments)
        out_chunks.append(chunk)


def emit_simple_node(node, text: str, name: str, start_byte: int, 
                     code_bytes: bytes, byte_to_char: Dict, out_chunks: List[Chunk],
                     lang: str, ctx: ProcessingContext):
    """Emit a node that fits within token limit."""
    symbols, comments, refs = extract_metadata_from_node(node, code_bytes)
    original_text, char_start, char_end = get_span(ctx, code_bytes, byte_to_char, 
                                                    start_byte, node.end_byte)
    
    ctx.push_heading(1, name)
    chunk = ctx.create_chunk(
        text=text,
        chunk_type=ChunkType.CODE,
        line_start=node.start_point[0],
        line_end=node.end_point[0] + 1,
        original_text=original_text,
        char_start=char_start,
        char_end=char_end,
    )
    
    if chunk:
        add_code_metadata(chunk, lang, symbols, refs, comments)
        out_chunks.append(chunk)


def emit_split_part(stmts: List[str], sig: str, footer: str, name: str, 
                   part_num: int, symbols, refs, comments, start_byte: int, end_byte: int,
                   needs_braces: bool, code_bytes: bytes, byte_to_char: Dict,
                   out_chunks: List[Chunk], lang: str, ctx: ProcessingContext):
    """Emit a split part of a function/class."""
    body_text = "\n".join(stmts)
    
    if footer:
        part_text = f"{sig}\n    # ... (Part {part_num})\n{body_text}\n{footer}"
    elif needs_braces:
        clean_sig = sig.rstrip("{").strip()
        part_text = f"{clean_sig} {{\n    // ... (Part {part_num})\n{body_text}\n}}"
    else:
        part_text = f"{sig}\n    # ... (Part {part_num})\n{body_text}"
    
    original_text, char_start, char_end = get_span(ctx, code_bytes, byte_to_char, start_byte, end_byte)
    
    # Calculate line numbers from byte offsets
    # Count newlines in the code up to start_byte and end_byte
    line_start = code_bytes[:start_byte].count(b'\n')
    line_end = code_bytes[:end_byte].count(b'\n') + 1
    
    ctx.push_heading(1, name)
    ctx.push_heading(2, f"Part {part_num}")
    
    chunk = ctx.create_chunk(
        text=part_text,
        chunk_type=ChunkType.CODE,
        line_start=line_start,
        line_end=line_end,
        original_text=original_text,
        char_start=char_start,
        char_end=char_end,
    )
    
    if chunk:
        add_code_metadata(chunk, lang, symbols, refs, comments, is_split=True)
        out_chunks.append(chunk)


def emit_line_split(node, name: str, code_bytes: bytes, byte_to_char: Dict,
                   out_chunks: List[Chunk], lang: str, settings: ChunkerSettings, 
                   ctx: ProcessingContext, max_tokens: int):
    """Fallback: Split node by lines when no structure available."""
    symbols, comments, refs = extract_metadata_from_node(node, code_bytes)
    
    node_bytes = code_bytes[node.start_byte:node.end_byte]
    lines = node_bytes.splitlines(keepends=True)
    
    parts: List[tuple] = []  # (text, start_byte, end_byte)
    current_lines: List[str] = []
    current_tokens = 0
    offset = 0
    current_start = node.start_byte
    current_end = node.start_byte
    
    for line in lines:
        line_text = line.decode("utf8", errors="replace")
        line_tokens = token_count(line_text, settings)
        line_start = node.start_byte + offset
        line_end = line_start + len(line)
        
        if current_tokens + line_tokens > max_tokens and current_lines:
            indent = len(line_text) - len(line_text.lstrip())
            if indent <= 4 or current_tokens > max_tokens * 0.8:
                parts.append(("".join(current_lines), current_start, current_end))
                current_lines = [line_text]
                current_start = line_start
                current_end = line_end
                current_tokens = line_tokens
                offset += len(line)
                continue
        
        if not current_lines:
            current_start = line_start
        current_lines.append(line_text)
        current_end = line_end
        current_tokens += line_tokens
        offset += len(line)
    
    if current_lines:
        parts.append(("".join(current_lines), current_start, current_end))
    
    # Emit parts
    for i, (part_text, part_start, part_end) in enumerate(parts):
        original_text, char_start, char_end = get_span(ctx, code_bytes, byte_to_char, part_start, part_end)
        
        ctx.push_heading(1, name)
        ctx.push_heading(2, f"Part {i+1}")
        
        chunk = ctx.create_chunk(
            text=textwrap.dedent(part_text).strip(),
            chunk_type=ChunkType.CODE,
            line_start=node.start_point[0],
            line_end=node.end_point[0] + 1,
            original_text=original_text,
            char_start=char_start,
            char_end=char_end,
        )
        
        if chunk:
            add_code_metadata(chunk, lang, symbols, refs, comments, is_split=True)
            out_chunks.append(chunk)
