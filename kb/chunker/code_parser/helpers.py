# chunker/code_parser/helpers.py
"""
Helper utilities for code parsing - span tracking, naming, metadata.
"""
from __future__ import annotations

import re
from typing import List, Dict, Any, Tuple, Optional

from .symbol_extraction import (
    extract_symbols_from_node,
    extract_comments_from_node,
    extract_references_from_node,
)
from .compat import K


def get_span(ctx, code_bytes: bytes, byte_to_char: Dict, start_byte: int, end_byte: int) -> Tuple[str, int, int]:
    """
    Get original text and char offsets, including gap since last emit.
    Returns (original_text, char_start, char_end).
    """
    last_end = getattr(ctx, "_last_byte_end", 0) or 0
    gap_start = min(last_end, start_byte)
    
    gap_text = code_bytes[gap_start:start_byte].decode("utf8", errors="replace") if start_byte > gap_start else ""
    raw_text = code_bytes[start_byte:end_byte].decode("utf8", errors="replace")
    original_text = gap_text + raw_text
    
    char_start = byte_to_char.get(gap_start, len(code_bytes[:gap_start].decode("utf8", errors="replace")))
    char_end = byte_to_char.get(end_byte, len(code_bytes[:end_byte].decode("utf8", errors="replace")))
    
    ctx._last_byte_end = end_byte
    return original_text, char_start, char_end


def get_node_name(node, code_bytes: bytes, ctx) -> str:
    """Extract name from a node (function name, class name, etc.)."""
    # Unwrap decorators/exports
    target = node
    if node.type == "decorated_definition":
        definition = node.child_by_field_name("definition")
        if definition:
            target = definition
    elif node.type == "export_statement":
        declaration = node.child_by_field_name("declaration")
        if declaration:
            target = declaration
    
    name_node = target.child_by_field_name("name")
    if name_node:
        return code_bytes[name_node.start_byte:name_node.end_byte].decode("utf8", errors="replace")
    
    # Try HTML id/class
    if node.type in ("element", "script_element", "style_element", "jsx_element"):
        return get_html_element_name(node, code_bytes, ctx)
    
    return f"Block_{ctx.global_index}"


def get_html_element_name(node, code_bytes: bytes, ctx) -> str:
    """Extract name from HTML element (id or class)."""
    if node.child_count < 1:
        return f"Block_{ctx.global_index}"
    
    start_tag = node.children[0]
    if "start_tag" not in start_tag.type and "opening_element" not in start_tag.type:
        return f"Block_{ctx.global_index}"
    
    tag_text = code_bytes[start_tag.start_byte:start_tag.end_byte].decode("utf8", errors="replace")
    
    id_match = re.search(r'\bid=["\']([^"\']+)["\']', tag_text)
    if id_match:
        tag_name = tag_text.split()[0].replace("<", "")
        return f"{tag_name}#{id_match.group(1)}"
    
    class_match = re.search(r'\bclass(?:Name)?=["\']([^"\']+)["\']', tag_text)
    if class_match:
        tag_name = tag_text.split()[0].replace("<", "")
        return f"{tag_name}.{class_match.group(1).split()[0]}"
    
    tag_name = tag_text.split()[0].replace("<", "").rstrip(">")
    return f"{tag_name}_{ctx.global_index}"


def infer_group_name(nodes, ctx) -> str:
    """Infer a name for a group of nodes."""
    for n in nodes:
        if "comment" not in n.type:
            first_type = n.type
            if "import" in first_type:
                return "Imports"
            elif "export" in first_type:
                return "Exports"
            elif "assignment" in first_type or "variable" in first_type or "lexical" in first_type:
                return "Constants"
            break
    return f"Block_{ctx.global_index}"


def get_child_text_with_indent(child, code_bytes: bytes) -> str:
    """Get child node text preserving leading whitespace."""
    child_start = child.start_byte
    line_start = child_start
    while line_start > 0 and code_bytes[line_start - 1:line_start] not in (b'\n', b'\r'):
        line_start -= 1
    
    leading_ws = code_bytes[line_start:child_start].decode("utf8", errors="replace")
    node_text = code_bytes[child_start:child.end_byte].decode("utf8", errors="replace")
    
    lines = node_text.split('\n')
    if lines:
        lines[0] = leading_ws + lines[0]
    return '\n'.join(lines)


def get_footer(node, code_bytes: bytes) -> str:
    """Get closing element for HTML-like nodes."""
    if node.type in ("element", "script_element", "style_element", "jsx_element"):
        if node.child_count >= 2:
            end_tag = node.children[-1]
            if "end_tag" in end_tag.type or "closing_element" in end_tag.type:
                return code_bytes[end_tag.start_byte:end_tag.end_byte].decode("utf8", errors="replace").strip()
    return ""


def extract_metadata_from_node(node, code_bytes: bytes) -> Tuple[List, str, List]:
    """Extract symbols, comments, refs from a single node."""
    symbols = extract_symbols_from_node(node, code_bytes)
    comments = extract_comments_from_node(node, code_bytes)
    refs = extract_references_from_node(node, code_bytes)
    return symbols, comments, dedupe_refs(refs)


def extract_metadata_from_nodes(nodes, code_bytes: bytes) -> Tuple[List, str, List]:
    """Extract metadata from multiple nodes."""
    all_symbols = []
    all_comments = []
    all_refs = []
    
    for n in nodes:
        all_symbols.extend(extract_symbols_from_node(n, code_bytes))
        c = extract_comments_from_node(n, code_bytes)
        if c:
            all_comments.append(c)
        all_refs.extend(extract_references_from_node(n, code_bytes))
    
    return all_symbols, "\n".join(all_comments), dedupe_refs(all_refs)


def dedupe_refs(refs: List[Dict]) -> List[Dict]:
    """Deduplicate references by name."""
    seen = set()
    unique = []
    for ref in refs:
        if ref["name"] not in seen:
            seen.add(ref["name"])
            unique.append(ref)
    return unique


def add_code_metadata(chunk, lang: str, symbols, refs, comments, is_split: bool = False):
    """Add code-specific metadata to a chunk."""
    chunk.metadata.update({
        K.META_LANGUAGE: lang,
        K.META_SYMBOLS: symbols,
        K.META_SYMBOLS_REF: refs,
        K.META_COMMENTS: comments,
    })
    if is_split:
        chunk.metadata["is_split_part"] = True
