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
    # Socket server wraps search payload as {"result": {"result": <tool_search_result>}}
    if isinstance(result, dict) and isinstance(result.get("result"), dict):
        result = result.get("result", {})
    tool_refs = result.get("tool_references", [])
    
    mapped_skills = []
    for ref in tool_refs:
        sig = ref.get("signature", {})
        skill_ref = sig.get("skillRef") or ref.get("tool_name") or ""
        skill_id = sig.get("skillId") or ""
        version = sig.get("version", "1")

        if not skill_id and isinstance(skill_ref, str) and skill_ref.startswith("skills:") and "@" in skill_ref:
            skill_id = skill_ref.split(":", 1)[1].split("@", 1)[0]

        if not skill_ref and skill_id:
            skill_ref = f"skills:{skill_id}@{version}"

        mapped_skills.append({
            "skillRef": skill_ref,
            "skillId": skill_id,
            "description": sig.get("description", ""),
            "version": version,
            "signature": sig,
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
