# 📚 Complete Knowledge Base Documentation

> **All README files stitched together** - Auto-generated on 2026-01-10 23:55

This document contains the complete documentation from all modules in the Knowledge Base system.

## Table of Contents

1. [Chunker](#chunker)
2. [Concept Harvester](#concept-harvester)
3. [Db](#db)
4. [Rag](#rag)
5. [Llm](#llm)
6. [Latent Memory](#latent-memory)
7. [Judgment](#judgment)
8. [File Patcher](#file-patcher)
9. [Agent](#agent)
10. [Services](#services)
11. [Api](#api)
12. [Ingestion](#ingestion)

---

# From: chunker/README.md
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


---


# From: concept_harvester/README.md
# Concept Harvester 🌾

**Version 3.4.0**

The **Concept Harvester** is the semantic extraction engine that turns raw text into a connected Knowledge Graph. It implements the **"Rich Metadata, Lazy Resolution"** pattern to bridge the gap between Code (AST) and Prose (GLiNER).

## Target Domains

Optimized for:
- 📚 Code library documentation
- 📄 Scientific research papers
- 💻 GitHub code parsing
- 🤖 AI/ML research

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │         ConceptManager              │
                    │   (Orchestrates Ghost Input Flow)   │
                    └─────────────────────────────────────┘
                        ↓              ↓              ↓
              ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
              │ ContextInj. │  │  Harvester   │  │   Resolver   │
              │ (Enrich)    │  │  (Extract)   │  │ (Canonicalize)
              └─────────────┘  └──────────────┘  └──────────────┘
```

### Full Pipeline Flow

```
Raw Chunk (JSON)
    │
    ▼
┌───────────────────────────┐
│  Context Injector         │ (context_injector.py)
│  "Ghost Input" Pattern    │ → Injects: [CONTEXT: Crawl4AI | Auth]
└────────────┬──────────────┘
             │
             ▼
┌───────────────────────────┐
│  Harvester (Polymorphic)  │ (harvester.py)
│  1. TEXT → GLiNER         │ → Semantic Extraction
│  2. CODE → AST Symbols    │ → Deterministic Extraction
│  3. TABLE → Headers       │ → Structured Extraction
└────────────┬──────────────┘
             │
             ▼
┌───────────────────────────┐
│  Concept Resolver         │ (concept_resolver.py)
│  1. L1 Cache (Fast)       │
│  2. L2 Postgres (Exact)   │
│  3. L3 Qdrant (Vector)    │ → Merges synonyms ("DB" == "Database")
└────────────┬──────────────┘
             │
             ▼
      Weighted Edges
```

## Quick Start

### Unified Manager (Recommended)

The `ConceptManager` is the recommended entry point. It orchestrates context injection, extraction, and resolution.

```python
from concept_harvester import create_concept_manager

# Initialize with database connections
manager = create_concept_manager(
    pg_session=db_session, 
    qdrant_client=qdrant
)

# Extract and Resolve in one call
edges = await manager.harvest_chunk(chunk, root_topic="MyLibrary")

# Or batch process for high throughput
result = await manager.harvest_batch(chunks, root_topic="MyLibrary")
print(f"Created {len(result.edges)} graph connections")
```

### Extraction Only (No Database)

If you only need extraction without resolution:

```python
from concept_harvester import create_concept_manager

manager = create_concept_manager()

# Extract concepts with Ghost Input + disambiguation
concepts = manager.tag_chunk(chunk, root_topic="PyTorch")
# Output: [{"name": "PyTorch Neural Network", "type": "Neural Network"}, ...]

# Generic terms are auto-disambiguated:
# "system" → "PyTorch system"
# "model" → "PyTorch model"
```

### Low-Level Access

```python
from concept_harvester import (
    ConceptHarvester,
    ContextInjector,
    ConceptResolver,
)

# 1. Inject context (Ghost Input)
injector = ContextInjector()
ghost_text = injector.inject(
    text="The model uses attention...",
    section_path="Architecture > Attention",
    root_topic="Transformers"
)

# 2. Extract concepts
harvester = ConceptHarvester()
concepts = harvester.extract_from_text(ghost_text)

# 3. Resolve to canonical IDs (requires database)
resolver = ConceptResolver(pg_session=db, qdrant_client=qdrant)
edges = await resolver.resolve(
    terms=["attention", "transformer"],
    source_chunk_id=123,
    chunk_text=ghost_text
)
```

## Modules

### `harvester.py` (The Extractor)

Routes extraction based on chunk type:

| Chunk Type | Extraction Method | Source |
|------------|-------------------|--------|
| **TEXT** | GLiNER semantic extraction | Full prose content |
| **CODE** | AST symbols + GLiNER on comments | `metadata.symbols_defined` + `comments_text` |
| **TABLE** | GLiNER on headers | `metadata.headers` |
| **HEADING** | Skip | Structure only |

### `concept_resolver.py` (The Linker)

Prevents graph explosion by canonicalizing terms:

- **Dynamic Stoplist:** Filters "supernodes" (concepts in >10% of docs) using IDF
- **Vector Handshake:** Qdrant similarity to merge "PostgreSQL" ↔ "Postgres DB"
- **Weighted Edges:** Heading=1.0, First sentence=0.8, Body=0.5

### `context_injector.py` (The Sanitizer)

Implements the **Ghost Input Pattern**:

1. Injects breadcrumb path before extraction
2. Disambiguates generic terms ("System" → "Auth System")
3. **Never stores** injected text — analysis only

### `graph_gardener.py` (The Maintainer)

Async maintenance agent for graph hygiene:

1. **Prune Islands:** Delete concepts with only 1 connection
2. **Compact Synonyms:** Merge high-similarity concepts
3. **Demote Supernodes:** Lower weight of overly common terms

```python
from concept_harvester.graph_gardener import DatabaseGardener

gardener = DatabaseGardener(
    pg_session=db,
    qdrant_client=qdrant,
    synonym_threshold=0.92
)
stats = await gardener.run()
```

> **Note:** There's also a `cli/file_watcher.py` for real-time file monitoring.
> That's a different tool for auto-syncing on file changes.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GLINER_MODEL` | `urchade/gliner_medium-v2.1` | GLiNER model name |
| `BASE_THRESH` | `0.50` | Confidence threshold (0.0-1.0) |
| `MAX_TEXT_CHARS` | `2000` | Max chars per extraction |
| `ONTOLOGY_PATH` | `./ontology.yaml` | Path to ontology file |

### Threshold Tuning

| Threshold | Use Case |
|-----------|----------|
| `0.40` | Discovery mode (find everything) |
| `0.50` | Balanced (default for technical docs) |
| `0.60` | Precision mode (high-confidence only) |

### Ontology (`ontology.yaml`)

The ontology defines what concept types GLiNER extracts. **60 labels** organized by domain:

| Category | Example Labels |
|----------|----------------|
| **Software** | Framework, Library, API, Design Pattern |
| **AI/ML** | Neural Network, Language Model, Embedding, Transformer, RAG |
| **Research** | Methodology, Theorem, Benchmark, Research Paper |
| **Entities** | Organization, Open Source Project, Dataset |

Add domain-specific labels dynamically:

```python
config = HarvesterConfig()
config.add_labels(["Custom Concept", "Domain Term"])
```

## API Reference

### Core Classes

```python
# Configuration
HarvesterConfig    # GLiNER settings, thresholds
InjectionConfig    # Context injection settings

# Components
ConceptHarvester   # Polymorphic extraction
ContextInjector    # Ghost Input Pattern
ConceptResolver    # 3-tier canonicalization

# Orchestrator
ConceptManager     # Unified facade

# Data Classes
ResolvedConcept    # Resolved concept with ID
ConceptEdge        # Weighted graph edge
HarvestResult      # Batch processing result
HarvestStats       # Processing statistics
```

### Utilities

```python
from concept_harvester import (
    clean_concept_name,        # Sanitize concept names
    inject_context_to_chunks,  # Batch context injection
)
```

## Performance

- **GPU Accelerated:** Uses CUDA for GLiNER inference
- **Caching:** 3-tier resolution cache (L1 memory → L2 Postgres → L3 Qdrant)
- **Batch Processing:** `harvest_batch()` for high throughput



---


# From: db/README.md
# Dual-Graph Architecture

Production-ready async ingestion system combining Postgres (Hard Graph) and Qdrant (Soft Graph).

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    ENRICHED JSON FILES                       │
│              (*_enriched.json with concepts)                 │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│            ASYNC DUAL-GRAPH INGESTION WORKER                 │
│                 (The "Unified Ingester")                    │
│                                                              │
│  Phase 0: Semantic Harvesting (Ghost Input Pattern)          │
│  Phase 1: Embed in ThreadPool (non-blocking)                │
│  Phase 2: Postgres Batch Write (Skeleton)                   │
│  Phase 3: Qdrant Batch Write (Nerves)                       │
│  Phase 4: 3-Tier Concept Resolution & Weighted Edges        │
└────────────┬────────────────────────────┬────────────────────┘
             │                            │
             ▼                            ▼
┌────────────────────────┐    ┌──────────────────────────────┐
│   POSTGRES (Hard Graph)│    │   QDRANT (Soft Graph)        │
│                         │    │                              │
│ • nodes (AST structure) │    │ • Hybrid Vectors             │
│ • global_concepts (hub) │    │   - Dense (semantic)        │
│ • edges (connections)   │    │   - Sparse (BM25)          │
│                         │    │ • Graph coordinates payload │
│ Denormalized pointers:  │    │   - section_root_id        │
│ • parent_id             │    │   - concept_tags           │
│ • prev_id / next_id     │    │                              │
└────────────────────────┘    └──────────────────────────────┘
```

## Setup

### 1. Install Dependencies

```bash
uv sync
```

### 2. Setup Postgres

```bash
# Using Docker
docker run -d \
  --name postgres-kb \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=kb \
  -p 5432:5432 \
  postgres:16-alpine

# Or install locally: https://www.postgresql.org/download/
```

### 3. Setup Qdrant

```bash
# Using Docker
docker run -d \
  --name qdrant-kb \
  -p 6333:6333 \
  -p 6334:6334 \
  qdrant/qdrant

# Or install locally: https://qdrant.tech/documentation/quick-start/
```

### 4. Configure Environment

Copy `.env.example` to `.env`:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/kb

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=  # Optional, for Qdrant Cloud

# LLM (optional for auto-review)
OPENAI_API_KEY=your-key-here
```

### 5. Initialize Databases

```bash
python -m db.async_init
```

This creates:
- Postgres tables (`nodes`, `global_concepts`, `edges`)
- Qdrant collection with hybrid vectors (`kb_chunks`)

## Ingestion

### Run on Enriched Files

```bash
python -m db.run_ingestion --glob "*_enriched.json"
```

### What Happens

1. **Semantic Harvesting (Phase 0)**: Uses GLiNER + AST via the `Harvester` to extract concepts. Employs the **Ghost Input Pattern** (injecting breadcrumbs/context) to disambiguate terms.
2. **Embedding (Async)**: Texts are embedded using `BAAI/bge-base-en-v1.5` (Dense) and BM25 (Sparse).
3. **Postgres Write**: Creates nodes with AST structure (parent/child/sibling links) and stability via stable IDs.
4. **Qdrant Write**: Stores dense + sparse vectors with graph coordinates for Latent Memory surgery.
5. **Concept Resolution (Phase 4)**: Uses a **3-tier Resolver** (Cache -> Postgres Exact -> Qdrant Similarity) to canonicalize concepts and create weighted `MENTIONS` edges.

### Data Flow

```python
# Input: enriched.json
{
  "text": [
    {
      "chunk_id": "abc123",
      "text": "Django is a web framework",
      "concepts": [
        {"name": "Django", "type": "Framework", "score": 0.92}
      ],
      "section_path": "Introduction > Overview"
    }
  ]
}

# Output: Postgres Node
Node(
  id=BLAKE2b("url|abc123"),
  type="CHUNK",
  content="Django is a web framework",
  parent_id=<section_header_id>,
  section_path="Introduction > Overview",
  ...
)

# Output: Qdrant Point
Point(
  id=<same_blake2b_id>,
  vector={
    "dense": [0.23, 0.45, ...],  # 768-dim FastEmbed
    "bm25": {indices: [...], values: [...]}
  },
  payload={
    "section_root_id": <section_header_id>,
    "concept_tags": ["Django"],
    ...
  }
)

# Output: Concept Edge
Edge(
  source_id=<chunk_id>,
  target_id=<django_concept_id>,
  edge_type="MENTIONS"
)
```

##  Features

### Stable IDs
Uses BLAKE2b hash of `url|chunk_id` for idempotency:
- Re-running ingestion updates existing data
- Same content always gets same ID
- Postgres and Qdrant IDs are synced

### Denormalized Graph
O(1) traversal without recursive joins:
- `parent_id`: Direct link to section header
- `prev_id`/`next_id`: Doubly-linked list for reading order
- `section_path`: Full breadcrumb for context

### Hybrid Search
Qdrant stores both:
- **Dense vectors**: Semantic similarity (FastEmbed)
- **Sparse vectors**: Keyword matching (BM25)

### Grouping API Ready
Payload includes `section_root_id` for **Qdrant's `search_groups`**:
```python
results = await qdrant.search_groups(
    collection_name="kb_chunks",
    query_vector=[...],
    group_by="section_root_id",  # Groups chunks by section
    limit=10,
    group_size=3
)
```

### Concept Hub-and-Spoke (3-Tier Resolution)
Instead of N² edges, concepts are hubs:
- **L1 (Local Cache)**: Instant lookup for frequent terms.
- **L2 (Postgres Exact)**: Normalization of known entities.
- **L3 (Qdrant Vector)**: Fuzzy matching for synonyms and related terms.
- **Weighted Edges**: Edges are weighted by concept prominence (Heading vs. Body).

### Latent Memory Architecture
Optimizations to minimize "Cyclical API Calls":
- **Vector Ripple**: Metadata-only updates in Qdrant after file edits.
- **KV Cache Management**: Structure-Invariant Prompting to maximize context reuse.
- **Citation-Driven Feedback**: Automatic retrieval refinement via LLM citation signals.

## Visualization

### Graph Viewer (Current - JSON based)
```bash
streamlit run graph_viewer.py
```

### Future: Database-Powered Viewer
Will query Postgres + Qdrant directly:
- **Map View**: Section hierarchy from Postgres
- **Heatmap View**: Concept distribution from Qdrant
- **Connection View**: Semantic links via `search_groups`

## Performance

### Async Benefits
- **Non-blocking embeddings**: CPU work in thread pool
- **Concurrent I/O**: Postgres + Qdrant writes overlap
- **Batch operations**: 50-100 nodes per commit

### Typical Speed
- **50 chunks**: ~2-3 seconds
- **500 chunks**: ~15-20 seconds
- Bottleneck: Embedding generation

## Schema Details

### Postgres Tables

#### `nodes`
| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGINT | BLAKE2b stable ID |
| `doc_url` | VARCHAR | Source document |
| `type` | VARCHAR | CHUNK, SECTION, ASSET, CODE |
| `content` | TEXT | Actual text |
| `parent_id` | BIGINT | Section header ID |
| `prev_id`/`next_id` | BIGINT | Reading order |
| `section_path` | TEXT | Breadcrumb trail |
| `meta` | JSON | h_level, lang, etc. |

#### `global_concepts`
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Auto-increment |
| `name` | VARCHAR | Unique concept name |
| `doc_count` | INTEGER | How many docs mention it |

#### `edges`
| Column | Type | Description |
|--------|------|-------------|
| `source_id` | BIGINT | Chunk/Node ID |
| `target_id` | BIGINT | Concept/Asset ID |
| `edge_type` | VARCHAR | MENTIONS, REFERS_TO |
| `weight` | FLOAT | Relevance score |

#### `conversation_logs` (STM)
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary Key |
| `session_id` | VARCHAR | Groups turns into a session |
| `role` | VARCHAR | user, assistant, system |
| `content` | TEXT | Raw message content |
| `token_count`| INTEGER | For cache budgeting |
| `model_used` | VARCHAR | Model identifier |
| `meta` | JSON | Citations, latency, etc. |
| `created_at` | DATETIME| Sorting for prefix stability |

### Qdrant Collection

**Vectors**:
- `dense`: 768-dim (FastEmbed `BAAI/bge-base-en-v1.5`)
- `bm25`: Sparse (BM25 indices + values)

**Payload**:
```json
{
  "section_root_id": 12345,  # For grouping
  "concept_tags": ["Django", "ORM"],  # For filtering
  "doc_id": "file.md",
  "section_path": "Auth > Tokens",
  "type": "text",
  "h_level": 2
}
```

## Next Steps

1. ✅ Database schema created
2. ✅ Async ingestion worker implemented (Unified Ingester)
3. ✅ Run ingestion on real data
4. ✅ Move Retrieval & Latent Memory to dedicated packages (`rag/`, `latent_memory/`)
5. ⏳ Update graph viewer to query databases
6. ⏳ Scale to multi-agent swarm

## References

- [Postgres Async Guide](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Qdrant Async Client](https://python-client.qdrant.tech/qdrant_client.async_qdrant_client)
- [Grouping API](https://qdrant.tech/documentation/concepts/search/#grouping-api)
- [PRD: graph.md](prd/graph.md)
- [PRD: graph-plan.md](prd/graph-plan.md)



---


# From: rag/README.md
# RAG Package 🔍

**Retrieval Augmented Generation** - Vector search + Graph enrichment.

## Quick Start

```python
from rag import create_rag_manager

# Initialize with database connection
rag = create_rag_manager(pg_session=db_session)

# Retrieve enriched chunks
chunks = await rag.retrieve("How does the chunker work?")

for chunk in chunks:
    print(f"[{chunk.source}] {chunk.content[:100]}...")
    print(f"  Concepts: {chunk.related_concepts}")

# Get formatted context for LLM
context = await rag.get_context(
    query="How does the chunker work?",
    limit=5,
    include_concepts=True
)
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     HIGH LEVEL - RAGManager                                  │
│                                                                              │
│   retrieve(query)   search(query)   enrich(hits)   get_context(query)       │
│       │                  │              │               │                    │
│       └──────────────────┴──────────────┴───────────────┘                    │
│                                    │                                         │
├────────────────────────────────────┼─────────────────────────────────────────┤
│                     MID LEVEL - Components                                   │
│                                    │                                         │
│   ┌────────────────────────────────┼──────────────────────────────────┐     │
│   │                                │                                   │     │
│   ▼                                ▼                                   ▼     │
│   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐        │
│   │ SearchPipeline   │   │ ContextRetriever │   │ SemanticCompress │        │
│   │                  │   │                  │   │                  │        │
│   │ • Document Scout │   │ • Graph traverse │   │ • Token budget   │        │
│   │ • Hybrid search  │   │ • Parent context │   │ • Compression    │        │
│   │ • RRF fusion     │   │ • Prev/next flow │   │                  │        │
│   │ • MMR diversity  │   │ • Concepts       │   │                  │        │
│   │ • Reranking      │   │                  │   │                  │        │
│   └──────────────────┘   └──────────────────┘   └──────────────────┘        │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                     LOW LEVEL - Models                                       │
│                                                                              │
│   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐        │
│   │  DenseEmbedder   │   │  SparseEmbedder  │   │     Reranker     │        │
│   │                  │   │                  │   │                  │        │
│   │ • FastEmbed      │   │ • BM25 via       │   │ • Cross-Encoder  │        │
│   │ • Ollama         │   │   FastEmbed      │   │ • MS MARCO       │        │
│   │ • OpenAI         │   │                  │   │                  │        │
│   └──────────────────┘   └──────────────────┘   └──────────────────┘        │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                     DATA - Core Types                                        │
│                                                                              │
│   RAGConfig | SearchHit | RAGResult | EnrichedChunk                         │
│   SearchMode (DENSE, SPARSE, HYBRID) | FusionMethod (RRF, WEIGHTED)         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Search Pipeline

The "Zoom-In" strategy:

```
Query: "How does chunking work?"
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│  1. DOCUMENT SCOUT (Grouped Search)                          │
│     Find top N documents that contain relevant content       │
│     → Returns: ["chunker/README.md", "chunker/ast_parser.py"]│
└──────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│  2. HYBRID SEARCH (Dense + Sparse)                           │
│     Within those documents, find best chunks                 │
│     Dense: Semantic similarity                               │
│     Sparse: BM25 keyword matching                            │
│     → RRF Fusion combines both rankings                      │
└──────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│  3. MMR (Maximal Marginal Relevance)                         │
│     Diversify results - avoid similar chunks                 │
└──────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│  4. RERANKING (Cross-Encoder)                                │
│     Re-score with query-document attention                   │
│     → Final top-K chunks                                     │
└──────────────────────────────────────────────────────────────┘
```

---

## Graph Enrichment

After vector search, chunks get enriched with graph context:

```python
EnrichedChunk:
├── chunk_id: 12345
├── content: "The AST parser extracts..."
├── source: "chunker/ast_parser.py"
├── section_path: "Chunker > AST Parser > Overview"
│
├── parent_context: "Chunker module documentation..."   # From PARENT edge
├── prev_chunk: "Previous section about..."             # From PREV edge
├── next_chunk: "Next section about..."                 # From NEXT edge
│
├── related_concepts: ["AST", "Parser", "Tree-sitter"]  # From MENTIONS edges
│
└── ide_url: "vscode://file/f:/kb/chunker/ast_parser.py:45"
```

---

## Embedding Providers

The system supports multiple embedding backends:

| Provider | Type | Usage |
|----------|------|-------|
| **FastEmbed** | Local | Default, CPU/GPU |
| **Ollama** | Remote | Local server |
| **OpenAI** | Remote | API |
| **Infinity** | Remote | Self-hosted |

Configure via environment:

```env
EMBEDDING_PROVIDER=ollama
EMBEDDING_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text
```

---

## File Structure

```
rag/
├── __init__.py            # Clean exports with layer docs
├── core.py                # Data types (RAGConfig, SearchHit, etc.)
│
├── models.py              # Embedders (Dense, Sparse, Reranker)
├── pipeline.py            # HierarchicalSearchPipeline
├── retriever.py           # ContextRetriever + EnrichedChunk
├── compressor.py          # SemanticCompressor
├── retrieval_functions.py # Postgres SQL functions
│
├── manager.py             # RAGManager (unified facade)
└── README.md              # This file
```

---

## Integration with Other Modules

| Module | Integration |
|--------|-------------|
| **LLM** | `LLMManager` uses `RAGManager.retrieve()` for context |
| **Latent Memory** | Shares embedders, uses `EnrichedChunk` format |
| **Judgment** | `SemanticLinter` shares embedders with RAG |
| **File Patcher** | `ContextRetriever` provides chunks for stitching |

---

## Token Counting

Chunks already have accurate token counts from the chunker:

```python
chunk = {
    "text": "...",
    "token_count": 91,   # Already computed!
    "token_start": 13,
    ...
}

# Use directly - no estimation needed
from rag import get_token_count
tokens = get_token_count(chunk)  # Returns 91
```



---


# From: llm/README.md
# 🧠 LLM Orchestration & Layer Cake Memory

The `llm` package is the **"Split-Brain" Controller**. It orchestrates the flow between Retrieval-Augmented Generation (RAG), Short-Term Memory (STM), and various LLM providers using a unified **Manager Pattern**.

## 🎛️ User Control API

The LLM system now provides **full user control** over all features via API parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session_id` | `str?` | `None` | Session ID. `None` = ephemeral (no DB state) |
| `branch_from` | `str?` | `None` | Fork conversation from another session |
| `include_history` | `bool` | `True` | Load conversation history from DB |
| `history_k` | `int` | `10` | Number of history turns to include |
| `learn` | `bool` | `True` | Save this turn to memory |
| `include_ltm` | `bool` | `True` | Include long-term semantic memories |
| `use_rag` | `bool` | `True` | Enable RAG retrieval |
| `retrieval_limit` | `int` | `5` | Number of chunks to retrieve |

### Example: Full Control

```python
# Ephemeral chat (no session tracking)
response = await llm.chat(
    session_id=None,  # No persistence
    query="What is RAG?"
)

# Persistent session with full history
response = await llm.chat(
    session_id="user_123_conv_1",
    query="Explain chunking",
    include_history=True,
    history_k=10,
    learn=True
)

# Branch a conversation for exploration
response = await llm.chat(
    session_id="user_123_conv_1_alt",
    branch_from="user_123_conv_1",  # Copy history from here
    query="Actually, try a different approach"
)

# Pure LLM mode (no RAG, no memory)
response = await llm.chat(
    session_id=None,
    query="Write a haiku",
    use_rag=False,
    include_history=False
)
```

---

## 🏗️ Architecture

### The 4-Step Orchestration Cycle

The `LLMManager` follows a strict cycle for every turn:

1. **RETRIEVE**: Semantic search via `RAGManager` (if `use_rag=True`)
2. **PREPARE**: Build cache-optimal prompt with history via `LatentMemoryManager`
3. **GENERATE**: Multi-provider execution (OpenAI, Anthropic, Ollama, etc.)
4. **LEARN**: Save turn and extract feedback (if `learn=True`)

### The "Layer Cake" Prompt Strategy 🍰

To maximize **Prompt Cache** efficiency, prompts are assembled in deterministic order:

| Layer | Type | Description | Stability |
| :--- | :--- | :--- | :--- |
| **System** | `[STATIC]` | "You are a helpful assistant..." | **Permanent** |
| **Graph Context** | `[STABLE]` | Chunks sorted by **Stable ID** (not relevance) | **High** |
| **History** | `[EPISODIC]` | Last K turns of conversation | **Medium** |
| **User Query** | `[DYNAMIC]` | The new input (placed at the very end) | **None** |

> ⚠️ **STABILITY RULE**: Chunks are sorted by their `id` (content hash), NOT by Relevance Score. Scores fluctuate; hashes are forever. This ensures the prefix remains byte-for-byte identical across turns.

---

## 📂 Module Structure

- **`manager.py`**: The central `LLMManager`. Orchestrates the 4-step cycle.
- **`client.py`**: The `LLMClient` facade. Unified interface for 12+ providers.
- **`kernel.py`**: Shared infrastructure (Base classes, Retry logic, Env utils).
- **`cache_adapter.py`**: Provider-specific cache hints (OpenAI, Anthropic, Gemini, Groq).
- **`providers/`**: Optimized implementations for each provider.

---

## 🚀 Usage

### Basic Initialization

```python
from llm import create_llm_manager

llm = create_llm_manager(
    provider="openai",
    model="gpt-4o-mini",
    pg_session=db_session
)

# Execute the chat cycle with user control
response = await llm.chat(
    session_id="session_01",
    query="How does the Surgical Patcher work?",
    use_rag=True,
    include_history=True,
    history_k=10
)

print(response["response"])
print(f"Latency: {response['latency_ms']}ms")
print(f"Config used: {response['config_used']}")
```

### Multi-Provider Flexibility

```python
# Use local Ollama
llm = create_llm_manager(provider="ollama", model="qwen2.5:14b")

# Use ultra-fast Groq
llm = create_llm_manager(provider="groq", model="llama-3.3-70b-versatile")
```

---

## 📊 Response Metadata

Every response includes detailed metadata:

```python
{
    "response": "The Surgical Patcher is...",
    "session_id": "session_01",
    "chunk_ids": [123, 456, 789],
    "chunks": [...],
    "latency_ms": 1234,
    "config_used": {  # What was actually applied
        "use_rag": True,
        "retrieval_limit": 5,
        "include_history": True,
        "history_k": 10,
        "include_ltm": True,
        "learned": True
    },
    # Token/cache metadata
    "cached": True,
    "cached_tokens": 12400,
    "input_tokens": 12800,
    "output_tokens": 256
}
```

---

## 📈 Monitoring & Performance

The manager monitors **Prompt Caching** hits automatically:

- **Cache HIT**: `🚀 Prompt Cache HIT: 12400/12800 tokens cached (96.8%)`
- **Cache MISS**: `📦 Prompt Cache MISS: (First turn on this topic)`

Logs also show what features were used:
- `💬 Chat: RAG: 5 chunks, history: 10t, 1234ms, cached=True`




---


# From: latent_memory/README.md
# Latent Memory Package 🧠

**Unified AI Memory Interface** - The invisible brain for your LLM.

## Quick Start

```python
from latent_memory import create_memory_manager

# Initialize once
llm = create_memory_manager(
    system_prompt="You are a helpful coding assistant.",
    pg_session=db_session,
    qdrant_client=qdrant
)

# 1. PREPARE - Build prompt with context + history
prompt = await llm.prepare(
    session_id="user_abc",
    query="How does the chunker work?",
    chunks=retrieved_chunks
)

# 2. Call your LLM
response = await openai.chat.completions.create(messages=[...])

# 3. LEARN - Save turn + extract citations
await llm.learn(
    session_id="user_abc",
    query="How does the chunker work?",
    chunks=retrieved_chunks,
    response=response.content
)

# 4. FEEDBACK - When user clicks 👍/👎
await llm.feedback(chunk_ids=[123, 456], positive=True)

# 5. FORGET - Clear a session
await llm.forget(session_id="user_abc")
```

That's it! **4 methods** is all you need.

---

## What Happens Behind the Scenes

| You Call | System Does |
|----------|-------------|
| `prepare()` | Recalls history → Boosts chunks → Fits to token budget → Builds cache-optimal prompt |
| `learn()` | Saves turns → Extracts citations → Updates feedback graph → Triggers compression |
| `feedback()` | Updates Qdrant payloads → Enables Recommend API |
| `forget()` | Clears session → Optionally preserves compressed LTM |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    LatentMemoryManager                            │
│                                                                   │
│     prepare()       learn()       feedback()       forget()       │
│         │              │              │               │           │
│         └──────────────┼──────────────┼───────────────┘           │
│                        ▼                                          │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                   Internal (Hidden)                          │ │
│  │                                                              │ │
│  │  ┌─────────────────┐  ┌───────────────┐  ┌────────────────┐  │ │
│  │  │MemoryOrchestrator│  │ContextRotator │  │KVCacheManager │  │ │
│  │  │  3-tier memory  │  │ Token budget  │  │ Prompt build  │  │ │
│  │  └─────────────────┘  └───────────────┘  └────────────────┘  │ │
│  │                                                              │ │
│  │  ┌──────────────────────────────────────────────────────┐    │ │
│  │  │ FeedbackManager (SoftLoop + HardLoop)               │    │ │
│  │  └──────────────────────────────────────────────────────┘    │ │
│  └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## Memory Tiers

| Tier | Name | Storage | Retention | Transition |
|------|------|---------|-----------|------------|
| **0** | Working | In-memory | Current request | → Tier 1 after response |
| **1** | Episodic | Postgres | Last K turns (full text) | → Tier 2 when >20 turns |
| **2** | Semantic | Qdrant + Postgres | Compressed summaries | 30 days |

Transitions are **automatic** - zero configuration needed.

---

## Component Responsibilities

| Component | Does | Does NOT |
|-----------|------|----------|
| **MemoryOrchestrator** | What history to recall, compression, LTM | Token limits, prompt format |
| **ContextRotator** | Token budgeting, chunk eviction | History, prompt building |
| **KVCacheManager** | Prompt structure, stable ID ordering | Token limits, memory |
| **FeedbackManager** | Learning from citations/user feedback | Memory, prompts |

---

## Feedback System

Two-tier learning:

| Tier | Signal | Source | Confidence |
|------|--------|--------|------------|
| **Soft** | LLM Citations | Automatic | Lower |
| **Hard** | User 👍/👎 | Explicit | Higher |

Both update the retrieval system to improve future results.

---

## Configuration

Most users don't need to configure anything. For power users:

```python
from latent_memory import LatentConfig, LatentMemoryManager

config = LatentConfig(
    max_tokens=128000,       # Context window size
    reserve_for_output=4000, # Tokens reserved for generation
    history_k=10,            # Recent turns to include
    enable_feedback=True,    # Learn from citations
    enable_compression=True, # LLM summarization
    enable_ltm=True          # Cross-session memory
)

llm = LatentMemoryManager(
    system_prompt="...",
    pg_session=db,
    config=config
)
```

---

## Low-Level Access

For advanced use cases, import internal components directly:

```python
# Memory tiers
from latent_memory.memory import (
    MemoryOrchestrator, EpisodicMemory, SemanticMemory,
    Turn, Memory, MemoryConfig
)

# Token budgeting
from latent_memory import ContextRotator, TokenBudget

# Prompt building
from latent_memory import KVCacheManager

# Feedback
from latent_memory import FeedbackManager, SoftFeedbackLoop, HardFeedbackLoop
```

---

## Background Worker

For automatic compression and cleanup:

```bash
# Run continuously (every 60s)
uv run python -m cli.run_memory_worker

# Run once
uv run python -m cli.run_memory_worker --once

# Custom interval
uv run python -m cli.run_memory_worker --interval 300
```

---

## File Structure

```
latent_memory/
├── __init__.py              # Clean exports
├── manager.py               # LatentMemoryManager (4-method API)
│
├── memory/                  # 3-Tier Memory System
│   ├── orchestrator.py      # Brain - routes to tiers
│   ├── episodic.py          # Tier 1: Recent turns
│   ├── semantic.py          # Tier 2: Compressed LTM
│   ├── compressor.py        # LLM summarization
│   └── models.py            # Turn, Memory, Config
│
├── feedback/                # Learning System
│   ├── manager.py           # Unified facade
│   ├── soft_loop.py         # Citation extraction
│   └── hard_loop.py         # User feedback
│
├── kv_cache.py              # Prompt builder (cache-optimal)
└── context_rotator.py       # Token budget manager
```

---

## Related Modules

| Module | Purpose |
|--------|---------|
| `file_patcher/` | Code mutations with safety gates |
| `judgment/` | Validator, Critic, Oracle, Immune |
| `rag/` | Retrieval pipeline |

---

## Cache Contract

For maximum KV Cache hits, prompts follow this structure:

| Position | Content | Cache Status |
|----------|---------|--------------|
| 1 | System Prompt | ✅ Always cached |
| 2 | Context (sorted by ID) | ✅ Cached until edit |
| 3 | History | ✅ Cached while stable |
| 4 | Query + Metadata | ❌ Recomputed |

**Key**: Sort by stable ID (content hash), not token_start!



---


# From: judgment/README.md
# Judgment System 🔍

**"Senior Engineer in a Box"** - Automated safety gates for code modifications.

## Quick Start

```python
from judgment import create_judgment_manager

# Initialize once
judgment = create_judgment_manager(
    session_maker=db_session,
    project_root="f:/kb"
)

# Evaluate a patch
result = await judgment.evaluate_patch(
    file_path="src/main.py",
    old_content="def foo(): pass",
    new_content="def foo(): return True"
)

if result.approved:
    print("✅ Patch approved!")
    # Apply the patch...
else:
    print(f"❌ Rejected by: {result.rejected_by}")
    for error in result.errors:
        print(f"  - {error}")
```

---

## The 5 Gates

| Gate | Purpose | Speed | Default |
|------|---------|-------|---------|
| **Validator** | Syntax checking (tree-sitter) | Fast | ✅ On |
| **Linter** | Duplicate detection | Fast | ✅ On |
| **Critic** | Diff discipline | Fast | ❌ Off |
| **Oracle** | Impact analysis (blast radius) | Medium | ❌ Off |
| **Immune** | Test verification | Slow | ❌ Off |

Gates run **in parallel** (except Immune) for maximum speed.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     HIGH LEVEL - JudgmentManager                             │
│                                                                              │
│   evaluate_patch(file, old, new)                                            │
│       │                                                                      │
│       ├──▶ Parallel: Validator | Linter | Critic | Oracle                   │
│       │                                                                      │
│       └──▶ Sequential: Immune (if enabled)                                  │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                     MID LEVEL - Individual Gates                             │
│                                                                              │
│   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│   │  Validator  │ │   Linter    │ │   Critic    │ │   Oracle    │           │
│   │             │ │             │ │             │ │             │           │
│   │ tree-sitter │ │  semantic   │ │  diff rules │ │  ripgrep    │           │
│   │ AST parse   │ │  similarity │ │  violations │ │  callers    │           │
│   └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘           │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │                        Immune                                │           │
│   │   Run pytest → Parse results → Pass/Fail decision           │           │
│   └─────────────────────────────────────────────────────────────┘           │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                     LOW LEVEL - Core                                         │
│                                                                              │
│   GateType | Decision | RiskLevel | Severity                                │
│   JudgmentResult | JudgmentConfig                                           │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                     AUDIT - VPC (Patch Logger)                               │
│                                                                              │
│   PatchRecord | PatchDecision | RejectionGate                               │
│   Postgres persistence for complete audit trail                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Gate Details

### 1. Validator (Syntax)

Uses **tree-sitter** to parse code and detect syntax errors BEFORE writing to disk.

```python
from judgment import PatchValidator, create_validator

validator = create_validator(strict_mode=True)

# Validate code directly
result = validator.validate_syntax("def foo():", "python")
print(result.valid)  # False - missing body

# Validate patch preview
preview = validator.validate_patch_preview(
    file_path="src/main.py",
    chunk_metadata={"processed_char_start": 0, "processed_char_end": 50},
    new_content="def bar(): return True"
)
```

**Supported Languages**: Python, JavaScript, TypeScript, Go, Rust, Java, C/C++, Ruby, Bash

### 2. Linter (Duplicates)

Detects **semantic duplication** - code that's similar to existing chunks.

```python
from judgment import SemanticLinter, create_linter

linter = create_linter(qdrant_client=qdrant)

duplicates = await linter.analyze_text(
    text="def calculate_sum(a, b): return a + b",
    filename="utils.py",
    threshold=0.85
)

for dup in duplicates:
    print(f"Similar to: {dup['matches'][0]['source']}")
```

### 3. Critic (Diff Discipline)

Enforces "senior engineer" patch discipline:

| Rule | Description |
|------|-------------|
| **Size** | Changes proportional to intent |
| **Scope** | Don't touch unrelated code |
| **Whitespace** | No formatting drift |
| **Dependencies** | Flag new/removed imports |
| **Safety** | Flag removed error handling/logging |

```python
from judgment import DiffCritic, create_critic

critic = create_critic()

critique = critic.critique_patch(
    old_content="def foo(): pass",
    new_content="def foo(): return True"
)

print(f"Approved: {critique.approved}")
print(f"Score: {critique.score}")
for v in critique.violations:
    print(f"  [{v.severity.value}] {v.message}")
```

### 4. Oracle (Impact Analysis)

Answers: **"What will break if I change this?"**

```python
from judgment import ImpactOracle, create_oracle

oracle = create_oracle(project_root="f:/kb")

report = await oracle.analyze_impact_async(
    file_path="src/utils.py",
    old_content="def helper(): pass",
    new_content="def helper(): return None"
)

print(f"Risk: {report.risk_level.value}")
print(f"Callers: {report.caller_count}")
print(f"Test files: {report.tests.test_files}")
```

Uses **ripgrep** for fast codebase-wide search.

### 5. Immune (Test Verification)

The final gate: **"Do the tests pass?"**

```python
from judgment import ImmuneSystem, create_immune_system

immune = create_immune_system(
    project_root="f:/kb",
    timeout_seconds=60,
    pytest_cmd="uv run pytest"
)

verification = immune.verify_patch(
    file_path="src/utils.py",
    changed_symbols=["helper", "calculate"],
    test_files=["tests/test_utils.py"]
)

print(f"Should apply: {verification.should_apply}")
print(f"Reason: {verification.reason}")
```

---

## Configuration

```python
from judgment import JudgmentConfig, create_judgment_manager

config = JudgmentConfig(
    validate_syntax=True,    # Gate 1
    check_duplicates=True,   # Gate 1b
    run_critic=True,         # Gate 2
    run_impact=True,         # Gate 3
    run_tests=False,         # Gate 4 (expensive)
    strict_mode=True,        # Reject any syntax error
    project_root="f:/kb"
)

judgment = create_judgment_manager(
    session_maker=db,
    **config.__dict__
)
```

---

## VPC (Audit Trail)

Every patch evaluation is logged:

```python
from judgment import PatchLogger, create_patch_logger

logger = create_patch_logger(session_maker=db)

record = await logger.log_patch(
    file_path="src/main.py",
    chunk_metadata={...},
    old_content="...",
    new_content="...",
    receipt={...}
)

print(f"Patch ID: {record.id}")
print(f"Decision: {record.decision}")
```

---

## File Structure

```
judgment/
├── __init__.py        # Clean exports
├── core.py            # Data structures (GateType, Decision, etc.)
├── manager.py         # JudgmentManager (orchestration)
│
├── validator.py       # Gate 1: Syntax (tree-sitter)
├── linter.py          # Gate 1b: Duplicates (semantic)
├── critic.py          # Gate 2: Diff discipline
├── oracle.py          # Gate 3: Impact (ripgrep)
├── immune.py          # Gate 4: Tests (pytest)
│
├── vpc.py             # Audit logging
└── README.md          # This file
```

---

## Integration with File Patcher

The judgment system is automatically used by `file_patcher`:

```python
from file_patcher import create_patcher_manager

patcher = create_patcher_manager(
    qdrant_client=qdrant,
    session_maker=db,
    validate_syntax=True,  # Uses PatchValidator
    run_critic=True,       # Uses DiffCritic
    run_impact=True,       # Uses ImpactOracle
    run_tests=False        # Uses ImmuneSystem
)

# All patches go through judgment automatically
result = await patcher.patch(file, collection, chunk, new_content)
```

---

## Philosophy

> "The best bug is the one that never ships."

The judgment system acts as a **pre-commit hook on steroids**:
- Catches syntax errors before they hit disk
- Enforces code quality at the patch level
- Measures blast radius before changes are made
- Runs tests before committing

This makes LLM-driven code modifications **trustworthy**.



---


# From: file_patcher/README.md
# File Patcher Package 🔧

**Safe code mutations with judgment gates.**

## Quick Start

```python
from file_patcher import create_patcher_manager

# Initialize once
patcher = create_patcher_manager(
    qdrant_client=qdrant,
    session_maker=db_session
)

# 1. PATCH - Edit an existing chunk
result = await patcher.patch(
    file_path="src/main.py",
    collection="kb_chunks",
    chunk={"id": 123, "index": 5, "processed_char_start": 100, ...},
    new_content="def fixed_function():\n    return True"
)

# 2. CREATE - Assemble new file from existing chunks
result = await patcher.create(
    grafts=[
        {"source": "src/utils.py", "start": 0, "end": 500},
        {"source": "src/models.py", "start": 100, "end": 300}
    ],
    output_path="generated/hybrid.py"
)

# 3. WRITE - Direct guarded write
success, receipt = await patcher.write(
    file_path="output.py",
    content="print('hello')"
)
```

That's it! **3 methods** for all file mutations.

---

## What Happens Behind the Scenes

| You Call | System Does |
|----------|-------------|
| `patch()` | Acquires lock → Validates syntax → Applies patch → Updates embedding → Ripples offsets |
| `create()` | Loads sources → Assembles grafts → Validates → Writes with guards |
| `write()` | Runs judgment pipeline → Writes if approved |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     HIGH LEVEL - FilePatcherManager                          │
│                                                                              │
│   patch()              create()              write()                         │
│     │                    │                     │                             │
│     └────────────────────┼─────────────────────┘                             │
│                          ▼                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                     MID LEVEL - Operations                                   │
│                                                                              │
│   ┌──────────────────────┐          ┌──────────────────────┐                │
│   │   SurgicalPatcher    │          │ FrankensteinStitcher │                │
│   │                      │          │                      │                │
│   │ • Byte-precise edit  │          │ • Byte-copy grafts   │                │
│   │ • Distributed lock   │          │ • Glue code support  │                │
│   │ • Vector Ripple      │          │ • Comment headers    │                │
│   └──────────────────────┘          └──────────────────────┘                │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                     LOW LEVEL - Core Primitives                              │
│                                                                              │
│   apply_patch()    assemble()    ripple()    read_file()    write_file()    │
│   PatchDelta       PatchResult                                               │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                     GUARDS - Judgment Pipeline                               │
│                                                                              │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│   │  Validate  │  │  Critique  │  │   Impact   │  │   Tests    │            │
│   │  (syntax)  │  │   (diff)   │  │  (oracle)  │  │  (immune)  │            │
│   └────────────┘  └────────────┘  └────────────┘  └────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Concepts

### 1. Surgical Edit

Replace a chunk at exact byte offsets while keeping the rest of the file intact.

```python
# Chunk metadata from Qdrant
chunk = {
    "id": 123,
    "index": 5,
    "processed_char_start": 1000,
    "processed_char_end": 1500,
    "original_text": "def old_function():..."
}

result = await patcher.patch(
    file_path="src/main.py",
    collection="kb_chunks",
    chunk=chunk,
    new_content="def new_function():..."
)

print(f"Bytes changed: {result.delta['char']}")
print(f"Downstream updated: {result.downstream_updated}")
```

### 2. Vector Ripple

When you edit a chunk, all chunks AFTER it shift position. Vector Ripple updates their metadata without re-embedding:

```
Before: [Chunk 1][Chunk 2][Chunk 3][Chunk 4]
Edit:   [Chunk 1][LARGER Chunk 2][Chunk 3][Chunk 4]
                            +100 bytes  +100 bytes

Ripple updates Chunk 3 and 4's offsets by +100 bytes
```

### 3. Frankenstein Stitching

Create new files by grafting verified chunks from existing files:

```python
result = await patcher.create(
    grafts=[
        {"source": "src/auth.py", "start": 0, "end": 200},
        {"source": "src/utils.py", "start": 500, "end": 800, "glue": "\n# Adapter\n"},
        {"source": "src/models.py", "start": 100, "end": 400}
    ],
    output_path="generated/combined.py"
)

print(f"Grafts: {result.grafts_count}")
print(f"Bytes: {result.bytes_assembled}")
```

**Philosophy**: "The best code is code that already works."

### 4. Distributed Locking

Prevents concurrent edits to the same file using Postgres CAS locks:

```
Agent A: Acquires lock on src/main.py ✓
Agent B: Tries to lock src/main.py → BLOCKED
Agent A: Finishes edit, releases lock
Agent B: Now can acquire lock ✓
```

---

## Judgment Gates

All writes pass through the judgment pipeline:

| Gate | Purpose | Default |
|------|---------|---------|
| **Validate** | Tree-sitter syntax check | ✅ Enabled |
| **Critique** | Diff discipline (scope, comments) | ❌ Disabled |
| **Impact** | Blast radius analysis | ❌ Disabled |
| **Tests** | Run related tests | ❌ Disabled |

Configure globally:

```python
from file_patcher import PatcherConfig, create_patcher_manager

config = PatcherConfig(
    validate_syntax=True,
    run_critic=True,
    run_impact=False,
    run_tests=False
)

patcher = create_patcher_manager(
    qdrant_client=qdrant,
    session_maker=db,
    **config.__dict__
)
```

---

## Low-Level Access

For fine-grained control:

```python
from file_patcher import SurgicalPatcher, FrankensteinStitcher
from file_patcher.core import apply_patch, assemble, ripple, PatchDelta

# Use core primitives directly
result = apply_patch(
    original="def foo(): pass",
    start=0,
    end=15,
    new_content="def bar(): return True"
)

print(result.patched_content)
print(result.delta.char_delta)
```

---

## File Structure

```
file_patcher/
├── __init__.py        # Clean exports
├── manager.py         # FilePatcherManager (3-method API)
├── surgical.py        # SurgicalPatcher + PatchReceipt
├── stitcher.py        # FrankensteinStitcher + StitchResult
├── core.py            # Low-level primitives
├── guards.py          # Judgment pipeline wrapper
└── README.md          # This file
```

---

## Related Modules

| Module | Purpose |
|--------|---------|
| `judgment/` | Validator, Critic, Oracle, Immune System |
| `latent_memory/` | Memory + Feedback + Prompt Building |
| `rag/` | Retrieval pipeline |



---


# From: agent/README.md
# agent/README.md
# 🧠 Agent Module

**Goal-Driven Autonomous Developer - The "Holy Grail" of AI Engineering**

You define WHAT. The system builds HOW.

## Quick Start

```python
from agent import create_agent_manager

agent = create_agent_manager()

# Execute a goal
result = await agent.execute("Add VIP discount feature for premium users")

if result.success:
    print(f"Created {len(result.files_created)} files!")
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  AgentManager                (High Level - execute())           │
├─────────────────────────────────────────────────────────────────┤
│  PERSONAS                    (Mid Level - The Trinity)          │
│  Architect | QAEngineer | Developer                             │
├─────────────────────────────────────────────────────────────────┤
│  core.py                     (Low Level - Data Structures)      │
│  GoalSpec | Plan | TestContract | AgentResult                   │
├─────────────────────────────────────────────────────────────────┤
│  REUSED MODULES              (External Dependencies)            │
│  RAGManager | JudgmentManager | FeatureFactory | FilePatcher    │
└─────────────────────────────────────────────────────────────────┘
```

## The Trinity

### 1. Architect (The Brain)
- Analyzes goals via RAG context retrieval
- Finds matching Golden Patterns
- Creates implementation plans

### 2. QA Engineer (The Conscience)  
- Generates test contracts (RED)
- Defines success criteria
- Creates verification assertions

### 3. Developer (The Hands)
- Scaffolds code using FeatureFactory
- Runs red-green loop
- Iterates until tests pass (GREEN)

## Module Structure

```
agent/
├── __init__.py     # Package exports
├── core.py         # Data structures (GoalSpec, Plan, Result)
├── architect.py    # The Brain - context + planning
├── qa.py           # The Conscience - test generation
├── developer.py    # The Hands - implementation
├── manager.py      # Orchestrator - coordinates Trinity
└── README.md       # This file
```

## CLI Usage

```bash
# Execute a goal
python -m cli.run_agent --goal "Add referral system"

# Dry run (preview)
python -m cli.run_agent --goal "Payment retry logic" --dry-run

# Target specific location
python -m cli.run_agent --goal "Add caching" --target src/cache.py
```

## Flow

```
Goal → Architect → Plan → QA → Test Contract → Developer → Code
         │                        │                  │
     RAG Context              Assertions        Scaffold
     Patterns                   (RED)              │
                                                   ▼
                                            Run Tests
                                                   │
                                          ┌────────┴────────┐
                                          │                 │
                                        FAIL              PASS
                                          │                 │
                                       Iterate           ✅ Done
```

## Configuration

```python
from agent import AgentConfig, create_agent_manager

config = AgentConfig(
    max_iterations=5,      # Max red-green iterations
    run_tests=True,        # Run pytest
    generate_tests=True,   # Generate test files
    dry_run=False,         # Preview only
)

agent = create_agent_manager()
result = await agent.execute("Add feature", config=config)
```

## Reused Modules

The Agent doesn't reinvent the wheel - it orchestrates:

| Module | Usage |
|--------|-------|
| `rag/` | Context retrieval for Architect |
| `cli/scaffold_feature.py` | Code scaffolding for Developer |
| `judgment/` | Validation gates |
| `file_patcher/` | Safe code mutations |



---


# From: services/README.md
# 🔧 Services Layer

Business logic façade that wraps core Managers with consistent formatting and error handling.

## Philosophy

**"Orchestrate and Format"** - Services should:
- ✅ Wrap underlying managers
- ✅ Format responses consistently
- ✅ Handle errors gracefully
- ✅ Log operations
- ❌ NOT contain core algorithms
- ❌ NOT duplicate manager logic
- ❌ NOT be tightly coupled to HTTP

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            Services Layer                                 │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │  Services (This Layer)                                               │ │
│  │                                                                      │ │
│  │  ChatService          - Chat orchestration, OpenAI-compatible output │ │
│  │  IngestionService     - File/directory ingestion control             │ │
│  │  PatchService         - Surgical patcher operations                  │ │
│  │  GraphService         - Knowledge graph queries                      │ │
│  │  WatcherService       - File watcher lifecycle                       │ │
│  │  PRService            - GitHub/GitLab PR review automation           │ │
│  │                                                                      │ │
│  │  chat/                                                               │ │
│  │  ├── service.py       - ChatService implementation                  │ │
│  │  ├── models.py        - Shared models (Persona, Session, Config)    │ │
│  │  ├── persona_service.py - Persona CRUD                              │ │
│  │  ├── session_service.py - Session management                        │ │
│  │  └── response_formatter.py - OpenAI-compatible formatter            │ │
│  │                                                                      │ │
│  │  pr_scanner/                                                         │ │
│  │  ├── scanner.py       - PRScanner (core logic)                      │ │
│  │  ├── service.py       - PRService (GitHub integration)              │ │
│  │  ├── formatter.py     - PR comment formatter                        │ │
│  │  └── providers/       - GitHub, GitLab API integrations             │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                    │                                      │
│                                    ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                          Managers Layer                              │ │
│  │                                                                      │ │
│  │  llm/LLMManager       - 4-step orchestration (Retrieve→Prepare→     │ │
│  │                         Generate→Learn)                              │ │
│  │  rag/RAGManager       - Retrieval + reranking + compression         │ │
│  │  latent_memory/       - 3-tier memory (Working→Episodic→Semantic)   │ │
│  │    LatentMemoryManager                                               │ │
│  │  ingestion/           - Scanner + Worker (queue-based)              │ │
│  │    IngestionManager                                                  │ │
│  │  file_patcher/        - VFS staging + surgical edits                │ │
│  │    FilePatcherManager                                                │ │
│  │  judgment/            - Safety gates (Validator, Oracle, Immune)    │ │
│  │    JudgmentManager                                                   │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
services/
├── __init__.py              # Exports
├── README.md                # This file
│
├── chat/                    # Chat domain (complex, multi-file)
│   ├── __init__.py          # Exports ChatService, models
│   ├── service.py           # ChatService - main orchestration
│   ├── models.py            # Persona, Session, Config models
│   ├── persona_service.py   # Persona CRUD
│   ├── session_service.py   # Session management
│   └── response_formatter.py # OpenAI-compatible formatting
│
├── pr_scanner/              # PR review automation (multi-file)
│   ├── __init__.py          # Exports PRService, PRScanner, etc.
│   ├── core.py              # Data structures (PRVerdict, FileChange)
│   ├── diff_parser.py       # Git diff parsing
│   ├── scanner.py           # PRScanner - core logic
│   ├── service.py           # PRService - GitHub/GitLab integration
│   ├── formatter.py         # PR comment Markdown formatting
│   └── providers/           # Git hosting integrations
│       ├── base.py          # Abstract GitProvider
│       └── github.py        # GitHub API implementation
│
├── ingestion_service.py     # IngestionService
├── graph_service.py         # GraphService  
├── patch_service.py         # PatchService
└── watcher_service.py       # WatcherService
```

## Manager vs Service: What's the Difference?

| Aspect | Manager | Service |
|--------|---------|---------|
| **Location** | Module folder (`llm/`, `rag/`) | `services/` folder |
| **Purpose** | Core business logic | Orchestration + formatting |
| **Users** | Services, CLI, tests | API layer, CLI |
| **Response Format** | Raw data, objects | Standardized dicts, OpenAI format |
| **Error Handling** | Raises exceptions | Returns error responses |
| **Reusability** | Maximum | HTTP-focused |

### Example Flow

```
API Request
    │
    ▼
ChatService.chat()          ← Service: orchestrates
    │
    ├─► PersonaService      ← Service: resolves config
    │
    └─► LLMManager.chat()   ← Manager: core logic
            │
            ├─► RAGManager.retrieve()   ← Manager: retrieval
            ├─► LatentMemoryManager.prepare()  ← Manager: memory
            ├─► LLMClient.generate()    ← Core: LLM call
            └─► LatentMemoryManager.learn()    ← Manager: learning
```

## Services Overview

### ChatService
```python
from services import ChatService

service = ChatService(pg_session=session)
response = await service.chat(
    session_id="user_123",
    query="Explain chunking",
    persona="code_assistant"
)
# Returns OpenAI-compatible response
```

### IngestionService
```python
from services import IngestionService

service = IngestionService()
result = await service.ingest_directory(Path("doc/"))
# Returns IngestionResponse with stats
```

### PatchService
```python
from services import PatchService

service = PatchService()
result = await service.apply_patch(file_path, changes)
# Returns patch result with rollback info
```

### GraphService
```python
from services import GraphService

service = GraphService(qdrant_client=qdrant)
summary = await service.get_summary()
# Returns graph statistics
```

### WatcherService
```python
from services import WatcherService

service = WatcherService()
await service.start_watching([Path("doc/")])
# Starts background file watcher
```

### PRService (PR Review Automation)
```python
from services import PRService, create_pr_service

# Quick setup with GitHub token
service = create_pr_service(github_token="ghp_...")

# Scan and post comment to GitHub PR
report = await service.scan_and_comment("owner/repo", pr_number=42)

# Just scan without posting
report = await service.scan_pr("owner/repo", 42)
print(report.summary)  # ✅ APPROVE: 5/5 files passed (low risk)
```

### PRScanner (Local Diff Scanning)
```python
from services import PRScanner, create_pr_scanner

scanner = create_pr_scanner(project_root="f:/kb")

# Scan a local diff
report = await scanner.scan_diff(
    diff_text=git_diff_output,
    pr_number=123,
    repo="myorg/myrepo"
)

# Access results
for file_result in report.file_results:
    print(f"{file_result.file_path}: {file_result.approved}")
```

## Writing a New Service

```python
# services/example_service.py
from typing import Dict, Any, Optional
from config import get_logger

logger = get_logger("ExampleService")

class ExampleService:
    """
    Service description.
    
    Wraps ExampleManager and provides:
    - Consistent response formatting
    - Error handling
    - Logging
    """
    
    def __init__(self, pg_session=None, **kwargs):
        self._pg_session = pg_session
        self._manager = None  # Lazy-loaded
        
    def _get_manager(self):
        """Lazy-load the underlying manager."""
        if self._manager is None:
            from example_module import ExampleManager
            self._manager = ExampleManager(pg_session=self._pg_session)
        return self._manager
    
    async def do_something(self, param: str) -> Dict[str, Any]:
        """
        Do something.
        
        Args:
            param: Description
            
        Returns:
            Standardized response dict
        """
        logger.info(f"📦 Processing: {param}")
        
        try:
            manager = self._get_manager()
            result = await manager.process(param)
            
            return {
                "success": True,
                "data": result,
                "error": None
            }
        except Exception as e:
            logger.error(f"❌ Failed: {e}")
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }
```

## Rules

1. **Wrap, don't duplicate** - Services call managers; they don't reimplement logic
2. **Standardize responses** - Consistent dict structure or Pydantic models
3. **Lazy-load managers** - Only initialize when first used
4. **Log with emojis** - Makes logs scannable (📦 start, ✅ success, ❌ error)
5. **Handle all exceptions** - Services should never raise to API layer
6. **Be stateless when possible** - Easier to test and scale



---


# From: api/README.md
# 📡 API Layer

Ultra-thin HTTP layer providing REST endpoints for all MyKBOS capabilities.

## Philosophy

**"Route, Don't Think"** - The API layer should:
- ✅ Validate requests (Pydantic)
- ✅ Route to services
- ✅ Return HTTP responses
- ❌ NOT contain business logic
- ❌ NOT access databases directly
- ❌ NOT have complex conditionals

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              API Layer                                    │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │  routes/                    models/                     deps.py      │ │
│  │  ├── health.py              ├── chat.py                (DI funcs)   │ │
│  │  ├── chat.py                ├── persona.py                          │ │
│  │  ├── persona.py             ├── session.py                          │ │
│  │  ├── sessions.py            ├── memory.py                           │ │
│  │  ├── memory.py              └── pr_scanner.py                       │ │
│  │  ├── ingest.py              ┌──────────────────────────┐            │ │
│  │  ├── watcher.py             │  No business logic here! │            │ │
│  │  ├── pr_scanner.py          └──────────────────────────┘            │ │
│  │  ├── graph.py                                                        │ │
│  │  └── patches.py                                                      │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                    │                                      │
│                                    ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                         Services Layer                               │ │
│  │  ChatService  │  IngestionService  │  PRService  │  etc.              │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
api/
├── __init__.py       # Router registration, exports
├── deps.py           # Dependency injection (get_session, get_chat_service)
│
├── routes/           # Endpoint handlers (thin)
│   ├── health.py     # /health, /health/live, /health/ready
│   ├── chat.py       # /v1/chat/completions (OpenAI compatible)
│   ├── persona.py    # /v1/personas/* (CRUD)
│   ├── sessions.py   # /v1/sessions/* (history, export, delete)
│   ├── memory.py     # /v1/memories/* (LTM management)
│   ├── ingest.py     # /v1/ingest/* (file/directory ingestion)
│   ├── watcher.py    # /v1/watcher/* (file watcher control)
│   ├── pr_scanner.py # /v1/pr/* (PR review automation)
│   ├── graph.py      # /api/graph/* (knowledge graph)
│   └── patches.py    # /api/patches/* (VPC audit)
│
└── models/           # Pydantic request/response models
    ├── chat.py       # ChatCompletionRequest, ChatMessage
    ├── persona.py    # PersonaListResponse, CreatePersonaRequest
    ├── session.py    # SessionListResponse, HistoryResponse
    ├── memory.py     # MemoryItem, MemorySearchRequest
    └── pr_scanner.py # ScanDiffRequest, PRVerdictResponse
```

## Endpoint Summary

### Chat (OpenAI-Compatible)
```
POST /v1/chat/completions    # Main chat endpoint
POST /v1/feedback            # User feedback (👍/👎)
```

### Personas
```
GET    /v1/personas          # List all personas
GET    /v1/personas/{id}     # Get persona details
POST   /v1/personas          # Create custom persona
DELETE /v1/personas/{id}     # Delete custom persona
```

### Sessions
```
GET    /v1/sessions              # List sessions (paginated)
GET    /v1/sessions/{id}         # Session stats
GET    /v1/sessions/{id}/history # Conversation history
POST   /v1/sessions/{id}/export  # Export for GDPR
DELETE /v1/sessions/{id}         # Delete (GDPR)
POST   /v1/sessions/{id}/branch  # Fork conversation
POST   /v1/sessions/{id}/compress # Trigger compression
```

### Memory (LTM)
```
GET    /v1/memories              # List memories
GET    /v1/memories/stats        # Statistics
GET    /v1/memories/{id}         # Memory details
DELETE /v1/memories/{id}         # Delete memory
DELETE /v1/memories/user/{id}    # Delete all user memories
POST   /v1/memories/search       # Semantic search
```

### Ingestion
```
GET  /v1/ingest/status           # Pipeline status
POST /v1/ingest/file             # Ingest file
POST /v1/ingest/directory        # Batch ingest
POST /v1/ingest/retry            # Retry failed
POST /v1/ingest/maintenance      # Graph gardener
```

### Watcher
```
GET  /v1/watcher/status          # Status
POST /v1/watcher/start           # Start watching
POST /v1/watcher/stop            # Stop watching
POST /v1/watcher/paths/add       # Add watch path
```

### Graph
```
GET /api/graph/summary           # Knowledge graph overview
GET /api/graph/neighbors/{id}    # Node neighbors
GET /api/graph/document          # Document reconstruction
GET /api/graph/files             # List indexed files
```

### Patches
```
GET  /api/patches                # List staged patches
GET  /api/patches/{id}           # Patch details
POST /api/patches/{id}/commit    # Mark as committed
```

### PR Scanner (NEW)
```
GET  /v1/pr/status               # Scanner status & config
POST /v1/pr/scan/diff            # Scan a diff directly
POST /v1/pr/scan/github          # Scan GitHub PR (with comment/labels)
GET  /v1/pr/scan/github/{o}/{r}/{n} # Quick scan GitHub PR
POST /v1/pr/webhook/github       # GitHub webhook for CI/CD
POST /v1/pr/format               # Preview comment format
```

## Writing a New Route

```python
# api/routes/example.py
from fastapi import APIRouter, HTTPException, Depends
from api.deps import get_example_service

router = APIRouter(prefix="/v1/example", tags=["Example"])

@router.get("/{id}")
async def get_example(id: str):
    """Get example by ID."""
    service = get_example_service()
    result = await service.get(id)
    
    if not result:
        raise HTTPException(404, f"Not found: {id}")
    
    return result  # Pydantic serializes automatically
```

## Rules

1. **No direct DB access** - Use services
2. **No business logic** - Keep routes under 20 lines
3. **Use Pydantic** - All requests/responses should be typed
4. **Document with docstrings** - They become OpenAPI docs
5. **Semantic HTTP codes** - 200, 201, 400, 404, 500



---


# From: ingestion/README.md
# Ingestion Pipeline v4.0

**Modular, Observable, Fully Idempotent Ingestion Architecture**

## Architecture

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                              IngestionManager                                      │
│                           (Unified Facade API)                                     │
│                                                                                    │
│                        manager.ingest(target)                                      │
│                                 │                                                  │
│                                 ▼                                                  │
│                       ┌───────────────────┐                                        │
│                       │ IngestionPipeline │                                        │
│                       │  (Orchestrator)   │                                        │
│                       └─────────┬─────────┘                                        │
│                                 │                                                  │
│    ┌────────────────────────────┼────────────────────────────────┐                │
│    ▼                            ▼                                ▼                │
│ ┌──────────────┐        ┌──────────────┐     ┌───────────────────────────┐        │
│ │ FileScanStage│        │ChunkingStage │     │     ConceptStage          │        │
│ │  (discover)  │───────▶│(parallel CPU)│────▶│ (GLiNER concept harvest)  │        │
│ └──────────────┘        └──────────────┘     └───────────┬───────────────┘        │
│                                                          │                         │
│                                                          ▼                         │
│                                              ┌───────────────────────┐             │
│                                              │    IndexingStage      │             │
│                                              │ (Embed + Qdrant sync) │             │
│                                              └───────────────────────┘             │
│                                                                                    │
│                          IngestionAnalytics                                        │
│                    (Real-time progress & reflection)                               │
│                                                                                    │
├────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                    │
│                         POSTGRES (Source of Truth)                                 │
│   ┌────────────┬────────────────────┬─────────────┬───────────────┐               │
│   │ documents  │  processing_queue  │   chunks    │    nodes      │               │
│   │ (registry) │  (job queue)       │  (parsed)   │   (graph)     │               │
│   └────────────┴────────────────────┴─────────────┴───────────────┘               │
│                                     │                                              │
│                                     ▼                                              │
│                         QDRANT (Derived Vectors)                                   │
│              Dense + Sparse BM25 + Concept tags + Metadata                         │
│                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────┘
```

## Key Principles

| Principle | Implementation |
|-----------|----------------|
| **Modular Stages** | Each pipeline step is a self-contained, testable stage |
| **Observable Pipeline** | `IngestionAnalytics` provides real-time reflection of progress |
| **Single Entry Point** | `manager.ingest()` handles files, lists, or directories |
| **Postgres is Source of Truth** | All chunks stored in Postgres before Qdrant |
| **Parallel Processing** | ProcessPoolExecutor for CPU, batching for GPU |
| **Full Idempotency** | Stable IDs, ON CONFLICT DO UPDATE, status tracking |
| **Crash Recovery** | Restart picks up exactly where it left off |

## Pipeline Stages

The ingestion pipeline is composed of modular, independent stages:

| Stage | Module | Description |
|-------|--------|-------------|
| **Scan** | `stages/scan.py` | Discovers files, computes checksums, creates/updates jobs |
| **Chunking** | `stages/chunking.py` | Parallel document parsing using `ProcessPoolExecutor` |
| **Concepts** | `stages/concepts.py` | GLiNER-based semantic concept extraction |
| **Indexing** | `stages/indexing.py` | Dense/sparse embedding + Qdrant upsert |

Each stage:
- Returns a `StageResult` with `success`, `processed_count`, `error_count`, `duration_ms`
- Updates its progress atomically in Postgres
- Is fully idempotent (safe to re-run)

## Usage

### Python API

```python
from ingestion import create_ingestion_manager
from pathlib import Path

manager = create_ingestion_manager()

# Single file
result = await manager.ingest(Path("doc/readme.md"))

# Multiple files
result = await manager.ingest([
    Path("doc/guide.md"),
    Path("src/main.py"),
    Path("tests/test_api.py")
])

# Directory
result = await manager.ingest(Path("doc/"), recursive=True)

# String paths work too
result = await manager.ingest("doc/readme.md")
result = await manager.ingest(["a.md", "b.py", "folder/"])

# Check results (returns IngestionAnalytics)
summary = result.get_summary()
print(f"Chunks: {summary['overall']['total_chunks']}")
print(f"Concepts: {summary['overall']['total_concepts']}")
print(f"Duration: {summary['overall']['duration_ms']}ms")

# Stage-by-stage breakdown
for stage, stats in summary['stages'].items():
    print(f"  {stage}: {stats['processed']} items in {stats['duration_ms']}ms")

# Pipeline status
status = await manager.get_status()
print(f"Pending: {status.pending_chunk_jobs} chunk, {status.pending_graph_jobs} embed")

# Process any pending work
analytics = await manager.process_pending()
analytics.print_reflection()
```

### REST API

```bash
# Ingest files or directories
POST /v1/ingest
{
  "paths": ["doc/readme.md"],
  "recursive": true,
  "wait": true
}

# Response includes full analytics
{
  "success": true,
  "operation": "ingest",
  "data": {
    "overall": {
      "duration_ms": 1234,
      "total_chunks": 150,
      "total_concepts": 45,
      "processed_files": ["doc/readme.md", "doc/guide.md"]
    },
    "stages": {
      "scan": {"processed": 2, "duration_ms": 50, "errors": 0},
      "chunking": {"processed": 2, "duration_ms": 800, "errors": 0},
      "concepts": {"processed": 150, "duration_ms": 200, "errors": 0},
      "indexing": {"processed": 150, "duration_ms": 180, "errors": 0}
    }
  }
}

# Get status
GET /v1/ingest/status

# Process pending jobs
POST /v1/ingest/process

# Retry failed jobs
POST /v1/ingest/retry

# Run maintenance (graph gardening)
POST /v1/ingest/maintenance
{"synonym_threshold": 0.92}

# List documents
GET /v1/ingest/documents
```

### CLI

```bash
# Ingest via manager
uv run python -m ingestion.manager ingest doc/
uv run python -m ingestion.manager ingest file1.md file2.py folder/
uv run python -m ingestion.manager status
uv run python -m ingestion.manager retry
uv run python -m ingestion.manager garden --threshold 0.92

# Direct pipeline run
uv run python -m ingestion.pipeline
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://...` | Postgres connection |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant server |
| `QDRANT_COLLECTION` | `kb_chunks` | Collection name |
| `DOC_DIR` | `doc` | Default scan directory |
| `INGEST_EXTENSIONS` | `.md,.py,.ts,.tsx,.html,.yaml,.yml` | File extensions |
| `INGEST_BATCH_SIZE` | `32` | Embedding batch size |
| `ENABLE_CONCEPTS` | `true` | GLiNER concept extraction |
| `ENABLE_SPARSE` | `true` | BM25 sparse vectors |
| `INGEST_MAX_CONCURRENT` | `4` | Max parallel chunking workers |

## Database Schema

```sql
-- Document registry
documents (id, file_path, checksum, sync_status, total_chunks, ...)

-- Job queue with status tracking
processing_queue (id, document_id, chunking_status, graph_status, ...)
-- Status: pending → processing → completed/failed

-- Parsed chunks (SOURCE OF TRUTH)
chunks (id, doc_id, content, embedding_status, concepts, meta, ...)
-- embedding_status: pending → done
```

## Analytics & Observability

The `IngestionAnalytics` class provides real-time insight into pipeline execution:

```python
analytics = IngestionAnalytics()

# Record stage results
analytics.record_step("chunking", result)

# Get comprehensive summary
summary = analytics.get_summary()
# {
#   "overall": {"duration_ms": ..., "total_chunks": ..., "processed_files": [...]},
#   "stages": {"scan": {...}, "chunking": {...}, ...}
# }

# Human-readable console output
analytics.print_reflection()
# ══════════════════════════════════════════════════
# 🚀 INGESTION REFLECTION
# ══════════════════════════════════════════════════
# Total Duration: 1234ms
# Total Chunks:   150
# Total Concepts: 45
# --------------------------------------------------
# [SCAN      ] Processed: 2     Errors: 0   Time: 50ms
# [CHUNKING  ] Processed: 2     Errors: 0   Time: 800ms
# [CONCEPTS  ] Processed: 150   Errors: 0   Time: 200ms
# [INDEXING  ] Processed: 150   Errors: 0   Time: 180ms
# ══════════════════════════════════════════════════
```

## Idempotency

Every operation is safe to re-run:

1. **Stable Chunk IDs**: `config.generate_stable_id(source, section, index)`
2. **UPSERT Semantics**: `ON CONFLICT (id) DO UPDATE SET ...`
3. **Checksum Detection**: Files only re-processed if content changed
4. **Status Tracking**: Each stage updates status atomically
5. **Crash Recovery**: Restart picks up pending items

## File Structure

```
ingestion/
├── __init__.py          # Exports + architecture docs
├── config.py            # IngestionConfig (env-based)
├── db_helpers.py        # SQL queries (repository pattern)
├── scanner.py           # DocumentScanner (queue producer)
├── pipeline.py          # IngestionPipeline (stage orchestrator)
├── manager.py           # IngestionManager (unified facade)
├── analytics.py         # IngestionAnalytics (observability)
├── stages/              # Modular pipeline stages
│   ├── __init__.py      # Base IngestionStage class + StageResult
│   ├── scan.py          # FileScanStage
│   ├── chunking.py      # ChunkingStage (parallel CPU)
│   ├── concepts.py      # ConceptStage (GLiNER)
│   └── indexing.py      # IndexingStage (Embed + Qdrant)
└── README.md            # This file
```

## Performance

| Files | Time | Notes |
|-------|------|-------|
| 100 docs | ~1-2 min | Parallel chunking + batched embedding |
| 1000 chunks | ~30s indexing | GPU-accelerated embedding |

3-5x faster than sequential due to:
- `ProcessPoolExecutor` for CPU-bound chunking
- Cross-document batching for GPU-bound embedding
- Bulk upserts to Qdrant
- Modular stage separation reduces overhead

## Error Handling

- Failed jobs are marked with `chunking_status = 'failed'` or `graph_status = 'failed'`
- Error messages stored in `chunking_error` / `graph_error` columns
- Use `POST /v1/ingest/retry` or `manager.retry_failed()` to reset and reprocess
- Each stage handles errors independently without blocking subsequent stages



---

