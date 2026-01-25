# Chunker Output Format Documentation

This document describes the structured JSON output format from the chunker, including all chunk types and their fields.

## Output Structure

The chunker produces a JSON file with the following top-level structure:

```json
{
  "metadata": {
    "source": "document.md",
    "total_chunks": 60
  },
  "text": [...],      // Text/prose chunks
  "code": [...],      // Code block chunks
  "table": [...],     // Table chunks
  "hierarchy": [...]  // Heading chunks (document structure)
}
```

---

## The "Trinity" Coordinate System 📐

Every chunk tracks three dimensions of location to enable **Surgical Patching**:

1.  **Bytes (The Disk)**: `processed_char_start` / `processed_char_end`
    *   **Definition**: Absolute byte offsets in the source file.
    *   **Purpose**: Used by the OS for atomic file I/O and patching.
    *   **Drift Protection**: These must match the `original_text` exactly.
2.  **Lines (The Human)**: `source_line_start` / `source_line_end`
    *   **Definition**: 0-indexed line numbers in the source file.
    *   **Purpose**: UI highlighting, IDE navigation, and human readability.
3.  **Tokens (The AI)**: `token_start` / `token_count`
    *   **Definition**: Exact token count using `tiktoken` (cl100k_base).
    *   **Purpose**: LLM context window budgeting and precise retrieval.

---

## Common Fields (All Chunk Types)

Every chunk, regardless of type, contains these fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | Unique stable ID (64-bit hash based on content + position) |
| `index` | `int` | Sequential order in the document |
| `text` | `string` | The chunk content (may include injected heading for context) |
| `type` | `string` | Chunk type: `"text"`, `"code"`, `"table"`, or `"heading"` |
| `source` | `string` | Source filename |
| `original_text` | `string` | **CAS Lock**: Raw content without header injection. Used for verification. |
| `heading` | `string` | The parent heading (e.g., `"## Section Title"`) |
| `h_level` | `int` | Heading level (1-6) |
| `section_path` | `string` | Full breadcrumb path (e.g., `"Parent > Child > Section"`) |
| `parent_chunk_id` | `int\|null` | ID of the parent heading chunk (for hierarchy) |
| `section_anchor` | `string` | Unique anchor for linking |
| `summary` | `string\|null` | Optional AI-generated summary |
| `child_chunk_ids` | `int[]` | IDs of child chunks |
| `processed_char_start` | `int` | **Absolute Byte Offset** (Start) in source file |
| `processed_char_end` | `int` | **Absolute Byte Offset** (End) in source file |
| `token_start` | `int` | Cumulative token offset in section context |
| `token_count` | `int` | Precise token count of `text` field |
| `source_line_start` | `int` | First line in source file (0-indexed) |
| `source_line_end` | `int` | Last line in source file (0-indexed) |
| `metadata` | `object` | Additional metadata (see below) |

---

## Chunk Type 1: `text`

Prose content from documentation, articles, and explanatory text.

### Example

```json
{
  "id": 4359110580737769530,
  "index": 1,
  "text": "**Markdown Generation Basics**\n\nOne of Crawl4AI's core features is generating **clean, structured markdown** from web pages...",
  "type": "text",
  "source": "markdown.md",
  "original_text": "One of Crawl4AI's core features is generating **clean, structured markdown** from web pages...",
  "heading": "# Markdown Generation Basics",
  "h_level": 1,
  "section_path": "Markdown Generation Basics",
  "parent_chunk_id": 4854879828526537493,
  "section_anchor": "67a46ab65185a401a756353de0c44df7",
  "summary": null,
  "child_chunk_ids": [],
  "processed_char_start": 450,
  "processed_char_end": 800,
  "token_start": 0,
  "token_count": 85,
  "source_line_start": 2,
  "source_line_end": 13,
  "metadata": {
    "pages": null,
    "breadcrumbs": ["Markdown Generation Basics"],
    "root_topic": "Markdown Generation Basics"
  }
}
```

### Key Characteristics
- Header is injected into `text` for better retrieval context
- `original_text` contains the raw content without headers
- Used for **GLiNER concept extraction** in the harvester

---

## Chunk Type 2: `code`

Code blocks from markdown fences or raw source files.

### Example

