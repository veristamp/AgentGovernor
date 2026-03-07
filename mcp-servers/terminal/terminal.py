#!/usr/bin/env python3

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict
from mcp.server.fastmcp import FastMCP, Context
import os
import logging
from pydantic import BaseModel, ValidationError
from functools import wraps

# Set event loop policy for Windows to avoid stdio pipe issues
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Constants
TRUNCATED_MESSAGE = "<response clipped>..."
MAX_RESPONSE_LEN = 16000
DEFAULT_PYTHON_PATH = "python3"  # Use system python3

# Server lifecycle
@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, str]]:
    logger.info("Starting Terminal MCP server")
    yield {"status": "running"}
    logger.info("Shutting down Terminal server")

# Create MCP server
mcp = FastMCP(name="terminal", lifespan=server_lifespan)

# Input schema
class RunCommandArgs(BaseModel):
    command: str
    directory: str = "~"  # Default to home directory
    timeout: float = 120.0  # Default timeout of 120 seconds
    truncate_after: int = MAX_RESPONSE_LEN

# Error handling decorator
def handle_errors(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValidationError as e:
            return f"Error: Invalid arguments - {e}"
        except Exception as e:
            return f"Error: {str(e)}"
    return wrapper

# Utility to truncate output
def maybe_truncate(content: str, truncate_after: int) -> str:
    return content if len(content) <= truncate_after else content[:truncate_after] + TRUNCATED_MESSAGE

# Tool
@mcp.tool()
@handle_errors
async def run_command(command: str, ctx: Context, directory: str = "~", timeout: float = 120.0, truncate_after: int = MAX_RESPONSE_LEN) -> str:
    """Run a shell command asynchronously with a timeout."""
    parsed = RunCommandArgs(command=command, directory=directory, timeout=timeout, truncate_after=truncate_after)
    
    # Adjust Python commands to use the specified Python path
    if parsed.command.strip().startswith("python"):
        parsed.command = f"{DEFAULT_PYTHON_PATH} {parsed.command.split(' ', 1)[1]}"
    
    # Expand the directory path
    directory = os.path.expanduser(parsed.directory)
    if not os.path.isdir(directory):
        return f"Error: Directory '{directory}' does not exist or is not a directory"

    # Basic safety gates
    forbidden = ["rm -rf", ":(){:|:&};:", ">&", ">>", "<<", "|&", ";/", "`", "$(", "nohup", "&"]
    if any(tok in parsed.command for tok in forbidden):
        return "Error: Command contains forbidden patterns."
    # Clamp timeout (0 < t <= 300s)
    t = max(1.0, min(parsed.timeout, 300.0))
    process = await asyncio.create_subprocess_shell(
        parsed.command,
        cwd=directory,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=t)
        returncode = process.returncode or 0
        stdout_str = maybe_truncate(stdout.decode(), parsed.truncate_after)
        stderr_str = maybe_truncate(stderr.decode(), parsed.truncate_after)
        
        result = f"Return code: {returncode}\nStdout:\n{stdout_str}\nStderr:\n{stderr_str}"
        logger.info(f"Ran command: {parsed.command[:50]}... in {directory} Return code: {returncode}")
        return result
    except asyncio.TimeoutError:
        process.kill()
        logger.error(f"Command '{parsed.command}' in {directory} timed out after {parsed.timeout} seconds")
        return f"Error: Command timed out after {parsed.timeout} seconds"

# Prompt
@mcp.prompt()
def execute_terminal_command(command: str = "echo 'Hello from MCP Terminal'") -> list[Dict[str, str]]:
    """Prompt to run a terminal command with confirmation."""
    return [
        {"role": "user", "content": f"Run this terminal command:\n{command}"},
        {"role": "assistant", "content": f"I'll use run_command('{command}', directory='~', timeout=120.0). Confirm to proceed."}
    ]

# Resource
@mcp.resource("status://terminal")
def get_terminal_status() -> str:
    """Return terminal server status."""
    return "Terminal server running"

# Main execution
if __name__ == "__main__":
    mcp.run(transport="stdio")
