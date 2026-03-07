# db/drop_tables.py
"""
Drop ALL data from Postgres and Qdrant.

WARNING: This is destructive! Use with caution.

Usage:
    python -m db.drop_tables           # Interactive confirmation
    python -m db.drop_tables --force   # Skip confirmation
"""

import asyncio
import argparse
import sys

from db.manager import create_db_manager


async def main():
    parser = argparse.ArgumentParser(description="Drop all Postgres tables and Qdrant collections")
    parser.add_argument("--force", "-f", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--postgres-only", action="store_true", help="Only drop Postgres tables")
    parser.add_argument("--qdrant-only", action="store_true", help="Only delete Qdrant collections")
    args = parser.parse_args()
    
    print("⚠️  DATABASE RESET TOOL")
    print("=" * 60)
    
    if not args.force:
        print("\nThis will PERMANENTLY DELETE:")
        if not args.qdrant_only:
            print("  • All Postgres tables (nodes, edges, concepts, documents, etc.)")
        if not args.postgres_only:
            print("  • All Qdrant collections (kb_chunks, kb_concepts, etc.)")
        print()
        
        confirm = input("Type 'yes' to confirm: ")
        if confirm.lower() != "yes":
            print("Aborted.")
            sys.exit(0)
    
    async with create_db_manager() as db:
        if args.postgres_only:
            print("\n🗑️  Dropping Postgres tables...")
            await db.drop_all_postgres()
            print("   ✅ Postgres tables dropped")
        elif args.qdrant_only:
            print("\n🗑️  Deleting Qdrant collections...")
            deleted = await db.drop_all_qdrant()
            if deleted:
                for name in deleted:
                    print(f"   ✅ Deleted collection: {name}")
            else:
                print("   (No collections found)")
        else:
            print("\n🗑️  Dropping ALL data...")
            result = await db.drop_all()
            print("   ✅ Postgres tables dropped")
            if result["qdrant_collections_deleted"]:
                for name in result["qdrant_collections_deleted"]:
                    print(f"   ✅ Deleted Qdrant collection: {name}")
            else:
                print("   (No Qdrant collections found)")
    
    print("\n" + "=" * 60)
    print("✅ Database reset complete!")
    print("\nTo reinitialize, run:")
    print("  python -m db.async_init")


if __name__ == "__main__":
    asyncio.run(main())
