# chunker/code_parser/chunker.py
"""
CodeChunker - Main class for tree-sitter based code parsing.
Mirrors MarkdownASTChunker design for consistency.
"""
from __future__ import annotations

from typing import List, Dict, Optional

from .compat import K, TREE_SITTER_AVAILABLE, get_parser, generate_stable_id
from .constants import EXTENSION_MAP, ATOMIC_TYPES, BRACE_LANGUAGES
from .helpers import (
    get_span,
    get_node_name,
    get_child_text_with_indent,
    get_footer,
    extract_metadata_from_node,
)
from .emitters import (
    emit_group,
    emit_simple_node,
    emit_split_part,
    emit_line_split,
)

from ..config import ChunkerSettings
from ..core import ChunkType, ProcessingContext, Chunk
from ..utils import token_count
from config import get_logger

logger = get_logger("chunker.code_parser.chunker")


class CodeChunker:
    """
    Tree-sitter based code chunker with structure-aware splitting.
    
    Usage:
        chunker = CodeChunker(code, "example.py", settings)
        chunks = chunker.chunk()
    """
    
    # Default thresholds (can be overridden via settings)
    DEFAULT_GROUP_LIMIT = 400
    DEFAULT_TINY_THRESHOLD = 100
    
    def __init__(self, code: str, source: str, settings: ChunkerSettings):
        self.code = code
        self.source = source
        self.settings = settings
        
        # Configurable thresholds (with defaults)
        self.GROUP_LIMIT = getattr(settings, 'code_group_limit', self.DEFAULT_GROUP_LIMIT)
        self.TINY_THRESHOLD = getattr(settings, 'code_tiny_threshold', self.DEFAULT_TINY_THRESHOLD)
        
        # Language from extension
        ext = source.split('.')[-1].lower() if '.' in source else ""
        self.lang = EXTENSION_MAP.get(ext) or "text"
        
        # Context
        self.ctx = ProcessingContext(source=source, settings=settings)
        
        # Byte data
        self.code_bytes = bytes(code, "utf8")
        self.byte_to_char = self._build_byte_char_map()
        
        # State
        self.out_chunks: List[Chunk] = []
        self.max_tokens = settings.max_tokens_by_type.get(
            ChunkType.CODE.value, settings.max_tokens_text
        )
        
        # Store on context for emitters
        self.ctx._code_bytes = self.code_bytes
        self.ctx._byte_to_char = self.byte_to_char
        self.ctx._last_byte_end = 0
    
    def _build_byte_char_map(self) -> Dict[int, int]:
        """Build byte->char mapping for accurate offsets."""
        mapping = {}
        byte_pos = 0
        for char_idx, ch in enumerate(self.code):
            mapping[byte_pos] = char_idx
            byte_pos += len(ch.encode("utf-8"))
        mapping[byte_pos] = len(self.code)
        return mapping
    
    def chunk(self) -> List[Chunk]:
        """Main entry point - parse and chunk the code."""
        if not TREE_SITTER_AVAILABLE or not self.settings.use_treesitter or self.lang == "text":
            return self._fallback_line_chunking()
        
        # Validate language is supported by tree-sitter
        if not self._validate_language():
            logger.debug(f"Language '{self.lang}' not supported by tree-sitter, using fallback")
            return self._fallback_line_chunking()
        
        try:
            parser = get_parser(self.lang)
            tree = parser.parse(self.code_bytes)
        except Exception as e:
            logger.warning(f"Tree-sitter parsing failed for {self.lang}: {e}")
            return self._fallback_line_chunking()
        
        # Create synthetic root heading (like MarkdownASTChunker does)
        self._create_root_heading()
        
        self._process_top_level(tree.root_node.children)
        self._preserve_trailing()
        
        logger.info(f"Generated {len(self.out_chunks)} chunks from code: {self.source}")
        return self.out_chunks
    
    def _validate_language(self) -> bool:
        """Check if tree-sitter supports this language."""
        if not TREE_SITTER_AVAILABLE or not get_parser:
            return False
        try:
            # Attempt to get parser - will raise if unsupported
            get_parser(self.lang)
            return True
        except Exception:
            return False
    
    def _create_root_heading(self):
        """Create a synthetic root heading for code files."""
        from pathlib import Path
        
        # Use filename as root heading
        filename = Path(self.source).stem
        root_name = filename.replace('_', ' ').replace('-', ' ').title()
        
        # Push heading to context (sets up section path)
        self.ctx.push_heading(1, root_name)
        
        # Create heading chunk
        root_id = generate_stable_id(self.source, root_name, 0)
        root_chunk = Chunk(
            id=root_id,
            index=self.ctx.next_global_index(),
            text="",
            chunk_type=ChunkType.HEADING,
            source=self.source,
            source_name=Path(self.source).name,
            h_level=1,
            heading=f"# {root_name}",
            section_path=root_name,
            original_text="",
            metadata={
                K.META_BREADCRUMBS: [root_name],
                K.META_ROOT_TOPIC: root_name,
                "is_synthetic": True,
                "language": self.lang,
            }
        )
        self.out_chunks.append(root_chunk)
        
        # Set as current parent for all subsequent chunks
        self.ctx.current_parent_id = root_id
    
    def _process_top_level(self, children):
        """Process top-level AST nodes with grouping logic."""
        current_group = []
        
        for node in children:
            is_atomic = node.type in ATOMIC_TYPES or "definition" in node.type or "declaration" in node.type
            
            if is_atomic:
                group_tokens = self._group_token_count(current_group)
                
                if current_group and group_tokens < self.TINY_THRESHOLD:
                    self._emit_node(node, prepend_bytes=current_group[0].start_byte)
                    current_group = []
                else:
                    if current_group:
                        emit_group(current_group, self.code_bytes, self.byte_to_char, 
                                   self.out_chunks, self.lang, self.settings, self.ctx)
                        current_group = []
                    self._emit_node(node)
            else:
                current_group.append(node)
                if self._group_token_count(current_group) > self.GROUP_LIMIT:
                    emit_group(current_group, self.code_bytes, self.byte_to_char,
                               self.out_chunks, self.lang, self.settings, self.ctx)
                    current_group = []
        
        if current_group:
            emit_group(current_group, self.code_bytes, self.byte_to_char,
                       self.out_chunks, self.lang, self.settings, self.ctx)
    
    def _group_token_count(self, nodes) -> int:
        """Calculate token count for a group of nodes."""
        if not nodes:
            return 0
        return sum(
            token_count(self.code_bytes[n.start_byte:n.end_byte].decode("utf8", errors="replace"), self.settings)
            for n in nodes
        )
    
    def _emit_node(self, node, prepend_bytes: Optional[int] = None):
        """Emit a single atomic node."""
        start_byte = prepend_bytes if prepend_bytes is not None else node.start_byte
        text = self.code_bytes[start_byte:node.end_byte].decode("utf8", errors="replace")
        name = get_node_name(node, self.code_bytes, self.ctx)
        
        if token_count(text, self.settings) <= self.max_tokens:
            emit_simple_node(node, text, name, start_byte, self.code_bytes, 
                            self.byte_to_char, self.out_chunks, self.lang, self.ctx)
        else:
            self._emit_split_node(node, text, name, start_byte)
    
    def _emit_split_node(self, node, text: str, name: str, start_byte: int):
        """Split a large node into multiple chunks."""
        body = node.child_by_field_name("body") or node.child_by_field_name("block") or node.child_by_field_name("content")
        
        if body:
            self._emit_structured_split(node, body, name)
        else:
            emit_line_split(node, name, self.code_bytes, self.byte_to_char,
                           self.out_chunks, self.lang, self.settings, self.ctx, self.max_tokens)
    
    def _emit_structured_split(self, node, body, name: str):
        """Split node by its internal structure."""
        sig_text = self.code_bytes[node.start_byte:body.start_byte].decode("utf8", errors="replace").strip()
        footer = get_footer(node, self.code_bytes)
        needs_braces = self.lang in BRACE_LANGUAGES and not footer
        
        symbols, comments, refs = extract_metadata_from_node(node, self.code_bytes)
        
        current_stmts: List[str] = []
        current_tokens = token_count(sig_text, self.settings) + token_count(footer, self.settings)
        part_num = 1
        current_start = node.start_byte
        
        skip_types = {"NEWLINE", "INDENT", "DEDENT", "{", "}", "(", ")"}
        children = [c for c in body.children if c.type not in skip_types]
        
        for i, child in enumerate(children):
            is_last = (i == len(children) - 1)
            child_text = get_child_text_with_indent(child, self.code_bytes)
            child_tokens = token_count(child_text, self.settings)
            
            if child_tokens > self.max_tokens:
                if current_stmts:
                    emit_split_part(current_stmts, sig_text, footer, name, part_num,
                                   symbols, refs, comments, current_start, child.start_byte,
                                   needs_braces, self.code_bytes, self.byte_to_char,
                                   self.out_chunks, self.lang, self.ctx)
                    part_num += 1
                    current_stmts = []
                    current_tokens = token_count(sig_text, self.settings) + token_count(footer, self.settings)
                self._emit_node(child)
                current_start = child.end_byte
                continue
            
            if current_tokens + child_tokens > self.max_tokens and current_stmts:
                emit_split_part(current_stmts, sig_text, footer, name, part_num,
                               symbols, refs, comments, current_start, child.start_byte,
                               needs_braces, self.code_bytes, self.byte_to_char,
                               self.out_chunks, self.lang, self.ctx)
                part_num += 1
                current_stmts = []
                current_tokens = token_count(sig_text, self.settings) + token_count(footer, self.settings)
                current_start = child.start_byte
            
            current_stmts.append(child_text)
            current_tokens += child_tokens
        
        if current_stmts:
            emit_split_part(current_stmts, sig_text, footer, name, part_num,
                           symbols, refs, comments, current_start, node.end_byte,
                           needs_braces, self.code_bytes, self.byte_to_char,
                           self.out_chunks, self.lang, self.ctx)
    
    def _preserve_trailing(self):
        """Ensure trailing bytes are preserved."""
        if not self.out_chunks:
            return
        
        last_end = getattr(self.ctx, "_last_byte_end", 0) or 0
        if last_end < len(self.code_bytes):
            tail = self.code_bytes[last_end:].decode("utf8", errors="replace")
            if tail:
                self.out_chunks[-1].original_text = (self.out_chunks[-1].original_text or "") + tail
                self.out_chunks[-1].char_end = self.byte_to_char.get(len(self.code_bytes), self.out_chunks[-1].char_end)
    
    def _fallback_line_chunking(self) -> List[Chunk]:
        """Fallback: Line-based chunking without tree-sitter."""
        # Create synthetic root heading
        self._create_root_heading()
        
        lines = self.code.splitlines(keepends=True)
        line_offsets = [0]
        for line in lines:
            line_offsets.append(line_offsets[-1] + len(line))
        
        current_tokens = 0
        start_line = 0
        
        for idx, line in enumerate(lines):
            line_tokens = token_count(line, self.settings)
            
            if current_tokens + line_tokens > self.max_tokens and idx > start_line:
                text = "".join(lines[start_line:idx])
                chunk = self.ctx.create_chunk(
                    text=text, chunk_type=ChunkType.CODE,
                    line_start=start_line, line_end=idx,
                    char_start=line_offsets[start_line], char_end=line_offsets[idx],
                    original_text=text,
                )
                if chunk:
                    chunk.metadata[K.META_LANGUAGE] = self.lang
                    self.out_chunks.append(chunk)
                start_line = idx
                current_tokens = 0
            current_tokens += line_tokens
        
        if start_line < len(lines):
            text = "".join(lines[start_line:])
            chunk = self.ctx.create_chunk(
                text=text, chunk_type=ChunkType.CODE,
                line_start=start_line, line_end=len(lines),
                char_start=line_offsets[start_line], char_end=line_offsets[-1],
                original_text=text,
            )
            if chunk:
                chunk.metadata[K.META_LANGUAGE] = self.lang
                self.out_chunks.append(chunk)
        
        return self.out_chunks

# =============================================================================
# PUBLIC API
# =============================================================================

def parse_raw_code(code: str, url: str, settings: ChunkerSettings) -> List[Chunk]:
    """Main entry point for raw code files."""
    return CodeChunker(code, url, settings).chunk()