```json
{
  "id": 2565558934349993176,
  "index": 0,
  "text": "# kb/chunking/chunker.py\nfrom __future__ import annotations\n\nimport re\nimport logging\nfrom typing import List, Dict, Any, Optional, Tuple\nfrom dataclasses import dataclass, field...",
  "type": "code",
  "source": "chunkerv1.py",
  "original_text": "# kb/chunking/chunker.py\nfrom __future__ import annotations...",
  "heading": "# Imports",
  "h_level": 1,
  "section_path": "Imports",
  "parent_chunk_id": null,
  "section_anchor": "295077b56fbf4ff40e313505566759bd",
  "summary": null,
  "child_chunk_ids": [],
  "processed_char_start": 0,
  "processed_char_end": 1294,
  "token_start": 0,
  "token_count": 215,
  "source_line_start": 0,
  "source_line_end": 43,
  "metadata": {
    "pages": null,
    "breadcrumbs": ["Imports"],
    "root_topic": "Imports",
    "language": "python",
    "lines": [0, 42]
  }
}
```

### Code-Specific Metadata
| Field | Type | Description |
|-------|------|-------------|
| `metadata.language` | `string` | Programming language (e.g., `"python"`, `"javascript"`) |
| `metadata.lines` | `[int, int]` | Line range in source file `[start, end]` |
| `metadata.symbols_defined` | `array` | AST-extracted symbols: `[{name, kind, start_line, end_line, parent?, scope}]` |
| `metadata.symbols_referenced` | `array` | Referenced symbols: `[{name, line}]` |
| `metadata.comments_text` | `string` | Extracted comments/docstrings for semantic analysis |
| `metadata.is_split_part` | `boolean` | True if this chunk is part of a split function/class |

### Key Characteristics
- Language is inferred from file extension or markdown fence
- **NEW (v2.0):** Symbols are extracted during AST traversal by tree-sitter
- **NEW (v2.0):** Comments/docstrings are extracted for GLiNER semantic analysis
- Harvester **trusts** metadata instead of re-parsing with regex

---

## Chunk Type 3: `table`

Markdown tables parsed into structured format.

### Example

```json
{
  "id": 7343108555276731576,
  "index": 10,
  "text": "**URL Seeding > The Trade-offs**\n\n| Aspect | Deep Crawling | URL Seeding |\n|---|---|---|\n| **Coverage** | Discovers pages dynamically | Gets most existing URLs instantly |\n| **Freshness** | Finds brand new pages | May miss very recent pages |\n| **Speed** | Slower, page by page | Extremely fast bulk discovery |",
  "type": "table",
  "source": "url-seed.md",
  "original_text": "| Aspect | Deep Crawling | URL Seeding |\n|---|---|---|\n| **Coverage** | Discovers pages dynamically | Gets most existing URLs instantly |...",
  "heading": "### The Trade-offs",
  "h_level": 3,
  "section_path": "URL Seeding: The Smart Way to Crawl at Scale > Why URL Seeding? > The Trade-offs",
  "parent_chunk_id": 12379910086883507243,
  "section_anchor": "5746dfcae6084f0ad4d2058cc357b0c2",
  "summary": null,
  "child_chunk_ids": [],
  "processed_char_start": 3500,
  "processed_char_end": 4200,
  "token_start": 0,
  "token_count": 140,
  "source_line_start": 66,
  "source_line_end": 73,
  "metadata": {
    "pages": null,
    "breadcrumbs": [
      "URL Seeding: The Smart Way to Crawl at Scale",
      "Why URL Seeding?",
      "The Trade-offs"
    ],
    "root_topic": "URL Seeding: The Smart Way to Crawl at Scale",
    "headers": ["Aspect", "Deep Crawling", "URL Seeding"],
    "row_count": 3
  }
}
```

### Table-Specific Metadata
| Field | Type | Description |
|-------|------|-------------|
| `metadata.headers` | `string[]` | Column headers from the table (first row) |
| `metadata.row_count` | `int` | Number of data rows (excluding header) |

### Key Characteristics
- Contains raw markdown table syntax
- Header is injected for context
- **NEW (v2.0):** Headers are extracted for GLiNER semantic analysis
- Harvester runs GLiNER on headers to discover domain concepts

---

## Chunk Type 4: `heading`

Document structure/hierarchy nodes (section markers).

### Example

