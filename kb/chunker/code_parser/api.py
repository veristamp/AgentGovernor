# chunker/code_parser/api.py
"""
Standalone API functions for code parsing.
Used by markdown parser for code blocks.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional
from config import get_logger

try:
    from tree_sitter_language_pack import get_parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ..config import ChunkerSettings
from ..core import ChunkType
from ..utils import token_count

from .constants import EXTENSION_MAP
from .symbol_extraction import (
    extract_symbols_from_node,
    extract_comments_from_node,
    extract_references_from_node,
)
from .compat import K

logger = get_logger("chunker.code_parser.api")

def treesitter_chunk_code(code: str, lang: str, settings: ChunkerSettings) -> Optional[List[str]]:
    """
    Used by Markdown parser to split code blocks.
    Returns list of text chunks (no metadata).
    """
    if not TREE_SITTER_AVAILABLE or not settings.use_treesitter:
        return None
    
    ts_lang = EXTENSION_MAP.get(lang.lower())
    if not ts_lang:
        return None
    
    try:
        code_bytes = bytes(code, "utf8")
        parser = get_parser(ts_lang)
        tree = parser.parse(code_bytes)
        
        max_t = settings.max_tokens_by_type.get(ChunkType.CODE.value, settings.max_tokens_text)
        chunks = []
        current_nodes = []
        current_tokens = 0
        
        for node in tree.root_node.children:
            node_text = code_bytes[node.start_byte:node.end_byte].decode("utf8", errors="replace")
            t = token_count(node_text, settings)
            
            if current_tokens + t > max_t and current_nodes:
                start = current_nodes[0].start_byte
                end = current_nodes[-1].end_byte
                chunks.append(code_bytes[start:end].decode("utf8", errors="replace"))
                current_nodes = [node]
                current_tokens = t
            else:
                current_nodes.append(node)
                current_tokens += t
        
        if current_nodes:
            start = current_nodes[0].start_byte
            end = current_nodes[-1].end_byte
            chunks.append(code_bytes[start:end].decode("utf8", errors="replace"))
        
        return chunks
    except Exception as e:
        logger.debug(f"Tree-sitter chunking failed: {e}")
        return None

def extract_code_block_metadata(code: str, lang: str) -> Dict[str, Any]:
    """
    Extract metadata from a markdown code block.
    Returns symbols, references, and comments.
    """
    result = {
        K.META_SYMBOLS: [],
        K.META_SYMBOLS_REF: [],
        K.META_COMMENTS: "",
    }
    
    if not code or not lang or not TREE_SITTER_AVAILABLE:
        return result
    
    ts_lang = EXTENSION_MAP.get(lang.lower()) or lang.lower()
    
    try:
        parser = get_parser(ts_lang)
        code_bytes = bytes(code, "utf8")
        tree = parser.parse(code_bytes)
        
        all_symbols = []
        all_comments = []
        all_refs = []
        
        for node in tree.root_node.children:
            all_symbols.extend(extract_symbols_from_node(node, code_bytes))
            c = extract_comments_from_node(node, code_bytes)
            if c:
                all_comments.append(c)
            all_refs.extend(extract_references_from_node(node, code_bytes))
        
        # Dedupe refs
        seen = set()
        unique_refs = [r for r in all_refs if r["name"] not in seen and not seen.add(r["name"])]
        
        result[K.META_SYMBOLS] = all_symbols
        result[K.META_SYMBOLS_REF] = unique_refs
        result[K.META_COMMENTS] = "\n".join(all_comments)
    except Exception as e:
        logger.debug(f"Metadata extraction failed for {lang}: {e}")
    
    return result
