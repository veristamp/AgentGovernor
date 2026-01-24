"""
Workflow using Skills Layer

This workflow demonstrates the proper layered architecture:
- Uses `import skills; filesystem = skills.load("filesystem")` (NOT raw mcp.use)
- Skills handle parsing/formatting
- LLM never sees raw tool names

The binding pattern routes all calls through the Policy Gate.
"""
import skills
from typing import Any

async def main():
    print("=== Starting Skill-Based Workflow ===")

    skills_api: Any = skills
    filesystem = skills_api.load("filesystem")
    
    # Step 1: List files using skill (NOT raw mcp.use)
    print("\n[1/3] Listing files using filesystem skill...")
    files = await filesystem.list_files(".")
    print(f"Files found: {len(files)}")
    for f in files[:5]:
        print(f"  - {f}")
    if len(files) > 5:
        print(f"  ... and {len(files) - 5} more")
    
    # Step 2: List directories
    print("\n[2/3] Listing directories...")
    dirs = await filesystem.list_dirs(".")
    print(f"Directories found: {len(dirs)}")
    for d in dirs[:5]:
        print(f"  - {d}/")
    
    # Step 3: Read a file
    print("\n[3/3] Reading package.json...")
    try:
        content = await filesystem.read("package.json")
        print(f"Read {len(content)} chars from package.json")
        print(f"Preview: {content[:200]}...")
    except Exception as e:
        print(f"Could not read: {e}")
    
    print("\n=== Workflow Complete ===")
    
    return {
        "status": "success",
        "files_count": len(files),
        "dirs_count": len(dirs)
    }
