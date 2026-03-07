# chunker/core.py
"""
Core Data Structures for Chunker.

Shared types and enums used across all chunker components.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple, TYPE_CHECKING
from enum import Enum
from pathlib import Path

if TYPE_CHECKING:
    from .config import ChunkerSettings


# =============================================================================
# ENUMS
# =============================================================================

# Import Language from central config
from config import Language, get_language_from_extension, is_code_file


class ChunkType(Enum):
    """Types of chunks produced by the chunker."""
    HEADING = "heading"     # Section/heading markers (hierarchy nodes)
    TEXT = "text"           # Prose content
    CODE = "code"           # Code blocks or code files
    TABLE = "table"         # Tables


# =============================================================================
# CHUNK DATA
# =============================================================================

@dataclass
class Chunk:
    """
    A single chunk of content.
    
    This is the internal representation used during processing.
    Use to_dict() to convert to the serializable format.
    """
    id: int
    index: int
    text: str
    chunk_type: ChunkType
    source: str
    
    # Position metadata
    line_start: int = 0
    line_end: int = 0
    char_start: int = 0
    char_end: int = 0
    
    # Token metadata
    token_start: int = 0
    token_count: int = 0
    
    # Hierarchy
    section_path: str = ""
    heading: str = ""
    h_level: int = 0
    parent_chunk_id: Optional[int] = None
    child_chunk_ids: List[int] = field(default_factory=list)
    
    # Original text (before header injection)
    original_text: str = ""
    source_name: str = ""
    
    # Code-specific
    language: Optional[str] = None
    symbols: List[str] = field(default_factory=list)
    
    # Extra metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary format compatible with ChunkKeys."""
        from config import ChunkKeys as K
        
        # Merge metadata first (we'll extract special keys from it)
        meta = self.metadata.copy() if self.metadata else {}
        if self.language:
            meta[K.META_LANGUAGE] = self.language
        if self.symbols:
            meta[K.META_SYMBOLS] = self.symbols
        
        # Extract special keys that go at top level
        section_anchor = meta.pop(K.SECTION_ANCHOR, None)
        summary = meta.pop(K.SUMMARY, None)
        
        # Build dictionary in consistent order
        d = {
            K.ID: self.id,
            K.INDEX: self.index,
            K.TEXT: self.text,
            K.TYPE: self.chunk_type.value if isinstance(self.chunk_type, ChunkType) else self.chunk_type,
            K.FILE_PATH: self.source,
            K.SOURCE_NAME: self.source_name,
            K.ORIGINAL_TEXT: self.original_text or self.text,
            K.HEADING: self.heading,
            K.H_LEVEL: self.h_level,
            K.SECTION_PATH: self.section_path,
            K.PARENT_ID: self.parent_chunk_id,
            K.SECTION_ANCHOR: section_anchor,
            K.SUMMARY: summary,
            K.CHILD_IDS: self.child_chunk_ids or [],
            K.CHAR_START: self.char_start,
            K.CHAR_END: self.char_end,
            K.TOKEN_START: self.token_start,
            K.TOKEN_COUNT: self.token_count,
            K.LINE_START: self.line_start,
            K.LINE_END: self.line_end,
            K.METADATA: meta,
        }
            
        return d


# =============================================================================
# PROCESSING CONTEXT
# =============================================================================

