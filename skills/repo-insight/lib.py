"""
Repo Insight Skill.

Builds a lightweight repository insight report, then stores it to memory and disk.
"""
from __future__ import annotations

import json
from typing import Any, Dict

_bindings: Dict[str, Any]


def _maybe_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _summarize_nodes(nodes: Any, limit: int = 8) -> Dict[str, Any]:
    payload = _maybe_json(nodes)
    if isinstance(payload, dict) and "entities" in payload:
        entities = payload.get("entities", [])
    elif isinstance(payload, list):
        entities = payload
    else:
        entities = []
    names = []
    for entry in entities:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.append(entry["name"])
    return {
        "count": len(entities),
        "sample": names[:limit],
    }


async def analyze_repo(
    query: str,
    output_dir: str,
    note_key: str,
    write_report: bool = True,
) -> Dict[str, Any]:
    """
    Search docs + code graph for repo insight, store summary to memory and disk.

    Args:
        query: What to learn about the repo.
        output_dir: Directory to write the report into.
        note_key: Key to store the report summary in memory.
        write_report: If true, write the report to disk.

    Returns:
        Dict with summary, memory key, and optional report path.
    """
    graph = _bindings["graph"]
    mem = _bindings["mem"]
    fs = _bindings["fs"]

    docs = await getattr(graph, "docs-semantic-search")(query=query)
    code = await getattr(graph, "nodes-semantic-search")(query=query)
    usage = await getattr(graph, "get-usage-dependency-links")(query=query)

    summary = {
        "query": query,
        "docs": _summarize_nodes(docs),
        "code": _summarize_nodes(code),
        "usage": _summarize_nodes(usage),
    }

    await getattr(mem, "create-entities")(entities=[{
        "name": note_key,
        "entityType": "RepoInsight",
        "observations": [json.dumps(summary)],
    }])

    report_path = None
    if write_report:
        try:
            await getattr(fs, "create-directory")(path=output_dir)
        except Exception:
            pass
        report_path = f"{output_dir.rstrip('/')}/{note_key}.json"
        await getattr(fs, "write-file")(path=report_path, content=json.dumps(summary, indent=2))

    return {
        "summary": summary,
        "memory_key": note_key,
        "report_path": report_path,
    }
