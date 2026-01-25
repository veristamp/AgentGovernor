# chunker/ast_parser.py
"""
Main AST-based markdown chunker implementation.
Refactored to use a class-based approach with ProcessingContext and core types.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from pathlib import Path
from markdown_it import MarkdownIt

from .config import ChunkerSettings
from .core import ChunkType, ProcessingContext, Chunk
from .text_splitter import token_aware_text_chunks_with_spans
from .block_handlers import split_code_block_to_chunks
from .code_parser import extract_code_block_metadata
from .chunk_factory import merge_small_chunks
from .utils import clean_markdown_for_breadcrumb, token_count, add_overlap_to_chunk, truncate_to_embedding_limit
from config import get_logger

# Safe import with fallback
try:
    from config import generate_stable_id, ChunkKeys as K
except ImportError:
    import hashlib
    def generate_stable_id(source: str, section_path: str, local_index: int) -> int:
        key = f"{source}:{section_path}:{local_index}"
        return int(hashlib.md5(key.encode()).hexdigest()[:16], 16)
    
    class K:
        META_LANGUAGE = "language"
        META_SYMBOLS = "symbols_defined"
        META_SYMBOLS_REF = "symbols_referenced"
        META_COMMENTS = "comments_text"
        META_HEADERS = "headers"
        META_ROW_COUNT = "row_count"
        META_BREADCRUMBS = "breadcrumbs"
        META_ROOT_TOPIC = "root_topic"
        META_HEADER_PREFIX = "header_prefix"

# Configure logging
logger = get_logger("chunker.ast_parser")

class MarkdownASTChunker:
    """
    Robust, AST-based, token-aware Markdown chunker.
    """
    
    def __init__(self, md: str, source: str, settings: ChunkerSettings, default_lang: str = ""):
        self.md = md
        self.source = source
        self.settings = settings
        self.default_lang = default_lang
        
        self.md_parser = MarkdownIt().enable('table')
        self.tokens = self.md_parser.parse(md)
        
        # Pre-calculate line offsets for 100% accurate character mapping
        self.all_source_lines = md.splitlines(keepends=True)
        self.line_offsets = [0]
        curr = 0
        for line in self.all_source_lines:
            curr += len(line)
            self.line_offsets.append(curr)
            
        # Initialize context
        self.ctx = ProcessingContext(
            source=source,
            settings=settings,
            local_counters={},
            section_token_offsets={}
        )
        
        # State
        self.out_chunks: List[Chunk] = [] # Use Chunk objects internally
        self.prose_buffer: List[str] = []
        self.prose_buffer_source_lines: Optional[Tuple[int, int]] = None
        
        self.in_heading = False
        self.pending_heading_level: Optional[int] = None
        self.pending_heading_text: str = ""
        self.pending_heading_source_lines: Optional[Tuple[int, int]] = None
        self.pending_heading_raw: str = ""
        
        self.in_list_item = False
        self.list_stack: List[Tuple[str, int]] = []
        self.blockquote_depth: int = 0
        self.skip_until = -1
        self.last_source_line_end: Optional[int] = 0

    def _gap_prefix(self, start_line: Optional[int]) -> tuple[str, Optional[int]]:
        """Return any raw gap text between the last chunk and the next start line."""
        if start_line is None or self.last_source_line_end is None:
            return "", start_line
        if start_line <= self.last_source_line_end:
            return "", start_line
        gap_text = "".join(self.all_source_lines[self.last_source_line_end:start_line])
        return gap_text, self.last_source_line_end

    def get_absolute_offset(self, line_num: Optional[int]) -> int:
        """Fast lookup of byte offset for a given 0-indexed line number."""
        if line_num is None or line_num <= 0:
            return 0
        if line_num >= len(self.line_offsets):
            return self.line_offsets[-1]
        return self.line_offsets[line_num]

    def flush_prose_buffer(self) -> None:
        """Process and emit accumulated prose."""
        if not self.prose_buffer:
            return
        
        # Use raw slices from the original markdown for higher fidelity
        raw_source_text = ""
        if self.prose_buffer_source_lines:
            start_line, end_line = self.prose_buffer_source_lines
            raw_source_text = "".join(self.all_source_lines[start_line:end_line])
            gap_text, gap_start = self._gap_prefix(start_line)
            if gap_text:
                raw_source_text = gap_text + raw_source_text
                start_line = gap_start
            full_text = raw_source_text
        else:
            full_text = "\n".join(self.prose_buffer).strip()
            start_line = None
            end_line = None
            raw_source_text = full_text

        self.prose_buffer = []
        self.prose_buffer_source_lines = None
        if not full_text.strip():
            return

        # Avoid standalone horizontal-rule chunks; attach to previous chunk for fidelity.
        stripped_lines = [l.strip() for l in full_text.splitlines() if l.strip()]
        if stripped_lines and all(l == "---" for l in stripped_lines):
            if self.out_chunks:
                last_chunk = self.out_chunks[-1]
                last_chunk.original_text = (last_chunk.original_text or "") + raw_source_text
                last_chunk.char_end += len(raw_source_text)
                if end_line is not None:
                    last_chunk.line_end = end_line
                self.ctx.char_offset = last_chunk.char_end
                return

        para_text_chunks = list(token_aware_text_chunks_with_spans(full_text, self.settings))
        block_char_start = self.get_absolute_offset(start_line) if start_line is not None else 0
        
        para_chunks: List[Chunk] = []
        for i, (text_chunk, span_start, span_end) in enumerate(para_text_chunks):
            # create_chunk handles token_count, token_start, char_offsets, etc.
            chunk = self.ctx.create_chunk(
                text=text_chunk, 
                chunk_type=ChunkType.TEXT,
                line_start=start_line,
                line_end=end_line,
                char_start=block_char_start + span_start,
                char_end=block_char_start + span_end,
                original_text=raw_source_text[span_start:span_end],
            )
            
            # Add overlap if needed (before final token count update if possible, 
            # but create_chunk already updated it. We might need a 'final_polish' step)
            if i > 0 and self.settings.overlap_tokens > 0:
                prev_text = para_chunks[i-1].text
                chunk.text = add_overlap_to_chunk([prev_text], chunk.text, self.settings)
                # Re-calculate token count if overlapped
                chunk.token_count = token_count(chunk.text, self.settings)

            para_chunks.append(chunk)
            self.out_chunks.append(chunk)
        
        if end_line is not None:
            self.last_source_line_end = end_line

    def chunk(self) -> List[Chunk]:
        """Main entry point to perform chunking."""
        for i, tok in enumerate(self.tokens):
            if i <= self.skip_until:
                continue
                
            try:
                method_name = f"_handle_{tok.type}"
                if hasattr(self, method_name):
                    getattr(self, method_name)(tok, i)
            except Exception as e:
                logger.error(f"Error processing token {tok.type}: {e}", exc_info=True)
                continue

        self.flush_prose_buffer()
        
        # FALLBACK: Synthetic structure & Orphan Fixing
        # We always run this now because it handles orphan detection/fixing as well
        self._apply_synthetic_structure(self.out_chunks)
            
        # MERGING: Optimize small text chunks
        self.out_chunks = merge_small_chunks(self.out_chunks, self.settings)
        
        if self.settings.min_keep_tokens > 0:
            self.out_chunks = [
                c for c in self.out_chunks 
                if c.chunk_type != ChunkType.TEXT or c.token_count >= self.settings.min_keep_tokens
            ]

        # Parent-child tracking
        self._establish_hierarchy(self.out_chunks)
        
        # Final pass: header injection
        self._inject_headers(self.out_chunks)
        
        # Recompute token offsets after final text mutations (headers/merges)
        self._recompute_token_offsets(self.out_chunks)

        logger.info(f"Generated {len(self.out_chunks)} chunks from document: {self.source}")
        return self.out_chunks

    def _handle_heading_open(self, tok, i):
        self.flush_prose_buffer()
        level = int(tok.tag[1]) if tok.tag and len(tok.tag) == 2 and tok.tag[0] == "h" else 1
        self.in_heading, self.pending_heading_level, self.pending_heading_text = True, level, ""
        if hasattr(tok, 'map') and tok.map:
            self.pending_heading_source_lines = (tok.map[0], tok.map[1])
            heading_raw = "".join(self.all_source_lines[tok.map[0]:tok.map[1]])
            gap_text, gap_start = self._gap_prefix(tok.map[0])
            if gap_text:
                heading_raw = gap_text + heading_raw
                self.pending_heading_source_lines = (gap_start, tok.map[1])
            self.pending_heading_raw = heading_raw

    def _handle_heading_close(self, tok, i):
        self.in_heading = False
        text = self.pending_heading_text.strip()
        clean_text = clean_markdown_for_breadcrumb(text)
        
        # Update stack with final clean text
        level = self.pending_heading_level or 1
        while self.ctx.heading_stack and self.ctx.heading_stack[-1][0] >= level:
            self.ctx.heading_stack.pop()
        self.ctx.heading_stack.append((level, clean_text))

        heading_section_path = self.ctx.get_section_path()
        heading_id = generate_stable_id(self.source, heading_section_path, -1)
        
        if self.settings.emit_heading_chunks:
            heading_md = f"{'#' * level} {clean_text}"
            start_line = self.pending_heading_source_lines[0] if self.pending_heading_source_lines else None
            
            chunk = self.ctx.create_chunk(
                text=heading_md, chunk_type=ChunkType.HEADING, 
                line_start=start_line,
                line_end=self.pending_heading_source_lines[1] if self.pending_heading_source_lines else None,
                original_text=self.pending_heading_raw if self.pending_heading_raw else None,
                char_start=self.get_absolute_offset(start_line) if start_line is not None else None,
                char_end=self.get_absolute_offset(self.pending_heading_source_lines[1]) if self.pending_heading_source_lines else None,
            )
            if chunk:
                self.out_chunks.append(chunk)
                self.ctx.current_parent_id = chunk.id
                if self.pending_heading_source_lines:
                    self.last_source_line_end = self.pending_heading_source_lines[1]
        else:
            self.ctx.current_parent_id = heading_id
        
        self.pending_heading_source_lines = None
        self.pending_heading_raw = ""

    def _handle_inline(self, tok, i):
        content = tok.content if hasattr(tok, 'content') else ""
        if not content:
            return
        if self.in_heading:
            self.pending_heading_text += content
        else:
            indent = "  " * (len(self.list_stack) - 1) if self.list_stack else ""
            prefix = ""
            if self.in_list_item and self.list_stack:
                list_type, counter = self.list_stack[-1]
                prefix = f"{indent}- " if list_type == "bullet" else f"{indent}{counter}. "
            if self.blockquote_depth > 0:
                prefix = "> " * self.blockquote_depth + prefix
            self.prose_buffer.append(prefix + content)

    def _handle_image(self, tok, i):
        alt_text = "".join(child.content for child in getattr(tok, 'children', []) if hasattr(child, 'content'))
        img_url = ""
        if hasattr(tok, 'attrGet'):
            img_url = tok.attrGet('src') or ""
        elif hasattr(tok, 'attrs'):
            img_url = next((v for k, v in tok.attrs if k == 'src'), "")
        
        image_md = f"![{alt_text}]({img_url})"
        if self.in_heading:
            self.pending_heading_text += f" {image_md}"
        else:
            prefix = "> " * self.blockquote_depth if self.blockquote_depth > 0 else ""
            self.prose_buffer.append(prefix + image_md)

    def _handle_html_block(self, tok, i):
        content = tok.content or ""
        if content:
            if hasattr(tok, 'map') and tok.map:
                if self.prose_buffer_source_lines is None:
                    self.prose_buffer_source_lines = (tok.map[0], tok.map[1])
                else:
                    self.prose_buffer_source_lines = (self.prose_buffer_source_lines[0], tok.map[1])
            self.prose_buffer.append(content)

    def _handle_hr(self, tok, i):
        # Keep horizontal rules in text for reconstruction, but avoid standalone chunks.
        if hasattr(tok, 'map') and tok.map:
            if self.prose_buffer_source_lines is None:
                self.prose_buffer_source_lines = (tok.map[0], tok.map[1])
            else:
                self.prose_buffer_source_lines = (self.prose_buffer_source_lines[0], tok.map[1])
        self.prose_buffer.append("---")

    def _handle_paragraph_open(self, tok, i):
        if hasattr(tok, 'map') and tok.map:
            if self.prose_buffer_source_lines is None:
                self.prose_buffer_source_lines = (tok.map[0], tok.map[1])
            else:
                self.prose_buffer_source_lines = (self.prose_buffer_source_lines[0], tok.map[1])

    def _handle_paragraph_close(self, tok, i):
        prefix = "> " * self.blockquote_depth if self.blockquote_depth > 0 else ""
        self.prose_buffer.append(prefix)

    def _handle_list_item_open(self, tok, i):
        self.in_list_item = True
        if hasattr(tok, 'map') and tok.map:
            if self.prose_buffer_source_lines is None:
                self.prose_buffer_source_lines = (tok.map[0], tok.map[1])
            else:
                self.prose_buffer_source_lines = (self.prose_buffer_source_lines[0], tok.map[1])

    def _handle_list_item_close(self, tok, i):
        self.in_list_item = False
        # Keep list items together; add a blank line separator between items.
        self.prose_buffer.append("")
        if self.list_stack:
            lt, c = self.list_stack[-1]
            self.list_stack[-1] = (lt, c + 1)

    def _handle_bullet_list_open(self, tok, i):
        self.list_stack.append(("bullet", 1))

    def _handle_ordered_list_open(self, tok, i):
        start = int(dict(tok.attrs).get('start', 1)) if hasattr(tok, 'attrs') and tok.attrs else 1
        self.list_stack.append(("ordered", start))

    def _handle_bullet_list_close(self, tok, i):
        if self.list_stack: self.list_stack.pop()

    def _handle_ordered_list_close(self, tok, i):
        if self.list_stack: self.list_stack.pop()

    def _handle_blockquote_open(self, tok, i):
        self.flush_prose_buffer()
        self.blockquote_depth += 1
        if hasattr(tok, 'map') and tok.map:
            if self.prose_buffer_source_lines is None:
                self.prose_buffer_source_lines = (tok.map[0], tok.map[1])
            else:
                self.prose_buffer_source_lines = (self.prose_buffer_source_lines[0], tok.map[1])

    def _handle_blockquote_close(self, tok, i):
        self.flush_prose_buffer()
        self.blockquote_depth = max(0, self.blockquote_depth - 1)

    def _handle_fence(self, tok, i):
        self._handle_code(tok, i)

    def _handle_code_block(self, tok, i):
        self._handle_code(tok, i)

    def _handle_code(self, tok, i):
        self.flush_prose_buffer()
        fence = "```"
        info = (tok.info or "").strip() if hasattr(tok, 'info') else ""
        code_text = tok.content or ""
        code_source_lines = (tok.map[0], tok.map[1]) if tok.map else (None, None)
        raw_code_block = "".join(self.all_source_lines[tok.map[0]:tok.map[1]]) if tok.map else ""
        if tok.map:
            gap_text, gap_start = self._gap_prefix(tok.map[0])
            if gap_text:
                raw_code_block = gap_text + raw_code_block
                code_source_lines = (gap_start, tok.map[1])
        code_lang = info.split()[0].strip() if info else self.default_lang
        
        code_metadata = extract_code_block_metadata(code_text, code_lang)
        pieces = list(split_code_block_to_chunks(
            code_text, fence=fence, info=info, 
            max_lines=self.settings.split_code_max_lines, settings=self.settings,
            default_lang=self.default_lang
        ))

        for piece_idx, piece in enumerate(pieces):
            start_line = code_source_lines[0]
            chunk = self.ctx.create_chunk(
                text=piece, chunk_type=ChunkType.CODE,
                line_start=start_line, line_end=code_source_lines[1],
                original_text=raw_code_block if len(pieces) == 1 and raw_code_block else None,
                char_start=self.get_absolute_offset(start_line) if start_line is not None else None,
                char_end=self.get_absolute_offset(code_source_lines[1]) if code_source_lines[1] is not None else None,
            )
            if chunk:
                chunk.metadata.update({
                    K.META_LANGUAGE: code_lang or "text",
                    K.META_SYMBOLS: code_metadata.get(K.META_SYMBOLS, []),
                    K.META_SYMBOLS_REF: code_metadata.get(K.META_SYMBOLS_REF, []),
                    K.META_COMMENTS: code_metadata.get(K.META_COMMENTS, ""),
                })
                self.out_chunks.append(chunk)
                if code_source_lines[1] is not None:
                    self.last_source_line_end = code_source_lines[1]

    def _handle_table_open(self, tok, i):
        self.flush_prose_buffer()
        table_source_lines = (tok.map[0], tok.map[1]) if tok.map else (None, None)
        if tok.map:
            gap_text, gap_start = self._gap_prefix(tok.map[0])
            if gap_text:
                table_source_lines = (gap_start, tok.map[1])
        table_tokens = []
        depth, j = 1, i + 1
        while j < len(self.tokens) and depth > 0:
            if self.tokens[j].type == "table_open": depth += 1
            elif self.tokens[j].type == "table_close": depth -= 1
            if depth > 0: table_tokens.append(self.tokens[j])
            j += 1
        self.skip_until = j - 1
        
        header_rows, body_rows, aligns = self._parse_table_ast(table_tokens)
        table_md = self._format_table_markdown(header_rows, body_rows, aligns)
        
        max_t = self.settings.max_tokens_by_type.get(ChunkType.TABLE.value, self.settings.max_tokens_text)
        split_rows = self.settings.split_table_rows
        
        if len(body_rows) <= split_rows or split_rows <= 0:
            self._emit_table_chunk(table_md, header_rows, body_rows, table_source_lines, max_t)
        else:
            for row_idx in range(0, len(body_rows), split_rows):
                chunk_body = body_rows[row_idx:row_idx + split_rows]
                chunk_md = self._format_table_markdown(header_rows, chunk_body, aligns)
                self._emit_table_chunk(chunk_md, header_rows, chunk_body, table_source_lines, max_t)

    def _parse_table_ast(self, table_tokens):
        def extract_row_data(row_toks):
            cells, aligns = [], []
            for rt in row_toks:
                if rt.type in ("th_open", "td_open"):
                    style = rt.attrGet('style') or ""
                    aligns.append('center' if 'center' in style else 'right' if 'right' in style else 'left')
                elif rt.type == "inline": cells.append(rt.content)
            return cells, aligns

        header_rows, body_rows, column_alignments = [], [], []
        current_section, current_row_tokens = None, []
        for tt in table_tokens:
            if tt.type == "thead_open": current_section = "thead"
            elif tt.type == "tbody_open": current_section = "tbody"
            elif tt.type == "tr_open": current_row_tokens = []
            elif tt.type == "tr_close":
                if current_row_tokens:
                    row_cells, row_aligns = extract_row_data(current_row_tokens)
                    if current_section == "thead":
                        header_rows.append(row_cells)
                        if not column_alignments: column_alignments = row_aligns
                    else:
                        body_rows.append(row_cells)
                current_row_tokens = []
            elif tt.type in ("th_open", "th_close", "td_open", "td_close", "inline"):
                current_row_tokens.append(tt)
        return header_rows, body_rows, column_alignments

    def _format_table_markdown(self, header, rows, aligns):
        if not header and not rows: return ""
        lines = []
        if header:
            for h_row in header: lines.append("| " + " | ".join(h_row) + " |")
            delims = []
            for idx in range(len(header[0])):
                a = aligns[idx] if aligns and idx < len(aligns) else 'left'
                delims.append(":---:" if a == 'center' else "---:" if a == 'right' else "---")
            lines.append("|" + "|".join(delims) + "|")
        for row in rows: lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def _emit_table_chunk(self, table_md, header_rows, body_rows, source_lines, max_t):
        if not table_md: return
        t_count = token_count(table_md, self.settings)
        chunk_type = ChunkType.TABLE if t_count <= max_t else ChunkType.TEXT
        table_raw = "".join(self.all_source_lines[source_lines[0]:source_lines[1]]) if source_lines[0] is not None else ""
        
        chunk = self.ctx.create_chunk(
            text=table_md, chunk_type=chunk_type,
            line_start=source_lines[0], line_end=source_lines[1],
            original_text=table_raw if table_raw else None,
            char_start=self.get_absolute_offset(source_lines[0]) if source_lines[0] is not None else None,
            char_end=self.get_absolute_offset(source_lines[1]) if source_lines[1] is not None else None,
        )
        if chunk:
            if header_rows and chunk_type == ChunkType.TABLE:
                chunk.metadata[K.META_HEADERS] = header_rows[0]
                chunk.metadata[K.META_ROW_COUNT] = len(body_rows)
            self.out_chunks.append(chunk)
            if source_lines[1] is not None:
                self.last_source_line_end = source_lines[1]

    def _apply_synthetic_structure(self, chunks: List[Chunk]):
        """Inject breadcrumbs and heading info if none exists, and fix orphans."""
        
        doc_name = Path(self.source).stem if self.source else "Document"
        synthetic = doc_name.replace('_', ' ').replace('-', ' ').title()
        
        # 1. Identify orphans (content without parent)
        orphans = [c for c in chunks if c.chunk_type in (ChunkType.TEXT, ChunkType.CODE, ChunkType.TABLE) and c.parent_chunk_id is None]
        
        if orphans and not any(c.chunk_type == ChunkType.HEADING for c in chunks):
            # Create synthetic root chunk
            root_id = generate_stable_id(self.source, "synthetic_root", 0)
            root_chunk = Chunk(
                id=root_id,
                index=0,
                text="",
                chunk_type=ChunkType.HEADING,
                source=self.source,
                source_name=Path(self.source).name,
                h_level=1,
                heading=f"# {synthetic}",
                section_path=synthetic,
                original_text="",
                metadata={
                    K.META_BREADCRUMBS: [synthetic],
                    K.META_ROOT_TOPIC: synthetic,
                    "is_synthetic": True
                }
            )
            # Insert at the beginning
            chunks.insert(0, root_chunk)
            
            # Reparent orphans
            for c in orphans:
                c.parent_chunk_id = root_id
        
        # 2. Breadcrumbs and Header Injection (Existing Logic)
        for chunk in chunks:
            if not chunk.metadata.get(K.META_BREADCRUMBS):
                chunk.metadata[K.META_BREADCRUMBS] = [synthetic]
                chunk.metadata[K.META_ROOT_TOPIC] = synthetic
                chunk.section_path = synthetic
                
                # Update parent if it was an orphan we just fixed
                if chunk in orphans and chunk.parent_chunk_id is None:
                     if 'root_id' in locals():
                         chunk.parent_chunk_id = root_id

                # If we're injecting headers, mark this for the final pass
                if self.settings.inject_headers and chunk.chunk_type in [ChunkType.TEXT, ChunkType.TABLE]:
                    chunk.metadata[K.META_HEADER_PREFIX] = f"**{synthetic}**\n\n"

    def _establish_hierarchy(self, chunks: List[Chunk]):
        """Establish parent-child relationships between headings and content."""
        child_map = defaultdict(list)
        for c in chunks:
            if c.parent_chunk_id:
                child_map[c.parent_chunk_id].append(c.id)
        
        for c in chunks:
            if c.chunk_type == ChunkType.HEADING and c.id in child_map:
                c.child_chunk_ids = sorted(child_map[c.id])

    def _inject_headers(self, chunks: List[Chunk]):
        """Final pass: Inject section paths into text for better retrieval."""
        for chunk in chunks:
            header = chunk.metadata.pop(K.META_HEADER_PREFIX, "")
            if header and chunk.chunk_type in [ChunkType.TEXT, ChunkType.TABLE]:
                if not chunk.text.startswith(header):
                    chunk.text = header + chunk.text
                # Enforce embedding limits on final text
                chunk.text = truncate_to_embedding_limit(chunk.text, self.settings)
    
    def _recompute_token_offsets(self, chunks: List[Chunk]) -> None:
        """Recompute token_start/token_count after final text mutations."""
        section_offsets: Dict[str, int] = {}
        for chunk in sorted(chunks, key=lambda c: c.index):
            section = chunk.section_path or "root"
            chunk.token_start = section_offsets.get(section, 0)
            chunk.token_count = token_count(chunk.text, self.settings)
            section_offsets[section] = chunk.token_start + chunk.token_count

def markdown_ast_chunker(md: str, source: str, settings: ChunkerSettings, default_lang: str = "") -> List[Chunk]:
    """Entry point for the Markdown AST chunker."""
    chunker = MarkdownASTChunker(md, source, settings, default_lang)
    return chunker.chunk()
