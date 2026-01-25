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
