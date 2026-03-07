"""
Docs to Files Skill.

Fetches documentation from Context7 and saves it to a file.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

_bindings: Dict[str, Any]


def _coerce_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _extract_library_id(value: Any) -> Optional[str]:
    payload = _coerce_json(value)

    if isinstance(payload, dict):
        for key in ("libraryId", "context7CompatibleLibraryID", "id"):
            if isinstance(payload.get(key), str):
                return payload[key]
        for key in ("libraries", "matches", "results", "data"):
            entries = payload.get(key)
            if isinstance(entries, list):
                for item in entries:
                    if isinstance(item, dict):
                        for inner_key in ("libraryId", "id", "context7CompatibleLibraryID"):
                            if isinstance(item.get(inner_key), str):
                                return item[inner_key]
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                for inner_key in ("libraryId", "id", "context7CompatibleLibraryID"):
                    if isinstance(item.get(inner_key), str):
                        return item[inner_key]
    if isinstance(payload, str):
        if payload.strip().startswith("/"):
            return payload.strip().split()[0]
        match = re.search(r"/[^\s]+/[^\s]+", payload)
        if match:
            return match.group(0)
    return None


async def fetch_and_store(
    library: str,
    topic: str,
    output_dir: str,
    file_name: Optional[str] = None,
    mode: str = "code",
) -> Dict[str, Any]:
    """
    Resolve a library, fetch docs, and write them to a file.

    Args:
        library: Library name or Context7 library ID (/org/project).
        topic: Topic to fetch.
        output_dir: Directory to store the output.
        file_name: Optional filename override.
        mode: Context7 mode (code or info).

    Returns:
        Dict with library ID and output path.
    """
    ctx = _bindings["ctx"]
    fs = _bindings["fs"]

    if library.strip().startswith("/"):
        library_id = library.strip()
    else:
        resolver = getattr(ctx, "resolve-library-id")
        resolved = await resolver(libraryName=library)
        library_id = _extract_library_id(resolved)
        if not library_id:
            raise ValueError(f"Unable to resolve library ID for '{library}'")

    fetch_docs = getattr(ctx, "query-docs")
    docs = await fetch_docs(
        libraryId=library_id,
        query=topic,
    )

    try:
        await getattr(fs, "create-directory")(path=output_dir)
    except Exception:
        pass

    safe_id = library_id.strip("/").replace("/", "_")
    file_basename = file_name or f"{safe_id}_{topic}.md"
    output_path = f"{output_dir.rstrip('/')}/{file_basename}"

    content = docs if isinstance(docs, str) else json.dumps(docs, indent=2)
    await getattr(fs, "write-file")(path=output_path, content=content)

    return {
        "library_id": library_id,
        "topic": topic,
        "output_path": output_path,
    }