@dataclass
class ProcessingContext:
    """
    Context passed through the chunking pipeline.
    
    Tracks state during document processing.
    """
    source: str                          # File path or URL
    settings: Any                        # ChunkerSettings
    global_index: int = 0               # Running chunk index
    token_offset: int = 0               # Running token position
    char_offset: int = 0                # Running char position
    
    # Heading stack for section_path
    heading_stack: List[Tuple[int, str]] = field(default_factory=list)
    
    # Parent tracking
    current_parent_id: Optional[int] = None
    
    # Section tracking
    section_token_offsets: Dict[str, int] = field(default_factory=dict) # section_path -> current token offset
    local_counters: Dict[str, int] = field(default_factory=dict)       # section_path -> local index
    
    # Page tracking (for PDFs)
    current_page: int = 1
    
    def get_section_path(self) -> str:
        """Build section path from heading stack."""
        return " > ".join(h for _, h in self.heading_stack) or "root"
    
    def push_heading(self, level: int, text: str):
        """Push a heading onto the stack, popping higher/equal levels."""
        while self.heading_stack and self.heading_stack[-1][0] >= level:
            self.heading_stack.pop()
        self.heading_stack.append((level, text))
    
    def next_global_index(self) -> int:
        """Get next global chunk index and increment."""
        idx = self.global_index
        self.global_index += 1
        return idx

    def next_local_index(self, section_path: Optional[str] = None) -> int:
        """Get next local index for a section."""
        path = section_path or self.get_section_path()
        idx = self.local_counters.get(path, 0)
        self.local_counters[path] = idx + 1
        return idx

    def get_token_offset(self, section_path: Optional[str] = None) -> int:
        """Get token offset for a section."""
        path = section_path or self.get_section_path()
        return self.section_token_offsets.get(path, 0)

    def update_token_offset(self, count: int, section_path: Optional[str] = None):
        """Update token offset for a section."""
        path = section_path or self.get_section_path()
        current = self.section_token_offsets.get(path, 0)
        self.section_token_offsets[path] = current + count

    def create_chunk(
        self,
        text: str,
        chunk_type: ChunkType,
        line_start: Optional[int] = None,
        line_end: Optional[int] = None,
        char_start: Optional[int] = None,
        char_end: Optional[int] = None,
        original_text: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Chunk:
        """
        Creates a new Chunk using context state.
        
        Handles: ID generation, token counting, metadata consolidation.
        NOTE: Header injection and truncation happen in ast_parser final pass.
        
        Raises:
            ValueError: If text is empty for content types
        """
        # Validation
        if not text and chunk_type != ChunkType.HEADING:
            raise ValueError(f"Empty text not allowed for chunk_type={chunk_type}")
        
        # Import helpers (config has graceful fallback built-in)
        try:
            from config import generate_stable_id, generate_section_anchor, ChunkKeys as K
        except ImportError:
            # Minimal fallback
            import hashlib
            generate_stable_id = lambda src, path, idx: int(hashlib.md5(f"{src}:{path}:{idx}".encode()).hexdigest()[:16], 16)
            generate_section_anchor = lambda src, path: f"{src}#{path.lower().replace(' ', '-')}"
            class K:
                SECTION_ANCHOR = "section_anchor"
                META_PAGES = "pages"
                META_BREADCRUMBS = "breadcrumbs"
                META_ROOT_TOPIC = "root_topic"
                META_HEADER_PREFIX = "header_prefix"
        
        from .utils import token_count, lookup_page_numbers, clean_page_markers
        
        # Get section path and indices
        section_path = self.get_section_path()
        local_idx = self.next_local_index(section_path)
        global_idx = self.next_global_index()
        
        # Token count (no truncation here - done in final pass)
        token_count_val = token_count(text, self.settings)
        
        # Char offsets
        c_start = char_start if char_start is not None else self.char_offset
        
        # Page mapping (for PDFs)
        page_nums = []
        page_map = getattr(self.settings, '_page_map', None)
        if page_map and page_map.get('has_pages'):
            page_nums = lookup_page_numbers(line_start, line_end, page_map)
        
        # Build metadata
        meta = metadata.copy() if metadata else {}
        meta.setdefault(K.SECTION_ANCHOR, generate_section_anchor(self.source, section_path))
        meta[K.META_PAGES] = page_nums or None
        meta[K.META_BREADCRUMBS] = [t for _, t in self.heading_stack]
        meta[K.META_ROOT_TOPIC] = self.heading_stack[0][1] if self.heading_stack else "General"
        
        # Header injection marker (actual injection in final pass)
        if self.settings.inject_headers and self.heading_stack and chunk_type in (ChunkType.TEXT, ChunkType.TABLE):
            meta[K.META_HEADER_PREFIX] = f"**{section_path}**\n\n"
        
        # Heading info
        level, heading_text = self.heading_stack[-1] if self.heading_stack else (0, "")
        heading_display = f"{'#' * level} {heading_text}".strip() if level else heading_text
        
        # Build chunk
        chunk = Chunk(
            id=generate_stable_id(self.source, section_path, local_idx),
            index=global_idx,
            text=clean_page_markers(text),
            chunk_type=chunk_type,
            source=self.source,
            source_name=Path(self.source).name,
            line_start=line_start or 0,
            line_end=line_end or 0,
            char_start=c_start,
            char_end=char_end or (c_start + len(original_text or text)),
            token_start=self.get_token_offset(section_path),
            token_count=token_count_val,
            section_path=section_path,
            heading=heading_display,
            h_level=level,
            parent_chunk_id=self.current_parent_id,
            original_text=original_text or text,
            metadata=meta
        )
        
        # Update state
        self.char_offset = chunk.char_end
        self.update_token_offset(chunk.token_count, section_path)
        
        return chunk


