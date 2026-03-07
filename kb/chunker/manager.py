# chunker/manager.py
"""
Unified Chunker Manager - Single entry point for all chunking operations.

This module provides a clean, unified interface for document chunking,
encapsulating all the lower-level components (AST parser, code parser, 
batch processor) into a single cohesive manager class.

Usage:
    from chunker import ChunkerManager

    # Initialize with default settings
    chunker = ChunkerManager()
    
    # Process a single file
    result = chunker.process_file("doc/example.md")
    
    # Process a directory
    results = chunker.process_directory("doc/", extensions=["*.md", "*.py"])
    
    # Process raw content
    result = chunker.process_content(content, filename="example.py")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from collections import Counter
from dataclasses import dataclass, field

from .config import ChunkerSettings
from .core import ChunkType, Chunk
from .code_parser import EXTENSION_MAP
from .utils import chunk_document

# Safe import with fallback
try:
    from config import get_logger, ChunkKeys as K
    logger = get_logger("ChunkerManager")
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    
    class K:
        META_COMMENTS = "comments_text"
        META_SYMBOLS = "symbols_defined"
        META_HEADERS = "headers"
        META_LANGUAGE = "language"


# ============================================================================
# RESULT DATA CLASSES
# ============================================================================

@dataclass
class ChunkStats:
    """Statistics about the chunking result."""
    hierarchy: int = 0
    text: int = 0
    code: int = 0
    table: int = 0
    linked: int = 0
    orphans: int = 0
    symbols: Dict[str, int] = field(default_factory=dict)
    languages: Dict[str, int] = field(default_factory=dict)
    with_comments: int = 0
    with_symbols: int = 0
    tables_with_headers: int = 0
    
    def merge(self, other: ChunkStats):
        """Merge statistics from another result."""
        self.hierarchy += other.hierarchy
        self.text += other.text
        self.code += other.code
        self.table += other.table
        self.linked += other.linked
        self.orphans += other.orphans
        self.with_comments += other.with_comments
        self.with_symbols += other.with_symbols
        self.tables_with_headers += other.tables_with_headers
        
        # Merge dictionaries
        for lang, count in other.languages.items():
            self.languages[lang] = self.languages.get(lang, 0) + count
        for sym, count in other.symbols.items():
            self.symbols[sym] = self.symbols.get(sym, 0) + count
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "hierarchy": self.hierarchy,
            "text": self.text,
            "code": self.code,
            "table": self.table,
            "linked": self.linked,
            "orphans": self.orphans,
            "symbols": self.symbols,
            "languages": self.languages,
            "with_comments": self.with_comments,
            "with_symbols": self.with_symbols,
            "tables_with_headers": self.tables_with_headers,
        }


@dataclass
class ChunkResult:
    """Result of chunking a single document."""
    source: str
    metadata: Dict[str, Any]
    hierarchy: List[Chunk]
    text: List[Chunk]
    code: List[Chunk]
    table: List[Chunk]
    stats: ChunkStats
    
    @property
    def total_chunks(self) -> int:
        """Total number of content chunks (excluding hierarchy)."""
        return len(self.text) + len(self.code) + len(self.table)
    
    @property
    def all_chunks(self) -> List[Chunk]:
        """All chunks including hierarchy for reconstruction."""
        return self.hierarchy + self.text + self.code + self.table
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to the standard output format (dictionaries)."""
        return {
            "source": self.source,
            "metadata": self.metadata,
            "stats": self.stats.to_dict(),
            "hierarchy": [c.to_dict() for c in self.hierarchy],
            "text": [c.to_dict() for c in self.text],
            "code": [c.to_dict() for c in self.code],
            "table": [c.to_dict() for c in self.table],
        }
    
    def save(self, path: Union[str, Path], indent: int = 2) -> Path:
        """Save the result to a JSON file."""
        path = Path(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=indent, ensure_ascii=False)
        return path


@dataclass
class BatchResult:
    """Result of batch chunking multiple documents."""
    results: Dict[str, ChunkResult]
    total_stats: ChunkStats
    
    @property
    def files_processed(self) -> int:
        return len(self.results)
    
    def get_result(self, source: str) -> Optional[ChunkResult]:
        """Get result for a specific source file."""
        return self.results.get(source)


# ============================================================================
# CHUNKER MANAGER
# ============================================================================

