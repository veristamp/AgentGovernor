# 🧩 Chunker Module

**High-Performance, AST-Based Document Chunking for RAG & LLMs**

The `chunker` module transforms raw documents (Markdown, Code, HTML) into semantically meaningful, token-optimized "chunks" ready for vector embeddings and RAG.

Unlike naive splitters that blindly chop text at character limits, this module uses **Abstract Syntax Tree (AST)** parsing to respect the document's logical structure.

---

## 🌟 Key Features

### 🧠 Semantic & Structural Awareness
- **AST-Based Markdown Parsing**: Uses `markdown-it-py` to traverse the document tree
- **Breadcrumb Context**: Every chunk carries its hierarchical path (e.g., `Docs > API > Auth`)
- **Tree-sitter Code Analysis**: Parses code files (Python, JS, Go, Rust, HTML, etc.)
- **Table Intelligence**: Large tables split row-by-row with **headers preserved**
- **Synthetic Hierarchy**: Code files get automatic root headings (no orphan chunks)

### ⚡ Performance & Efficiency
- **Token-Aware Splitting**: Uses embedding model tokenizers for exact sizing
- **Paragraph-First Splitting**: Text chunks respect paragraph and sentence boundaries
- **Word Boundary Respect**: Long sentences split at word boundaries (no "frag-mented" words)
- **Smart Caching**: SHA-256 content-addressable caching (~90% speedup on re-runs)

### 🛡️ Robustness & Stability
- **Stable Chunk IDs**: Deterministic IDs based on content and position
- **Byte-Perfect Reconstruction**: Chunks track exact character offsets for source mapping
- **Page Tracking**: Detects `<!-- PAGE X -->` markers for PDF citations

---

## 📦 Installation

```bash
pip install markdown-it-py transformers tree-sitter-language-pack pysbd
```

---

## 🚀 Quick Start

### ChunkerManager (Recommended)

```python
from chunker import create_chunker

chunker = create_chunker()

# Process a single file
result = chunker.process_file("doc/example.md")
print(f"Extracted {result.total_chunks} chunks")

# Access structured results
for chunk in result.text:
    print(f"[{chunk.id}] {chunk.text[:100]}...")

# Save to JSON
result.save("output.json")
```

### Batch Processing

```python
from chunker import ChunkerManager

chunker = ChunkerManager()
batch_result = chunker.process_directory("doc/", recursive=True)
print(f"Processed {batch_result.files_processed} files")
```

---

## ⚙️ Configuration

The `ChunkerSettings` dataclass controls splitting behavior:

