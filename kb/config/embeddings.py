# config/embeddings.py
"""
Central Embedding Model Configuration.

This module provides a single source of truth for embedding model configuration
across the entire codebase (chunker, RAG, db).

All settings are configurable via environment variables:
- EMBEDDING_MODEL: Model name/path (default: nomic-ai/nomic-embed-text-v2-moe)
- EMBEDDING_DIM: Vector dimension (default: 768)
- EMBEDDING_MAX_TOKENS: Max tokens for chunking (default: 8192)
- SPARSE_MODEL: Sparse embedding model (default: Qdrant/bm25)
- RERANKER_MODEL: Cross-encoder reranker (default: cross-encoder/ms-marco-MiniLM-L-6-v2)

Usage:
    from config.embeddings import EMBEDDING_CONFIG
    
    model_name = EMBEDDING_CONFIG.model_name
    dim = EMBEDDING_CONFIG.dim
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EmbeddingConfig:
    """
    Central configuration for embedding models.
    
    All values are read from environment variables with sensible defaults.
    The config is frozen (immutable) to prevent accidental modification.
    """
    
    # Dense Embedding Model
    model_name: str
    dim: int
    max_tokens: int
    
    # Provider Settings (fastembed, ollama, openai)
    provider: str
    base_url: Optional[str]
    
    # Sparse Embedding Model (for hybrid search)
    sparse_model: str
    
    # Reranker Model (cross-encoder)
    reranker_model: str
    reranker_provider: str
    reranker_base_url: Optional[str]
    
    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        """
        Create configuration from environment variables.
        """
        return cls(
            model_name=os.getenv(
                "EMBEDDING_MODEL",
                "nomic-ai/nomic-embed-text-v1.5"
            ),
            dim=int(os.getenv("EMBEDDING_DIM", "768")),
            max_tokens=int(os.getenv("EMBEDDING_MAX_TOKENS", "8192")),
            provider=os.getenv("EMBEDDING_PROVIDER", "fastembed").lower(),
            base_url=os.getenv("EMBEDDING_BASE_URL"),
            sparse_model=os.getenv("SPARSE_MODEL", "Qdrant/bm25"),
            reranker_model=os.getenv(
                "RERANKER_MODEL",
                "cross-encoder/ms-marco-MiniLM-L-6-v2"
            ),
            reranker_provider=os.getenv("RERANKER_PROVIDER", "local").lower(),
            reranker_base_url=os.getenv("RERANKER_BASE_URL"),
        )
    
    def __repr__(self) -> str:
        return (
            f"EmbeddingConfig(\n"
            f"  model_name='{self.model_name}',\n"
            f"  dim={self.dim},\n"
            f"  max_tokens={self.max_tokens},\n"
            f"  sparse_model='{self.sparse_model}',\n"
            f"  reranker_model='{self.reranker_model}'\n"
            f")"
        )


# Global singleton - loaded once at import time
EMBEDDING_CONFIG = EmbeddingConfig.from_env()


# Convenience exports for quick access
def get_model_name() -> str:
    """Get the configured dense embedding model name."""
    return EMBEDDING_CONFIG.model_name


def get_dim() -> int:
    """Get the configured embedding dimension."""
    return EMBEDDING_CONFIG.dim


def get_max_tokens() -> int:
    """Get the configured max tokens for the embedding model."""
    return EMBEDDING_CONFIG.max_tokens


def get_sparse_model() -> str:
    """Get the configured sparse embedding model name."""
    return EMBEDDING_CONFIG.sparse_model


def get_reranker_model() -> str:
    """Get the configured reranker model name."""
    return EMBEDDING_CONFIG.reranker_model


# For quick debugging
if __name__ == "__main__":
    print("🔧 Embedding Configuration")
    print("=" * 50)
    print(EMBEDDING_CONFIG)
    print()
    print("Environment Variables:")
    print(f"  EMBEDDING_MODEL={os.getenv('EMBEDDING_MODEL', '(not set)')}")
    print(f"  EMBEDDING_DIM={os.getenv('EMBEDDING_DIM', '(not set)')}")
    print(f"  EMBEDDING_MAX_TOKENS={os.getenv('EMBEDDING_MAX_TOKENS', '(not set)')}")
    print(f"  SPARSE_MODEL={os.getenv('SPARSE_MODEL', '(not set)')}")
    print(f"  RERANKER_MODEL={os.getenv('RERANKER_MODEL', '(not set)')}")