class ChunkerManager:
    """
    Unified manager for document chunking operations.
    
    Provides a clean interface for:
    - Single file processing
    - Directory batch processing
    - Raw content processing
    - Statistics and validation
    
    Example:
        chunker = ChunkerManager()
        result = chunker.process_file("doc/readme.md")
        print(f"Extracted {result.total_chunks} chunks")
        result.save("output.json")
    """
    
    # Default file extensions to process in batch mode
    DEFAULT_EXTENSIONS = [
        # Markdown
        "*.md",
        # Python
        "*.py",
        # JavaScript/TypeScript
        "*.js", "*.jsx", "*.ts", "*.tsx",
        # Web
        "*.html", "*.htm", "*.css",
        # Systems languages
        "*.go", "*.rs", "*.c", "*.cpp", "*.cc",
        # Other languages
        "*.java", "*.rb", "*.php", "*.cs",
        # Config
        "*.yaml", "*.yml",
        # Shell
        "*.sh", "*.bash",
    ]
    
    def __init__(
        self,
        settings: Optional[ChunkerSettings] = None,
    ):
        """
        Initialize the ChunkerManager.
        
        Args:
            settings: ChunkerSettings configuration. If None, uses defaults.
        """
        self.settings = settings or self._default_settings()
        self.logger = logger
    
    @staticmethod
    def _default_settings() -> ChunkerSettings:
        """
        Create default chunker settings.
        
        Settings are read from EMBEDDING_CONFIG (set via environment variables).
        """
        return ChunkerSettings(
            # tokenizer_name and embedding_max_tokens come from EMBEDDING_CONFIG
            max_tokens_text=2000,
            overlap_tokens=300,
            min_keep_tokens=1,  # Ensure 100% content fidelity
            emit_heading_chunks=True,
            inject_headers=True,
            split_code_max_lines=50,
            split_table_rows=100,
            use_treesitter=True,
            max_tokens_by_type={
                ChunkType.TEXT.value: 2000, 
                ChunkType.CODE.value: 2000, 
                ChunkType.TABLE.value: 2000
            },
        )
    
    
    # =========================================================================
    # CORE PROCESSING METHODS
    # =========================================================================
    
    def process_content(
        self,
        content: str,
        filename: str,
        settings: Optional[ChunkerSettings] = None,
    ) -> ChunkResult:
        """
        Process raw content into structured chunks.
        
        Args:
            content: The raw file content (code or markdown)
            filename: The filename (used to determine file type from extension)
            settings: Optional settings override for this operation
            
        Returns:
            ChunkResult with separated chunks and statistics
        """
        use_settings = settings or self.settings
        
        # Chunk the content
        all_chunks = chunk_document(content, filename, use_settings)
        
        # Separate chunks by type
        hierarchy: List[Chunk] = []
        text: List[Chunk] = []
        code: List[Chunk] = []
        table: List[Chunk] = []
        
        for chunk in all_chunks:
            ctype = chunk.chunk_type
                
            if ctype == ChunkType.HEADING:
                hierarchy.append(chunk)
            elif ctype == ChunkType.TEXT:
                text.append(chunk)
            elif ctype == ChunkType.CODE:
                code.append(chunk)
            elif ctype == ChunkType.TABLE:
                table.append(chunk)
        
        # Calculate statistics
        stats = self._calculate_stats(hierarchy, text, code, table)
        
        # Build metadata
        from chunker import __version__
        metadata = {
            "source": filename,
            "total_chunks": len(all_chunks),
            "pipeline_version": __version__,
        }
        
        return ChunkResult(
            source=filename,
            metadata=metadata,
            hierarchy=hierarchy,
            text=text,
            code=code,
            table=table,
            stats=stats,
        )
    
    def process_file(
        self,
        path: Union[str, Path],
        output_path: Optional[Union[str, Path]] = None,
        settings: Optional[ChunkerSettings] = None,
    ) -> ChunkResult:
        """
        Process a single file into structured chunks.
        
        Args:
            path: Path to the file to process
            output_path: Optional path for JSON output. If None, uses {stem}_structured.json
            settings: Optional settings override for this operation
            
        Returns:
            ChunkResult with separated chunks and statistics
        """
        path = Path(path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        if not path.is_file():
            raise ValueError(f"Not a file: {path}")
        
        # Read content
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Process
        result = self.process_content(content, path.name, settings)
        
        # Save if output path specified or use default
        if output_path:
            result.save(output_path)
        
        return result
    
    def process_directory(
        self,
        directory: Union[str, Path],
        extensions: Optional[List[str]] = None,
        output_suffix: str = "_structured.json",
        recursive: bool = False,
        settings: Optional[ChunkerSettings] = None,
    ) -> BatchResult:
        """
        Process all matching files in a directory.
        
        Args:
            directory: Path to the directory to process
            extensions: List of glob patterns (e.g., ["*.md", "*.py"]). 
                        If None, uses DEFAULT_EXTENSIONS.
            output_suffix: Suffix for output files (default: "_structured.json")
            recursive: If True, process subdirectories recursively
            settings: Optional settings override for this operation
            
        Returns:
            BatchResult with all results and aggregate statistics
        """
        directory = Path(directory)
        
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        
        if not directory.is_dir():
            raise ValueError(f"Not a directory: {directory}")
        
        extensions = extensions or self.DEFAULT_EXTENSIONS
        
        # Find all matching files
        files = []
        for ext in extensions:
            if recursive:
                files.extend(directory.rglob(ext))
            else:
                files.extend(directory.glob(ext))
        
        # Filter out our structured output files
        files = [f for f in files if not f.name.endswith("_structured.json")]
        files = sorted(set(files))  # Remove duplicates and sort
        
        if not files:
            self.logger.warning(f"⚠️ No matching files found in {directory}")
            return BatchResult(results={}, total_stats=ChunkStats())
        
        self.logger.info(f"\n🚀 BATCH PROCESSING: {len(files)} files")
        
        # Process each file
        results = {}
        total_stats = ChunkStats()
        
        for file_path in files:
            try:
                output_path = file_path.with_name(f"{file_path.stem}{output_suffix}")
                result = self.process_file(file_path, output_path, settings)
                results[str(file_path)] = result
                
                # Aggregate stats
                total_stats.merge(result.stats)
                
                self.logger.info(f"  ✅ {file_path.name}: {result.total_chunks} chunks")
                
            except Exception as e:
                self.logger.error(f"  ❌ {file_path.name}: {e}")
        
        self._log_batch_summary(len(results), total_stats)
        
        return BatchResult(results=results, total_stats=total_stats)
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def _calculate_stats(
        self,
        hierarchy: List[Chunk],
        text: List[Chunk],
        code: List[Chunk],
        table: List[Chunk],
    ) -> ChunkStats:
        """Calculate statistics for the chunking result."""
        # 1. Base counts
        stats = ChunkStats(
            hierarchy=len(hierarchy),
            text=len(text),
            code=len(code),
            table=len(table),
        )
        
        # 2. Relationship analysis
        all_content = text + code + table
        stats.orphans = sum(1 for c in all_content if not c.parent_chunk_id)
        stats.linked = len(all_content) - stats.orphans
        
        # 3. Rich metadata analysis
        stats.with_comments = self._count_with_metadata(code, K.META_COMMENTS)
        stats.with_symbols = self._count_with_metadata(code, K.META_SYMBOLS)
        stats.tables_with_headers = self._count_with_metadata(table, K.META_HEADERS)
        
        # 4. Symbol kinds & Languages
        stats.languages = self._count_languages(code)
        
        all_symbols = []
        for c in code:
            all_symbols.extend(c.metadata.get(K.META_SYMBOLS, []))
        stats.symbols = self._summarize_symbols(all_symbols)
        
        return stats

    @staticmethod
    def _summarize_symbols(symbols: List[Dict[str, Any]]) -> Dict[str, int]:
        """Summarize symbol counts by kind."""
        counts: Counter = Counter()
        for sym in symbols:
            counts[sym.get("kind", "unknown")] += 1
        return dict(counts)
    
    @staticmethod
    def _count_languages(chunks: List[Chunk]) -> Dict[str, int]:
        """Count code chunks by language."""
        counts: Counter = Counter()
        for chunk in chunks:
            lang = chunk.metadata.get(K.META_LANGUAGE, "unknown")
            if lang and lang != "unknown":
                counts[lang] += 1
        return dict(counts)
    
    @staticmethod
    def _count_with_metadata(chunks: List[Chunk], key: str) -> int:
        """Count chunks that have non-empty metadata for a given key."""
        return sum(1 for c in chunks if c.metadata.get(key))
    
    # =========================================================================
    # LOGGING
    # =========================================================================
    
    def _log_batch_summary(self, files_count: int, stats: ChunkStats) -> None:
        """Log batch processing summary."""
        self.logger.info(f"\n{'='*60}")
        self.logger.info("📈 BATCH SUMMARY")
        self.logger.info(f"{'='*60}")
        self.logger.info(f"   Files Processed:    {files_count}")
        self.logger.info(f"   Total Hierarchy:    {stats.hierarchy}")
        self.logger.info(f"   Total Text:         {stats.text}")
        self.logger.info(f"   Total Code:         {stats.code}")
        self.logger.info(f"   Total Table:        {stats.table}")


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_chunker(
    settings: Optional[ChunkerSettings] = None,
    **kwargs,
) -> ChunkerManager:
    """
    Factory function to create a ChunkerManager.
    
    Args:
        settings: Optional ChunkerSettings instance
        **kwargs: Additional settings to merge with defaults
        
    Returns:
        Configured ChunkerManager instance
    """
    if settings is None and kwargs:
        settings = ChunkerSettings(**kwargs)
    return ChunkerManager(settings=settings)
