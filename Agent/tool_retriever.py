#!/usr/bin/env python3
"""
Module for retrieving relevant tools from Qdrant.
Uses Hybrid Search (RRF) to get candidates, then
a Reranker to get the final relevant tools.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List
from collections import defaultdict

from qdrant_client import QdrantClient, models as qm

from .embedder import Embedder, SparseBM25
from . import config
from .tiny_reranker import TinyReranker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s tool_retriever :: %(message)s")
log = logging.getLogger("tool_retriever")

try:
    dense_embedder = Embedder(model_name=config.DENSE_EMBED_MODEL)
    sparse_embedder = SparseBM25(model_name=config.SPARSE_EMBED_MODEL)
    
    reranker = TinyReranker(model=config.RERANKER_MODEL_NAME)
    log.info(f"Reranker model loaded (kind: {reranker.kind}).")

    qdrant_client = QdrantClient(url=config.QDRANT_URL)
    log.info(f"Connected to Qdrant at {config.QDRANT_URL}")
except Exception as e:
    log.critical(f"Failed to initialize models or Qdrant client: {e}", exc_info=True)
    dense_embedder = None
    sparse_embedder = None
    reranker = None
    qdrant_client = None

def find_relevant_tools(query: str, top_k: int = config.DEFAULT_TOOL_TOP_K) -> List[Dict[str, Any]]:
    """
    Finds relevant tools from Qdrant using hybrid search + reranking.
    
    Returns a list of tool dictionaries (the payload from Qdrant).
    """
    if not all([qdrant_client, dense_embedder, sparse_embedder, reranker]):
        log.error("Tool retriever is not initialized. Cannot find tools.")
        return []

    log.info(f"Generating embeddings for query: '{query}'")
    dense_vec = dense_embedder.embed([query])[0]
    sparse_vec_data = sparse_embedder.embed([query])[0]
    
    sparse_vec = qm.SparseVector(
        indices=sparse_vec_data["indices"],
        values=sparse_vec_data["values"]
    )

    log.info(f"Searching collection '{config.QDRANT_COLLECTION_NAME}' for {config.HYBRID_CANDIDATE_COUNT} candidates...")
    
    try:
        d_query = qm.QueryRequest(
            query=dense_vec,
            using='dense', 
            limit=config.HYBRID_CANDIDATE_COUNT,
            with_payload=True,
            with_vector=False
        )
        
        query_requests = [d_query]

        if sparse_vec.indices and sparse_vec.values:
            s_query = qm.QueryRequest(
                query=sparse_vec,
                using='bm25', 
                limit=config.HYBRID_CANDIDATE_COUNT,
                with_payload=True,
                with_vector=False
            )
            query_requests.append(s_query)
        else:
            log.warning("Empty sparse vector generated for query, skipping sparse search.")
        
        results_batches = qdrant_client.query_batch_points(
            collection_name=config.QDRANT_COLLECTION_NAME,
            requests=query_requests
        )
        
        d_points = results_batches[0].points if len(results_batches) > 0 and results_batches[0] else []
        s_points = results_batches[1].points if len(results_batches) > 1 and results_batches[1] else []
        
        rrf_k = 60 
        rankings = defaultdict(float)
        all_hits_map = {} 

        for i, hit in enumerate(d_points, start=1):
            hit_id = getattr(hit, "id")
            if hit_id:
                rankings[hit_id] += (1.0 / (rrf_k + i))
                all_hits_map[hit_id] = hit

        for i, hit in enumerate(s_points or [], start=1):
            hit_id = getattr(hit, "id")
            if hit_id:
                rankings[hit_id] += (1.0 / (rrf_k + i))
                all_hits_map[hit_id] = hit
        
        if not rankings:
            log.warning("Hybrid search returned no results.")
            return []
            
        sorted_ids = sorted(rankings.keys(), key=lambda pid: rankings[pid], reverse=True)[:config.HYBRID_CANDIDATE_COUNT]
        
        candidate_items = [all_hits_map[pid] for pid in sorted_ids if pid in all_hits_map]
        
        log.info(f"Reranking {len(candidate_items)} candidates against query...")
        
        reranked_items = reranker.rerank(query, candidate_items, top_n=top_k)
        
        log.info(f"Reranking complete. Returning top {len(reranked_items)} tools.")

        tools = []
        for item in reranked_items:
            payload = getattr(item, "payload", {})
            if payload:
                try:
                    payload["schema"] = json.loads(payload.get("schema_json", "{}"))
                except json.JSONDecodeError:
                    payload["schema"] = {}
                tools.append(payload)
                log.info(f"  -> Reranked Tool: {payload['qualified_name']}")
        
        log.info(f"Retrieved and reranked {len(tools)} tools.")
        return tools

    except Exception as e:
        log.error(f"Error searching Qdrant: {e}", exc_info=True)
        return []

if __name__ == '__main__':
    log.info("--- Running Tool Retriever Standalone Test ---")
    
    test_query = "create a new entity in the knowledge graph about a user"
    
    if not all([qdrant_client, dense_embedder, sparse_embedder, reranker]):
        log.critical("Failed to initialize models. Exiting test.")
    else:
        try:
            tools = find_relevant_tools(test_query)
            if tools:
                log.info(f"--- Test Query Succeeded ---")
                log.info(f"Query: '{test_query}'")
                log.info(f"Found {len(tools)} tools:")
                for i, tool in enumerate(tools):
                    log.info(f"  {i+1}. {tool['qualified_name']}")
            else:
                log.warning("--- Test Query Failed: No tools returned ---")
        except Exception as e:
            log.error(f"--- Test Query Crashed ---")
            log.error(f"Error: {e}", exc_info=True)