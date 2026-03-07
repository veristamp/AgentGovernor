# rag/manager.py
"""
Unified RAG Manager - Single Entry Point for Retrieval.

Combines all RAG components into a single cohesive interface:
- HierarchicalSearchPipeline: Multi-stage search (Document → Section → Chunk)
- ContextRetriever: Graph-powered context expansion
- DenseEmbedder, SparseEmbedder, Reranker: Model wrappers

This is the single entry point for the LLM Wrapper.

Usage:
    from rag import RAGManager
    
    manager = RAGManager(
        qdrant_url="http://localhost:6333",
        collection_name="kb_chunks",
        pg_session=db_session
    )
    
    # Single method to search and enrich
    enriched_chunks = await manager.retrieve(
        query="How does the chunker work?",
        limit=5
    )
    
    # Or get formatted context ready for LLM
    context = await manager.get_context(
        query="How does the chunker work?",
        limit=5
    )
"""

import logging
from typing import List, Dict, Any, Optional

from qdrant_client import AsyncQdrantClient

from .core import RAGConfig
from .pipeline import HierarchicalSearchPipeline
from .retriever import ContextRetriever, EnrichedChunk
from .models import DenseEmbedder, SparseEmbedder, Reranker
from .compressor import SemanticCompressor

# Import central config for defaults
from config import EMBEDDING_CONFIG, DATABASE_CONFIG, get_logger

logger = get_logger("RAGManager")

