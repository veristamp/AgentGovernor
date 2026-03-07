# rag/pipeline.py
"""
Hierarchical Search Pipeline - The "Zoom-In" Strategy.

Implements a multi-stage retrieval process:
1. Document Scout: Find relevant documents using dense search + grouping.
2. Section Zoom: Hybrid search (Dense+Sparse) within those documents.
3. Rerank & Refine: Apply RRF, MMR, and Reranking to select the best chunks.
4. Compress: Semantic compression to fit context window.
"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple, Set, Union

from collections import defaultdict
import numpy as np
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from rag.models import DenseEmbedder, SparseEmbedder, Reranker
from config import get_logger

logger = get_logger("SearchPipeline")

class HierarchicalSearchPipeline:
    """
    Advanced retrieval pipeline with Hierarchical Grouping + Hybrid Search.
    """
    
    def __init__(
        self,
        qdrant_client: AsyncQdrantClient,
        collection_name: str,
        dense_embedder: DenseEmbedder,
        sparse_embedder: SparseEmbedder,
        reranker: Reranker
    ):
        self.client = qdrant_client
        self.collection_name = collection_name
        self.dense = dense_embedder
        self.sparse = sparse_embedder
        self.reranker = reranker

    async def search(
        self,
        query: str,
        limit: int = 5,
        group_by: str = "source",  # Group by document (source file)
        rerank: bool = True,
        use_mmr: bool = True,
        mmr_lambda: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Execute the full Hierarchical Search Pipeline.
        
        Args:
            query: User question.
            limit: Final number of chunks to return.
            group_by: Metadata field to group by (e.g., 'source', 'doc_id').
            rerank: Whether to apply cross-encoder reranking.
            use_mmr: Whether to apply Maximal Marginal Relevance diversity.
            mmr_lambda: Diversity factor for MMR (lower = more diverse).
            
        Returns:
            List of unique, relevant chunks with scores.
        """
        if not query.strip():
            return []

        # 1. EMBED QUERY (Dense + Sparse)
        # Model methods are now async (handle threading/network internally)
        dense_vec_list, sparse_vec_list = await asyncio.gather(
            self.dense.encode([query]),
            self.sparse.encode([query])
        )
        
        dense_vec = dense_vec_list[0]
        sparse_vec_dict = sparse_vec_list[0]
        
        sparse_vec = qm.SparseVector(
            indices=sparse_vec_dict["indices"],
            values=sparse_vec_dict["values"]
        )

        # 2. DOCUMENT SCOUT (Grouping Search)
        # Find top N documents that contain relevant content
        groups = await self._document_scout(
            dense_vec, 
            group_by=group_by, 
            group_size=3,
            limit=5
        )
        
        if not groups:
            logger.info("No documents found in scout phase.")
            return []

        target_sources = [g.id for g in groups]
        logger.info(f"🔎 Scouting selected docs: {target_sources}")

        # 3. NATIVE HYBRID SEARCH (Offloaded to Qdrant)
        # Search deeply within documents using Qdrant's prefetch + RRF
        doc_filter = qm.Filter(
            must=[
                qm.FieldCondition(
                    key=group_by,
                    match=qm.MatchAny(any=target_sources)
                )
            ]
        )

        try:
            # Modern Qdrant Hybrid Search (one call, native fusion)
            prefetch = [
                qm.Prefetch(
                    query=dense_vec,
                    using="dense",
                    filter=doc_filter,
                    limit=limit * 3
                ),
                qm.Prefetch(
                    query=sparse_vec,
                    using="bm25",
                    filter=doc_filter,
                    limit=limit * 3
                )
            ]
            
            fused_result = await self.client.query_points(
                collection_name=self.collection_name,
                prefetch=prefetch,
                query=qm.FusionQuery(fusion=qm.Fusion.RRF),
                limit=limit * 2,
                with_payload=True,
                with_vectors=True # For MMR
            )
            fused_hits = fused_result.points

        except Exception as e:
            logger.warning(f"Native RRF failed, falling back to sequential batch: {e}")
            # Sequential fallback (older Qdrant or API mismatch)
            dense_hits, sparse_hits = await self._hybrid_search(
                dense_vec, sparse_vec, doc_filter, limit=limit * 3
            )
            fused_hits = self._rrf_fusion(dense_hits, sparse_hits, limit=limit * 2)

        # 4. DIVERSITY (MMR)
        if use_mmr and fused_hits:
            fused_hits = self._apply_mmr(dense_vec, fused_hits, top_k=limit * 2, lambda_mult=mmr_lambda)

        # 5. RERANKING (Cross-Encoder)
        if rerank and self.reranker:
            hits_as_dicts = [self._point_to_dict(h) for h in fused_hits]
            reranked = await self.reranker.rerank(
                query, 
                hits_as_dicts, 
                top_k=limit
            )
        else:
            reranked = [self._point_to_dict(h) for h in fused_hits[:limit]]

        return reranked

    async def _document_scout(
        self, 
        dense_vec: List[float], 
        group_by: str, 
        group_size: int, 
        limit: int
    ):
        """Perform grouped search to find relevant documents."""
        # Check if async
        if hasattr(self.client, 'async_search_groups'):
            result = await self.client.async_search_groups(
                collection_name=self.collection_name,
                query_vector=dense_vec,
                group_by=group_by,
                limit=limit,
                group_size=group_size,
                with_payload=False, # We just need the group IDs (doc paths)
                with_vectors=False
            )
            return result.groups
        else:
            # Sync client fallback (wrapped in future if needed, or just run)
            # Assuming QdrantClient is sync, but we are in async method.
            # If using AsyncQdrantClient, the method is search_groups (awaitable).
            # If using standard QdrantClient, it blocks.
            # We'll assume AsyncQdrantClient API pattern if 'await' is used in caller.
            # Correct method for AsyncQdrantClient is `query_points_groups` or `search_groups`
            try:
                # Try new API with named vector
                return (await self.client.query_points_groups(
                    collection_name=self.collection_name,
                    query=dense_vec,
                    using="dense",  # IMPORTANT: Specify which vector to use
                    group_by=group_by,
                    limit=limit,
                    group_size=group_size
                )).groups
            except AttributeError:
                # Fallback to older API or sync
                return self.client.search_groups(
                    collection_name=self.collection_name,
                    query_vector=qm.NamedVector(name="dense", vector=dense_vec),
                    group_by=group_by,
                    limit=limit,
                    group_size=group_size
                ).groups

    async def _hybrid_search(
        self, 
        dense_vec: List[float], 
        sparse_vec: qm.SparseVector, 
        q_filter: qm.Filter, 
        limit: int
    ):
        """Perform parallel Dense and Sparse search."""
        
        # Dense Request
        dense_req = qm.SearchRequest(
            vector=qm.NamedVector(name="dense", vector=dense_vec),
            filter=q_filter,
            limit=limit,
            with_payload=True,
            with_vector=True # Need vectors for MMR
        )
        
        # Sparse Request
        sparse_req = qm.SearchRequest(
            vector=qm.NamedSparseVector(name="sparse", vector=sparse_vec),
            filter=q_filter,
            limit=limit,
            with_payload=True,
            with_vector=False
        )
        
        # Execute Batch
        if hasattr(self.client, 'search_batch'):
            # Async client
            if hasattr(self.client, 'async_search_batch'):
                 results = await self.client.async_search_batch(
                    collection_name=self.collection_name,
                    requests=[dense_req, sparse_req]
                )
            else:
                # Sync client acting async? Or AsyncClient.search_batch is awaitable
                 results = await self.client.search_batch(
                    collection_name=self.collection_name,
                    requests=[dense_req, sparse_req]
                )
        else:
             # Just separate calls if batch not supported
             r1 = await self.client.search(
                 collection_name=self.collection_name,
                 query_vector=qm.NamedVector(name="dense", vector=dense_vec),
                 filter=q_filter,
                 limit=limit,
                 with_payload=True,
                 with_vector=True
             )
             r2 = await self.client.search(
                 collection_name=self.collection_name,
                 query_vector=qm.NamedSparseVector(name="sparse", vector=sparse_vec),
                 filter=q_filter,
                 limit=limit,
                 with_payload=True
             )
             results = [r1, r2]

        return results[0], results[1]

    def _rrf_fusion(self, dense_hits, sparse_hits, limit: int, k: int = 60):
        """Reciprocal Rank Fusion."""
        scores = defaultdict(float)
        point_map = {}
        
        # Map hits
        for i, hit in enumerate(dense_hits):
            point_map[hit.id] = hit
            scores[hit.id] += 1 / (k + i + 1)
            
        for i, hit in enumerate(sparse_hits):
            if hit.id not in point_map:
                point_map[hit.id] = hit
            scores[hit.id] += 1 / (k + i + 1)
            
        # Sort by fused score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        return [point_map[pid] for pid in sorted_ids[:limit]]

    def _apply_mmr(self, query_vec, hits, top_k, lambda_mult):
        """Maximal Marginal Relevance to diversify results."""
        if not hits:
            return []
            
        # Extract dense vectors from hits
        # Note: Sparse hits might not have dense vectors if we didn't fetch them
        # We prioritize hits that have dense vectors for MMR calculation
        valid_hits = [h for h in hits if h.vector and "dense" in h.vector]
        
        if not valid_hits:
            return hits[:top_k]
            
        doc_vectors = [h.vector["dense"] for h in valid_hits]
        
        # Simple MMR implementation
        selected = []
        candidates = list(range(len(valid_hits)))
        
        # Helper: Cosine Similarity
        def cosine_sim(a, b):
            return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
            
        # 1. Select best match first
        best_idx = max(candidates, key=lambda i: cosine_sim(query_vec, doc_vectors[i]))
        selected.append(best_idx)
        candidates.remove(best_idx)
        
        # 2. Iteratively select next best (Tradeoff: Relevance vs Diversity)
        while len(selected) < top_k and candidates:
            best_mmr = -float('inf')
            next_idx = -1
            
            for i in candidates:
                rel = cosine_sim(query_vec, doc_vectors[i])
                div = max([cosine_sim(doc_vectors[i], doc_vectors[j]) for j in selected])
                mmr = lambda_mult * rel - (1 - lambda_mult) * div
                
                if mmr > best_mmr:
                    best_mmr = mmr
                    next_idx = i
            
            if next_idx != -1:
                selected.append(next_idx)
                candidates.remove(next_idx)
                
        return [valid_hits[i] for i in selected]

    def _point_to_dict(self, point) -> Dict[str, Any]:
        """Convert Qdrant PointStruct to clean dict."""
        return {
            "id": point.id,
            "score": point.score,
            "text": point.payload.get("text", "") or point.payload.get("original_text", ""),
            "source": point.payload.get("source", ""),
            "section_path": point.payload.get("section_path", ""),
            "metadata": point.payload
        }
