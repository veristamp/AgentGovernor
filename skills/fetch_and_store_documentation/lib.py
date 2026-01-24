"""
Fetch and Store Documentation Skill.

Downloads documentation from a URL using the terminal tool and writes it to disk.
"""
from __future__ import annotations

import json
from typing import Any, Dict

_bindings: Dict[str, Any]


async def fetch_and_store(url: str, file_path: str) -> Dict[str, Any]:
    """
    Fetch documentation from a URL and save it to a file.

    Args:
        url: Documentation URL to fetch.
        file_path: Output file path for the downloaded content.

    Returns:
        Dict with URL, file path, and status metadata.
    """
    shell = _bindings["shell"]
    fs = _bindings["fs"]

    command = f'curl -L "{url}"'
    result = await getattr(shell, "run-command")(command=command)
    content = result
    if isinstance(result, dict):
        content = result.get("stdout") or result.get("output") or json.dumps(result)
    await getattr(fs, "write-file")(path=file_path, content=str(content))

    return {
        "url": url,
        "file_path": file_path,
        "status": "ok",
    }
