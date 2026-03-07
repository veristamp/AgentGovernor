# config/database.py
"""
Central Database Configuration.

This module provides a unified configuration for all database connections
in the system (PostgreSQL and Qdrant).

Single source of truth: reads from .env file via DATABASE_URL.
"""

import os
from dataclasses import dataclass
from typing import Optional

# Load .env file (single source of truth)
from dotenv import load_dotenv
load_dotenv()


@dataclass(frozen=True)
class DatabaseConfig:
    """
    Configuration for database connections.
    Values are read from environment variables with sensible defaults.
    """
    
    # --- PostgreSQL (Hard Graph) ---
    postgres_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/kb"
    postgres_pool_size: int = 10
    postgres_max_overflow: int = 20
    
    # --- Qdrant (Soft Graph) ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    qdrant_collection_chunks: str = "kb_chunks"
    qdrant_collection_concepts: str = "kb_concepts"
    
    @property
    def postgres_dsn(self) -> str:
        """Get asyncpg compatible connection string (removes +asyncpg)."""
        return self.postgres_url.replace("+asyncpg", "")
    
    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Load configuration from environment variables."""
        return cls(
            postgres_url=os.getenv(
                "DATABASE_URL", 
                "postgresql+asyncpg://postgres:postgres@localhost:5432/kb"
            ),
            postgres_pool_size=int(os.getenv("PG_POOL_SIZE", "10")),
            postgres_max_overflow=int(os.getenv("PG_MAX_OVERFLOW", "20")),
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            qdrant_api_key=os.getenv("QDRANT_API_KEY"),
            qdrant_collection_chunks=os.getenv("QDRANT_COLLECTION", "kb_chunks"),
            qdrant_collection_concepts=os.getenv("QDRANT_CONCEPTS_COLLECTION", "kb_concepts"),
        )
    
    def __repr__(self) -> str:
        return (
            f"DatabaseConfig(\n"
            f"  postgres_url='{self.postgres_url.split('@')[-1] if '@' in self.postgres_url else self.postgres_url}',\n"
            f"  qdrant_url='{self.qdrant_url}',\n"
            f"  qdrant_collection_chunks='{self.qdrant_collection_chunks}'\n"
            f")"
        )


# Global singleton
DATABASE_CONFIG = DatabaseConfig.from_env()


def get_pg_url() -> str:
    """Get the PostgreSQL connection URL."""
    return DATABASE_CONFIG.postgres_url


def get_qdrant_url() -> str:
    """Get the Qdrant connection URL."""
    return DATABASE_CONFIG.qdrant_url
