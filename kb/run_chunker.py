#!/usr/bin/env python
"""
Chunker CLI - Process documents into structured chunks with rich metadata.

This is a thin CLI wrapper around the unified ChunkerManager.

Usage:
    python run_chunker.py doc/example.md
    python run_chunker.py src/app.py --out output.json
    python run_chunker.py doc/ --batch  # Process all files in directory

For programmatic use, use the create_chunker factory:
    from chunker import create_chunker
    
    chunker = create_chunker()
    result = chunker.process_file("doc/example.md")
"""

import argparse
import warnings
import logging
from pathlib import Path

# Import central config
from config import setup_logging, get_logger

# Suppress SyntaxWarnings from pysbd library
warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

try:
    from chunker import create_chunker, ChunkerSettings
except ImportError:
    print("❌ Error: Could not find the 'chunker' module.")
    exit(1)

# ============================================================================
# DISPLAY HELPERS
# ============================================================================

def display_result(result, logger: logging.Logger) -> None:
    """Display detailed statistics for a single file result."""
    stats = result.stats
    
    logger.info("")
    logger.info("  📊 STRUCTURE")
    logger.info(f"     ├── Hierarchy Nodes:  {stats.hierarchy}")
    logger.info(f"     ├── Text Chunks:      {stats.text}")
    logger.info(f"     ├── Code Chunks:      {stats.code}")
    logger.info(f"     └── Table Chunks:     {stats.table}")
    
    if result.code:
        logger.info("")
        logger.info("  💻 CODE ANALYSIS (Rich Metadata)")
        
        # Languages
        if stats.languages:
            langs = ", ".join(f"{k}({v})" for k, v in stats.languages.items())
            logger.info(f"     ├── Languages:        {langs}")
        
        # Symbols
        if stats.symbols:
            syms = ", ".join(f"{k}({v})" for k, v in stats.symbols.items())
            logger.info(f"     ├── Symbols Defined:  {syms}")
        
        # Metadata coverage
        code_count = len(result.code)
        logger.info(f"     ├── With Comments:    {stats.with_comments}/{code_count}")
        logger.info(f"     └── With Symbols:     {stats.with_symbols}/{code_count}")
    
    if result.table:
        logger.info("")
        logger.info("  📊 TABLE ANALYSIS")
        logger.info(f"     └── With Headers:     {stats.tables_with_headers}/{len(result.table)}")
    
    logger.info("")
    logger.info("  🔗 HIERARCHY VALIDATION")
    logger.info(f"     ├── Linked Chunks:    {stats.linked}")
    logger.info(f"     └── Orphaned Chunks:  {stats.orphans} {'✅' if stats.orphans == 0 else '⚠️'}")

# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Chunk documents into structured JSON with rich metadata.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_chunker.py doc/example.md           # Single markdown file
  python run_chunker.py src/app.py               # Single code file
  python run_chunker.py doc/ --batch             # All files in directory
  python run_chunker.py doc/example.md -v        # Verbose output
    
Programmatic Usage:
  from chunker import create_chunker
    
  chunker = create_chunker()
  result = chunker.process_file("doc/example.md")
  print(f"Extracted {result.total_chunks} chunks")
        """
    )
    parser.add_argument("file", help="Path to file or directory (with --batch)")
    parser.add_argument("--out", "-o", help="Output JSON filename", default=None)
    parser.add_argument("--batch", "-b", action="store_true", help="Process all files in directory")
    parser.add_argument("--recursive", "-r", action="store_true", help="Process subdirectories recursively")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--overlap", type=int, default=300, help="Number of overlap tokens")
    args = parser.parse_args()

    # Use central logging setup
    setup_logging(level="DEBUG" if args.verbose else "INFO")
    logger = get_logger("ChunkerCLI")
    
    input_path = Path(args.file)
    
    if not input_path.exists():
        logger.error(f"❌ Path not found: {input_path}")
        return

    # =========================================================================
    # INITIALIZE CHUNKER (settings come from EMBEDDING_CONFIG via ChunkerSettings)
    # =========================================================================
    settings = ChunkerSettings(
        # tokenizer_name comes from EMBEDDING_CONFIG (env: EMBEDDING_MODEL)
        max_tokens_text=2000,
        overlap_tokens=args.overlap,
        min_keep_tokens=1,  # Ensure 100% content fidelity
        emit_heading_chunks=True,
        inject_headers=True,
        split_code_max_lines=50,
        split_table_rows=100,
        use_treesitter=True,
        max_tokens_by_type={"text": 2000, "code": 2000, "table": 2000},
    )
    
    chunker = create_chunker(settings=settings, logger=logger)

    # =========================================================================
    # BATCH MODE
    # =========================================================================
    if args.batch and input_path.is_dir():
        batch_result = chunker.process_directory(
            input_path,
            recursive=args.recursive,
        )
        
        # Detailed per-file display (if verbose)
        if args.verbose:
            for source, result in batch_result.results.items():
                logger.info(f"\n{'='*60}")
                logger.info(f"📖 {Path(source).name}")
                logger.info(f"{'='*60}")
                display_result(result, logger)
        
    # =========================================================================
    # SINGLE FILE MODE
    # =========================================================================
    elif input_path.is_file():
        output_path = args.out if args.out else str(input_path.parent / f"{input_path.stem}_structured.json")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📖 Processing: {input_path.name}")
        logger.info(f"{'='*60}")
        
        result = chunker.process_file(input_path, output_path)
        display_result(result, logger)
        
        logger.info("")
        logger.info(f"  💾 Saved to: {output_path}")
        
    else:
        logger.error(f"❌ Not a file or directory: {input_path}")
        return
    
    logger.info(f"\n✅ Done!")

if __name__ == "__main__":
    main()