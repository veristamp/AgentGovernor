# db/async_init.py
"""
Initialize Dual-Graph Database System.

Creates Postgres tables and Qdrant collections using central config.

Usage:
    python -m db.async_init              # Initialize both
    python -m db.async_init --recreate   # Drop and recreate collections
"""

import asyncio
import argparse

from config import DATABASE_CONFIG, EMBEDDING_CONFIG
from db.manager import create_db_manager


async def main():
    parser = argparse.ArgumentParser(description="Initialize Dual-Graph Database System")
    parser.add_argument("--recreate", action="store_true", help="Recreate Qdrant collections")
    args = parser.parse_args()
    
    print("🚀 Initializing Dual-Graph Database System")
    print("=" * 60)
    
    print(f"\n📦 Configuration:")
    print(f"   Postgres: {DATABASE_CONFIG.postgres_url.split('@')[-1]}")
    print(f"   Qdrant: {DATABASE_CONFIG.qdrant_url}")
    print(f"   Chunks Collection: {DATABASE_CONFIG.qdrant_collection_chunks}")
    print(f"   Concepts Collection: {DATABASE_CONFIG.qdrant_collection_concepts}")
    print(f"   Vector Dimension: {EMBEDDING_CONFIG.dim}")
    
    async with create_db_manager() as db:
        # Postgres
        print(f"\n📊 Postgres:")
        try:
            await db.init_postgres()
            print("   ✅ Tables created successfully")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            print("   Make sure Postgres is running and database exists")
        
        # Qdrant - Chunks collection
        print(f"\n🔍 Qdrant:")
        try:
            await db.init_qdrant_collection(
                collection_name=DATABASE_CONFIG.qdrant_collection_chunks,
                vector_size=EMBEDDING_CONFIG.dim,
                recreate=args.recreate
            )
            print(f"   ✅ Collection '{DATABASE_CONFIG.qdrant_collection_chunks}' ready")
            
            # Concepts collection
            await db.init_qdrant_collection(
                collection_name=DATABASE_CONFIG.qdrant_collection_concepts,
                vector_size=EMBEDDING_CONFIG.dim,
                recreate=args.recreate
            )
            print(f"   ✅ Collection '{DATABASE_CONFIG.qdrant_collection_concepts}' ready")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            print("   Make sure Qdrant is running at the specified URL")
    
    print("\n" + "=" * 60)
    print("✅ Initialization Complete!")
    print("\nNext steps:")
    print("  1. Run ingestion: python -m cli.run_ingestion --glob 'doc/*_structured.json'")
    print("  2. Start server: python server.py")
    print("  3. View Qdrant: http://localhost:6333/dashboard")


if __name__ == "__main__":
    asyncio.run(main())
