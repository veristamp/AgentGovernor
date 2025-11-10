#!/usr/bin/env python3
"""
Script to ingest tools (from tools_schema.json) AND
workflows (from a directory) into separate Qdrant vector databases.
"""

from __future__ import annotations

import json
import logging
import sys
import yaml
from pathlib import Path
from typing import Any, Dict, List, Tuple
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
    """Creates a Qdrant collection if it doesn't exist."""
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
            # Fallback for different client versions
            info = client.http.collections_api.get_collection(collection_name=name)
        except Exception as e2:
            if "not found" in str(e1).lower() or "not found" in str(e2).lower():
                _create()
                info = None
            else:
                print(f"Warning: Could not verify vector dim for '{name}': {e1} / {e2}")
                info = None

    # Check dimension mismatch if collection already exists
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

# --- Config (Hardcoded) ---
QDRANT_URL = agent_config.QDRANT_URL
TOOLS_COLLECTION_NAME = agent_config.QDRANT_COLLECTION_NAME  # "mcp_tools"
WORKFLOW_COLLECTION_NAME = "mcp_workflows"  # New collection for workflows
TOOLS_FILE = "tools_schema.json"
WORKFLOW_DIR = "workflows"
EMBED_MODEL = agent_config.DENSE_EMBED_MODEL
SPARSE_MODEL = agent_config.SPARSE_EMBED_MODEL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s ingest :: %(message)s"
)
log = logging.getLogger("ingest")

# --- Data Loading (New Unified Structure) ---

# This tuple defines the unified data structure:
# (id_string, embed_text, payload_dictionary)
ItemData = Tuple[str, str, Dict[str, Any]]

def load_tools_data(tools_file: str) -> List[ItemData]:
    """Loads tools from the JSON file."""
    items: List[ItemData] = []
    try:
        with open(tools_file, "r", encoding="utf-8") as f:
            tools = json.load(f)
        if not isinstance(tools, list):
            log.error(f"Error: {tools_file} should contain a JSON list of tools.")
            return []
    except FileNotFoundError:
        log.error(f"Error: Tools file not found at {tools_file}")
        return []
    except json.JSONDecodeError:
        log.error(f"Error: Could not decode JSON from {tools_file}")
        return []

    for tool in tools:
        qname = tool.get("qualified_name")
        if not qname:
            continue

        pid = str(uuid5(NAMESPACE_URL, qname))
        
        desc = tool.get("description", "No description.")
        schema = tool.get("schema", {})
        props = schema.get("properties", {})
        arg_list = [f"{name} ({details.get('type', 'any')})" for name, details in props.items()]
        arg_text = f"Arguments: {', '.join(arg_list)}" if arg_list else "No arguments."
        doc_text = f"Tool: {qname}\nDescription: {desc}\n{arg_text}"
        
        payload = {
            "type": "tool",
            "qualified_name": qname,
            "server_prefix": tool.get("server_prefix"),
            "name": tool.get("name"),
            "description": desc,
            "schema_json": json.dumps(schema),
            "embed_text": doc_text
        }
        items.append((pid, doc_text, payload))
        
    log.info(f"Loaded {len(items)} tools from {tools_file}")
    return items

def load_workflows_data(workflow_dir: str) -> List[ItemData]:
    """Loads workflows from the YAML directory."""
    items: List[ItemData] = []
    workflow_path = Path(workflow_dir)
    if not workflow_path.is_dir():
        log.warning(f"Workflow directory not found at {workflow_dir}. Skipping.")
        return []
        
    for yaml_file in workflow_path.glob("*.yaml"):
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                content = f.read()
                data = yaml.safe_load(content)
                if not isinstance(data, dict):
                    continue
            
            pid = str(uuid5(NAMESPACE_URL, str(yaml_file.resolve())))
            doc_text = data.get("description")
            
            if not doc_text:
                log.warning(f"Skipping {yaml_file.name}: missing top-level 'description' key.")
                continue
            
            payload = {
                "type": "workflow",
                "description": doc_text,
                "yaml_content": content,
                "source_file": yaml_file.name,
                "embed_text": doc_text
            }
            items.append((pid, doc_text, payload))
            
        except yaml.YAMLError as e:
            log.error(f"Error parsing YAML from {yaml_file.name}: {e}")
        except Exception as e:
            log.error(f"Error loading {yaml_file.name}: {e}")
            
    log.info(f"Loaded {len(items)} workflows from {workflow_dir}")
    return items

