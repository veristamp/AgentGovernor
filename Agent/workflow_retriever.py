#!/usr/bin/env python3
"""
Module for retrieving relevant *workflow examples* from Qdrant.
This is separate from tool_retriever.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List
from collections import defaultdict

from qdrant_client import QdrantClient, models as qm

from .embedder import Embedder, SparseBM25
from . import config
from .tiny_reranker import TinyReranker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s workflow_retriever :: %(message)s")
log = logging.getLogger("workflow_retriever")

try:
    # We can re-use the same models and client
    dense_embedder = Embedder(model_name=config.DENSE_EMBED_MODEL)
    sparse_embedder = SparseBM25(model_name=config.SPARSE_EMBED_MODEL)
    reranker = TinyReranker(model=config.RERANKER_MODEL_NAME)
    qdrant_client = QdrantClient(url=config.QDRANT_URL)
    log.info(f"Workflow retriever connected to Qdrant at {config.QDRANT_URL}")
except Exception as e:
    log.critical(f"Failed to initialize models or Qdrant client: {e}", exc_info=True)
    dense_embedder = None
    sparse_embedder = None
    reranker = None
    qdrant_client = None

def find_relevant_workflows(goal: str, top_k: int = 3) -> List[str]:
    """
    Finds relevant workflow examples from Qdrant.
    Returns a list of raw YAML strings.
    """
    if not all([qdrant_client, dense_embedder, sparse_embedder, reranker]):
        log.error("Workflow retriever is not initialized. Cannot find examples.")
        return []

    log.info(f"Searching for workflow examples for goal: '{goal}'")
    
    # 1. Embed the user's goal
    dense_vec = dense_embedder.embed([goal])[0]
    sparse_vec_data = sparse_embedder.embed([goal])[0]
    
    sparse_vec = qm.SparseVector(
        indices=sparse_vec_data["indices"],
        values=sparse_vec_data["values"]
    )

    # 2. Build Hybrid Search
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
    
    try:
        results_batches = qdrant_client.query_batch_points(
            collection_name=config.QDRANT_WORKFLOW_COLLECTION_NAME, # Use new collection
            requests=query_requests
        )

        # 3. RRF Merge
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
            log.warning("No workflow examples found.")
            return []
            
        sorted_ids = sorted(rankings.keys(), key=lambda pid: rankings[pid], reverse=True)[:config.HYBRID_CANDIDATE_COUNT]
        candidate_items = [all_hits_map[pid] for pid in sorted_ids if pid in all_hits_map]
        
        # 4. Rerank
        log.info(f"Reranking {len(candidate_items)} workflow candidates...")
        reranked_items = reranker.rerank(goal, candidate_items, top_n=top_k)
        
        # 5. Extract YAML content
        yaml_examples = []
        for item in reranked_items:
            payload = getattr(item, "payload", {})
            yaml_content = payload.get("yaml_content")
            if yaml_content:
                yaml_examples.append(yaml_content)
                log.info(f"  -> Found relevant example: {payload.get('source_file')}")
        
        return yaml_examples

    except Exception as e:
        # Check if the collection just doesn't exist
        if "not found" in str(e).lower():
            log.warning(f"Collection '{config.QDRANT_WORKFLOW_COLLECTION_NAME}' not found. No examples will be used.")
        else:
            log.error(f"Error searching for workflows: {e}", exc_info=True)
        return []

if __name__ == '__main__':
    log.info("--- Running Workflow Retriever Standalone Test ---")
    test_goal = "list all files in a directory and save the list to a new file"
    
    if not all([qdrant_client, dense_embedder, sparse_embedder, reranker]):
        log.critical("Failed to initialize models. Exiting test.")
    else:
        try:
            examples = find_relevant_workflows(test_goal, top_k=2)
            if examples:
                log.info(f"--- Test Query Succeeded ---")
                log.info(f"Goal: '{test_goal}'")
                log.info(f"Found {len(examples)} examples:")
                for i, yaml_str in enumerate(examples):
                    log.info(f"--- Example {i+1} ---\n{yaml_str}\n------------------")
            else:
                log.warning("--- Test Query Failed: No examples returned ---")
        except Exception as e:
            log.error(f"--- Test Query Crashed ---")
            log.error(f"Error: {e}", exc_info=True)