| Setting | Default | Description |
| :--- | :--- | :--- |
| `max_tokens_text` | 2000 | Target token limit for text chunks |
| `overlap_tokens` | 300 | Context overlap between chunks |
| `min_merge_tokens` | 50 | Small chunks below this are merged |
| `inject_headers` | `True` | Prepends breadcrumb path to chunk text |
| `split_table_rows` | 100 | Max rows per table chunk |
| `split_code_max_lines` | 200 | Max lines for code blocks |
| `tokenizer_name` | auto | Uses embedding model tokenizer |
| `embedding_max_tokens` | 8192 | Hard limit for embedding model |
| `use_treesitter` | `True` | Enable tree-sitter for code parsing |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                 HIGH LEVEL - ChunkerManager                     │
│                                                                 │
│   process_content(content, filename)                            │
│   process_file(path)                                            │
│   process_directory(path, extensions)                           │
├─────────────────────────────────────────────────────────────────┤
│                 MID LEVEL - Parsers                             │
│                                                                 │
│   ┌─────────────────────────┐   ┌────────────────────────────┐  │
│   │  MarkdownASTChunker     │   │      CodeChunker           │  │
│   │  (ast_parser.py)        │   │  (code_parser/chunker.py)  │  │
│   │                         │   │                            │  │
│   │  • markdown-it-py AST   │   │  • Tree-sitter parsing     │  │
│   │  • Heading stack        │   │  • Symbol extraction       │  │
│   │  • Table handling       │   │  • Synthetic root heading  │  │
│   └─────────────────────────┘   └────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                 LOW LEVEL - Core                                │
│                                                                 │
│   core.py        - Chunk, ProcessingContext, ChunkType         │
│   config.py      - ChunkerSettings, ChunkKeys                  │
│   utils.py       - token_count(), split_sentences()            │
│   factories.py   - TokenizerFactory, SegmenterFactory          │
│   text_splitter.py - token_aware_text_chunks_with_spans()      │
│   chunk_factory.py - merge_small_chunks()                      │
└─────────────────────────────────────────────────────────────────┘
```

### Module Structure

| Layer | File | Purpose |
| :--- | :--- | :--- |
| **High** | `manager.py` | ChunkerManager - unified interface |
| **Mid** | `ast_parser.py` | MarkdownASTChunker class |
| **Mid** | `code_parser/` | CodeChunker class + helpers |
| **Low** | `core.py` | Chunk dataclass, ProcessingContext |
| **Low** | `config.py` | ChunkerSettings |
| **Low** | `text_splitter.py` | Token-aware text splitting |
| **Low** | `utils.py` | Utility functions |
| **Low** | `factories.py` | Tokenizer/Segmenter factories |

### Code Parser Module

```
code_parser/
├── __init__.py          # Exports
├── chunker.py           # CodeChunker class (~340 lines)
├── emitters.py          # Chunk emission functions (~200 lines)
├── helpers.py           # Span, naming, metadata utilities (~180 lines)
├── constants.py         # Language mappings, node types (~120 lines)
├── symbol_extraction.py # AST symbol/comment extraction (~200 lines)
└── api.py               # Standalone functions for markdown (~120 lines)
```

---

## 📊 Chunk Output Structure

Each chunk is a `Chunk` dataclass (or dict via `to_dict()`):

```python
Chunk(
    id=84720194823,               # Stable deterministic ID
    index=5,                      # Sequential index
    text="**API > Endpoints**\n\nGET /users returns...",
    chunk_type=ChunkType.TEXT,    # TEXT, CODE, TABLE, HEADING
    source="docs/api.md",
    source_name="api.md",
    section_path="API > Endpoints",
    token_count=142,
    parent_chunk_id=84720194800,  # Links to parent heading
    char_start=1024,              # Absolute char offset
    char_end=1524,
    original_text="...",          # For byte-perfect reconstruction
    metadata={
        "breadcrumbs": ["API", "Endpoints"],
        "root_topic": "API",
        "language": "python",     # For code chunks
        "symbols": [...],         # Extracted functions/classes
    }
)
```

### ChunkResult

```python
result = chunker.process_file("doc.md")

# Access by type
result.hierarchy  # Heading chunks (for tree reconstruction)
result.text       # Text chunks (for embeddings)
result.code       # Code chunks
result.table      # Table chunks

# Statistics
result.stats.hierarchy
result.stats.text
result.stats.languages  # {"python": 5, "javascript": 3}

# Export
result.to_dict()        # Full JSON structure
result.save("out.json")
```

---

## 🔧 CLI Usage

```bash
# Single file
python -m cli.run_chunker doc/example.md

# Batch processing
python -m cli.run_chunker doc/ --batch --recursive
```

---

## ✅ Verification

Test byte-perfect reconstruction:

```bash
python -m tests.local_reconstruction_check doc/example.md
# Output: OK: byte-perfect reconstruction
```

---

## 🔑 Design Principles

1. **Chunk dataclass is source of truth** - All internal operations use `Chunk` objects
2. **ProcessingContext tracks state** - Heading stack, offsets, parent IDs
3. **to_dict() for serialization only** - Convert at output boundary
4. **Span preservation** - Every chunk tracks exact source positions
5. **Graceful degradation** - Works without optional dependencies (tree-sitter, pysbd)