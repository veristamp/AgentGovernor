"""
Example workflow using the FileSystem MCP server.

This demonstrates how to use the new Governed Code Mode
with your existing MCP servers defined in mcp_servers.json.

Tools available from FileSystem server:
- FileSystem.list_directory
- FileSystem.read_file
- FileSystem.write_file
- FileSystem.get_file_info
- FileSystem.search_files
- FileSystem.create_directory
- FileSystem.move_file
"""
import mcp

async def main():
    # List files in current directory
    # The tool name is: {ServerName}.{tool_name} -> FileSystem.list_directory
    listing = await mcp.use("filesystem.list_directory", path=".")
    print(f"Directory listing: {listing}")
    
    # Read a specific file
    try:
        content = await mcp.use("filesystem.read_file", path="package.json")
        print(f"package.json contents: {content[:100]}...")
    except Exception as e:
        print(f"Could not read file: {e}")
    
    # Search for Python files
    py_files = await mcp.use("filesystem.search_files", path=".", pattern="*.py")
    print(f"Python files found: {py_files}")
    
    return {
        "status": "success",
        "message": "Filesystem exploration complete"
    }
