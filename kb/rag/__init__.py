# rag/__init__.py
"""
RAG Package - Retrieval Augmented Generation.

Simple usage:
    from rag import create_rag_manager
    
    rag = create_rag_manager(pg_session=db)
    
    # Retrieve context for a query
    chunks = await rag.retrieve("How does the chunker work?")
    
    # Get formatted context for LLM
    context = await rag.get_context("How does the chunker work?")

Layer Structure:
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
└─────────────────────────────────────────────────────────────────┘
"""

# Core data structures
from .core import (
    SearchMode,
    FusionMethod,
    RAGConfig,
    SearchHit,
    RAGResult,
    get_token_count,
    format_chunk_for_prompt,
)

# Low level - Embedding models
from .models import (
    DenseEmbedder,
    SparseEmbedder,
    Reranker,
)

# Mid level - Components
from .compressor import SemanticCompressor
from .retriever import ContextRetriever, EnrichedChunk
from .pipeline import HierarchicalSearchPipeline

# High level - Manager
from .manager import RAGManager, create_rag_manager

__all__ = [
    # Core
    "SearchMode",
    "FusionMethod", 
    "RAGConfig",
    "SearchHit",
    "RAGResult",
    "get_token_count",
    "format_chunk_for_prompt",
    
    # Models
    "DenseEmbedder",
    "SparseEmbedder",
    "Reranker",
    
    # Components
    "SemanticCompressor",
    "ContextRetriever",
    "EnrichedChunk",
    "HierarchicalSearchPipeline",
    
    # Manager
    "RAGManager",
    "create_rag_manager",
]
