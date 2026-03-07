"""
Example workflow for testing the Governed Code Mode system.
"""
import mcp

async def main():
    # Search for files about authentication
    results = await mcp.use("cortex.search", query="authentication vulnerability")
    
    # Read each file found
    for file in results:
        content = await mcp.use("cortex.read", path=file["path"])
        
        # Check for issues
        if "password" in content.lower():
            await mcp.use("human.notify", 
                         message=f"Found password reference in {file['path']}")
    
    # Return summary
    return {"files_checked": len(results)}