def prepare_and_embed(
    items: List[ItemData],
    dense_embedder: Embedder,
    sparse_embedder: SparseBM25,
) -> List[qm.PointStruct]:
    """Helper function to run embedding and create Qdrant points."""
    
    documents = [item[1] for item in items]
    
    log.info(f"Generating dense embeddings for {len(documents)} items...")
    dense_vectors = dense_embedder.embed(documents)
    
    log.info(f"Generating sparse embeddings for {len(documents)} items...")
    sparse_vectors = sparse_embedder.embed(documents)
    
    log.info("Preparing Qdrant points...")
    points = []
    for idx, item_data in enumerate(items):
        pid, doc_text, payload = item_data
        
        dense_vec = dense_vectors[idx]
        sparse_vec_data = sparse_vectors[idx]
        
        bm25 = qm.SparseVector(
            indices=list(map(int, sparse_vec_data["indices"])),
            values=list(map(float, sparse_vec_data["values"]))
        )
        
        points.append(qm.PointStruct(
            id=pid,
            vector={"dense": dense_vec, "bm25": bm25},
            payload=payload
        ))
    return points

# --- Main ---

def main():
    """Main script entrypoint. All config is hardcoded above."""
    
    # --- 1. Init ---
    log.info("Initializing embedders...")
    try:
        dense_embedder = Embedder(model_name=EMBED_MODEL, use_gpu=True)
        sparse_embedder = SparseBM25(model_name=SPARSE_MODEL)
    except Exception as e:
        log.error(f"Error initializing embedders: {e}")
        sys.exit(1)

    log.info(f"Connecting to Qdrant at {QDRANT_URL}")
    try:
        client = QdrantClient(url=QDRANT_URL)
        client.get_collections() 
    except Exception as e:
        log.error(f"Error: Could not connect to Qdrant at {QDRANT_URL}.")
        sys.exit(1)

    # --- 2. Process Tools ---
    tool_items = load_tools_data(TOOLS_FILE)
    if tool_items:
        log.info(f"--- Processing {len(tool_items)} Tools ---")
        try:
            ensure_collection(
                client,
                name=TOOLS_COLLECTION_NAME,
                dense_dim=dense_embedder.dim,
                bulk_ingest=True
            )
            
            tool_points = prepare_and_embed(tool_items, dense_embedder, sparse_embedder)
            
            log.info(f"Upserting {len(tool_points)} tool points to collection '{TOOLS_COLLECTION_NAME}'...")
            client.upsert(
                collection_name=TOOLS_COLLECTION_NAME,
                points=tool_points,
                wait=True
            )
            log.info("Successfully upserted tools.")
        
        except Exception as e:
            log.error(f"Error during tool upsert: {e}", exc_info=True)
    else:
        log.info("No tools found to ingest.")

    # --- 3. Process Workflows ---
    workflow_items = load_workflows_data(WORKFLOW_DIR)
    if workflow_items:
        log.info(f"--- Processing {len(workflow_items)} Workflows ---")
        try:
            ensure_collection(
                client,
                name=WORKFLOW_COLLECTION_NAME,
                dense_dim=dense_embedder.dim,
                bulk_ingest=True
            )
            
            workflow_points = prepare_and_embed(workflow_items, dense_embedder, sparse_embedder)
            
            log.info(f"Upserting {len(workflow_points)} workflow points to collection '{WORKFLOW_COLLECTION_NAME}'...")
            client.upsert(
                collection_name=WORKFLOW_COLLECTION_NAME,
                points=workflow_points,
                wait=True
            )
            log.info("Successfully upserted workflows.")
        
        except Exception as e:
            log.error(f"Error during workflow upsert: {e}", exc_info=True)
    else:
        log.info("No workflows found to ingest.")

    log.info("--- Ingestion Complete ---")


if __name__ == "__main__":
    main()