"""
Example workflow using context7 MCP server.

This demonstrates using the available context7 tools:
- context7.resolve-library-id: Find library ID for a package
- context7.query-docs: Query documentation for a library

NOTE: The tool names use the server prefix from mcp_servers.json
"""
import mcp

async def main():
    # First, resolve the library ID for "python"
    print("Resolving library ID for 'python'...")
    
    library_info = await mcp.use(
        "context7.resolve-library-id",
        libraryName="python",
        query="how to use asyncio"
    )
    print(f"Library info: {library_info}")
    
    # Now query the docs (using a known library ID)
    print("\nQuerying docs for Next.js...")
    
    docs = await mcp.use(
        "context7.query-docs",
        libraryId="/vercel/next.js",
        query="how to create API routes"
    )
    print(f"Documentation: {docs[:500] if docs else 'No results'}...")
    
    return {
        "status": "success",
        "library_info": library_info,
        "docs_preview": str(docs)[:200] if docs else None
    }
