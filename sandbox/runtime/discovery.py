"""Discovery helpers for Governed Code Mode.

This module provides a deterministic, low-latency way to:
- search available tools (by name/description)
- inspect a tool schema before calling it

It talks to the host via the existing JSON-RPC socket.

Deprecated: Prefer skill_discovery for skills-first workflows.
"""

import asyncio
from typing import Any, Dict, List

import mcp

_mcp_get_client = getattr(mcp, "_get_client")


async def search(query: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Search tools by substring across name/description."""
    client = _mcp_get_client()  # reuse the existing connection
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        client._send_request,
        "__search__",
        {"query": query, "limit": limit},
    )
    tools = result.get("tools", []) if isinstance(result, dict) else []
    return tools if isinstance(tools, list) else []


async def inspect(tool: str) -> Dict[str, Any]:
    """Fetch tool metadata (including input schema) for a qualified tool name."""
    client = _mcp_get_client()
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        client._send_request,
        "__inspect__",
        {"tool": tool},
    )
    if isinstance(result, dict) and isinstance(result.get("tool"), dict):
        return result["tool"]
    return {}