```json
{
  "id": 12087906455769254880,
  "index": 0,
  "text": "# URL Seeding: The Smart Way to Crawl at Scale",
  "type": "heading",
  "source": "url-seed.md",
  "original_text": "# URL Seeding: The Smart Way to Crawl at Scale",
  "heading": "# URL Seeding: The Smart Way to Crawl at Scale",
  "h_level": 1,
  "section_path": "URL Seeding: The Smart Way to Crawl at Scale",
  "parent_chunk_id": null,
  "section_anchor": "342053ad0a4bcd8a22d167d589effcae",
  "summary": null,
  "child_chunk_ids": [],
  "processed_char_start": 0,
  "processed_char_end": 46,
  "token_start": 0,
  "token_count": 12,
  "source_line_start": 0,
  "source_line_end": 1,
  "metadata": {
    "pages": null,
    "breadcrumbs": ["URL Seeding: The Smart Way to Crawl at Scale"],
    "root_topic": "URL Seeding: The Smart Way to Crawl at Scale"
  }
}
```

### Key Characteristics
- Found in the `hierarchy` array (not `text`)
- `text` field contains only the heading markdown
- `parent_chunk_id` is usually `null` (they ARE the parents)
- `child_chunk_ids` contains IDs of content chunks under this heading
- Used to build the **Hard Graph** structure in Postgres

---

## Metadata Object

The `metadata` field contains additional context:

| Field | Type | Description |
|-------|------|-------------|
| `pages` | `int[]\|null` | Page numbers (for PDFs) |
| `breadcrumbs` | `string[]` | Heading hierarchy as array |
| `root_topic` | `string` | Top-level document topic |
| `language` | `string` | (Code only) Programming language |
| `lines` | `[int, int]` | (Code only) Line range in source |

---

## Graph Relationships

The chunker output enables building a **Hard Graph** using these fields:

```
parent_chunk_id  → CHILD_OF edge (structural hierarchy)
section_path     → Breadcrumb navigation
child_chunk_ids  → Parent's children (bidirectional)
index            → FOLLOWS edge (reading order)
```

Heading: "# URL Seeding"  (id: 12087906455769254880)
    └── Text: "Why URL Seeding?"  (parent_chunk_id: 12087906455769254880)
         └── Table: "The Trade-offs"  (parent_chunk_id: ...)
         └── Code: "config = SeedingConfig(...)"  (parent_chunk_id: ...)

---

## Vector Store Schema (Qdrant Payload) 🗄️

While the Chunker produces the JSON above, the **Ingestion Pipeline** (`db/ingestion.py`) transforms it into a Qdrant payload optimized for **Hierarchical Retrieval**.

| Field | Type | Description |
|-------|------|-------------|
| `chunk_id` | `string` | The stable 64-bit ID (as string) |
| `doc_id` | `string` | The full file path/URL (used for Document-level grouping) |
| `source` | `string` | The filename only (for cleaner UI/Filtering) |
| `section_root_id` | `int` | **CRITICAL**: The ID of the parent section heading. Enables `group_by` to find coherent sections. |
| `type` | `string` | `text`, `code`, `table` |
| `concept_tags` | `string[]` | Canonical concept names extracted during ingestion |
| `token_start` | `int` | Trinity Coordinate for KV-Cache alignment |

### The "Hierarchical Grouping" Pattern
By storing `doc_id` and `section_root_id`, the search pipeline can execute:
1. `group_by="doc_id"`: To find the most relevant documents.
2. `group_by="section_root_id"`: To find the most relevant sections within those documents.

---

## Usage in Concept Harvester (v2.0)

| Chunk Type | Extraction Strategy | Source |
|------------|---------------------|--------|
| `text` | **GLiNER** on full text | Semantic extraction from prose |
| `code` | **AST symbols** + **GLiNER on comments** | `metadata.symbols_defined` + `metadata.comments_text` |
| `table` | **GLiNER** on headers | `metadata.headers` |
| `heading` | Skip | Structure only, no content |

### The "Rich Metadata, Lazy Resolution" Pattern

1. **Chunker (CPU)**: Walks AST with tree-sitter, extracts symbols ONCE
2. **Harvester (GPU)**: Reads pre-extracted metadata, runs GLiNER on semantic content
3. **Resolver**: Merges concepts to canonical IDs, creates graph edges

This creates the **Brain-Body Bridge**: code symbols (from AST) and semantic concepts (from comments/docstrings) resolve to the same knowledge graph, linking implementation to documentation.

---
