#!/usr/bin/env python3
"""
Script to ingest tools from tools_schema.json into a Qdrant vector database
with hybrid embeddings (dense + sparse).

** MODIFIED TO USE SHARED Agent.embedder and Agent.config **
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Dict, List
from uuid import uuid5, NAMESPACE_URL
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

try:
    from Agent.embedder import Embedder, SparseBM25
    from Agent import config as agent_config
except ImportError:
    print("Error: Could not import from 'Agent' package.")
    print("Please run this script from the root of your 'mcp-inspector' project.")
    sys.exit(1)


def ensure_collection(
    client: QdrantClient,
    name: str,
    dense_dim: int,
    on_disk: bool = False,
    shard_number: int = 2,
    bulk_ingest: bool = False,
) -> None:
    def _create():
        print(f"[ensure_collection] Creating collection '{name}' (dim={dense_dim})")
        client.create_collection(
            collection_name=name,
            vectors_config={
                "dense": qm.VectorParams(size=dense_dim, distance=qm.Distance.COSINE, on_disk=on_disk),
            },
            sparse_vectors_config={
                "bm25": qm.SparseVectorParams(modifier=qm.Modifier.IDF),
            },
            shard_number=shard_number,
            hnsw_config=qm.HnswConfigDiff(m=0) if bulk_ingest else None,
            optimizers_config=qm.OptimizersConfigDiff(indexing_threshold=0) if bulk_ingest else None,
        )


    try:
        info = client.get_collection(collection_name=name)
    except Exception as e1:
        try:
            info = client.http.collections_api.get_collection(collection_name=name)
        except Exception as e2:
            if "not found" in str(e1).lower() or "not found" in str(e2).lower():
                _create()
                info = None
            else:
                print(f"Warning: Could not verify vector dim for '{name}': {e1} / {e2}")
                info = None

    if info:
        cfg = getattr(getattr(getattr(info, "config", None), "params", None), "vectors", None)
        dense_params = None
        if isinstance(cfg, dict):
            dense_params = cfg.get("dense")
        elif cfg is not None:
            params_map = getattr(cfg, "params_map", None)
            if isinstance(params_map, dict):
                dense_params = params_map.get("dense")
            else:
                dense_params = getattr(cfg, "default", None)

        existing_dim = getattr(dense_params, "size", None)
        if existing_dim is not None and existing_dim != dense_dim:
            raise ValueError(
                f"Vector dimension mismatch: collection '{name}' has {existing_dim}, "
                f"new data has {dense_dim}. Use a different collection or re-index."
            )

DEFAULT_QDRANT_URL = agent_config.QDRANT_URL
DEFAULT_COLLECTION_NAME = agent_config.QDRANT_COLLECTION_NAME
DEFAULT_TOOLS_FILE = "tools_schema.json"
DEFAULT_EMBED_MODEL = agent_config.DENSE_EMBED_MODEL
DEFAULT_SPARSE_MODEL = agent_config.SPARSE_EMBED_MODEL # Added
UPSERT_BATCH_SIZE = 64 # This is now unused by upsert, but harmless

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s ingest_tools :: %(message)s"
)
log = logging.getLogger("ingest_tools")


def load_tools(tools_file: str) -> List[Dict[str, Any]]:
    """Loads the tool schema list from the JSON file."""
    try:
        with open(tools_file, "r", encoding="utf-8") as f:
            tools = json.load(f)
        if not isinstance(tools, list):
            log.error("Error: %s should contain a JSON list of tools.", tools_file)
            return []
        log.info("Loaded %d tools from %s", len(tools), tools_file)
        return tools
    except FileNotFoundError:
        log.error("Error: Tools file not found at %s", tools_file)
        return []
    except json.JSONDecodeError:
        log.error("Error: Could not decode JSON from %s", tools_file)
        return []

def prepare_tool_documents(tools: List[Dict[str, Any]]) -> List[str]:
    """
    Creates a single text document for each tool, which will be used
    to generate the embeddings.
    """
    documents = []
    for tool in tools:
        qname = tool.get("qualified_name", "unknown.tool")
        desc = tool.get("description", "No description.")
        
        schema = tool.get("schema", {})
        props = schema.get("properties", {})
        arg_list = []
        if props:
            for arg_name, arg_details in props.items():
                arg_type = arg_details.get('type', 'any')
                arg_desc = arg_details.get('description', '')
                arg_list.append(f"- {arg_name} ({arg_type}): {arg_desc}")
        
        arg_text = "\n".join(arg_list)
        if not arg_text:
            arg_text = "No arguments."

        doc = (
            f"Tool: {qname}\n"
            f"Description: {desc}\n"
            f"Arguments:\n{arg_text}"
        )
        documents.append(doc)
    
    return documents

def prepare_qdrant_points(
    tools: List[Dict[str, Any]],
    documents: List[str],
    dense_vecs: List[List[float]],
    sparse_vecs: List[Dict]
) -> List[qm.PointStruct]:
    """
    Combines tools, documents, and vectors into Qdrant PointStruct objects.
    """
    points = []
    for idx, tool in enumerate(tools):
        dense_vec = dense_vecs[idx]
        sparse_vec_data = sparse_vecs[idx]
        
        bm25 = qm.SparseVector(
            indices=list(map(int, sparse_vec_data["indices"])),
            values=list(map(float, sparse_vec_data["values"]))
        )
        
        qname = tool["qualified_name"]
        pid = str(uuid5(NAMESPACE_URL, qname))
        
        payload = {
            "qualified_name": qname,
            "server_prefix": tool.get("server_prefix"),
            "name": tool.get("name"),
            "description": tool.get("description"),
            "schema_json": json.dumps(tool.get("schema", {})),
            "embed_text": documents[idx]
        }
        
        points.append(qm.PointStruct(
            id=pid,
            vector={"dense": dense_vec, "bm25": bm25},
            payload=payload
        ))
    
    return points

def main():
    """Main script entrypoint."""
    parser = argparse.ArgumentParser(
        description="Ingest MCP tools into Qdrant for RAG.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--qdrant-url",
        type=str,
        default=DEFAULT_QDRANT_URL,
        help="URL for the Qdrant instance."
    )
    parser.add_argument(
        "--collection-name",
        type=str,
        default=DEFAULT_COLLECTION_NAME,
        help="Name of the Qdrant collection to use."
    )
    parser.add_argument(
        "--tools-file",
        type=str,
        default=DEFAULT_TOOLS_FILE,
        help="Path to the tools_schema.json file."
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default=DEFAULT_EMBED_MODEL,
        help="Name of the dense embedding model to use (e.g., 'BAAI/bge-base-en-v1.5')."
    )
    parser.add_argument(
        "--sparse-model-name",
        type=str,
        default=DEFAULT_SPARSE_MODEL,
        help="Name of the sparse embedding model to use (e.g., 'Qdrant/bm25')."
    )
    args = parser.parse_args()

    # 1. Load Tools
    tools = load_tools(args.tools_file)
    if not tools:
        sys.exit(1)

    # 2. Initialize Embedders
    log.info("Initializing embedders...")
    try:
        dense_embedder = Embedder(model_name=args.model_name, use_gpu=True)
        sparse_embedder = SparseBM25(model_name=args.sparse_model_name)
        log.info(
            "Dense embedder '%s' ready (dim=%d). Sparse embedder '%s' ready.",
            args.model_name, dense_embedder.dim, args.sparse_model_name
        )
    except Exception as e:
        log.error("Error initializing embedders: %s", e)
        sys.exit(1)

    # 3. Initialize Qdrant Client and Collection
    log.info("Connecting to Qdrant at %s", args.qdrant_url)
    try:
        client = QdrantClient(url=args.qdrant_url)
        client.get_collections() 
    except Exception as e:
        log.error(
            "Error: Could not connect to Qdrant at %s. Is it running?",
            args.qdrant_url
        )
        log.error(e)
        sys.exit(1)

    log.info("Ensuring collection '%s' exists...", args.collection_name)
    try:
        ensure_collection(
            client,
            name=args.collection_name,
            dense_dim=dense_embedder.dim,
            bulk_ingest=True
        )
    except Exception as e:
        log.error("Error ensuring collection: %s", e)
        sys.exit(1)

    # 4. Prepare and Embed Documents
    log.info("Preparing text documents for embedding...")
    documents = prepare_tool_documents(tools)
    
    log.info("Generating dense embeddings for %d tools...", len(documents))
    dense_vectors = dense_embedder.embed(documents)
    
    log.info("Generating sparse embeddings for %d tools...", len(documents))
    sparse_vectors = sparse_embedder.embed(documents)
    
    # 5. Prepare Qdrant Points
    log.info("Preparing Qdrant points...")
    points = prepare_qdrant_points(tools, documents, dense_vectors, sparse_vectors)

    # 6. Upsert to Qdrant
    log.info("Upserting %d points to collection '%s'...",
             len(points), args.collection_name
    )
    try:
        # --- THIS IS THE FIX ---
        # Removed 'batch_size' and 'parallel' as they are not
        # valid arguments for the 'upsert' method.
        client.upsert(
            collection_name=args.collection_name,
            points=points,
            wait=True
        )
        # --- END FIX ---
        log.info("Successfully upserted all tools.")
    except Exception as e:
        log.error("Error during Qdrant upsert: %s", e)
        sys.exit(1)

    log.info("Ingestion complete.")

if __name__ == "__main__":
    main()