"""
MCP Runtime Client with Binding Support

This module provides:
1. Direct tool calls: await mcp.use("server.tool", arg=val)
2. Binding proxies: _binding.tool_name(arg=val) -> mcp.use()

The binding pattern is MORE SECURE because:
- LLM only sees skill functions (list_files, read, write)
- LLM never sees raw tool names (filesystem.list_directory)
- All calls route through the Policy Gate
"""

import asyncio
import json
import os
import sys
from typing import Any, Optional, Dict
from functools import partial

# Get socket path from environment or use platform-appropriate default
def _get_socket_path():
    if os.environ.get("MCP_SOCKET_PATH"):
        return os.environ["MCP_SOCKET_PATH"]
    if sys.platform == "win32":
        return r"\\.\pipe\mcp-workflow"
    return "/tmp/mcp-workflow.sock"

SOCKET_PATH = _get_socket_path()


class MCPClient:
    """Minimal JSON-RPC client over socket/named pipe."""
    
    def __init__(self, socket_path: str = SOCKET_PATH):
        self.socket_path = socket_path
        self._file: Optional[Any] = None
        self._request_id = 0
    
    def _connect(self):
        """Connect to the socket/pipe."""
        if self._file is not None:
            return
        
        if sys.platform == "win32":
            # Windows named pipe - use file open
            self._file = open(self.socket_path, "r+b", buffering=0)
        else:
            # Unix socket
            import socket
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(self.socket_path)
            self._file = sock.makefile('rwb', buffering=0)
    
    def _send_request(self, method: str, params: dict) -> Any:
        """Send JSON-RPC request and wait for response."""
        self._connect()
        assert self._file is not None
        
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._request_id,
        }
        
        # Send request
        request_bytes = (json.dumps(request) + "\n").encode('utf-8')
        self._file.write(request_bytes)
        self._file.flush()
        
        # Read response line
        response_bytes = b""
        while True:
            chunk = self._file.read(1)
            if not chunk:
                raise ConnectionError("Socket closed")
            if chunk == b"\n":
                break
            response_bytes += chunk
        
        response = json.loads(response_bytes.decode('utf-8'))
        
        if "error" in response:
            error = response["error"]
            raise RuntimeError(f"MCP Error ({error.get('code')}): {error.get('message')}")
        
        return response.get("result")
    
    def close(self):
        """Close the connection."""
        if self._file:
            self._file.close()
            self._file = None


# ============== Binding Proxy ==============

class BindingProxy:
    """
    Proxy object that intercepts method calls and routes them through MCP.
    
    When you do: _binding.list_directory(path=".")
    It becomes:  mcp.use("filesystem.list_directory", path=".")
    
    This is the I/O trap - all external calls go through the Policy Gate.
    """
    
    def __init__(self, server_prefix: str, client: 'MCPClient', skill_context: Optional[Dict[str, str]] = None):
        self._prefix = server_prefix
        self._client = client
        self._skill_context = skill_context
    
    def __getattr__(self, name: str):
        """
        Intercept attribute access and return an async callable.
        
        _binding.read_file -> returns async function that calls filesystem.read_file
        """
        if name.startswith('_'):
            raise AttributeError(name)
        
        async def method_proxy(**kwargs) -> Any:
            tool_name = f"{self._prefix}.{name}"
            if self._skill_context:
                kwargs = {**kwargs, "__context": self._skill_context}
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, 
                self._client._send_request, 
                tool_name, 
                kwargs
            )
        
        return method_proxy

    
    def __repr__(self):
        return f"<BindingProxy for {self._prefix}>"


# ============== Global Client ==============

_client: Optional[MCPClient] = None

def _get_client() -> MCPClient:
    global _client
    if _client is None:
        _client = MCPClient()
    return _client


# ============== Public API ==============

async def use(tool: str, **kwargs) -> Any:
    """
    Call an MCP tool directly.
    
    Args:
        tool: Fully qualified tool name (e.g., "filesystem.list_directory")
        **kwargs: Tool arguments
    
    Returns:
        Tool result
    
    Example:
        files = await mcp.use("filesystem.list_directory", path=".")
    """
    client = _get_client()
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, client._send_request, tool, kwargs)


def create_binding(server_prefix: str, skill_context: Optional[str] = None) -> BindingProxy:
    """
    Create a binding proxy for a specific MCP server.

    This is used by the skill loader to inject _binding into skill modules.

    Args:
        server_prefix: The server name (e.g., "filesystem", "terminal")
        skill_context: Optional skill reference (e.g., "skills:filesystem@1")

    Returns:
        A BindingProxy that routes calls to that server

    Example:
        _binding = mcp.create_binding("filesystem", skill_context="skills:filesystem@1")
        result = await _binding.list_directory(path=".")
        # This calls: filesystem.list_directory
    """
    context = {"skill": skill_context} if skill_context else None
    return BindingProxy(server_prefix, _get_client(), context)



async def capabilities() -> list:
    """Get list of available tools."""
    client = _get_client()
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, client._send_request, "__capabilities__", {})
    return result.get("tools", [])


def complete(result: Any) -> None:
    """Signal workflow completion."""
    client = _get_client()
    client._send_request("__complete__", {"result": result})


# ============== Cleanup ==============

import atexit

def _cleanup():
    global _client
    if _client:
        _client.close()
        _client = None

atexit.register(_cleanup)
