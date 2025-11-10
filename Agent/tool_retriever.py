#!/usr/bin/env python3
"""
Module for retrieving relevant tools from Qdrant.
Uses Hybrid Search (RRF) to get candidates, then
a Reranker to get the final relevant tools.

** MODIFIED to support Per-Query Reranking for true diversification **
"""
from __future__ import annotations

import json
import logging
import math
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

def find_relevant_tools(
    queries: List[str],  # Changed from query: str
    top_k: int = config.DEFAULT_TOOL_TOP_K
) -> List[Dict[str, Any]]:
    """
    Finds relevant tools from Qdrant using hybrid search + reranking.
    
    LOGIC (Per-Query Reranking):
    1. Loop through each sub-query.
    2. For each query, run hybrid search (dense + sparse).
    3. RRF-merge the results for *that query*.
    4. Rerank the candidates *against that query*.
    5. Take the top K_per_query tools.
    6. Collate, de-duplicate, and return the final balanced list.
    """
    if not all([qdrant_client, dense_embedder, sparse_embedder, reranker]):
        log.error("Tool retriever is not initialized. Cannot find tools.")
        return []
    
    if not queries:
        log.warning("find_relevant_tools received an empty list of queries.")
        return []

    # Use a dict to automatically de-duplicate tools
    final_tools_map: Dict[str, Dict[str, Any]] = {}
    
    k_per_query = math.ceil(top_k / len(queries)) + 2
    
    log.info(f"Starting diversified RAG for {len(queries)} sub-queries (target {k_per_query} tools/query)...")

    for query in queries:
        log.info(f"--- Processing sub-query: '{query}' ---")
        try:
            # --- 1. Embed THIS query ---
            dense_vec = dense_embedder.embed([query])[0]
            sparse_vec_data = sparse_embedder.embed([query])[0]
            
            sparse_vec = qm.SparseVector(
                indices=sparse_vec_data["indices"],
                values=sparse_vec_data["values"]
            )
            
            # --- 2. Build batch request for THIS query ---
            query_requests = []
            query_requests.append(qm.QueryRequest(
                query=dense_vec,
                using='dense', 
                limit=config.HYBRID_CANDIDATE_COUNT,
                with_payload=True,
                with_vector=False
            ))
            
            if sparse_vec.indices and sparse_vec.values:
                query_requests.append(qm.QueryRequest(
                    query=sparse_vec,
                    using='bm25', 
                    limit=config.HYBRID_CANDIDATE_COUNT,
                    with_payload=True,
                    with_vector=False
                ))

            # --- 3. Run search for THIS query ---
            results_batches = qdrant_client.query_batch_points(
                collection_name=config.QDRANT_COLLECTION_NAME,
                requests=query_requests
            )

            # --- 4. RRF merge for THIS query ---
            rrf_k = 60 
            rankings = defaultdict(float)
            all_hits_map = {} 

            for results_batch in results_batches:
                if not results_batch:
                    continue
                for i, hit in enumerate(results_batch.points, start=1):
                    hit_id = getattr(hit, "id")
                    if hit_id:
                        rankings[hit_id] += (1.0 / (rrf_k + i))
                        all_hits_map[hit_id] = hit
            
            if not rankings:
                log.warning(f"No results for sub-query: '{query}'")
                continue # Skip to next query
                
            # Get top N candidates from the merged RRF rankings
            sorted_ids = sorted(rankings.keys(), key=lambda pid: rankings[pid], reverse=True)[:config.HYBRID_CANDIDATE_COUNT]
            candidate_items = [all_hits_map[pid] for pid in sorted_ids if pid in all_hits_map]
            
            # --- 5. Rerank against THIS query ---
            log.info(f"Reranking {len(candidate_items)} candidates against ITS OWN query.")
            # THIS IS THE KEY FIX: rerank against `query`, not `queries[0]`
            reranked_items = reranker.rerank(query, candidate_items, top_n=k_per_query) 
            
            # --- 6. Add finalists to the map ---
            for item in reranked_items:
                payload = getattr(item, "payload", {})
                if not payload:
                    continue
                
                qname = payload.get('qualified_name')
                if not qname:
                    continue

                # Load schema
                try:
                    payload["schema"] = json.loads(payload.get("schema_json", "{}"))
                except json.JSONDecodeError:
                    payload["schema"] = {}
                
                # Add to map (de-duplicates)
                if qname not in final_tools_map:
                    final_tools_map[qname] = payload
                    log.info(f"  -> Added tool for this query: {qname}")
        
        except Exception as e:
            log.error(f"Error processing sub-query '{query}': {e}", exc_info=True)
            continue # Don't let one failed query stop the others

    # --- 7. Return the final list ---
    final_tool_list = list(final_tools_map.values())
    log.info(f"Total diverse tools retrieved: {len(final_tool_list)}")
    return final_tool_list

if __name__ == '__main__':
    log.info("--- Running Tool Retriever Standalone Test ---")
    
    # Test with multiple queries to simulate diversified RAG
    test_queries = [
        "create a new entity in the knowledge graph about a user",
        "list all files in the current directory",
        "run a shell command"
    ]
    
    if not all([qdrant_client, dense_embedder, sparse_embedder, reranker]):
        log.critical("Failed to initialize models. Exiting test.")
    else:
        try:
            # Pass the list of queries
            tools = find_relevant_tools(test_queries)
            
            if tools:
                log.info(f"--- Test Query Succeeded ---")
                log.info(f"Queries: {test_queries}")
                log.info(f"Found {len(tools)} tools:")
                for i, tool in enumerate(tools):
                    log.info(f"  {i+1}. {tool['qualified_name']}")
            else:
                log.warning("--- Test Query Failed: No tools returned ---")
        except Exception as e:
            log.error(f"--- Test Query Crashed ---")
            log.error(f"Error: {e}", exc_info=True)