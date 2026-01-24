"""Skill discovery helpers for Governed Code Mode.

Provides deterministic, low-latency discovery of skills using the host socket.
Adapts the standardized GCM Registry Search to legacy Python structures.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import mcp

_mcp_get_client = getattr(mcp, "_get_client")


def _client():
    return _mcp_get_client()


async def search(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search skills using the standardized tool registry."""
    client = _client()
    loop = asyncio.get_event_loop()
    
    # Call the new standardized endpoint
    response = await loop.run_in_executor(
        None,
        client._send_request,
        "__tool_search__",
        {"query": query, "limit": limit},
    )
    
    # Unpack the new structure: { "result": { "tool_references": [ ... ] } }
    if not isinstance(response, dict):
        return []
    
    result = response.get("result", {})
    tool_refs = result.get("tool_references", [])
    
    mapped_skills = []
    for ref in tool_refs:
        sig = ref.get("signature", {})
        skill_id = sig.get("id", "").replace("skills.", "") # "skills.foo" -> "foo"
        version = sig.get("version", "1")
        
        # reconstruct legacy skillRef for loader compatibility
        skill_ref = f"skills:{skill_id}@{version}"
        
        mapped_skills.append({
            "skillRef": skill_ref,
            "skillId": skill_id,
            "description": sig.get("description", ""),
            "version": version,
            # Pass through the full signature for consumers who know how to use it
            "signature": sig
        })
        
    return mapped_skills


async def inspect(skill_ref: str) -> Dict[str, Any]:
    """Fetch skill metadata (manifest + doc summary)."""
    client = _client()
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        client._send_request,
        "__inspect_skill__",
        {"skill": skill_ref},
    )
    if isinstance(result, dict) and isinstance(result.get("skill"), dict):
        return result["skill"]
    return {}
