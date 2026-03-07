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