class RAGManager:
    """
    Unified facade for all RAG components.
    
    Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                       RAGManager                            │
    │                                                             │
    │  ┌─────────────────────────────────────────────────────────┐│
    │  │              HierarchicalSearchPipeline                 ││
    │  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐   ││
    │  │  │DenseEmbedder│ │SparseEmbedder│ │    Reranker     │   ││
    │  │  └─────────────┘ └─────────────┘ └─────────────────┘   ││
    │  └─────────────────────────────────────────────────────────┘│
    │                              │                              │
    │                              ▼                              │
    │  ┌─────────────────────────────────────────────────────────┐│
    │  │              ContextRetriever                            ││
    │  │  (Graph expansion: Parent, Next, Concepts)              ││
    │  └─────────────────────────────────────────────────────────┘│
    │                                                             │
    │  Methods:                                                   │
    │  • retrieve()     - Search + Enrich in one call             │
    │  • search()       - Raw vector search                       │
    │  • enrich()       - Graph context expansion                 │
    │  • get_context()  - Formatted LLM-ready context             │
    └─────────────────────────────────────────────────────────────┘
    """
    
    def __init__(
        self,
        qdrant_url: Optional[str] = None,
        collection_name: Optional[str] = None,
        pg_session: Optional[Any] = None,
        config: Optional[RAGConfig] = None,
        dense_model: str = None,
        sparse_model: str = None,
        reranker_model: str = None,
        embedding_provider: str = None,
        embedding_base_url: str = None,
        reranker_provider: str = None,
        reranker_base_url: str = None,
        lazy_load_models: bool = False,
        feedback_loop: Optional[Any] = None,
        qdrant_client: Optional[AsyncQdrantClient] = None
    ):
        """
        Initialize the unified RAG manager.
        """
        from config import DATABASE_CONFIG
        
        # Store config for defaults
        self.config = config or RAGConfig()
        
        self.qdrant_url = qdrant_url or DATABASE_CONFIG.qdrant_url
        self.collection_name = collection_name or DATABASE_CONFIG.qdrant_collection_chunks
        self._pg_session = pg_session
        
        # Use central config for defaults
        self._dense_model_name = dense_model or EMBEDDING_CONFIG.model_name
        self._sparse_model_name = sparse_model or EMBEDDING_CONFIG.sparse_model
        self._reranker_model_name = reranker_model or EMBEDDING_CONFIG.reranker_model
        
        # Provider settings
        self._embedding_provider = embedding_provider or EMBEDDING_CONFIG.provider
        self._embedding_base_url = embedding_base_url or EMBEDDING_CONFIG.base_url
        self._reranker_provider = reranker_provider or EMBEDDING_CONFIG.reranker_provider
        self._reranker_base_url = reranker_base_url or EMBEDDING_CONFIG.reranker_base_url
        
        # Feedback loop for soft signal boosting
        self._feedback_loop = feedback_loop
        
        # Lazy-loaded components
        self._qdrant: Optional[AsyncQdrantClient] = qdrant_client
        self._dense: Optional[DenseEmbedder] = None
        self._sparse: Optional[SparseEmbedder] = None
        self._reranker: Optional[Reranker] = None
        self._pipeline: Optional[HierarchicalSearchPipeline] = None
        self._retriever: Optional[ContextRetriever] = None
        self._compressor: Optional[SemanticCompressor] = None
        
        if not lazy_load_models:
            self._initialize_models()
    
    def _initialize_models(self):
        """Initialize all models (can be called lazily)."""
        if self._dense is None:
            # We log here because this is the first time heavy logic is triggered
            # Note: models themselves handle internal weight caching to be silent
            self._dense = DenseEmbedder(
                model_name=self._dense_model_name,
                provider=self._embedding_provider,
                base_url=self._embedding_base_url
            )
            self._sparse = SparseEmbedder(model_name=self._sparse_model_name)
            self._reranker = Reranker(
                model_name=self._reranker_model_name,
                provider=self._reranker_provider,
                base_url=self._reranker_base_url
            )
    
    @property
    def qdrant(self) -> AsyncQdrantClient:
        """Lazy-load Qdrant client."""
        if self._qdrant is None:
            self._qdrant = AsyncQdrantClient(url=self.qdrant_url)
        return self._qdrant
    
    @property
    def pipeline(self) -> HierarchicalSearchPipeline:
        """Lazy-load search pipeline."""
        if self._pipeline is None:
            self._initialize_models()
            self._pipeline = HierarchicalSearchPipeline(
                qdrant_client=self.qdrant,
                collection_name=self.collection_name,
                dense_embedder=self._dense,
                sparse_embedder=self._sparse,
                reranker=self._reranker
            )
        return self._pipeline
    
    @property
    def retriever(self) -> ContextRetriever:
        """Lazy-load context retriever."""
        if self._retriever is None:
            self._retriever = ContextRetriever(self._pg_session)
        return self._retriever
    
    @property
    def compressor(self) -> SemanticCompressor:
        """Lazy-load semantic compressor."""
        if self._compressor is None:
            self._initialize_models()
            self._compressor = SemanticCompressor(self._dense)
        return self._compressor
    
    def set_pg_session(self, session):
        """Set or update the Postgres session."""
        self._pg_session = session
        self._retriever = None  # Force re-creation with new session
    
    def set_feedback_loop(self, feedback_loop):
        """Set the feedback loop for soft signal boosting."""
        self._feedback_loop = feedback_loop
    
    async def retrieve(
        self,
        query: str,
        limit: Optional[int] = None,
        group_by: Optional[str] = None,
        rerank: Optional[bool] = None,
        use_mmr: Optional[bool] = None,
        mmr_lambda: Optional[float] = None,
        apply_feedback_boost: Optional[bool] = None,
        compress: bool = False
    ) -> List[EnrichedChunk]:
        """
        Main entry point: Search + Boost + Enrich in one call.
        
        Args:
            query: User's question
            limit: Maximum number of chunks to return
            group_by: Metadata field to group by (e.g., 'source')
            rerank: Whether to apply cross-encoder reranking
            use_mmr: Whether to apply MMR diversification
            mmr_lambda: MMR diversity parameter (0=diverse, 1=relevant)
            apply_feedback_boost: Whether to apply soft signal boosting
            compress: Whether to apply semantic compression to reduce noise
        Returns:
            List of EnrichedChunk objects with full graph context
        """
        # Use config defaults for None values
        limit = limit if limit is not None else self.config.limit
        group_by = group_by if group_by is not None else self.config.group_by
        rerank = rerank if rerank is not None else self.config.rerank
        use_mmr = use_mmr if use_mmr is not None else self.config.use_mmr
        mmr_lambda = mmr_lambda if mmr_lambda is not None else self.config.mmr_lambda
        apply_feedback_boost = apply_feedback_boost if apply_feedback_boost is not None else self.config.apply_feedback_boost
        
        # 1. Search
        search_results = await self.search(
            query=query,
            limit=limit,
            group_by=group_by,
            rerank=rerank,
            use_mmr=use_mmr,
            mmr_lambda=mmr_lambda
        )
        
        # 2. Apply soft signal boost (from citation-driven feedback)
        if apply_feedback_boost and self._feedback_loop:
            search_results = self._feedback_loop.boost_results(
                query=query,
                base_results=search_results,
                score_key="score"
            )
            logger.info("🎯 Applied soft signal boost to search results")
        
        # 3. Apply semantic compression (optional)
        if compress:
            search_results = await self.compressor.compress_chunks(query, search_results)
            logger.info(f"🗜️ Compressed {len(search_results)} chunks")
        
        # 4. Enrich with graph context
        enriched = await self.enrich(search_results)
        
        logger.info(f"📊 RAG: {len(enriched)} chunks retrieved and enriched for query")
        return enriched
    
    async def search(
        self,
        query: str,
        limit: int = 5,
        group_by: str = "source",
        rerank: bool = True,
        use_mmr: bool = True,
        mmr_lambda: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Perform hierarchical vector search.
        
        Returns raw search results (dicts with id, score, payload).
        """
        return await self.pipeline.search(
            query=query,
            limit=limit,
            group_by=group_by,
            rerank=rerank,
            use_mmr=use_mmr,
            mmr_lambda=mmr_lambda
        )
    
    async def enrich(
        self,
        search_results: List[Dict[str, Any]]
    ) -> List[EnrichedChunk]:
        """
        Enrich search results with graph context.
        
        Args:
            search_results: Raw search results from search()
            
        Returns:
            List of EnrichedChunk with parent, prev/next, and concepts
        """
        if not self._pg_session:
            # Without Postgres, return basic EnrichedChunks
            return [
                EnrichedChunk(
                    chunk_id=r.get("id", 0),
                    content=r.get("text", r.get("content", "")),
                    source=r.get("source", ""),
                    section_path=r.get("section_path", ""),
                    score=r.get("score", 0.0)
                )
                for r in search_results
            ]
        
        return await self.retriever.enrich_search_results(search_results)
    
    async def get_context(
        self,
        query: str,
        limit: int = 5,
        system_prompt: Optional[str] = None,
        include_flow: bool = False,
        include_concepts: bool = True
    ) -> str:
        """
        Get formatted context ready for LLM.
        
        Args:
            query: User's question
            limit: Maximum number of chunks
            system_prompt: Optional system prompt to prepend
            include_flow: Include prev/next chunk text
            include_concepts: Include related concepts
            
        Returns:
            Formatted string ready to be included in LLM prompt
        """
        enriched = await self.retrieve(query=query, limit=limit)
        
        parts = []
        if system_prompt:
            parts.append(system_prompt)
            parts.append("\n\n")
        
        parts.append("## Retrieved Context\n\n")
        for chunk in enriched:
            parts.append(chunk.to_prompt_format(
                include_flow=include_flow,
                include_concepts=include_concepts
            ))
            parts.append("\n\n")
        
        return "".join(parts)
    
    def to_cache_format(self, enriched_chunks: List[EnrichedChunk]) -> List[Dict[str, Any]]:
        """
        Convert EnrichedChunks to the format expected by LatentMemoryManager.
        
        Args:
            enriched_chunks: List of EnrichedChunk objects
            
        Returns:
            List of dicts with id, text, source, token_start, token_count
        """
        return [
            {
                "id": ec.chunk_id,
                "text": ec.content,
                "source": ec.source,
                "token_start": ec.char_start,  # Use char_start as proxy
                "token_count": ec.token_count if ec.token_count > 0 else len(ec.content) // 4
            }
            for ec in enriched_chunks
        ]
    
    async def close(self):
        """Cleanup resources."""
        if self._qdrant:
            await self._qdrant.close()

# =============================================================================
# CONVENIENCE FACTORY
# =============================================================================

def create_rag_manager(
    qdrant_url: Optional[str] = None,
    collection_name: Optional[str] = None,
    pg_session: Optional[Any] = None,
    config: Optional[RAGConfig] = None,
    lazy_load: bool = True,
    feedback_loop: Optional[Any] = None,
    # Embedding configuration
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    dense_model: Optional[str] = None,
    sparse_model: Optional[str] = None,
    # Reranker configuration
    reranker_model: Optional[str] = None,
    reranker_provider: Optional[str] = None,
    reranker_base_url: Optional[str] = None,
    qdrant_client: Optional[Any] = None
) -> RAGManager:
    """
    Factory function to create a RAGManager.
    
    Args:
        qdrant_url: Qdrant server URL
        collection_name: Collection to search
        pg_session: Postgres session for graph queries
        config: RAGConfig with search defaults
        lazy_load: Defer model loading until first use
        feedback_loop: FeedbackLoop for soft signal boosting
        provider: Embedding provider (fastembed, ollama, openai, infinity)
        base_url: Embedding API base URL
        dense_model: Dense embedding model name
        sparse_model: Sparse embedding model name
        reranker_model: Reranker model name
    """
    return RAGManager(
        qdrant_url=qdrant_url,
        collection_name=collection_name,
        pg_session=pg_session,
        config=config,
        lazy_load_models=lazy_load,
        feedback_loop=feedback_loop,
        embedding_provider=provider,
        embedding_base_url=base_url,
        dense_model=dense_model,
        sparse_model=sparse_model,
        reranker_model=reranker_model,
        reranker_provider=reranker_provider,
        reranker_base_url=reranker_base_url,
        qdrant_client=qdrant_client
    )
