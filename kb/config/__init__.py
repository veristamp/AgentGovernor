# config/__init__.py
"""
Central Configuration Module.

Provides unified configuration for:
- Database connections (Postgres, Qdrant)
- Logging setup
- Embedding models
- Chunk schemas
"""

from .embeddings import (
    EMBEDDING_CONFIG,
    EmbeddingConfig,
    get_model_name,
    get_dim,
    get_max_tokens,
    get_sparse_model,
    get_reranker_model,
)
from .database import (
    DATABASE_CONFIG,
    DatabaseConfig,
    get_pg_url,
    get_qdrant_url,
)
from .logging import (
    setup_logging,
    get_logger,
    console,
    InterstellarLogger,
)
from .chunks import ChunkKeys, validate_chunk
from .id_system import generate_stable_id, generate_section_anchor
from .languages import (
    Language,
    EXTENSION_TO_LANGUAGE,
    EXTENSION_TO_TREESITTER,
    get_language_from_extension,
    get_treesitter_lang,
    is_code_file,
)

__all__ = [
    # Embeddings
    "EMBEDDING_CONFIG",
    "EmbeddingConfig",
    "get_model_name",
    "get_dim",
    "get_max_tokens",
    "get_sparse_model",
    "get_reranker_model",
    # Database
    "DATABASE_CONFIG",
    "DatabaseConfig",
    "get_pg_url",
    "get_qdrant_url",
    # Logging
    "setup_logging",
    "get_logger",
    "console",
    "InterstellarLogger",
    # Chunks
    "ChunkKeys",
    "validate_chunk",
    # ID System
    "generate_stable_id",
    "generate_section_anchor",
    # Languages
    "Language",
    "EXTENSION_TO_LANGUAGE",
    "EXTENSION_TO_TREESITTER",
    "get_language_from_extension",
    "get_treesitter_lang",
    "is_code_file",
]

