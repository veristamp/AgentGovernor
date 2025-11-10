# dump_tools_schema.py
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict

from mcp_client.config import Config
from mcp_client.manager import MCPClientManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s"
)
logger = logging.getLogger("DumpToolsSchema")


def _to_plain(obj: Any) -> Any:
    """
    Best-effort conversion of MCP SDK / pydantic objects to plain JSON-serializable types.
    Tries .model_dump(), then __dict__-like extraction, otherwise returns the object as-is
    (json will handle primitives and lists/dicts of primitives).
    """
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]
    # pydantic v2
    model_dump = getattr(obj, "model_dump", None)
    if callable(model_dump):
        try:
            return model_dump()
        except Exception:
            pass
    # dataclass-like / simple objects
    d = {}
    for key in ("name", "description", "input_schema", "inputSchema", "parameters", "args", "schema"):
        if hasattr(obj, key):
            d[key] = getattr(obj, key)
    if d:
        return {k: _to_plain(v) for k, v in d.items()}
    # fallback string
    try:
        return str(obj)
    except Exception:
        return None


def _extract_schema(tool_obj: Any) -> Dict[str, Any]:
    """
    Normalize a tool's input schema to a plain JSON Schema dict.
    Checks common MCP SDK field names.
    """
    # Try typical field names in order of likelihood
    for attr in ("input_schema", "inputSchema", "parameters", "args", "schema"):
        if hasattr(tool_obj, attr):
            raw = getattr(tool_obj, attr)
            plain = _to_plain(raw)
            if isinstance(plain, dict):
                return plain
    # If the tool object itself is model-like, try to pluck something structured
    maybe = _to_plain(tool_obj)
    if isinstance(maybe, dict):
        # Heuristics
        for key in ("input_schema", "inputSchema", "parameters", "args", "schema"):
            if isinstance(maybe.get(key), dict):
                return maybe[key]
    return {}  # fallback: unknown/empty schema


async def main() -> None:
    # Load config from ./mcp_servers.json
    cfg = Config.load("mcp_servers.json")

    # Connect and discover tools
    async with MCPClientManager(cfg) as mgr:
        await mgr.wait_ready()
        caps = mgr.get_capabilities()
        tools: Dict[str, Any] = caps.get("tools", {})

        out = []
        for qualified_name, tool_obj in tools.items():
            # prefix & bare name
            if "." in qualified_name:
                prefix, bare = qualified_name.split(".", 1)
            else:
                prefix, bare = "", qualified_name

            item = {
                "qualified_name": qualified_name,  # e.g., "filesystem.read_file"
                "server_prefix": prefix,           # e.g., "filesystem"
                "name": bare,                      # e.g., "read_file"
                "description": getattr(tool_obj, "description", None),
                "schema": _extract_schema(tool_obj),  # normalized JSON Schema (dict)
            }
            out.append(item)

        # Save to root path
        path = "tools_schema.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

        logger.info("Wrote %d tool schemas to %s", len(out), path)


if __name__ == "__main__":
    asyncio.run(main())
