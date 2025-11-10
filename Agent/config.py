#!/usr/bin/env python3
"""
Central configuration file for the MCP Agent.
"""
import os
import dotenv
dotenv.load_dotenv()
# --- Qdrant Configuration ---
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "mcp_tools")
RERANKER_MODEL_NAME = os.getenv("RERANKER_MODEL_NAME", "jinaai/jina-reranker-v1-turbo-en")
# --- Embedding Model Configuration ---
# This should match the model used in upsert.py
DENSE_EMBED_MODEL = os.getenv("DENSE_EMBED_MODEL", "BAAI/bge-base-en-v1.5")
SPARSE_EMBED_MODEL = os.getenv("SPARSE_EMBED_MODEL", "Qdrant/bm25")

# --- LLM Client Configuration ---
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "kwaipilot/kat-coder-pro:free")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "300"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# --- Planner Configuration ---
MAX_REPAIR_ITERATIONS = 3
DEFAULT_TOOL_TOP_K = 12 # Number of tools to retrieve for the context
HYBRID_CANDIDATE_COUNT = int(os.getenv("HYBRID_CANDIDATE_COUNT", "40"))