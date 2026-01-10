#!/usr/bin/env python3
"""
Workflow Runner

This script is the entry point that runs inside the sandbox.
It receives workflow code via stdin, executes it, and returns the result.

Key features:
1. Installs `skills` package for `from skills import X` syntax
2. Injects `mcp` for direct tool access
3. Handles async execution and error reporting
"""

import asyncio
import sys
import os
import traceback
from pathlib import Path

# Add runtime directory to path
runtime_dir = Path(__file__).parent
sys.path.insert(0, str(runtime_dir))

# Import our modules
import mcp
from skill_loader import install_skills_package

# Find skills directory (relative to project root)
# When running from project root, skills/ is at ./skills/
# When running from sandbox/runtime/, skills/ is at ../../skills/
def _find_skills_dir() -> str:
    # Try relative paths
    candidates = [
        Path.cwd() / "skills",
        runtime_dir / ".." / ".." / "skills",
        Path(os.environ.get("MCP_SKILLS_DIR", "skills")),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())
    return "skills"  # Default


async def run_workflow(code: str) -> None:
    """Execute workflow code and return result via MCP."""
    
    # Install skills package for import-style access
    skills_dir = _find_skills_dir()
    install_skills_package(skills_dir)
    
    # Create execution namespace
    namespace = {
        "mcp": mcp,
        "asyncio": asyncio,
        "__name__": "__main__",
        "__file__": "<workflow>",
    }
    
    try:
        # Execute the code to define main()
        exec(code, namespace)
        
        # Get main function
        main_fn = namespace.get("main")
        if main_fn is None:
            raise RuntimeError("Workflow must define 'async def main()'")
        
        if not asyncio.iscoroutinefunction(main_fn):
            raise RuntimeError("main() must be an async function")
        
        # Run main()
        result = await main_fn()
        
        # Signal completion
        mcp.complete(result)
        
    except Exception as e:
        # Signal error completion
        error_info = {
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }
        mcp.complete({"__error__": error_info})
        sys.exit(1)


def main():
    # Read workflow code from stdin
    code = sys.stdin.read()
    
    if not code.strip():
        print("Error: No workflow code provided", file=sys.stderr)
        sys.exit(1)
    
    # Run the workflow
    asyncio.run(run_workflow(code))


if __name__ == "__main__":
    main()
