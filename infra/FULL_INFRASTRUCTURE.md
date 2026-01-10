# 🏗️ Complete Infrastructure Documentation

> **Full system documentation with ALL classes, functions, and exports**
> 
> Auto-generated on 2026-01-10 23:55

This document contains comprehensive documentation extracted from every module in the Knowledge Base system.

---

## 📊 System Overview

| Metric | Count |
|--------|-------|
| **Modules** | 14 |
| **Services** | 6 |
| **API Routes** | 43 |
| **Config Keys** | 13 |
| **Total Classes** | 311 |
| **Total Functions** | 817 |

---

## 📑 Table of Contents

### Core Modules

- [🧩 Chunker](#chunker)
- [🔍 Rag](#rag)
- [🤖 Llm](#llm)
- [🗄️ Db](#db)
- [⚙️ Config](#config)
- [🔧 File_Patcher](#file_patcher)
- [⚖️ Judgment](#judgment)
- [🧠 Latent_Memory](#latent_memory)
- [🌾 Concept_Harvester](#concept_harvester)
- [🤖 Agent](#agent)

### Services & API

- [🌐 Services](#services)
- [🌍 Api](#api)
- [📥 Ingestion](#ingestion)

### CLI Tools

- [💻 Cli](#cli)

### Reference

- [🌍 API Endpoints](#api-endpoints)
- [🌐 Services](#services-reference)
- [⚙️ Configuration](#configuration-reference)

---

# 📦 Module Details

## 🧩 Chunker {#chunker}

**Chunker Package - Modular document chunking for knowledge bases.**


| Property | Value |
|----------|-------|
| Classes | 20 |
| Functions | 80 |
| Factory Functions | 2 |
| Exports | 28 |
| Dependencies | config |


### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  ChunkerManager                 (High Level - Facade)           │
│    process_content() / process_file() / process_directory()    │
├─────────────────────────────────────────────────────────────────┤
│  Parsers                        (Mid Level - Document Parsing)  │
│    ast_parser.py    - Markdown documents                        │
│    code_parser/     - Code files (Python, JS, Go, etc.)        │
├─────────────────────────────────────────────────────────────────┤
│  Processors                     (Mid Level - Content Handling)  │
│    text_splitter.py   - Token-aware text chunking               │
│    block_handlers.py  - Code blocks, tables                     │
├─────────────────────────────────────────────────────────────────┤
│  Core                           (Low Level - Building Blocks)   │
│    core.py            - ChunkType, Chunk, ProcessingContext     │
│    chunk_factory.py   - merge_small_chunks                      │
│    utils.py           - token_count, split_sentences            │
│    factories.py       - Tokenizer/Segmenter factories           │
│    config.py          - ChunkerSettings                         │
```


### Quick Start

```python
from chunker import create_chunker

chunker = create_chunker()
result = chunker.process_file("doc/example.md")

print(f"Total chunks: {result.total_chunks}")
for chunk in result.text:
    print(f"[{chunk['type']}] {chunk['text'][:50]}...")
```


### Exports (`__all__`)

`ChunkKeys`, `generate_stable_id`, `generate_section_anchor`, `ChunkerManager`, `create_chunker`, `ChunkResult`, `ChunkStats`, `BatchResult`, `ChunkType`, `Language`, `Chunk`, `ProcessingContext`, `ChunkerSettings`, `token_count`, `add_overlap_to_chunk`, `split_sentences`, `merge_small_chunks`, `token_aware_text_chunks_with_spans`, `split_code_block_to_chunks`, `extract_table_markdown`, `markdown_ast_chunker`, `parse_raw_code`, `chunk_document`, `EXTENSION_MAP`, `SENTENCE_SPLIT_RE`, `PARAGRAPH_SPLIT_RE`, `PAGE_MARKER_RE`, `build_page_map`


### Factory Functions

| Function | Description |
|----------|-------------|
| `create_chunk()` | Creates a new Chunk using context state. |
| `create_chunker()` | Factory function to create a ChunkerManager. |


### Classes

| Class | File | Description |
|-------|------|-------------|
| `MarkdownASTChunker` | `ast_parser.py` | Robust, AST-based, token-aware Markdown chunker. |
| `K` | `ast_parser.py` |  |
| `ChunkCache` | `cache_optimizer.py` | File-based cache for chunker results using cont... |
| `ChunkerSettings` | `config.py` | Configuration for the chunker, allowing per-cor... |
| `ChunkType` | `core.py` | Types of chunks produced by the chunker. |
| `Chunk` | `core.py` | A single chunk of content. |
| `ProcessingContext` | `core.py` | Context passed through the chunking pipeline. |
| `TokenizerFactory` | `factories.py` | Thread-safe singleton factory for tokenizers. |
| `SegmenterFactory` | `factories.py` | Thread-safe singleton factory for pysbd Segmenter. |
| `HealthChecker` | `health_check.py` | Validates chunker dependencies and reports degr... |
| `ChunkStats` | `manager.py` | Statistics about the chunking result. |
| `ChunkResult` | `manager.py` | Result of chunking a single document. |
| `BatchResult` | `manager.py` | Result of batch chunking multiple documents. |
| `ChunkerManager` | `manager.py` | Unified manager for document chunking operations. |
| `CodeChunker` | `code_parser\chunker.py` | Tree-sitter based code chunker with structure-a... |
| `Symbol` | `code_parser\constants.py` | A code symbol extracted from the AST. |


### Functions

| Function | File | Description |
|----------|------|-------------|
| `markdown_ast_chunker()` | `ast_parser.py` | Entry point for the Markdown AST chunker. |
| `get_absolute_offset()` | `ast_parser.py` | Fast lookup of byte offset for a given 0-indexe... |
| `flush_prose_buffer()` | `ast_parser.py` | Process and emit accumulated prose. |
| `chunk()` | `ast_parser.py` | Main entry point to perform chunking. |
| `generate_stable_id()` | `ast_parser.py` |  |
| `extract_row_data()` | `ast_parser.py` |  |
| `split_code_block_to_chunks()` | `block_handlers.py` | Split long code blocks by semantics (Tree-sitte... |
| `extract_table_markdown()` | `block_handlers.py` | Extract table markdown and split into smaller t... |
| `is_table_delimiter()` | `block_handlers.py` | Robust table delimiter detection using multiple... |
| `get_hash()` | `cache_optimizer.py` | Generate cache key from content + metadata |
| `get()` | `cache_optimizer.py` | Retrieve cached chunks if available |
| `set()` | `cache_optimizer.py` | Store chunks in cache |
| `clear()` | `cache_optimizer.py` | Clear all cached chunks |
| `merge_small_chunks()` | `chunk_factory.py` | Merges small text chunks to reduce noise while ... |
| `get_tokenizer()` | `config.py` | Get tokenizer instance via factory pattern. |
| `get_segmenter()` | `config.py` | Get segmenter instance via factory pattern. |
| `to_dict()` | `core.py` | Convert to serializable dictionary format compa... |
| `get_section_path()` | `core.py` | Build section path from heading stack. |
| `push_heading()` | `core.py` | Push a heading onto the stack, popping higher/e... |
| `next_global_index()` | `core.py` | Get next global chunk index and increment. |
| `next_local_index()` | `core.py` | Get next local index for a section. |
| `get_token_offset()` | `core.py` | Get token offset for a section. |
| `update_token_offset()` | `core.py` | Update token offset for a section. |
| `get_tokenizer()` | `factories.py` | Get or create a tokenizer instance. |
| `clear_cache()` | `factories.py` | Clear all cached tokenizer instances (useful fo... |
| `get_segmenter()` | `factories.py` | Get or create a pysbd Segmenter instance. |
| `clear_cache()` | `factories.py` | Clear cached segmenter instances (useful for te... |
| `check_tokenizer()` | `health_check.py` | Check if transformers tokenizer works |
| `check_tree_sitter()` | `health_check.py` | Check if tree-sitter works for code parsing |
| `check_pysbd()` | `health_check.py` | Check if pysbd sentence splitter works |
| `check_markdown_it()` | `health_check.py` | Check if markdown-it-py works |
| `check_all()` | `health_check.py` | Run all health checks |
| `print_report()` | `health_check.py` | Print human-readable health report |
| `merge()` | `manager.py` | Merge statistics from another result. |
| `to_dict()` | `manager.py` | Convert to dictionary for serialization. |
| `total_chunks()` | `manager.py` | Total number of content chunks (excluding hiera... |
| `all_chunks()` | `manager.py` | All chunks including hierarchy for reconstruction. |
| `to_dict()` | `manager.py` | Convert to the standard output format (dictiona... |
| `save()` | `manager.py` | Save the result to a JSON file. |
| `files_processed()` | `manager.py` |  |
| `get_result()` | `manager.py` | Get result for a specific source file. |
| `process_content()` | `manager.py` | Process raw content into structured chunks. |
| `process_file()` | `manager.py` | Process a single file into structured chunks. |
| `process_directory()` | `manager.py` | Process all matching files in a directory. |
| `token_aware_text_chunks_with_spans()` | `text_splitter.py` | Token-aware chunking that preserves exact subst... |
| `get_token_count()` | `text_splitter.py` |  |
| `lookup_page_numbers()` | `utils.py` | Finds pages based on line numbers using the pre... |
| `clean_page_markers()` | `utils.py` | Removes <!-- PAGE X --> markers so they don't i... |
| `clean_markdown_for_breadcrumb()` | `utils.py` | Strips markdown links and images from text for ... |
| `token_count()` | `utils.py` | Estimates token count, using tokenizer if avail... |
| `truncate_to_embedding_limit()` | `utils.py` | Truncate text to the embedding token limit, pre... |
| `add_overlap_to_chunk()` | `utils.py` | Adds overlap from previous chunk to maintain co... |
| `split_sentences()` | `utils.py` | Split text into sentences using pysbd if availa... |
| `build_page_map()` | `utils.py` | Build a map of text positions to page numbers b... |
| `chunk_document()` | `utils.py` | Main entry point for chunking. Correctly routes... |
| `treesitter_chunk_code()` | `code_parser\api.py` | Used by Markdown parser to split code blocks. |
| `extract_code_block_metadata()` | `code_parser\api.py` | Extract metadata from a markdown code block. |
| `parse_raw_code()` | `code_parser\chunker.py` | Main entry point for raw code files. |
| `chunk()` | `code_parser\chunker.py` | Main entry point - parse and chunk the code. |
| `generate_stable_id()` | `code_parser\compat.py` | Fallback stable ID generator. |
| `generate_section_anchor()` | `code_parser\compat.py` | Fallback anchor generator. |
| `emit_group()` | `code_parser\emitters.py` | Emit a group of small nodes as one chunk. |
| `emit_simple_node()` | `code_parser\emitters.py` | Emit a node that fits within token limit. |
| `emit_split_part()` | `code_parser\emitters.py` | Emit a split part of a function/class. |
| `emit_line_split()` | `code_parser\emitters.py` | Fallback: Split node by lines when no structure... |
| `get_span()` | `code_parser\helpers.py` | Get original text and char offsets, including g... |
| `get_node_name()` | `code_parser\helpers.py` | Extract name from a node (function name, class ... |
| `get_html_element_name()` | `code_parser\helpers.py` | Extract name from HTML element (id or class). |
| `infer_group_name()` | `code_parser\helpers.py` | Infer a name for a group of nodes. |
| `get_child_text_with_indent()` | `code_parser\helpers.py` | Get child node text preserving leading whitespace. |
| `get_footer()` | `code_parser\helpers.py` | Get closing element for HTML-like nodes. |
| `extract_metadata_from_node()` | `code_parser\helpers.py` | Extract symbols, comments, refs from a single n... |
| `extract_metadata_from_nodes()` | `code_parser\helpers.py` | Extract metadata from multiple nodes. |
| `dedupe_refs()` | `code_parser\helpers.py` | Deduplicate references by name. |
| `add_code_metadata()` | `code_parser\helpers.py` | Add code-specific metadata to a chunk. |
| `extract_symbols_from_node()` | `code_parser\symbol_extraction.py` | Recursively extract symbol definitions from an ... |
| `extract_comments_from_node()` | `code_parser\symbol_extraction.py` | Extract all comments and docstrings from a node... |
| `extract_references_from_node()` | `code_parser\symbol_extraction.py` | Extract symbol references (function calls, impo... |


### File Structure

```
chunker/
├── __init__.py
├── code_parser/
├── ast_parser.py
├── block_handlers.py
├── cache_optimizer.py
├── chunk_factory.py
├── config.py
├── core.py
├── factories.py
├── health_check.py
├── manager.py
├── text_splitter.py
└── utils.py
```


---

## 🔍 Rag {#rag}

**RAG Package - Retrieval Augmented Generation.**


| Property | Value |
|----------|-------|
| Classes | 18 |
| Functions | 44 |
| Factory Functions | 4 |
| Exports | 16 |
| Dependencies | None |


### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  RAGManager                   (High Level - Facade)             │
│    retrieve() / search() / enrich() / get_context()            │
├─────────────────────────────────────────────────────────────────┤
│  Components                   (Mid Level - Operations)          │
│    HierarchicalSearchPipeline - Vector search + RRF fusion      │
│    ContextRetriever           - Graph enrichment                │
│    SemanticCompressor         - Token budgeting                 │
├─────────────────────────────────────────────────────────────────┤
│  Models                       (Low Level - Embeddings)          │
│    DenseEmbedder / SparseEmbedder / Reranker                   │
├─────────────────────────────────────────────────────────────────┤
│  Core                         (Data Structures)                 │
│    RAGConfig / SearchHit / RAGResult                           │
```


### Quick Start

```python
from rag import create_rag_manager

rag = create_rag_manager(pg_session=db)

# Retrieve context for a query
chunks = await rag.retrieve("How does the chunker work?")

# Get formatted context for LLM
context = await rag.get_context("How does the chunker work?")
```


### Exports (`__all__`)

`SearchMode`, `FusionMethod`, `RAGConfig`, `SearchHit`, `RAGResult`, `get_token_count`, `format_chunk_for_prompt`, `DenseEmbedder`, `SparseEmbedder`, `Reranker`, `SemanticCompressor`, `ContextRetriever`, `EnrichedChunk`, `HierarchicalSearchPipeline`, `RAGManager`, `create_rag_manager`


### Factory Functions

| Function | Description |
|----------|-------------|
| `create_compressor()` | Factory function to create a SemanticCompressor. |
| `create_rag_manager()` | Factory function to create a RAGManager. |
| `create_retrieval_functions()` | Factory function |
| `create_retriever()` | Create a retriever, optionally with Postgres. |


### Classes

| Class | File | Description |
|-------|------|-------------|
| `SemanticCompressor` | `compressor.py` | Async Semantic Compressor - keeps only query-re... |
| `SearchMode` | `core.py` | Search modes for retrieval. |
| `FusionMethod` | `core.py` | Fusion methods for hybrid search. |
| `RAGConfig` | `core.py` | Configuration for RAG system. |
| `SearchHit` | `core.py` | A single search result from vector DB. |
| `RAGResult` | `core.py` | Complete RAG retrieval result. |
| `RAGManager` | `manager.py` | Unified facade for all RAG components. |
| `DenseEmbedder` | `models.py` | Unified Dense Embedder Facade (Async). |
| `FastEmbedEmbedder` | `models.py` | Local FastEmbed-powered Dense Embedder (Threade... |
| `OllamaEmbedder` | `models.py` | Remote Ollama-powered Dense Embedder (True Async). |
| `OpenAIEmbedder` | `models.py` | Remote OpenAI-compatible Dense Embedder (True A... |
| `SparseEmbedder` | `models.py` | FastEmbed-powered BM25 Sparse Embedder (Threade... |
| `Reranker` | `models.py` | Unified Reranker Facade (Async). |
| `LocalReranker` | `models.py` | Local Cross-Encoder Reranker (Threaded Async). |
| `RemoteReranker` | `models.py` | Remote Cross-Encoder Reranker (True Async). |
| `HierarchicalSearchPipeline` | `pipeline.py` | Advanced retrieval pipeline with Hierarchical G... |
| `EnrichedChunk` | `retriever.py` | A chunk with full graph context. |
| `ContextRetriever` | `retriever.py` | Graph-powered context retriever using Postgres ... |


### Functions

| Function | File | Description |
|----------|------|-------------|
| `compress_chunks()` | `compressor.py` | Compress chunks by keeping only query-relevant ... |
| `get_token_count()` | `core.py` | Get token count from chunk metadata (already co... |
| `format_chunk_for_prompt()` | `core.py` | Format a chunk for LLM prompt. |
| `to_dict()` | `core.py` |  |
| `hit_count()` | `core.py` |  |
| `to_dict()` | `core.py` |  |
| `qdrant()` | `manager.py` | Lazy-load Qdrant client. |
| `pipeline()` | `manager.py` | Lazy-load search pipeline. |
| `retriever()` | `manager.py` | Lazy-load context retriever. |
| `compressor()` | `manager.py` | Lazy-load semantic compressor. |
| `set_pg_session()` | `manager.py` | Set or update the Postgres session. |
| `set_feedback_loop()` | `manager.py` | Set the feedback loop for soft signal boosting. |
| `retrieve()` | `manager.py` | Main entry point: Search + Boost + Enrich in on... |
| `search()` | `manager.py` | Perform hierarchical vector search. |
| `enrich()` | `manager.py` | Enrich search results with graph context. |
| `get_context()` | `manager.py` | Get formatted context ready for LLM. |
| `to_cache_format()` | `manager.py` | Convert EnrichedChunks to the format expected b... |
| `close()` | `manager.py` | Cleanup resources. |
| `encode()` | `models.py` | Return list of vectors (Async). |
| `encode()` | `models.py` |  |
| `encode()` | `models.py` |  |
| `encode()` | `models.py` |  |
| `encode()` | `models.py` |  |
| `rerank()` | `models.py` |  |
| `rerank()` | `models.py` |  |
| `rerank()` | `models.py` |  |
| `search()` | `pipeline.py` | Execute the full Hierarchical Search Pipeline. |
| `cosine_sim()` | `pipeline.py` |  |
| `get_init_sql()` | `retrieval_functions.py` |  |
| `format_search_results_for_retriever()` | `retriever.py` | Convert Qdrant results to the format expected b... |
| `to_prompt_format()` | `retriever.py` | Format for LLM prompt. |
| `generate_ide_url()` | `retriever.py` | Generate a deep link to open this chunk in an IDE. |
| `get_git_blame()` | `retriever.py` | Run git blame for this chunk's lines to find Au... |
| `get_full_context()` | `retriever.py` | Fetch full context for a chunk using the Postgr... |
| `enrich_search_results()` | `retriever.py` | Enrich vector search results with graph context. |
| `assemble_rag_context()` | `retriever.py` | Assemble complete RAG context from search results. |
| `find_related_documents()` | `retriever.py` | Find related documents via the Hub-Hop pattern. |
| `find_chunks_by_concepts()` | `retriever.py` | Identify chunks that mention a set of high-leve... |
| `identify_chunks_for_task()` | `retriever.py` | Identify which "Gifts" (chunks) are needed for ... |
| `generate_stitcher_recipe()` | `retriever.py` | Generate a "Recipe" for the FrankensteinStitcher. |


### File Structure

```
rag/
├── __init__.py
├── compressor.py
├── core.py
├── manager.py
├── models.py
├── pipeline.py
├── retrieval_functions.py
└── retriever.py
```


---

## 🤖 Llm {#llm}

**LLM Package - Unified AI Orchestration.**


| Property | Value |
|----------|-------|
| Classes | 24 |
| Functions | 64 |
| Factory Functions | 1 |
| Exports | 8 |
| Dependencies | None |


### Quick Start

```python
from llm import create_llm_manager

llm = create_llm_manager(
    provider="openai",
    model="gpt-4o",
    pg_session=db
)
```


### Exports (`__all__`)

`LLMManager`, `LLMConfig`, `create_llm_manager`, `LLMClient`, `CacheStats`, `get_cache_adapter`, `LLMResponse`, `BaseLLM`


### Factory Functions

| Function | Description |
|----------|-------------|
| `create_llm_manager()` | Create an LLMManager with sensible defaults. |


### Classes

| Class | File | Description |
|-------|------|-------------|
| `CacheStats` | `cache_adapter.py` | Unified cache statistics across all providers. |
| `BaseCacheAdapter` | `cache_adapter.py` | Abstract base for provider-specific cache adapt... |
| `OpenAICacheAdapter` | `cache_adapter.py` | OpenAI Cache Adapter. |
| `AnthropicCacheAdapter` | `cache_adapter.py` | Anthropic Cache Adapter. |
| `GeminiCacheAdapter` | `cache_adapter.py` | Gemini Cache Adapter. |
| `GroqCacheAdapter` | `cache_adapter.py` | Groq Cache Adapter. |
| `NoOpCacheAdapter` | `cache_adapter.py` | No-Op Cache Adapter. |
| `LLMClient` | `client.py` | Standardized Client for interacting with any LL... |
| `LLMResponse` | `kernel.py` | Response string that carries essential metadata... |
| `BaseLLM` | `kernel.py` | Abstract base for all LLM providers. |
| `LLMConfig` | `manager.py` | LLM Manager configuration with smart defaults. |
| `LLMManager` | `manager.py` | Unified LLM Orchestrator. |
| `AnthropicProvider` | `providers\anthropic_provider.py` |  |
| `AzureProvider` | `providers\azure_provider.py` |  |
| `GCPProvider` | `providers\gcp_provider.py` |  |
| `GeminiProvider` | `providers\gemini_provider.py` |  |
| `GroqProvider` | `providers\groq_provider.py` |  |
| `HuggingFaceProvider` | `providers\huggingface_provider.py` |  |
| `MistralProvider` | `providers\mistral_provider.py` | Official Mistral SDK (v1+). |
| `OllamaProvider` | `providers\ollama_provider.py` |  |
| `OpenAIConfig` | `providers\openai_provider.py` | Advanced configuration for OpenAI Responses API. |
| `OpenAIProvider` | `providers\openai_provider.py` | OpenAI LLM Provider using the Responses API. |
| `OpenRouterProvider` | `providers\openrouter_provider.py` |  |
| `XAIProvider` | `providers\xai_provider.py` |  |


### Functions

| Function | File | Description |
|----------|------|-------------|
| `get_cache_adapter()` | `cache_adapter.py` | Get the appropriate cache adapter for a provider. |
| `to_dict()` | `cache_adapter.py` | Convert to dictionary for JSON serialization. |
| `prepare_request()` | `cache_adapter.py` | Add provider-specific cache hints to the request. |
| `parse_response()` | `cache_adapter.py` | Extract cache statistics from provider response. |
| `estimate_savings()` | `cache_adapter.py` | Estimate cost savings percentage from caching. |
| `prepare_request()` | `cache_adapter.py` | Add OpenAI-specific cache hints. |
| `parse_response()` | `cache_adapter.py` | Extract cache stats from OpenAI response. |
| `prepare_request()` | `cache_adapter.py` | Add Anthropic cache_control markers. |
| `parse_response()` | `cache_adapter.py` | Extract cache stats from Anthropic response. |
| `prepare_request()` | `cache_adapter.py` | Prepare Gemini-specific hints. |
| `parse_response()` | `cache_adapter.py` | Extract cache stats from Gemini response. |
| `prepare_request()` | `cache_adapter.py` | No hints needed - Groq handles caching automati... |
| `parse_response()` | `cache_adapter.py` | Extract cache stats from Groq response. |
| `prepare_request()` | `cache_adapter.py` | No cache hints for this provider. |
| `parse_response()` | `cache_adapter.py` | No cache stats available. |
| `cache_adapter()` | `client.py` | Lazy-load cache adapter. |
| `generate()` | `client.py` | Unified async generation interface. |
| `get_cache_stats()` | `client.py` | Get cache statistics from the last (or specifie... |
| `list_models()` | `client.py` | Fetch available models. |
| `set_key()` | `kernel.py` | Set a key in an env file. |
| `get_or_request_key()` | `kernel.py` | Fetch key from env, prompt if missing. |
| `get_key_silent()` | `kernel.py` | Return env key if exists, else None. No prompts. |
| `with_retry()` | `kernel.py` | Decorator to add retry logic with exponential b... |
| `generate()` | `kernel.py` | Generate a response from the LLM. |
| `decorator()` | `kernel.py` |  |
| `wrapper()` | `kernel.py` |  |
| `chat()` | `manager.py` | Complete RAG + Memory chat cycle with FULL user... |
| `learn()` | `manager.py` | Learn from a conversation turn (save & feedback). |
| `feedback()` | `manager.py` | Record explicit user feedback (👍/👎). |
| `get_stats()` | `manager.py` | Get memory and session statistics. |
| `forget()` | `manager.py` | Clear a conversation session. |
| `set_pg_session()` | `manager.py` | Update the database session for all sub-managers. |
| `set_qdrant_client()` | `manager.py` | Update the Qdrant client for all sub-managers. |
| `close()` | `manager.py` | Cleanup resources. |
| `generate()` | `providers\anthropic_provider.py` |  |
| `list_models()` | `providers\anthropic_provider.py` | Dynamically fetch available models from Anthrop... |
| `generate()` | `providers\azure_provider.py` |  |
| `list_models()` | `providers\azure_provider.py` | Dynamically fetch available models from Azure O... |
| `generate()` | `providers\gcp_provider.py` | Generate text using GCP Vertex AI models |
| `list_models()` | `providers\gcp_provider.py` | List available Vertex AI models |
| `generate()` | `providers\gemini_provider.py` |  |
| `list_models()` | `providers\gemini_provider.py` |  |
| `stream_generator()` | `providers\gemini_provider.py` |  |
| `generate()` | `providers\groq_provider.py` |  |
| `list_models()` | `providers\groq_provider.py` |  |
| `stream_generator()` | `providers\groq_provider.py` |  |
| `generate()` | `providers\huggingface_provider.py` |  |
| `list_models()` | `providers\huggingface_provider.py` |  |
| `stream_gen()` | `providers\huggingface_provider.py` |  |
| `generate()` | `providers\mistral_provider.py` |  |
| `list_models()` | `providers\mistral_provider.py` |  |
| `list_models()` | `providers\ollama_provider.py` |  |
| `generate()` | `providers\ollama_provider.py` |  |
| `generate()` | `providers\openai_provider.py` | Generate text using OpenAI Responses API. |
| `last_response_id()` | `providers\openai_provider.py` | Get the last response ID for conversation chain... |
| `list_models()` | `providers\openai_provider.py` | List available models (synchronous). |
| `poll_background()` | `providers\openai_provider.py` | Poll a background response until completion. |
| `cancel_background()` | `providers\openai_provider.py` | Cancel an in-flight background response. |
| `generate()` | `providers\openrouter_provider.py` |  |
| `list_models()` | `providers\openrouter_provider.py` |  |
| `stream_generator()` | `providers\openrouter_provider.py` |  |
| `generate()` | `providers\xai_provider.py` |  |
| `list_models()` | `providers\xai_provider.py` |  |


### File Structure

```
llm/
├── __init__.py
├── doc/
├── providers/
├── cache_adapter.py
├── client.py
├── kernel.py
└── manager.py
```


---

## 🗄️ Db {#db}

**Database Module - Dual-Graph Data Layer (Postgres + Qdrant).**


| Property | Value |
|----------|-------|
| Classes | 13 |
| Functions | 18 |
| Factory Functions | 1 |
| Exports | 20 |
| Dependencies | None |


### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
```


### Quick Start

```python
from db import create_db_manager

async with create_db_manager() as db:
    async with db.pg_session() as session:
        # Use Postgres
        pass
    # Use Qdrant
```


### Exports (`__all__`)

`DatabaseManager`, `create_db_manager`, `get_pg_session`, `get_qdrant_client`, `Base`, `Document`, `ProcessingJob`, `Chunk`, `Node`, `Edge`, `GlobalConcept`, `ConversationLog`, `CompressedMemory`, `UserPreference`, `Session`, `PatchHistory`, `FileLock`, `get_async_engine`, `get_session_maker`, `init_database`


### Factory Functions

| Function | Description |
|----------|-------------|
| `create_db_manager()` | Factory function for DatabaseManager. |


### Classes

| Class | File | Description |
|-------|------|-------------|
| `DatabaseManager` | `manager.py` | Unified manager for Postgres and Qdrant connect... |
| `Document` | `schema.py` | Registry of all source documents in the knowled... |
| `ProcessingJob` | `schema.py` | Queue and history of background processing tasks. |
| `Chunk` | `schema.py` | Parsed document chunks - Postgres is source of ... |
| `ConversationLog` | `schema.py` | Episodic Memory (STM) - The raw logs of interac... |
| `CompressedMemory` | `schema.py` | Semantic Memory (LTM) - Compressed summaries of... |
| `UserPreference` | `schema.py` | Long-Term User Preferences - Cross-session memory. |
| `Session` | `schema.py` | Shared Session State for Horizontal Scaling. |
| `Node` | `schema.py` | Physical structure of the document (Topological... |
| `GlobalConcept` | `schema.py` | Unified registry for conceptual nodes (Hubs). |
| `Edge` | `schema.py` | Relationships between Graph elements. |
| `PatchHistory` | `schema.py` | Verified Patch Contract - First-class audit log... |
| `FileLock` | `schema.py` | Distributed lock for concurrent file mutations. |


### Functions

| Function | File | Description |
|----------|------|-------------|
| `main()` | `async_init.py` |  |
| `main()` | `drop_tables.py` |  |
| `get_pg_session()` | `manager.py` | Get a quick Postgres session (caller must close). |
| `get_qdrant_client()` | `manager.py` | Get a quick Qdrant client (caller must close). |
| `engine()` | `manager.py` | Get SQLAlchemy async engine. |
| `session_maker()` | `manager.py` | Get async session maker. |
| `qdrant()` | `manager.py` | Get Qdrant async client. |
| `pg_session()` | `manager.py` | Context manager for Postgres session. |
| `init_postgres()` | `manager.py` | Create all Postgres tables. |
| `init_qdrant_collection()` | `manager.py` | Initialize a Qdrant collection with hybrid vect... |
| `drop_all_postgres()` | `manager.py` | Drop all Postgres tables. |
| `drop_all_qdrant()` | `manager.py` | Delete all Qdrant collections. Returns list of ... |
| `drop_all()` | `manager.py` | Drop ALL data from both Postgres and Qdrant. |
| `close()` | `manager.py` | Close all connections. |
| `get_async_engine()` | `schema.py` |  |
| `get_session_maker()` | `schema.py` |  |
| `init_database()` | `schema.py` | Initialize full database schema from Python mod... |


### File Structure

```
db/
├── __init__.py
├── async_init.py
├── drop_tables.py
├── manager.py
└── schema.py
```


---

## ⚙️ Config {#config}

**Central Configuration Module.**


| Property | Value |
|----------|-------|
| Classes | 5 |
| Functions | 21 |
| Factory Functions | 0 |
| Exports | 25 |
| Dependencies | None |


### Exports (`__all__`)

`EMBEDDING_CONFIG`, `EmbeddingConfig`, `get_model_name`, `get_dim`, `get_max_tokens`, `get_sparse_model`, `get_reranker_model`, `DATABASE_CONFIG`, `DatabaseConfig`, `get_pg_url`, `get_qdrant_url`, `setup_logging`, `get_logger`, `console`, `InterstellarLogger`, `ChunkKeys`, `validate_chunk`, `generate_stable_id`, `generate_section_anchor`, `Language`, `EXTENSION_TO_LANGUAGE`, `EXTENSION_TO_TREESITTER`, `get_language_from_extension`, `get_treesitter_lang`, `is_code_file`


### Classes

| Class | File | Description |
|-------|------|-------------|
| `ChunkKeys` | `chunks.py` | The 'Canon' of keys for any chunk in the system. |
| `DatabaseConfig` | `database.py` | Configuration for database connections. |
| `EmbeddingConfig` | `embeddings.py` | Central configuration for embedding models. |
| `Language` | `languages.py` | Supported programming languages for code chunks. |
| `InterstellarLogger` | `logging.py` | Enhanced logger that provides convenience metho... |


### Functions

| Function | File | Description |
|----------|------|-------------|
| `validate_chunk()` | `chunks.py` | Check if a chunk follows the mandatory schema f... |
| `get_pg_url()` | `database.py` | Get the PostgreSQL connection URL. |
| `get_qdrant_url()` | `database.py` | Get the Qdrant connection URL. |
| `postgres_dsn()` | `database.py` | Get asyncpg compatible connection string (remov... |
| `from_env()` | `database.py` | Load configuration from environment variables. |
| `get_model_name()` | `embeddings.py` | Get the configured dense embedding model name. |
| `get_dim()` | `embeddings.py` | Get the configured embedding dimension. |
| `get_max_tokens()` | `embeddings.py` | Get the configured max tokens for the embedding... |
| `get_sparse_model()` | `embeddings.py` | Get the configured sparse embedding model name. |
| `get_reranker_model()` | `embeddings.py` | Get the configured reranker model name. |
| `from_env()` | `embeddings.py` | Create configuration from environment variables. |
| `generate_stable_id()` | `id_system.py` | Generates a globally stable 63-bit positive int... |
| `generate_section_anchor()` | `id_system.py` | Stable hex anchor to group chunks under the sam... |
| `get_language_from_extension()` | `languages.py` | Get Language enum from file extension. |
| `get_treesitter_lang()` | `languages.py` | Get tree-sitter language string from file exten... |
| `is_code_file()` | `languages.py` | Check if a file is a code file based on extension. |
| `setup_logging()` | `logging.py` | Configure project-wide logging. |
| `get_logger()` | `logging.py` | Get a consistent logger for a specific module. |
| `success()` | `logging.py` |  |
| `panel()` | `logging.py` | Display a beautiful panel in the console. |
| `table()` | `logging.py` | Display a beautiful table in the console. |


### File Structure

```
config/
├── __init__.py
├── chunks.py
├── database.py
├── embeddings.py
├── id_system.py
├── languages.py
└── logging.py
```


---

## 🔧 File_Patcher {#file_patcher}

**File Patcher - Safe Code Mutations with Judgment Gates.**


| Property | Value |
|----------|-------|
| Classes | 21 |
| Functions | 58 |
| Factory Functions | 6 |
| Exports | 20 |
| Dependencies | None |


### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  FilePatcherManager           (High Level - 3 methods)          │
├─────────────────────────────────────────────────────────────────┤
│  SurgicalPatcher / Stitcher   (Mid Level - Operations)          │
├─────────────────────────────────────────────────────────────────┤
│  core.py                      (Low Level - Primitives)          │
│  apply_patch / assemble / ripple / read / write                 │
├─────────────────────────────────────────────────────────────────┤
│  guards.py                    (Judgment Pipeline)               │
│  validate_syntax / critique / impact / tests                    │
```


### Quick Start

```python
from file_patcher import create_patcher_manager

patcher = create_patcher_manager(
    qdrant_client=qdrant,
    session_maker=db_session
)

# Edit a chunk
result = await patcher.patch("src/main.py", "kb_chunks", chunk, new_code)

# Create new file from existing chunks
result = await patcher.create(chunks, "generated/hybrid.py")
```


### Exports (`__all__`)

`FilePatcherManager`, `PatcherConfig`, `create_patcher_manager`, `SurgicalPatcher`, `PatchReceipt`, `apply_surgical_patch`, `create_patcher`, `FrankensteinStitcher`, `StitchResult`, `create_stitcher`, `guarded_write`, `run_judgment_pipeline`, `validate_syntax_only`, `critique_only`, `apply_patch`, `assemble`, `ripple`, `update_embedding`, `PatchDelta`, `PatchResult`


### Factory Functions

| Function | Description |
|----------|-------------|
| `create_ui_resource()` | Create a UIResource object compatible with MCP-UI spec. |
| `create_unified_diff()` | Factory function |
| `create_directory()` | Create a new directory or ensure it exists. |
| `create_patcher_manager()` | Create a FilePatcherManager. |
| `create_stitcher()` | Factory function for FrankensteinStitcher. |
| `create_patcher()` | Factory function for SurgicalPatcher. |


### Classes

| Class | File | Description |
|-------|------|-------------|
| `PatchDelta` | `core.py` | Change metrics from a patch operation. |
| `PatchResult` | `core.py` | Result of a patch operation. |
| `ReadFileArgs` | `filesystem.py` |  |
| `ReadMultipleFilesArgs` | `filesystem.py` |  |
| `WriteFileArgs` | `filesystem.py` |  |
| `EditOperation` | `filesystem.py` |  |
| `EditFileArgs` | `filesystem.py` |  |
| `CreateDirectoryArgs` | `filesystem.py` |  |
| `ListDirectoryArgs` | `filesystem.py` |  |
| `DirectoryTreeArgs` | `filesystem.py` |  |
| `MoveFileArgs` | `filesystem.py` |  |
| `SearchFilesArgs` | `filesystem.py` |  |
| `GetFileInfoArgs` | `filesystem.py` |  |
| `SetAllowedDirectoriesArgs` | `filesystem.py` |  |
| `FileInfo` | `filesystem.py` |  |
| `PatcherConfig` | `manager.py` | Configuration for the file patcher. |
| `FilePatcherManager` | `manager.py` | Unified facade for all file mutation operations. |
| `StitchResult` | `stitcher.py` | Result of a stitch operation. |
| `FrankensteinStitcher` | `stitcher.py` | Assembles new files from existing code chunks. |
| `PatchReceipt` | `surgical.py` | Result of a surgical patch operation. |
| `SurgicalPatcher` | `surgical.py` | Surgical editor for code chunks. |


### Functions

| Function | File | Description |
|----------|------|-------------|
| `apply_patch()` | `core.py` | Apply a byte-precise patch to content. |
| `assemble()` | `core.py` | Assemble content from multiple source grafts. |
| `ripple()` | `core.py` | Update downstream chunk metadata after an edit. |
| `update_embedding()` | `core.py` | Update the embedding vector for a chunk. |
| `read_file()` | `core.py` | Read file content. |
| `write_file()` | `core.py` | Write content to file. |
| `to_dict()` | `core.py` |  |
| `normalize_path()` | `filesystem.py` |  |
| `expand_home()` | `filesystem.py` |  |
| `validate_path_sync()` | `filesystem.py` |  |
| `validate_path()` | `filesystem.py` |  |
| `server_lifespan()` | `filesystem.py` |  |
| `normalize_line_endings()` | `filesystem.py` |  |
| `handle_errors()` | `filesystem.py` |  |
| `read_file()` | `filesystem.py` | Read the complete contents of a file asynchrono... |
| `read_multiple_files()` | `filesystem.py` | Read the contents of multiple files asynchronou... |
| `write_file()` | `filesystem.py` | Create or overwrite a file with new content asy... |
| `edit_file()` | `filesystem.py` | Make line-based edits to a text file with flexi... |
| `list_directory()` | `filesystem.py` | Get a detailed listing of directory contents. |
| `view_directory_ui()` | `filesystem.py` | Renders an interactive UI to display the conten... |
| `directory_tree()` | `filesystem.py` | Get a recursive tree view of files and director... |
| `move_file()` | `filesystem.py` | Move or rename files and directories. |
| `search_files()` | `filesystem.py` | Recursively search for files matching a pattern. |
| `get_file_info()` | `filesystem.py` | Retrieve detailed metadata about a file or dire... |
| `list_allowed_directories()` | `filesystem.py` | Returns the list of directories this server can... |
| `set_allowed_directories()` | `filesystem.py` | Update the list of allowed directories at runtime. |
| `read_and_summarize_file()` | `filesystem.py` | Prompt to read and summarize a file, structured... |
| `search_and_list_files()` | `filesystem.py` | Prompt to search for files matching a pattern, ... |
| `write_content_to_file()` | `filesystem.py` | Prompt to write content to a file, with confirm... |
| `edit_file_content()` | `filesystem.py` | Prompt to edit a file, showing a preview and as... |
| `get_server_status()` | `filesystem.py` | Return server status with allowed directories. |
| `get_directory_listing()` | `filesystem.py` | Expose directory contents as a resource. |
| `get_file_content()` | `filesystem.py` | Expose file contents as a resource, read synchr... |
| `get_file_metadata()` | `filesystem.py` | Expose file metadata as a resource. |
| `wrapper()` | `filesystem.py` |  |
| `build_tree()` | `filesystem.py` |  |
| `run_judgment_pipeline()` | `guards.py` | Run the judgment pipeline on a proposed change. |
| `guarded_write()` | `guards.py` | Write to file with judgment gates. |
| `validate_syntax_only()` | `guards.py` | Quick synchronous syntax check. |
| `critique_only()` | `guards.py` | Quick synchronous diff critique. |
| `patch()` | `manager.py` | Edit an existing chunk in a file. |
| `create()` | `manager.py` | Create a new file from grafts. |
| `write()` | `manager.py` | Write content to file with judgment gates. |
| `validate_only()` | `manager.py` | Quick syntax validation (sync). |
| `critique_only()` | `manager.py` | Quick diff critique (sync). |
| `to_dict()` | `stitcher.py` |  |
| `stitch()` | `stitcher.py` | Assemble a new file from grafts. |
| `stitch_from_chunks()` | `stitcher.py` | Stitch from chunk metadata (from Qdrant/DB). |
| `apply_surgical_patch()` | `surgical.py` | Legacy function for backwards compatibility. |
| `to_dict()` | `surgical.py` |  |
| `qdrant()` | `surgical.py` | Lazy-load Qdrant client. |
| `patch()` | `surgical.py` | Perform a surgical edit with safety gates. |


### File Structure

```
file_patcher/
├── __init__.py
├── core.py
├── filesystem.py
├── guards.py
├── manager.py
├── stitcher.py
└── surgical.py
```


---

## ⚖️ Judgment {#judgment}

**Judgment System - "Senior Engineer in a Box"**


| Property | Value |
|----------|-------|
| Classes | 33 |
| Functions | 81 |
| Factory Functions | 8 |
| Exports | 40 |
| Dependencies | None |


### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  JudgmentManager              (High Level - evaluate())         │
├─────────────────────────────────────────────────────────────────┤
│  GATES                        (Mid Level - Individual Gates)    │
│  Validator | Linter | Critic | Oracle | Immune                  │
├─────────────────────────────────────────────────────────────────┤
│  core.py                      (Low Level - Data Structures)     │
│  GateType | Decision | RiskLevel | JudgmentResult               │
├─────────────────────────────────────────────────────────────────┤
│  VPC (PatchLogger)            (Audit Trail)                     │
```


### Quick Start

```python
from judgment import create_judgment_manager

judgment = create_judgment_manager(session_maker=db)

result = await judgment.evaluate(
    file_path="src/main.py",
    old_content="...",
    new_content="..."
)

if result.approved:
    # Apply the patch
    ...
```


### Exports (`__all__`)

`GateType`, `Decision`, `RiskLevel`, `Severity`, `GateResult`, `JudgmentResult`, `JudgmentConfig`, `get_language_from_path`, `JudgmentManager`, `create_judgment_manager`, `PatchEvaluation`, `PatchValidator`, `create_validator`, `validate_before_patch`, `ValidationResult`, `PreviewResult`, `SemanticLinter`, `create_linter`, `LintResult`, `DuplicateMatch`, `DiffCritic`, `create_critic`, `Critique`, `Violation`, `DiffStats`, `ImpactOracle`, `create_oracle`, `ImpactReport`, `Caller`, `TestCoverage`, `ImmuneSystem`, `create_immune_system`, `TestResult`, `PatchVerification`, `TestStatus`, `PatchLogger`, `PatchRecord`, `create_patch_logger`, `PatchDecision`, `RejectionGate`


### Factory Functions

| Function | Description |
|----------|-------------|
| `create_critic()` | Factory function to create a DiffCritic instance. |
| `create_immune_system()` | Factory function to create an ImmuneSystem instance. |
| `create_linter()` | Create a SemanticLinter instance. |
| `create_judgment_manager()` | Create a JudgmentManager. |
| `create_oracle()` | Factory function to create an ImpactOracle instance. |
| `create_validator()` | Factory function to create a PatchValidator instance. |
| `create_patch_logger()` | Factory function to create a PatchLogger. |
| `create_record()` | Create a PatchRecord from patcher inputs and receipt. |


### Classes

| Class | File | Description |
|-------|------|-------------|
| `GateType` | `core.py` | Types of judgment gates. |
| `Decision` | `core.py` | Patch decision outcomes. |
| `RiskLevel` | `core.py` | Risk levels for impact analysis. |
| `Severity` | `core.py` | Violation severity levels. |
| `GateResult` | `core.py` | Base result for any gate. |
| `JudgmentResult` | `core.py` | Complete judgment result for a patch. |
| `JudgmentConfig` | `core.py` | Configuration for judgment system. |
| `ViolationType` | `critic.py` | Types of patch discipline violations. |
| `Violation` | `critic.py` | A single patch discipline violation. |
| `DiffStats` | `critic.py` | Statistics about a diff. |
| `Critique` | `critic.py` | Result of patch critique. |
| `DiffCritic` | `critic.py` | Analyzes patches for quality and adherence to s... |
| `TestStatus` | `immune.py` | Status of a test run. |
| `TestResult` | `immune.py` | Result of running tests. |
| `PatchVerification` | `immune.py` | Complete verification result for a patch. |
| `ImmuneSystem` | `immune.py` | Test-based verification for patches. |
| `DuplicateMatch` | `linter.py` | A single duplicate match found. |
| `LintResult` | `linter.py` | Result of semantic linting. |
| `SemanticLinter` | `linter.py` | Checks for semantic duplication using hybrid ve... |
| `JudgmentManager` | `manager.py` | Unified manager for patch safety evaluation. |
| `Caller` | `oracle.py` | A location that calls/imports the target symbol. |
| `TestCoverage` | `oracle.py` | Test coverage information for a code region. |
| `ImpactReport` | `oracle.py` | Complete impact analysis report. |
| `ImpactOracle` | `oracle.py` | Analyzes the impact of code changes. |
| `ValidationResult` | `validator.py` | Result of syntax validation. |
| `PreviewResult` | `validator.py` | Result of patch preview with validation. |
| `PatchValidator` | `validator.py` | Validates patches before they are applied to disk. |
| `PatchDecision` | `vpc.py` | Final decision for a patch. |
| `RejectionGate` | `vpc.py` | Which gate rejected the patch. |
| `PatchRecord` | `vpc.py` | A complete record of a patch attempt. |
| `PatchLogger` | `vpc.py` | Logs patch operations to the database. |


### Functions

| Function | File | Description |
|----------|------|-------------|
| `get_language_from_path()` | `core.py` | Get tree-sitter language from file extension. |
| `to_dict()` | `core.py` |  |
| `to_dict()` | `core.py` |  |
| `summary()` | `core.py` | Human-readable summary. |
| `extract_imports()` | `critic.py` | Extract all import statements from content. |
| `quick_critique()` | `critic.py` | Quick critique for simple use cases. |
| `to_dict()` | `critic.py` |  |
| `change_ratio()` | `critic.py` | Ratio of lines changed to original line count. |
| `to_dict()` | `critic.py` |  |
| `to_dict()` | `critic.py` |  |
| `get_agent_feedback()` | `critic.py` | Generate structured feedback for the LLM agent ... |
| `compute_diff_stats()` | `critic.py` | Compute detailed statistics about a diff. |
| `detect_whitespace_only_changes()` | `critic.py` | Find lines that only differ by whitespace. |
| `detect_removed_patterns()` | `critic.py` | Detect removed safety-critical patterns. |
| `critique_patch()` | `critic.py` | Analyze a patch and return a critique. |
| `parse_pytest_output()` | `immune.py` | Parse pytest output to extract test counts. |
| `parse_pytest_json()` | `immune.py` | Parse pytest JSON output (if using --json flag). |
| `quick_test_check()` | `immune.py` | Quick test check for simple use cases. |
| `verify_before_patch()` | `immune.py` | Quick verification check for use in patcher.py. |
| `summary()` | `immune.py` | Human-readable summary. |
| `to_dict()` | `immune.py` |  |
| `to_dict()` | `immune.py` |  |
| `run_test_files()` | `immune.py` | Run specific test files. |
| `run_tests_for_symbol()` | `immune.py` | Run tests relevant to a specific symbol. |
| `run_tests_for_file()` | `immune.py` | Run tests related to a source file. |
| `verify_patch()` | `immune.py` | Full verification pipeline for a patch. |
| `run_quick_sanity_check()` | `immune.py` | Run a quick sanity check on a Python file. |
| `to_dict()` | `linter.py` |  |
| `to_dict()` | `linter.py` |  |
| `analyze_text()` | `linter.py` | Analyze text for semantic duplicates using hybr... |
| `analyze_file()` | `linter.py` | Analyze an entire file for semantic duplication. |
| `lint()` | `linter.py` | Run semantic linting and return structured result. |
| `evaluate()` | `manager.py` | Evaluate a patch through all enabled gates. |
| `evaluate_patch()` | `manager.py` | Legacy alias for evaluate(). |
| `validate_only()` | `manager.py` | Quick syntax check (sync). |
| `critique_only()` | `manager.py` | Quick diff critique (sync). |
| `extract_function_names()` | `oracle.py` | Extract function/method names from code content. |
| `extract_class_names()` | `oracle.py` | Extract class names from code content. |
| `run_ripgrep()` | `oracle.py` | Run ripgrep to find pattern matches. |
| `find_callers_with_ripgrep()` | `oracle.py` | Find all locations that call a function/method. |
| `find_importers_with_ripgrep()` | `oracle.py` | Find all files that import a module. |
| `find_related_tests()` | `oracle.py` | Find test files that might cover a symbol. |
| `quick_impact_check()` | `oracle.py` | Quick impact check for simple use cases. |
| `to_dict()` | `oracle.py` |  |
| `to_dict()` | `oracle.py` |  |
| `caller_count()` | `oracle.py` |  |
| `summary()` | `oracle.py` | Generate a human-readable summary. |
| `to_dict()` | `oracle.py` |  |
| `analyze_impact()` | `oracle.py` | Analyze the impact of a code change. |
| `analyze_impact_async()` | `oracle.py` | Async version of analyze_impact (for FastAPI in... |
| `validate_before_patch()` | `validator.py` | Quick validation check for use in patcher.py. |
| `to_dict()` | `validator.py` |  |
| `to_dict()` | `validator.py` |  |
| `get_language()` | `validator.py` | Determine tree-sitter language from file extens... |
| `validate_syntax()` | `validator.py` | Validate that content is syntactically valid fo... |
| `validate_file()` | `validator.py` | Validate an existing file on disk. |
| `validate_patch_preview()` | `validator.py` | Validate a patch BEFORE applying it. |
| `compute_content_hash()` | `vpc.py` | Compute SHA-256 hash of content. |
| `compute_diff_summary()` | `vpc.py` | Generate a truncated unified diff. |
| `extract_symbols_from_receipt()` | `vpc.py` | Extract changed symbols from a patcher receipt. |
| `determine_rejection_gate()` | `vpc.py` | Determine which gate rejected the patch. |
| `quick_log_patch()` | `vpc.py` | Quick logging for simple cases. |
| `to_dict()` | `vpc.py` | Convert to dictionary for JSON serialization. |
| `summary()` | `vpc.py` | Human-readable summary. |
| `log_to_buffer()` | `vpc.py` | Log a record to the in-memory buffer. |
| `log_to_database()` | `vpc.py` | Log a record to the database. |
| `log_patch()` | `vpc.py` | Main entry point: Create and log a patch record. |
| `log_patch_sync()` | `vpc.py` | Synchronous version: Create and log to buffer o... |
| `get_file_history()` | `vpc.py` | Get patch history for a specific file. |
| `get_session_history()` | `vpc.py` | Get all patches from a session. |
| `get_buffer()` | `vpc.py` | Get in-memory buffer contents. |
| `clear_buffer()` | `vpc.py` | Clear the in-memory buffer. Returns count of cl... |
| `flush_buffer_to_db()` | `vpc.py` | Flush buffered records to database. Returns cou... |


### File Structure

```
judgment/
├── __init__.py
├── core.py
├── critic.py
├── immune.py
├── linter.py
├── manager.py
├── oracle.py
├── validator.py
└── vpc.py
```


---

## 🧠 Latent_Memory {#latent_memory}

**Latent Memory - Unified AI Memory Interface.**


| Property | Value |
|----------|-------|
| Classes | 20 |
| Functions | 81 |
| Factory Functions | 11 |
| Exports | 49 |
| Dependencies | judgment, file_patcher |


### Quick Start

```python
from latent_memory import create_memory_manager

llm = create_memory_manager(
    system_prompt="You are helpful.",
    pg_session=db
)

prompt = await llm.prepare("session_123", "How do I chunk?", chunks)
# ... call LLM to get response ...
await llm.learn("session_123", "How do I chunk?", chunks, response)
```


### Exports (`__all__`)

`LatentMemoryManager`, `LatentConfig`, `create_memory_manager`, `FeedbackManager`, `create_feedback_manager`, `FeedbackLoop`, `create_feedback_loop`, `SoftFeedbackLoop`, `HardFeedbackLoop`, `ChunkSignal`, `extract_citations`, `KVCacheManager`, `ContextRotator`, `TokenBudget`, `MemoryOrchestrator`, `create_orchestrator`, `EpisodicMemory`, `SemanticMemory`, `MemoryCompressor`, `Turn`, `Memory`, `MemoryConfig`, `SurgicalPatcher`, `apply_surgical_patch`, `FrankensteinStitcher`, `guarded_write`, `FilePatcherManager`, `create_patcher_manager`, `JudgmentManager`, `create_judgment_manager`, `PatchEvaluation`, `PatchValidator`, `create_validator`, `validate_before_patch`, `DiffCritic`, `create_critic`, `Critique`, `Violation`, `ImpactOracle`, `create_oracle`, `ImpactReport`, `RiskLevel`, `ImmuneSystem`, `create_immune_system`, `TestResult`, `PatchVerification`, `PatchLogger`, `PatchRecord`, `create_patch_logger`


### Factory Functions

| Function | Description |
|----------|-------------|
| `create_memory_manager()` | Create a LatentMemoryManager with sensible defaults. |
| `create_feedback_manager()` | Factory function for FeedbackManager. |
| `create_orchestrator()` | Factory function to create a MemoryOrchestrator. |
| `create_feedback_loop()` | Factory function (from exports) |
| `create_patcher_manager()` | Factory function (from exports) |
| `create_judgment_manager()` | Factory function (from exports) |
| `create_validator()` | Factory function (from exports) |
| `create_critic()` | Factory function (from exports) |
| `create_oracle()` | Factory function (from exports) |
| `create_immune_system()` | Factory function (from exports) |
| `create_patch_logger()` | Factory function (from exports) |


### Classes

| Class | File | Description |
|-------|------|-------------|
| `TokenBudget` | `context_rotator.py` | Token allocation summary. |
| `ContextRotator` | `context_rotator.py` | Manages token budget for context chunks. |
| `PrefixMetadata` | `kv_cache.py` | Logical tracking of what is currently in the LL... |
| `KVCacheManager` | `kv_cache.py` | Builds cache-optimal prompts. |
| `LatentConfig` | `manager.py` | Configuration with smart defaults. |
| `LatentMemoryManager` | `manager.py` | Unified AI Memory Manager. |
| `HardFeedbackLoop` | `feedback\hard_loop.py` | Hard (User-Confirmed) Feedback Loop. |
| `FeedbackManager` | `feedback\manager.py` | Unified manager for two-tier feedback system. |
| `ChunkSignal` | `feedback\signal_tracker.py` | Tracks the learned signal for a query-chunk pair. |
| `SoftFeedbackLoop` | `feedback\soft_loop.py` | Soft (Automatic) Feedback Loop. |
| `MemoryCompressor` | `memory\compressor.py` | Compresses conversation turns into compact memo... |
| `EpisodicMemory` | `memory\episodic.py` | Manages recent conversation turns with full text. |
| `TurnRole` | `memory\models.py` | Valid roles for conversation turns. |
| `ImportanceLevel` | `memory\models.py` | Importance categories for prioritization. |
| `Turn` | `memory\models.py` | A single conversation turn with rich metadata. |
| `Memory` | `memory\models.py` | A compressed memory from multiple turns. |
| `SessionStats` | `memory\models.py` | Analytics for a conversation session. |
| `MemoryConfig` | `memory\models.py` | Configuration for the memory system. |
| `MemoryOrchestrator` | `memory\orchestrator.py` | Zero-config memory management. |
| `SemanticMemory` | `memory\semantic.py` | Long-term memory storage with vector search. |


### Functions

| Function | File | Description |
|----------|------|-------------|
| `fit_to_context()` | `context_rotator.py` | Simple function to fit chunks within a token bu... |
| `total_used()` | `context_rotator.py` |  |
| `available()` | `context_rotator.py` |  |
| `utilization()` | `context_rotator.py` |  |
| `to_dict()` | `context_rotator.py` |  |
| `pin_chunk()` | `context_rotator.py` | Pin a chunk so it's never evicted. |
| `clear_pinned()` | `context_rotator.py` | Remove all pinned chunks. |
| `fit_chunks()` | `context_rotator.py` | Fit chunks within available token budget. |
| `calculate_budget()` | `context_rotator.py` | Calculate token budget without modifying chunks. |
| `get_available_for_history()` | `context_rotator.py` | Calculate how many tokens are available for his... |
| `build_prompt()` | `kv_cache.py` | One-shot prompt building. |
| `estimate_cache_savings()` | `kv_cache.py` | Estimate compute savings from cache reuse. |
| `calculate_hit_rate()` | `kv_cache.py` | Calculate logical hit rate for current chunks. |
| `build()` | `kv_cache.py` | Build a cache-optimal prompt. |
| `mark_cached()` | `kv_cache.py` | Mark chunks as cached after successful LLM call. |
| `get_cache_hit_ratio()` | `kv_cache.py` | Estimate logical hit rate for given chunks. |
| `get_stats()` | `kv_cache.py` | Get logical cache statistics. |
| `invalidate()` | `kv_cache.py` | Invalidate logical cache (call after file edits). |
| `prepare()` | `manager.py` | Prepare a complete prompt for the LLM with USER... |
| `learn()` | `manager.py` | Learn from an LLM response. |
| `feedback()` | `manager.py` | Record explicit user feedback. |
| `forget()` | `manager.py` | Forget a conversation session. |
| `get_stats()` | `manager.py` | Get memory and feedback statistics. |
| `invalidate()` | `manager.py` | Invalidate all caches (use after document chang... |
| `extract_citations()` | `feedback\citation_extractor.py` | Extract chunk IDs cited in the LLM response. |
| `detect_text_overlap()` | `feedback\citation_extractor.py` | Detect which chunks were used based on text ove... |
| `client()` | `feedback\hard_loop.py` | Lazy-load Qdrant client. |
| `set_qdrant_client()` | `feedback\hard_loop.py` | Set Qdrant client. |
| `set_pg_session()` | `feedback\hard_loop.py` | Set Postgres session for edge persistence. |
| `confirm_feedback()` | `feedback\hard_loop.py` | User confirmed feedback - HARD SIGNAL. |
| `get_recommendations()` | `feedback\hard_loop.py` | Use Qdrant Recommend API with accumulated hard ... |
| `get_stats()` | `feedback\hard_loop.py` | Get hard feedback statistics. |
| `clear_signals()` | `feedback\hard_loop.py` | Clear all accumulated signals (use with caution). |
| `set_pg_session()` | `feedback\manager.py` | Set Postgres session for both loops. |
| `set_qdrant_client()` | `feedback\manager.py` | Set Qdrant client for hard loop. |
| `process_turn()` | `feedback\manager.py` | Process a turn for automatic learning (SOFT sig... |
| `boost_results()` | `feedback\manager.py` | Apply soft signal boosting to search results. |
| `confirm_feedback()` | `feedback\manager.py` | Record user-confirmed feedback (HARD signal). |
| `get_recommendations()` | `feedback\manager.py` | Get recommendations using Qdrant Recommend API ... |
| `get_stats()` | `feedback\manager.py` | Get combined statistics from both tiers. |
| `export_soft_edges()` | `feedback\manager.py` | Export soft signal edges for knowledge graph. |
| `confidence()` | `feedback\signal_tracker.py` | Calculate confidence in this signal using Wilso... |
| `is_positive()` | `feedback\signal_tracker.py` | Whether this signal indicates the chunk is useful. |
| `is_significant()` | `feedback\signal_tracker.py` | Whether this signal has enough data to be meani... |
| `set_pg_session()` | `feedback\soft_loop.py` | Set Postgres session for edge persistence. |
| `process_turn()` | `feedback\soft_loop.py` | Process a complete turn. AUTOMATIC - runs after... |
| `boost_results()` | `feedback\soft_loop.py` | Boost retrieval results based on learned associ... |
| `get_stats()` | `feedback\soft_loop.py` | Get soft feedback statistics. |
| `export_graph_edges()` | `feedback\soft_loop.py` | Export feedback as graph edges for the Knowledg... |
| `compress()` | `memory\compressor.py` | Compress multiple turns into a single memory. |
| `estimate_compression()` | `memory\compressor.py` | Estimate compression without actually running it. |
| `add_turn()` | `memory\episodic.py` | Add a conversation turn with rich metadata. |
| `get_recent()` | `memory\episodic.py` | Get recent turns, optionally filtered by import... |
| `search_relevant()` | `memory\episodic.py` | Search for turns semantically relevant to query. |
| `update_feedback()` | `memory\episodic.py` | Update feedback score for a turn. |
| `get_session_stats()` | `memory\episodic.py` | Get comprehensive stats for a session. |
| `clear_session()` | `memory\episodic.py` | Delete all turns for a session. |
| `get_turns_for_compression()` | `memory\episodic.py` | Get turns that should be compressed. |
| `delete_turns()` | `memory\episodic.py` | Delete specific turns by ID. |
| `wrapper()` | `memory\episodic.py` |  |
| `to_dict()` | `memory\models.py` | Convert to dictionary for serialization. |
| `from_dict()` | `memory\models.py` | Create from dictionary. |
| `compression_ratio()` | `memory\models.py` | Calculate compression efficiency. |
| `duration_minutes()` | `memory\models.py` | Session duration in minutes. |
| `remember()` | `memory\orchestrator.py` | Remember a conversation turn. |
| `recall()` | `memory\orchestrator.py` | Recall relevant conversation context. |
| `forget()` | `memory\orchestrator.py` | Clear session memory. |
| `feedback()` | `memory\orchestrator.py` | Record user feedback for a turn. |
| `build_context()` | `memory\orchestrator.py` | Build optimized context for LLM prompt. |
| `compress_session()` | `memory\orchestrator.py` | Compress old turns into semantic memory. |
| `get_stats()` | `memory\orchestrator.py` | Get comprehensive session statistics. |
| `get_working_memory()` | `memory\orchestrator.py` | Get current working memory (volatile). |
| `estimate_compression_savings()` | `memory\orchestrator.py` | Estimate potential savings from compression. |
| `store()` | `memory\semantic.py` | Store a compressed memory. |
| `search()` | `memory\semantic.py` | Search memories semantically. |
| `get_user_context()` | `memory\semantic.py` | Get relevant context for a user across all thei... |
| `cleanup_old()` | `memory\semantic.py` | Remove memories older than retention period. |
| `get_stats()` | `memory\semantic.py` | Get memory storage statistics. |


### File Structure

```
latent_memory/
├── __init__.py
├── feedback/
├── memory/
├── context_rotator.py
├── kv_cache.py
└── manager.py
```


---

## 🌾 Concept_Harvester {#concept_harvester}

**Concept Harvester - Semantic Extraction Layer**


| Property | Value |
|----------|-------|
| Classes | 12 |
| Functions | 32 |
| Factory Functions | 1 |
| Exports | 14 |
| Dependencies | None |


### Architecture

```
┌─────────────────────────────────────┐
```


### Exports (`__all__`)

`HarvesterConfig`, `InjectionConfig`, `ConceptHarvester`, `Harvester`, `ConceptResolver`, `ContextInjector`, `ConceptManager`, `create_concept_manager`, `ResolvedConcept`, `ConceptEdge`, `HarvestResult`, `HarvestStats`, `clean_concept_name`, `inject_context`


### Factory Functions

| Function | Description |
|----------|-------------|
| `create_concept_manager()` | Factory function for ConceptManager. |


### Classes

| Class | File | Description |
|-------|------|-------------|
| `ResolvedConcept` | `concept_resolver.py` | A resolved concept with its ID and resolution m... |
| `ConceptEdge` | `concept_resolver.py` | An edge connecting a chunk to a concept. |
| `ConceptResolver` | `concept_resolver.py` | Resolves terms to canonical concept IDs with 4-... |
| `HarvesterConfig` | `config.py` | Configuration for the Concept Harvester. |
| `InjectionConfig` | `context_injector.py` | Configuration for context injection. |
| `ContextInjector` | `context_injector.py` | Injects document structure context into text be... |
| `DatabaseGardener` | `graph_gardener.py` | Async maintenance agent for the Dual-Graph. |
| `ConceptHarvester` | `harvester.py` | Polymorphic concept extraction engine. |
| `K` | `harvester.py` |  |
| `HarvestStats` | `manager.py` | Statistics for a harvesting operation. |
| `HarvestResult` | `manager.py` | Result of a harvesting operation. |
| `ConceptManager` | `manager.py` | Unified manager for concept extraction and reso... |


### Functions

| Function | File | Description |
|----------|------|-------------|
| `calculate_edge_weight()` | `concept_resolver.py` | Calculate edge weight based on position and fre... |
| `set_total_docs()` | `concept_resolver.py` |  |
| `get_stats()` | `concept_resolver.py` |  |
| `clear_cache()` | `concept_resolver.py` |  |
| `resolve_single()` | `concept_resolver.py` | Resolve a single term through the 4-tier lookup. |
| `resolve()` | `concept_resolver.py` | Resolve terms and generate weighted edges. |
| `batch_resolve()` | `concept_resolver.py` | Batch resolve concepts from multiple chunks. |
| `get_label_count()` | `config.py` | Return the number of ontology labels. |
| `add_labels()` | `config.py` | Dynamically add labels to the ontology. |
| `inject_context()` | `context_injector.py` | Inject context into chunks (convenience wrapper). |
| `inject()` | `context_injector.py` | Inject context prefix into text. |
| `inject_chunk()` | `context_injector.py` | Inject context into a chunk dict. |
| `inject_batch()` | `context_injector.py` | Inject context into multiple chunks. |
| `is_noise_candidate()` | `context_injector.py` | Check if term is too generic without context. |
| `disambiguate_term()` | `context_injector.py` | Disambiguate generic term using context. |
| `main()` | `graph_gardener.py` | CLI entry point. |
| `run()` | `graph_gardener.py` | Run all maintenance tasks. |
| `compact_synonyms()` | `graph_gardener.py` | Merge concepts with high vector similarity. |
| `prune_islands()` | `graph_gardener.py` | Remove orphaned concepts (degree=1, old). |
| `demote_supernodes()` | `graph_gardener.py` | Reduce weights for overconnected concepts. |
| `clean_concept_name()` | `harvester.py` | Clean and validate a concept name. |
| `extract()` | `harvester.py` | Extract concepts from a single chunk. |
| `batch_extract()` | `harvester.py` | Batch extract concepts with concurrent processing. |
| `batch_extract_async()` | `harvester.py` | Async wrapper for batch_extract. |
| `add()` | `manager.py` |  |
| `pg_session()` | `manager.py` |  |
| `pg_session()` | `manager.py` |  |
| `tag_chunk()` | `manager.py` | Extract concepts from a chunk with Ghost Input ... |
| `harvest_chunk()` | `manager.py` | Extract and resolve concepts to weighted graph ... |
| `harvest_batch()` | `manager.py` | Process a batch of chunks for the dual-graph. |
| `garden()` | `manager.py` | Run graph maintenance (synonym merging, pruning... |


### File Structure

```
concept_harvester/
├── __init__.py
├── concept_resolver.py
├── config.py
├── context_injector.py
├── graph_gardener.py
├── harvester.py
└── manager.py
```


---

## 🤖 Agent {#agent}

**Agent - Goal-Driven Autonomous Development.**


| Property | Value |
|----------|-------|
| Classes | 12 |
| Functions | 7 |
| Factory Functions | 1 |
| Exports | 12 |
| Dependencies | None |


### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  AgentManager                (High Level - 3 methods)           │
│  execute / analyze / verify                                     │
├─────────────────────────────────────────────────────────────────┤
│  Trinity Personas            (Mid Level - Domain Logic)         │
│  Architect / QAEngineer / Developer                             │
├─────────────────────────────────────────────────────────────────┤
│  Core Data Structures        (Low Level - Types)                │
│  GoalSpec / Plan / Contract / Result                            │
├─────────────────────────────────────────────────────────────────┤
│  External Dependencies       (Reused Managers)                  │
│  RAGManager / LatentMemory / JudgmentManager / FilePatcher      │
└─────────────────────────────────────────────────────────────────┘
```


### Quick Start

```python
from agent import create_agent_manager

agent = create_agent_manager(
    llm_client=llm,
    rag_manager=rag,
    memory_manager=memory
)

result = await agent.execute("Add VIP discount with 20% off for premium users")
```


### Exports (`__all__`)

`AgentManager`, `create_agent_manager`, `AgentConfig`, `AgentResult`, `Architect`, `QAEngineer`, `Developer`, `GoalSpec`, `ImplementationPlan`, `TestContract`, `TestResult`, `AgentPhase`


### Factory Functions

| Function | Description |
|----------|-------------|
| `create_agent_manager()` | Factory function for AgentManager. |


### Classes

| Class | File | Description |
|-------|------|-------------|
| `Architect` | `architect.py` | The Brain of the Trinity. |
| `AgentPhase` | `core.py` | Phases of the agent execution cycle. |
| `GoalSpec` | `core.py` | A goal specification from the Product Owner. |
| `ImplementationPlan` | `core.py` | The Architect's plan for achieving a goal. |
| `TestContract` | `core.py` | The QA Engineer's test contract (verification c... |
| `TestResult` | `core.py` | Result of running tests. |
| `AgentResult` | `core.py` | Result of the autonomous development cycle. |
| `AgentConfig` | `core.py` | Configuration for the Agent. |
| `Developer` | `developer.py` | The Hands of the Trinity. |
| `ManagerConfig` | `manager.py` | Configuration for AgentManager. |
| `AgentManager` | `manager.py` | Agent Manager - The Orchestrator. |
| `QAEngineer` | `qa.py` | The Conscience of the Trinity. |


### Functions

| Function | File | Description |
|----------|------|-------------|
| `analyze()` | `architect.py` | Analyze a goal and create an implementation plan. |
| `implement()` | `developer.py` | Implement a feature with TDD loop. |
| `execute()` | `manager.py` | Execute complete development cycle for a goal. |
| `analyze()` | `manager.py` | Just analyze and plan - no code generation. |
| `verify()` | `manager.py` | Just verify - run tests on existing code. |
| `generate_contract()` | `qa.py` | Generate the test contract (verification criter... |


### File Structure

```
agent/
├── __init__.py
├── architect.py
├── core.py
├── developer.py
├── manager.py
└── qa.py
```


---

## 🌐 Services {#services}

**Core Services Layer**


| Property | Value |
|----------|-------|
| Classes | 46 |
| Functions | 138 |
| Factory Functions | 9 |
| Exports | 12 |
| Dependencies | None |


### Architecture

```
┌──────────────────────────────────────────────────────────────┐
```


### Exports (`__all__`)

`ChatService`, `GraphService`, `PatchService`, `IngestionService`, `create_ingestion_service`, `WatcherService`, `create_watcher_service`, `PRService`, `PRScanner`, `PRVerdictReport`, `create_pr_service`, `create_pr_scanner`


### Factory Functions

| Function | Description |
|----------|-------------|
| `create_ingestion_service()` | Factory function for IngestionService. |
| `create_watchdog_observer()` | Create a watchdog observer if available. |
| `create_watcher_service()` | Factory function for WatcherService. |
| `create_persona()` | Create a custom persona. |
| `create_pr_scanner()` | Factory function to create a PRScanner. |
| `create_pr_service()` | Factory function to create a PRService with GitHub integration. |
| `create_review()` | Create a PR review. |
| `create_github_provider()` | Factory function to create a GitHubProvider. |
| `create_review()` | Create a PR review. |


### Classes

| Class | File | Description |
|-------|------|-------------|
| `GraphService` | `graph_service.py` | Graph-related operations. |
| `IngestionResponse` | `ingestion_service.py` | Standardized response from ingestion operations. |
| `IngestionService` | `ingestion_service.py` | Ingestion service providing high-level ingestio... |
| `PatchFilter` | `patch_service.py` | Filter parameters for patch history. |
| `PatchService` | `patch_service.py` | Patch history and audit operations. |
| `WatcherConfig` | `watcher_service.py` | Configuration for the watcher service. |
| `WatcherStats` | `watcher_service.py` | Runtime statistics. |
| `FileEventHandler` | `watcher_service.py` | Handles file events with debouncing. |
| `PollingWatcher` | `watcher_service.py` | Fallback file watcher using polling. |
| `WatcherService` | `watcher_service.py` | Toggleable file watcher service. |
| `WatchdogBridge` | `watcher_service.py` |  |
| `MemoryService` | `chat\memory_service.py` | Service layer for long-term memory operations. |
| `SessionState` | `chat\models.py` | Current state of a chat session. |
| `ChatContext` | `chat\models.py` | Context for a single chat request. |
| `ChatConfig` | `chat\models.py` | Configuration for the Chat Service. |
| `MemoryConfig` | `chat\models.py` | Memory tier configuration. |
| `RAGConfig` | `chat\models.py` | RAG pipeline configuration. |
| `LLMConfig` | `chat\models.py` | LLM provider configuration for personas. |
| `FeedbackConfig` | `chat\models.py` | Feedback system configuration. |
| `PersonaDefinition` | `chat\models.py` | Complete persona definition. |
| `PersonaOverrides` | `chat\models.py` | Per-request persona overrides. |
| `Config` | `chat\models.py` |  |
| `BaseSessionStore` | `chat\persistence.py` | Abstract base for session storage. |
| `PostgresSessionStore` | `chat\persistence.py` | Postgres-backed session store. |
| `MemorySessionStore` | `chat\persistence.py` | In-memory store for dev/testing. |
| `PersonaService` | `chat\persona_service.py` | Service layer for persona operations. |
| `ResponseFormat` | `chat\response_formatter.py` | Supported response formats. |
| `ResponseFormatter` | `chat\response_formatter.py` | Multi-format response adapter. |
| `ChatService` | `chat\service.py` | Refactored Chat completion service. |
| `SessionService` | `chat\session_service.py` | Service layer for session operations. |
| `PRVerdict` | `pr_scanner\core.py` | Final verdict for a Pull Request. |
| `PRRiskLevel` | `pr_scanner\core.py` | Overall risk level for a PR. |
| `FileChangeType` | `pr_scanner\core.py` | Type of file change in a PR. |
| `DiffHunk` | `pr_scanner\core.py` | A single hunk within a file diff. |
| `FileChange` | `pr_scanner\core.py` | A changed file in a PR. |
| `FileReviewResult` | `pr_scanner\core.py` | Review result for a single file. |
| `PRVerdictReport` | `pr_scanner\core.py` | Complete PR review verdict. |
| `PRScannerConfig` | `pr_scanner\core.py` | Configuration for PR Scanner. |
| `DiffParser` | `pr_scanner\diff_parser.py` | Parses unified diff format into structured File... |
| `PRCommentFormatter` | `pr_scanner\formatter.py` | Formats PRVerdictReport into beautiful Markdown... |
| `PRScanner` | `pr_scanner\scanner.py` | Main PR review scanner. |
| `PRService` | `pr_scanner\service.py` | High-level PR scanning service. |
| `PRInfo` | `pr_scanner\providers\base.py` | Pull Request information from any git provider. |
| `CommentInfo` | `pr_scanner\providers\base.py` | Posted comment information. |
| `GitProvider` | `pr_scanner\providers\base.py` | Abstract base class for git hosting providers. |
| `GitHubProvider` | `pr_scanner\providers\github.py` | GitHub API integration using httpx. |


### Functions

| Function | File | Description |
|----------|------|-------------|
| `get_summary()` | `graph_service.py` | Get high-level graph overview. |
| `get_neighbors()` | `graph_service.py` | Get immediate neighbors for a node. |
| `get_document()` | `graph_service.py` | Reconstruct a document from its chunks. |
| `list_files()` | `graph_service.py` | List all available documents. |
| `to_dict()` | `ingestion_service.py` |  |
| `ingest()` | `ingestion_service.py` | Unified ingestion entry point. |
| `ingest_file()` | `ingestion_service.py` | Alias for ingest() with a single file. |
| `ingest_files()` | `ingestion_service.py` | Alias for ingest() with multiple files. |
| `ingest_directory()` | `ingestion_service.py` | Alias for ingest() with a directory. |
| `get_status()` | `ingestion_service.py` | Get current ingestion pipeline status. |
| `list_documents()` | `ingestion_service.py` | List indexed documents. |
| `process_pending()` | `ingestion_service.py` | Process pending jobs in the queue. |
| `retry_failed()` | `ingestion_service.py` | Retry all failed jobs. |
| `run_maintenance()` | `ingestion_service.py` | Run graph maintenance (gardener). |
| `cancel_document()` | `ingestion_service.py` | Cancel pending jobs for a specific document. |
| `compute_badges()` | `patch_service.py` | Compute display badges for a patch record. |
| `list_patches()` | `patch_service.py` | List patch attempts with filtering. |
| `get_patch()` | `patch_service.py` | Get full details for a specific patch. |
| `mark_committed()` | `patch_service.py` | Mark a patch as committed to git. |
| `uptime()` | `watcher_service.py` |  |
| `to_dict()` | `watcher_service.py` |  |
| `should_process()` | `watcher_service.py` | Check if file matches patterns and isn't ignored. |
| `on_modified()` | `watcher_service.py` | Queue a modified event. |
| `on_created()` | `watcher_service.py` | Queue a created event. |
| `on_deleted()` | `watcher_service.py` | Queue a deleted event. |
| `get_ready_events()` | `watcher_service.py` | Get events past the debounce window. |
| `start()` | `watcher_service.py` |  |
| `stop()` | `watcher_service.py` |  |
| `ingestion()` | `watcher_service.py` | Lazy-load ingestion service. |
| `is_running()` | `watcher_service.py` | Check if watcher is currently running. |
| `start()` | `watcher_service.py` | Start watching directories. |
| `stop()` | `watcher_service.py` | Stop watching directories. |
| `add_watch_path()` | `watcher_service.py` | Add a new path to watch (requires restart). |
| `remove_watch_path()` | `watcher_service.py` | Remove a path from watching (requires restart). |
| `get_status()` | `watcher_service.py` | Get current watcher status. |
| `on_modified()` | `watcher_service.py` |  |
| `on_created()` | `watcher_service.py` |  |
| `on_deleted()` | `watcher_service.py` |  |
| `get_memory_service()` | `chat\memory_service.py` | Get or create the singleton MemoryService insta... |
| `set_memory_service()` | `chat\memory_service.py` | Set the MemoryService instance (for testing/DI). |
| `list_memories()` | `chat\memory_service.py` | List long-term memories with filtering. |
| `get_memory()` | `chat\memory_service.py` | Get details of a specific memory. |
| `search_memories()` | `chat\memory_service.py` | Search long-term memories. |
| `delete_memory()` | `chat\memory_service.py` | Delete a specific memory (GDPR compliance). |
| `delete_user_memories()` | `chat\memory_service.py` | Delete all memories for a user (GDPR compliance). |
| `get_stats()` | `chat\memory_service.py` | Get memory statistics. |
| `is_new()` | `chat\models.py` |  |
| `get_latency_ms()` | `chat\models.py` |  |
| `to_llm_config()` | `chat\models.py` |  |
| `get_session_state()` | `chat\persistence.py` |  |
| `save_session_state()` | `chat\persistence.py` |  |
| `clear_session()` | `chat\persistence.py` |  |
| `get_session_state()` | `chat\persistence.py` | Retrieve session from database and convert to S... |
| `save_session_state()` | `chat\persistence.py` | Upsert SessionState into database. |
| `clear_session()` | `chat\persistence.py` | Delete session from database. |
| `get_session_state()` | `chat\persistence.py` |  |
| `save_session_state()` | `chat\persistence.py` |  |
| `clear_session()` | `chat\persistence.py` |  |
| `get_persona_service()` | `chat\persona_service.py` | Get or create the singleton PersonaService inst... |
| `set_persona_service()` | `chat\persona_service.py` | Set the PersonaService instance (for testing/DI). |
| `get_persona()` | `chat\persona_service.py` | Get a persona by ID. |
| `list_personas()` | `chat\persona_service.py` | List all available personas. |
| `list_persona_ids()` | `chat\persona_service.py` | Get list of all persona IDs. |
| `update_persona()` | `chat\persona_service.py` | Update a custom persona. |
| `delete_persona()` | `chat\persona_service.py` | Delete a custom persona. |
| `resolve_config()` | `chat\persona_service.py` | Resolve final configuration from persona + over... |
| `get_stats()` | `chat\persona_service.py` | Get persona statistics. |
| `format()` | `chat\response_formatter.py` | Format internal result to specified output format. |
| `format_error()` | `chat\response_formatter.py` | Format error response in the specified format. |
| `format_empty()` | `chat\response_formatter.py` | Format response for empty query. |
| `format_completion()` | `chat\response_formatter.py` | Legacy method - defaults to OpenAI format. |
| `get_chat_service()` | `chat\service.py` | Get or create the singleton ChatService instance. |
| `set_chat_service()` | `chat\service.py` | Set the ChatService instance (for testing/DI). |
| `model_name()` | `chat\service.py` | Get the full model identifier. |
| `complete()` | `chat\service.py` | Chat completion with full user control. |
| `record_feedback()` | `chat\service.py` | Record user feedback with full analytics tracking. |
| `get_session_stats()` | `chat\service.py` | Get session state summary. |
| `clear_session()` | `chat\service.py` | Clear session state from both store and memory. |
| `close()` | `chat\service.py` | Cleanup shared resources. |
| `get_session_service()` | `chat\session_service.py` | Get or create the singleton SessionService inst... |
| `set_session_service()` | `chat\session_service.py` | Set the SessionService instance (for testing/DI). |
| `list_sessions()` | `chat\session_service.py` | List sessions with pagination. |
| `get_session()` | `chat\session_service.py` | Get session stats. |
| `get_history()` | `chat\session_service.py` | Get paginated conversation history. |
| `export_session()` | `chat\session_service.py` | Export all session data (GDPR compliance). |
| `delete_session()` | `chat\session_service.py` | Delete session and all associated data. |
| `branch_session()` | `chat\session_service.py` | Create a branch/fork of a session. |
| `compress_session()` | `chat\session_service.py` | Manually trigger session compression. |
| `lines_added()` | `pr_scanner\core.py` |  |
| `lines_removed()` | `pr_scanner\core.py` |  |
| `to_dict()` | `pr_scanner\core.py` |  |
| `to_dict()` | `pr_scanner\core.py` |  |
| `to_dict()` | `pr_scanner\core.py` |  |
| `summary()` | `pr_scanner\core.py` | Human-readable one-line summary. |
| `parse_diff()` | `pr_scanner\diff_parser.py` | Quick function to parse a diff. |
| `filter_changes()` | `pr_scanner\diff_parser.py` | Filter file changes based on patterns and size ... |
| `parse()` | `pr_scanner\diff_parser.py` | Parse a complete diff into structured file chan... |
| `format_pr_comment()` | `pr_scanner\formatter.py` | Quick function to format a PR verdict report. |
| `format_inline_comment()` | `pr_scanner\formatter.py` | Format an inline comment for a specific line. |
| `format()` | `pr_scanner\formatter.py` | Format a PRVerdictReport as a Markdown comment. |
| `judgment_risk_to_pr_risk()` | `pr_scanner\scanner.py` | Map Judgment RiskLevel to PRRiskLevel. |
| `judgment()` | `pr_scanner\scanner.py` | Lazy-load judgment manager. |
| `scan_diff()` | `pr_scanner\scanner.py` | Scan a PR from its diff text. |
| `scan_files()` | `pr_scanner\scanner.py` | Scan a list of pre-parsed file changes. |
| `quick_scan_pr()` | `pr_scanner\service.py` | Quick function to scan a PR and get results. |
| `quick_scan_and_comment()` | `pr_scanner\service.py` | Quick function to scan a PR and post comment. |
| `scanner()` | `pr_scanner\service.py` | Lazy-load scanner. |
| `provider()` | `pr_scanner\service.py` | Get the git provider (raises if not configured). |
| `scan_pr()` | `pr_scanner\service.py` | Scan a PR and return the verdict report. |
| `scan_and_comment()` | `pr_scanner\service.py` | Scan a PR and post a comment with the results. |
| `get_pr_info()` | `pr_scanner\service.py` | Get PR information without scanning. |
| `to_dict()` | `pr_scanner\providers\base.py` |  |
| `name()` | `pr_scanner\providers\base.py` | Provider name (e.g., 'github', 'gitlab'). |
| `get_pr()` | `pr_scanner\providers\base.py` | Get PR information. |
| `get_pr_diff()` | `pr_scanner\providers\base.py` | Get the unified diff for a PR. |
| `post_comment()` | `pr_scanner\providers\base.py` | Post a comment on a PR. |
| `update_comment()` | `pr_scanner\providers\base.py` | Update an existing comment. |
| `add_labels()` | `pr_scanner\providers\base.py` | Add labels to a PR. |
| `post_inline_comment()` | `pr_scanner\providers\base.py` | Post an inline comment on a specific line. |
| `name()` | `pr_scanner\providers\github.py` |  |
| `get_pr()` | `pr_scanner\providers\github.py` | Get PR information from GitHub API. |
| `get_pr_diff()` | `pr_scanner\providers\github.py` | Get unified diff for a PR. |
| `get_pr_files()` | `pr_scanner\providers\github.py` | Get list of changed files with patches. |
| `post_comment()` | `pr_scanner\providers\github.py` | Post a comment on a PR (issue comment). |
| `update_comment()` | `pr_scanner\providers\github.py` | Update an existing comment. |
| `add_labels()` | `pr_scanner\providers\github.py` | Add labels to a PR. |
| `remove_labels()` | `pr_scanner\providers\github.py` | Remove labels from a PR. |
| `post_inline_comment()` | `pr_scanner\providers\github.py` | Post an inline comment on a specific line. |
| `close()` | `pr_scanner\providers\github.py` | Close the HTTP client. |


### File Structure

```
services/
├── __init__.py
├── chat/
├── pr_scanner/
├── graph_service.py
├── ingestion_service.py
├── patch_service.py
└── watcher_service.py
```


---

## 🌍 Api {#api}

**API Layer - HTTP Endpoints.**


| Property | Value |
|----------|-------|
| Classes | 35 |
| Functions | 62 |
| Factory Functions | 1 |
| Exports | 18 |
| Dependencies | None |


### Architecture

```
┌──────────────────────────────────────────────────────────────┐
```


### Exports (`__all__`)

`get_state`, `set_state`, `require_ready`, `get_session`, `get_chat_service`, `get_ingestion_service`, `get_pr_scanner`, `get_pr_service`, `health_router`, `chat_router`, `persona_router`, `sessions_router`, `memory_router`, `ingest_router`, `watcher_router`, `graph_router`, `patches_router`, `pr_scanner_router`


### Factory Functions

| Function | Description |
|----------|-------------|
| `create_persona()` | Create a custom persona. |


### Classes

| Class | File | Description |
|-------|------|-------------|
| `ChatMessage` | `models\chat.py` | A single chat message. |
| `ChatCompletionRequest` | `models\chat.py` | Chat completion request with multi-format respo... |
| `FeedbackRequest` | `models\chat.py` | User feedback on chunk quality. |
| `MemoryItem` | `models\memory.py` | A long-term memory summary. |
| `MemoryListResponse` | `models\memory.py` | List of memories. |
| `MemorySearchResult` | `models\memory.py` | Search result item. |
| `MemorySearchResponse` | `models\memory.py` | Search response. |
| `MemoryStatsResponse` | `models\memory.py` | Memory statistics. |
| `PersonaListItem` | `models\persona.py` | Persona summary for listing. |
| `PersonaListResponse` | `models\persona.py` | List of personas. |
| `CreatePersonaRequest` | `models\persona.py` | Request to create a custom persona. |
| `PRVerdictEnum` | `models\pr_scanner.py` | Verdict for a PR review. |
| `PRRiskLevelEnum` | `models\pr_scanner.py` | Risk level assessment. |
| `ScanDiffRequest` | `models\pr_scanner.py` | Request to scan a diff directly. |
| `ScanPRRequest` | `models\pr_scanner.py` | Request to scan a GitHub PR. |
| `ScanConfigRequest` | `models\pr_scanner.py` | Configuration overrides for a scan. |
| `WebhookPayload` | `models\pr_scanner.py` | GitHub/GitLab webhook payload (simplified). |
| `FileReviewResultResponse` | `models\pr_scanner.py` | Review result for a single file. |
| `PRVerdictResponse` | `models\pr_scanner.py` | Complete PR review verdict. |
| `PRVerdictDetailResponse` | `models\pr_scanner.py` | Detailed verdict including per-file results. |
| `ScanStatusResponse` | `models\pr_scanner.py` | Status of the PR scanner service. |
| `WebhookResponse` | `models\pr_scanner.py` | Response to webhook processing. |
| `Config` | `models\pr_scanner.py` |  |
| `SessionListItem` | `models\session.py` | Session summary for listing. |
| `SessionListResponse` | `models\session.py` | Paginated session list. |
| `HistoryTurn` | `models\session.py` | A conversation turn. |
| `HistoryResponse` | `models\session.py` | Paginated history. |
| `BranchRequest` | `models\session.py` | Branch request body. |
| `ExportResponse` | `models\session.py` | GDPR export response. |
| `IngestRequest` | `routes\ingest.py` | Unified ingestion request. |
| `MaintenanceRequest` | `routes\ingest.py` | Request to run graph maintenance. |
| `WatcherStartRequest` | `routes\watcher.py` | Request to start the watcher. |
| `WatcherPathRequest` | `routes\watcher.py` | Request to add/remove a watch path. |


### Functions

| Function | File | Description |
|----------|------|-------------|
| `get_state()` | `deps.py` | Get the global state dictionary. |
| `set_state()` | `deps.py` | Set a state value. Called during startup. |
| `require_ready()` | `deps.py` | Dependency that ensures the app is ready. |
| `get_session()` | `deps.py` | Dependency that provides a database session. |
| `get_chat_service()` | `deps.py` | Get the chat service instance. |
| `get_ingestion_service()` | `deps.py` | Get the ingestion service instance. |
| `get_pr_scanner()` | `deps.py` | Get the PR scanner instance (lazy-loaded). |
| `get_pr_service()` | `deps.py` | Get the PR service with GitHub integration (ret... |
| `chat_completions()` | `routes\chat.py` | OpenAI-compatible chat completion with RAG & La... |
| `submit_feedback()` | `routes\chat.py` | Submit user feedback on chunk quality. |
| `get_graph_summary()` | `routes\graph.py` | Get high-level graph overview. |
| `get_node_neighbors()` | `routes\graph.py` | Get immediate neighbors for a node. |
| `get_document()` | `routes\graph.py` | Reconstruct a document from its chunks. |
| `list_files()` | `routes\graph.py` | List all available documents. |
| `health_check()` | `routes\health.py` | System health check. |
| `liveness()` | `routes\health.py` | Kubernetes liveness probe - always returns 200 ... |
| `readiness()` | `routes\health.py` | Kubernetes readiness probe - returns 503 if not... |
| `get_status()` | `routes\ingest.py` | Get ingestion pipeline status. |
| `ingest()` | `routes\ingest.py` | Ingest files or directories. |
| `process_pending()` | `routes\ingest.py` | Process pending jobs in the queue. |
| `retry_failed()` | `routes\ingest.py` | Retry all failed jobs. |
| `run_maintenance()` | `routes\ingest.py` | Run graph maintenance (gardener). |
| `list_documents()` | `routes\ingest.py` | List all indexed documents. |
| `cancel_document()` | `routes\ingest.py` | Cancel pending jobs for a document. |
| `list_memories()` | `routes\memory.py` | List long-term memories with filtering. |
| `get_memory_stats()` | `routes\memory.py` | Get memory statistics. |
| `get_memory()` | `routes\memory.py` | Get details of a specific memory. |
| `delete_memory()` | `routes\memory.py` | Delete a specific memory (GDPR compliance). |
| `delete_user_memories()` | `routes\memory.py` | Delete all memories for a user (GDPR compliance). |
| `search_memories()` | `routes\memory.py` | Search long-term memories. |
| `list_patches()` | `routes\patches.py` | List patch attempts with filtering. |
| `get_patch_detail()` | `routes\patches.py` | Get full details for a specific patch. |
| `mark_patch_committed()` | `routes\patches.py` | Mark a patch as committed to git. |
| `list_personas()` | `routes\persona.py` | List all available personas. |
| `get_persona_stats()` | `routes\persona.py` | Get persona statistics. |
| `get_persona()` | `routes\persona.py` | Get full details of a specific persona. |
| `delete_persona()` | `routes\persona.py` | Delete a custom persona. |
| `get_pr_scanner()` | `routes\pr_scanner.py` | Get or create PR scanner from global state. |
| `get_pr_service()` | `routes\pr_scanner.py` | Get or create PR service with GitHub integration. |
| `verdict_to_response()` | `routes\pr_scanner.py` | Convert PRVerdictReport to API response dict. |
| `verdict_to_detail_response()` | `routes\pr_scanner.py` | Convert PRVerdictReport to detailed API response. |
| `get_scanner_status()` | `routes\pr_scanner.py` | Get PR scanner status and configuration. |
| `scan_diff()` | `routes\pr_scanner.py` | Scan a diff directly. |
| `scan_github_pr()` | `routes\pr_scanner.py` | Scan a GitHub PR. |
| `quick_scan_github_pr()` | `routes\pr_scanner.py` | Quick scan a GitHub PR (GET request). |
| `github_webhook()` | `routes\pr_scanner.py` | GitHub webhook endpoint for automatic PR scanning. |
| `format_verdict_comment()` | `routes\pr_scanner.py` | Format a verdict as a Markdown comment. |
| `run_scan()` | `routes\pr_scanner.py` |  |
| `list_sessions()` | `routes\sessions.py` | List all sessions with pagination. |
| `get_session_stats()` | `routes\sessions.py` | Get session statistics and state. |
| `get_session_history()` | `routes\sessions.py` | Get paginated conversation history with filtering. |
| `export_session()` | `routes\sessions.py` | Export all session data (GDPR compliance). |
| `delete_session()` | `routes\sessions.py` | Delete session and all associated data (GDPR co... |
| `branch_session()` | `routes\sessions.py` | Create a branch/fork of a session. |
| `compress_session()` | `routes\sessions.py` | Manually trigger memory compression. |
| `get_watcher_status()` | `routes\watcher.py` | Get watcher service status. |
| `start_watcher()` | `routes\watcher.py` | Start the file watcher. |
| `stop_watcher()` | `routes\watcher.py` | Stop the file watcher. |
| `add_watch_path()` | `routes\watcher.py` | Add a directory to watch. |
| `remove_watch_path()` | `routes\watcher.py` | Remove a directory from watching. |
| `get_watcher_stats()` | `routes\watcher.py` | Get watcher statistics. |


### File Structure

```
api/
├── __init__.py
├── models/
├── routes/
└── deps.py
```


---

## 📥 Ingestion {#ingestion}

**Ingestion Pipeline v3.1 - Parallel Processing with Full Idempotency.**


| Property | Value |
|----------|-------|
| Classes | 18 |
| Functions | 49 |
| Factory Functions | 1 |
| Exports | 19 |
| Dependencies | None |


### Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
```


### Quick Start

```python
from ingestion import create_ingestion_manager
from pathlib import Path

manager = create_ingestion_manager()

# Single file
result = await manager.ingest_file(Path("doc/readme.md"))

# Directory (always parallel)
result = await manager.ingest_directory(Path("doc/"))
print(f"Indexed {result.pipeline_stats.vectors_indexed} vectors")

# Check status
status = await manager.get_status()
print(f"Pending: {status.pending_chunk_jobs} chunk, {status.pending_graph_jobs} embed")

# Direct pipeline access
from ingestion import run_pipeline
stats = await run_pipeline()
```


### Exports (`__all__`)

`IngestionConfig`, `IngestionStage`, `JobPhase`, `INGESTION_CONFIG`, `pg_connection`, `pg_transaction`, `get_pipeline_stats`, `WorkerQueries`, `QueueQueries`, `DocumentScanner`, `ScanResult`, `scan_directory`, `IngestionPipeline`, `IngestionAnalytics`, `run_pipeline`, `IngestionManager`, `IngestionResult`, `PipelineStatus`, `create_ingestion_manager`


### Factory Functions

| Function | Description |
|----------|-------------|
| `create_ingestion_manager()` | Factory function for IngestionManager. |


### Classes

| Class | File | Description |
|-------|------|-------------|
| `StageStats` | `analytics.py` | Detailed stats for a specific stage. |
| `IngestionAnalytics` | `analytics.py` | Tracks progress and performance across all inge... |
| `IngestionStage` | `config.py` | Stages in the ingestion pipeline. |
| `JobPhase` | `config.py` | Which phase the job is in. |
| `IngestionConfig` | `config.py` | Central configuration for ingestion pipeline. |
| `QueueQueries` | `db_helpers.py` | Queue-related SQL queries (used by manager). |
| `WorkerQueries` | `db_helpers.py` | Worker-specific SQL queries (job claiming, chun... |
| `IngestionResult` | `manager.py` | Result of an ingestion operation. |
| `PipelineStatus` | `manager.py` | Current status of the ingestion pipeline. |
| `IngestionManager` | `manager.py` | Unified facade for document ingestion. |
| `IngestionPipeline` | `pipeline.py` | Thin orchestrator for the modular ingestion pip... |
| `ScanResult` | `scanner.py` | Result of a directory scan operation. |
| `DocumentScanner` | `scanner.py` | Scans directories and populates the processing ... |
| `ChunkingStage` | `stages\chunking.py` | Stage that chunks documents in parallel using C... |
| `ConceptStage` | `stages\concepts.py` | Stage that extracts semantic concepts from chunks. |
| `EmbeddingStage` | `stages\embedding.py` | Stage that generates dense and sparse vectors f... |
| `IndexingStage` | `stages\indexing.py` | Stage that generates vectors and syncs them to ... |
| `FileScanStage` | `stages\scan.py` | Stage that scans the filesystem and populates t... |


### Functions

| Function | File | Description |
|----------|------|-------------|
| `total_duration_ms()` | `analytics.py` |  |
| `record_step()` | `analytics.py` | Record the result of a single stage iteration. |
| `get_processed_count()` | `analytics.py` | Get the total number of items processed by a sp... |
| `get_summary()` | `analytics.py` | Get a comprehensive summary of the ingestion run. |
| `print_reflection()` | `analytics.py` | Print a human-readable reflection of the curren... |
| `postgres_url()` | `config.py` | SQLAlchemy async URL (with +asyncpg). |
| `postgres_dsn()` | `config.py` | Raw asyncpg DSN (without +asyncpg). |
| `qdrant_url()` | `config.py` | Qdrant server URL. |
| `qdrant_collection()` | `config.py` | Qdrant collection name. |
| `from_env()` | `config.py` | Create config from environment variables. |
| `pg_connection()` | `db_helpers.py` | Async context manager for Postgres connections. |
| `pg_transaction()` | `db_helpers.py` | Async context manager with automatic transaction. |
| `get_pipeline_stats()` | `db_helpers.py` | Get comprehensive pipeline statistics. |
| `retry_failed_jobs()` | `db_helpers.py` | Reset all failed jobs for retry. Returns count. |
| `cancel_document_jobs()` | `db_helpers.py` | Cancel pending jobs for a document. Returns count. |
| `to_dict()` | `manager.py` |  |
| `get_summary()` | `manager.py` | Convert to summary format for API compatibility. |
| `from_stats()` | `manager.py` |  |
| `to_dict()` | `manager.py` |  |
| `scanner()` | `manager.py` |  |
| `pipeline()` | `manager.py` |  |
| `ingest()` | `manager.py` | Unified ingestion entry point. |
| `ingest_file()` | `manager.py` | Alias for ingest() with a single file. |
| `ingest_files()` | `manager.py` | Alias for ingest() with multiple files. |
| `ingest_directory()` | `manager.py` | Alias for ingest() with a directory. |
| `process_pending()` | `manager.py` | Process any pending jobs in the queue. |
| `get_status()` | `manager.py` | Get current pipeline status. |
| `cancel_jobs()` | `manager.py` | Cancel pending jobs for a document. |
| `retry_failed()` | `manager.py` | Retry all failed jobs. |
| `list_documents()` | `manager.py` | List indexed documents with their stats. |
| `run_gardener()` | `manager.py` | Run Graph Gardener maintenance. |
| `main()` | `manager.py` |  |
| `run_pipeline()` | `pipeline.py` | Run the full ingestion pipeline. |
| `run()` | `pipeline.py` | Run the full pipeline: scan -> chunk -> concept... |
| `run_stage()` | `pipeline.py` | Run a single iteration of a stage. |
| `close()` | `pipeline.py` | Cleanup resources in all stages. |
| `main()` | `pipeline.py` |  |
| `compute_checksum()` | `scanner.py` | Compute SHA-256 checksum of a file. |
| `scan_directory()` | `scanner.py` | Convenience function to scan a directory. |
| `success()` | `scanner.py` |  |
| `scan()` | `scanner.py` | Scan directory and create processing jobs for n... |
| `get_pending_count()` | `scanner.py` | Get count of pending jobs in queue. |
| `run()` | `stages\chunking.py` |  |
| `run()` | `stages\concepts.py` | Run concept extraction on a batch of chunks. |
| `run()` | `stages\embedding.py` |  |
| `run()` | `stages\indexing.py` |  |
| `close()` | `stages\indexing.py` |  |
| `run()` | `stages\scan.py` | Run the scanner. Batch size is ignored for scan... |


### File Structure

```
ingestion/
├── __init__.py
├── stages/
├── analytics.py
├── config.py
├── db_helpers.py
├── manager.py
├── pipeline.py
└── scanner.py
```


---

## 💻 Cli {#cli}

**Command Line Interface Tools for the Knowledge Base System.**


| Property | Value |
|----------|-------|
| Classes | 34 |
| Functions | 82 |
| Factory Functions | 6 |
| Exports | 5 |
| Dependencies | None |


### Exports (`__all__`)

`run_chunker`, `run_harvester`, `run_ingestion`, `run_gardener`, `run_linter`


### Factory Functions

| Function | Description |
|----------|-------------|
| `create_watchdog_observer()` | Create a watchdog observer if available. |
| `create_gardener()` | Factory function for Gardener. |
| `create_compiler()` | Factory function for KnowledgeCompiler. |
| `create_readme_factory()` | Factory function for ReadmeFactory. |
| `create_feature_factory()` | Factory function for FeatureFactory. |
| `create_transition_generator()` | Factory function for TransitionGenerator. |


### Classes

| Class | File | Description |
|-------|------|-------------|
| `RouteInfo` | `compile_full_infra.py` |  |
| `ServiceInfo` | `compile_full_infra.py` |  |
| `ConfigKey` | `compile_full_infra.py` |  |
| `GardenerConfig` | `file_watcher.py` | Configuration for the Gardener daemon. |
| `GardenerStats` | `file_watcher.py` | Statistics for the Gardener session. |
| `GardenerEventHandler` | `file_watcher.py` | Handles file system events with debouncing. |
| `PollingWatcher` | `file_watcher.py` | Fallback file watcher using polling. |
| `EventProcessor` | `file_watcher.py` | Processes file events: chunk, embed, update graph. |
| `Gardener` | `file_watcher.py` | The Gardener Daemon - keeps your Knowledge Base... |
| `WatchdogHandler` | `file_watcher.py` |  |
| `Symbol` | `find_unused.py` | A defined symbol (function, class, method). |
| `AnalysisResult` | `find_unused.py` | Results of the dead code analysis. |
| `SymbolVisitor` | `find_unused.py` | AST visitor to collect definitions and references. |
| `ServiceConfig` | `ignite_swarm.py` | Configuration for a deployed service. |
| `IgnitionResult` | `ignite_swarm.py` | Result of the ignition process. |
| `SwarmIgnition` | `ignite_swarm.py` | Transforms Python services into Docker containers. |
| `CompilerConfig` | `knowledge_compiler.py` | Configuration for the Knowledge Compiler. |
| `CompiledDocument` | `knowledge_compiler.py` | Result of a compilation. |
| `KnowledgeCompiler` | `knowledge_compiler.py` | Compiles knowledge from RAG queries into struct... |
| `SymbolInfo` | `readme_factory.py` | Information about a code symbol (class, functio... |
| `ModuleIntelligence` | `readme_factory.py` | Extracted intelligence about a Python module. |
| `ReadmeResult` | `readme_factory.py` | Result of README generation. |
| `ModuleAnalyzer` | `readme_factory.py` | Analyzes a Python module to extract documentati... |
| `ReadmeBuilder` | `readme_factory.py` | Builds a standardized README from module intell... |
| `ReadmeFactory` | `readme_factory.py` | The main orchestrator for README generation. |
| `Dummy` | `run_ingestion.py` |  |
| `MemoryWorker` | `run_memory_worker.py` | Background worker for memory maintenance tasks. |
| `ScaffoldConfig` | `scaffold_feature.py` | Configuration for feature scaffolding. |
| `ScaffoldResult` | `scaffold_feature.py` | Result of a scaffold operation. |
| `CodeGlueGenerator` | `scaffold_feature.py` | Generates code-specific glue between pattern ch... |
| `PatternLibrary` | `scaffold_feature.py` | Registry of "Golden Patterns" - verified code c... |
| `FeatureFactory` | `scaffold_feature.py` | The "Frankenstein" for Features. |
| `TransitionStyle` | `transition_generator.py` | Configuration for transition generation. |
| `TransitionGenerator` | `transition_generator.py` | Generates narrative transitions between documen... |


### Functions

| Function | File | Description |
|----------|------|-------------|
| `extract_api_routes()` | `compile_full_infra.py` | Extract all API routes from api/routes/*.py |
| `extract_services()` | `compile_full_infra.py` | Extract service classes from services/*.py and ... |
| `extract_config()` | `compile_full_infra.py` | Extract config keys from config/*.py |
| `build_full_infrastructure_doc()` | `compile_full_infra.py` | Build the complete infrastructure document. |
| `compile_full_infrastructure()` | `compile_full_infra.py` | Extract ALL details from ALL modules and create... |
| `full_endpoint()` | `compile_full_infra.py` | Get full endpoint path with prefix. |
| `compile_readmes()` | `compile_readme_stitch.py` | Find all README.md files and stitch them into o... |
| `main()` | `file_watcher.py` | CLI entry point. |
| `uptime()` | `file_watcher.py` | Get human-readable uptime. |
| `should_process()` | `file_watcher.py` | Check if a file matches our patterns and isn't ... |
| `on_modified()` | `file_watcher.py` | Handle file modification. |
| `on_created()` | `file_watcher.py` | Handle file creation. |
| `on_deleted()` | `file_watcher.py` | Handle file deletion. |
| `get_ready_events()` | `file_watcher.py` | Get events that have passed the debounce window. |
| `start()` | `file_watcher.py` | Start the polling thread. |
| `stop()` | `file_watcher.py` | Stop the polling thread. |
| `process_modified()` | `file_watcher.py` | Process a modified file. |
| `process_created()` | `file_watcher.py` | Process a newly created file. |
| `process_deleted()` | `file_watcher.py` | Process a deleted file - prune from graph. |
| `run()` | `file_watcher.py` | Run the Gardener daemon. |
| `on_modified()` | `file_watcher.py` |  |
| `on_created()` | `file_watcher.py` |  |
| `on_deleted()` | `file_watcher.py` |  |
| `analyze_file()` | `find_unused.py` | Analyze a single Python file. |
| `analyze_directory()` | `find_unused.py` | Analyze all Python files in a directory. |
| `main()` | `find_unused.py` |  |
| `full_name()` | `find_unused.py` |  |
| `unused()` | `find_unused.py` | Symbols that are defined but never referenced. |
| `visit_Module()` | `find_unused.py` |  |
| `visit_ClassDef()` | `find_unused.py` |  |
| `visit_FunctionDef()` | `find_unused.py` |  |
| `visit_AsyncFunctionDef()` | `find_unused.py` |  |
| `visit_Name()` | `find_unused.py` |  |
| `visit_Attribute()` | `find_unused.py` |  |
| `visit_Call()` | `find_unused.py` |  |
| `main()` | `ignite_swarm.py` | CLI entry point. |
| `ignite()` | `ignite_swarm.py` | Main ignition sequence. |
| `start_swarm()` | `ignite_swarm.py` | Start the Docker swarm. |
| `main()` | `knowledge_compiler.py` | CLI entry point. |
| `compile_from_topic()` | `knowledge_compiler.py` | Compile a document from a semantic topic query. |
| `compile_from_concepts()` | `knowledge_compiler.py` | Compile a document from a list of concepts. |
| `compile_from_sources()` | `knowledge_compiler.py` | Compile a document from specific source files/d... |
| `sort_key()` | `knowledge_compiler.py` |  |
| `main()` | `readme_factory.py` | CLI entry point. |
| `analyze_module()` | `readme_factory.py` | Analyze a module directory and extract intellig... |
| `build_readme()` | `readme_factory.py` | Build a complete README from module intelligence. |
| `generate_readme()` | `readme_factory.py` | Generate a README for a module. |
| `generate_all()` | `readme_factory.py` | Generate READMEs for all modules. |
| `clear_queue()` | `reset_ingestion.py` |  |
| `main()` | `run_agent.py` | CLI entry point. |
| `display_result()` | `run_chunker.py` | Display detailed statistics for a single file r... |
| `main()` | `run_chunker.py` |  |
| `main()` | `run_gardener.py` |  |
| `display_result()` | `run_harvester.py` |  |
| `run_harvest()` | `run_harvester.py` | Run harvesting on one or more files. |
| `main()` | `run_harvester.py` |  |
| `process_queue_worker()` | `run_ingestion.py` | Worker that picks up Phase 1 results and perfor... |
| `main()` | `run_ingestion.py` |  |
| `encode()` | `run_ingestion.py` |  |
| `embed()` | `run_ingestion.py` |  |
| `dim()` | `run_ingestion.py` |  |
| `run_linter()` | `run_linter.py` |  |
| `main()` | `run_linter.py` |  |
| `run_worker()` | `run_memory_worker.py` | Run the memory worker. |
| `main()` | `run_memory_worker.py` |  |
| `run_once()` | `run_memory_worker.py` | Run all maintenance tasks once. |
| `get_stats_table()` | `run_memory_worker.py` | Generate stats table for display. |
| `main()` | `scaffold_feature.py` | CLI entry point. |
| `generate_imports()` | `scaffold_feature.py` | Generate import statements for the assembled file. |
| `generate_adapter()` | `scaffold_feature.py` | Generate adapter code between two chunks. |
| `find_patterns()` | `scaffold_feature.py` | Find Golden Patterns matching the feature request. |
| `scaffold()` | `scaffold_feature.py` | Scaffold a new feature from verified patterns. |
| `order_key()` | `scaffold_feature.py` |  |
| `generate_bridge()` | `transition_generator.py` | Generate a transition bridge between two conten... |
| `should_generate_transition()` | `transition_generator.py` | Determine if a transition should be generated b... |
| `get_stats()` | `transition_generator.py` | Get generation statistics. |


### File Structure

```
cli/
├── __init__.py
├── compile_full_infra.py
├── compile_readme_stitch.py
├── file_watcher.py
├── find_unused.py
├── ignite_swarm.py
├── knowledge_compiler.py
├── readme_factory.py
├── reset_ingestion.py
├── run_agent.py
├── run_chunker.py
├── run_gardener.py
├── run_harvester.py
├── run_ingestion.py
├── run_linter.py
├── run_memory_worker.py
├── scaffold_feature.py
└── transition_generator.py
```


---

# 🌍 API Endpoints {#api-endpoints}

| Method | Endpoint | Handler | File | Description |
|--------|----------|---------|------|-------------|
| `GET` | `/health` | `health_check` | health.py | System health check. |
| `GET` | `/health/live` | `liveness` | health.py | Kubernetes liveness probe - always returns 200 if server is  |
| `GET` | `/health/ready` | `readiness` | health.py | Kubernetes readiness probe - returns 503 if not ready. |
| `GET` | `/api/graph/document` | `get_document` | graph.py | Reconstruct a document from its chunks. |
| `GET` | `/api/graph/files` | `list_files` | graph.py | List all available documents. |
| `GET` | `/api/graph/neighbors/{node_id}` | `get_node_neighbors` | graph.py | Get immediate neighbors for a node. |
| `GET` | `/api/graph/summary` | `get_graph_summary` | graph.py | Get high-level graph overview. |
| `GET` | `/api/patches/{patch_id}` | `get_patch_detail` | patches.py | Get full details for a specific patch. |
| `POST` | `/api/patches/{patch_id}/commit` | `mark_patch_committed` | patches.py | Mark a patch as committed to git. |
| `POST` | `/v1/chat/completions` | `chat_completions` | chat.py |  |
| `POST` | `/v1/feedback` | `submit_feedback` | chat.py | Submit user feedback on chunk quality. |
| `DELETE` | `/v1/ingest/documents/{doc_id}` | `cancel_document` | ingest.py | Cancel pending jobs for a document. |
| `GET` | `/v1/ingest/documents` | `list_documents` | ingest.py | List all indexed documents. |
| `GET` | `/v1/ingest/status` | `get_status` | ingest.py | Get ingestion pipeline status. |
| `POST` | `/v1/ingest/maintenance` | `run_maintenance` | ingest.py | Run graph maintenance (gardener). |
| `POST` | `/v1/ingest/process` | `process_pending` | ingest.py | Process pending jobs in the queue. |
| `POST` | `/v1/ingest/retry` | `retry_failed` | ingest.py | Retry all failed jobs. |
| `DELETE` | `/v1/memories/user/{user_id}` | `delete_user_memories` | memory.py | Delete all memories for a user (GDPR compliance). |
| `DELETE` | `/v1/memories/{memory_id}` | `delete_memory` | memory.py | Delete a specific memory (GDPR compliance). |
| `GET` | `/v1/memories/stats` | `get_memory_stats` | memory.py | Get memory statistics. |
| `GET` | `/v1/memories/{memory_id}` | `get_memory` | memory.py | Get details of a specific memory. |
| `POST` | `/v1/memories/search` | `search_memories` | memory.py | Search long-term memories. |
| `DELETE` | `/v1/personas/{persona_id}` | `delete_persona` | persona.py | Delete a custom persona. |
| `GET` | `/v1/personas/stats` | `get_persona_stats` | persona.py | Get persona statistics. |
| `GET` | `/v1/personas/{persona_id}` | `get_persona` | persona.py | Get full details of a specific persona. |
| `GET` | `/v1/pr/scan/github/{owner}/{repo}/{pr_number}` | `quick_scan_github_pr` | pr_scanner.py |  |
| `GET` | `/v1/pr/status` | `get_scanner_status` | pr_scanner.py | Get PR scanner status and configuration. |
| `POST` | `/v1/pr/format` | `format_verdict_comment` | pr_scanner.py | Format a verdict as a Markdown comment. |
| `POST` | `/v1/pr/scan/diff` | `scan_diff` | pr_scanner.py |  |
| `POST` | `/v1/pr/scan/github` | `scan_github_pr` | pr_scanner.py | Scan a GitHub PR. |
| `POST` | `/v1/pr/webhook/github` | `github_webhook` | pr_scanner.py |  |
| `DELETE` | `/v1/sessions/{session_id}` | `delete_session` | sessions.py | Delete session and all associated data (GDPR compliance). |
| `GET` | `/v1/sessions/{session_id}` | `get_session_stats` | sessions.py | Get session statistics and state. |
| `GET` | `/v1/sessions/{session_id}/history` | `get_session_history` | sessions.py |  |
| `POST` | `/v1/sessions/{session_id}/branch` | `branch_session` | sessions.py | Create a branch/fork of a session. |
| `POST` | `/v1/sessions/{session_id}/compress` | `compress_session` | sessions.py | Manually trigger memory compression. |
| `POST` | `/v1/sessions/{session_id}/export` | `export_session` | sessions.py | Export all session data (GDPR compliance). |
| `GET` | `/v1/watcher/stats` | `get_watcher_stats` | watcher.py | Get watcher statistics. |
| `GET` | `/v1/watcher/status` | `get_watcher_status` | watcher.py | Get watcher service status. |
| `POST` | `/v1/watcher/paths/add` | `add_watch_path` | watcher.py | Add a directory to watch. |
| `POST` | `/v1/watcher/paths/remove` | `remove_watch_path` | watcher.py | Remove a directory from watching. |
| `POST` | `/v1/watcher/start` | `start_watcher` | watcher.py | Start the file watcher. |
| `POST` | `/v1/watcher/stop` | `stop_watcher` | watcher.py | Stop the file watcher. |

---

# 🌐 Services Reference {#services-reference}

### GraphService

**File:** `services/graph_service.py`

Graph Service - Core graph operations.


**Methods:**
- `get_summary()`
- `get_neighbors()`
- `get_document()`
- `list_files()`

### IngestionService

**File:** `services/ingestion_service.py`

Ingestion Service - High-level API for document ingestion.


**Methods:**
- `ingest()`
- `ingest_file()`
- `ingest_files()`
- `ingest_directory()`
- `get_status()`
- `list_documents()`
- `process_pending()`
- `retry_failed()`
- `run_maintenance()`
- `cancel_document()`

### PatchService

**File:** `services/patch_service.py`

Patch Service - VPC (Verified Patch Contract) operations.


**Methods:**
- `list_patches()`
- `get_patch()`
- `mark_committed()`

### WatcherService

**File:** `services/watcher_service.py`

Watcher Service - Auto-Syncing Service for the Knowledge Base.


**Methods:**
- `start()`
- `stop()`
- `add_watch_path()`
- `remove_watch_path()`

### ChatService

**File:** `services/chat/service.py`

Chat Service - Orchestrator.


**Methods:**
- `complete()`
- `record_feedback()`
- `get_session_stats()`
- `clear_session()`
- `close()`

### PRService

**File:** `services/pr_scanner/service.py`

PR Service - High-level integration for end-to-end PR scanning.


**Methods:**
- `scan_pr()`
- `scan_and_comment()`
- `get_pr_info()`
- `quick_scan_pr()`
- `quick_scan_and_comment()`


---

# ⚙️ Configuration Reference {#configuration-reference}

| Variable | Environment Key | Default | File |
|----------|-----------------|---------|------|
| `postgres_url` | `DATABASE_URL` | `postgresql+asyncpg://postgres:` | database.py |
| `qdrant_url` | `QDRANT_URL` | `http://localhost:6333` | database.py |
| `qdrant_api_key` | `QDRANT_API_KEY` | *required* | database.py |
| `qdrant_collection_chunks` | `QDRANT_COLLECTION` | `kb_chunks` | database.py |
| `qdrant_collection_concepts` | `QDRANT_CONCEPTS_COLLECTION` | `kb_concepts` | database.py |
| `model_name` | `EMBEDDING_MODEL` | `nomic-ai/nomic-embed-text-v1.5` | embeddings.py |
| `provider` | `EMBEDDING_PROVIDER` | `fastembed` | embeddings.py |
| `base_url` | `EMBEDDING_BASE_URL` | *required* | embeddings.py |
| `sparse_model` | `SPARSE_MODEL` | `Qdrant/bm25` | embeddings.py |
| `reranker_model` | `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-` | embeddings.py |
| `reranker_provider` | `RERANKER_PROVIDER` | `local` | embeddings.py |
| `reranker_base_url` | `RERANKER_BASE_URL` | *required* | embeddings.py |
| `DEFAULT_LOG_LEVEL` | `LOG_LEVEL` | `INFO` | logging.py |

---


---

*Auto-generated by [Full Infrastructure Compiler](cli/compile_full_infra.py) on 2026-01-10 23:55*

**Total Statistics:**
- Analyzed 14 modules
- Extracted 311 classes
- Extracted 817 functions
- Found 43 API routes
- Found 6 services
- Found 13 config keys
