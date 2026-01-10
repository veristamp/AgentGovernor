#!/usr/bin/env python3
"""
Tool Schema Dumper - Creates structured tools/ directory.

This is LAYER 1 of the architecture:
  tools/           <- Raw MCP tool definitions (this script creates)
  skills/          <- Composed tasks using tools (created separately) 
  workflows/       <- Business logic using skills (created by agent)

Output structure:
  tools/
    <server>/
      <tool_name>.md    <- Human-readable description
      <tool_name>.json  <- API schema for programmatic use
    ...

Usage:
  uv run python list_tools.py

This should be run whenever mcp_servers.json changes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List

from mcp_client.config import Config
from mcp_client.manager import MCPClientManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s"
)
logger = logging.getLogger("ToolsDumper")

TOOLS_DIR = Path("tools")


def _to_plain(obj: Any) -> Any:
    """
    Best-effort conversion of MCP SDK / pydantic objects to plain JSON-serializable types.
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
    try:
        return str(obj)
    except Exception:
        return None


def _extract_schema(tool_obj: Any) -> Dict[str, Any]:
    """
    Normalize a tool's input schema to a plain JSON Schema dict.
    """
    for attr in ("input_schema", "inputSchema", "parameters", "args", "schema"):
        if hasattr(tool_obj, attr):
            raw = getattr(tool_obj, attr)
            plain = _to_plain(raw)
            if isinstance(plain, dict):
                return plain
    maybe = _to_plain(tool_obj)
    if isinstance(maybe, dict):
        for key in ("input_schema", "inputSchema", "parameters", "args", "schema"):
            if isinstance(maybe.get(key), dict):
                return maybe[key]
    return {}


def _format_signature(name: str, schema: Dict[str, Any]) -> str:
    """Generate a Python-style signature from JSON schema."""
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    
    type_map = {
        "string": "str",
        "integer": "int", 
        "number": "float",
        "boolean": "bool",
        "array": "list",
        "object": "dict"
    }
    
    args = []
    for param_name, param_def in props.items():
        py_type = type_map.get(param_def.get("type", "any"), "any")
        if param_name in required:
            args.append(f"{param_name}: {py_type}")
        else:
            default = param_def.get("default")
            if default is not None:
                if isinstance(default, str):
                    args.append(f'{param_name}: {py_type} = "{default}"')
                else:
                    args.append(f"{param_name}: {py_type} = {default}")
            else:
                args.append(f"{param_name}: {py_type} = None")
    
    return f"{name}({', '.join(args)})"


def _generate_tool_md(tool: Dict[str, Any]) -> str:
    """Generate markdown documentation for a single tool."""
    name = tool["name"]
    qualified = tool["qualified_name"]
    desc = tool.get("description", "No description available.")
    schema = tool.get("schema", {})
    
    sig = _format_signature(name, schema)
    
    # Build parameters section
    params_md = ""
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    
    if props:
        params_md = "\n## Parameters\n\n| Name | Type | Required | Description |\n|------|------|----------|-------------|\n"
        for param_name, param_def in props.items():
            param_type = param_def.get("type", "any")
            param_desc = param_def.get("description", "-")
            is_req = "✓" if param_name in required else ""
            params_md += f"| `{param_name}` | {param_type} | {is_req} | {param_desc} |\n"
    
    return f"""# {qualified}

> {desc.split(chr(10))[0]}

## Signature

```python
await {sig}
```

## Description

{desc}
{params_md}
## Usage Example

```python
result = await {qualified.replace('.', '_binding.')}(
    # Add parameters here
)
```
"""


async def main() -> None:
    """Connect to MCP servers and dump tool schemas to tools/ directory."""
    
    # Load config
    cfg = Config.load("mcp_servers.json")
    
    # Clear and recreate tools directory
    if TOOLS_DIR.exists():
        shutil.rmtree(TOOLS_DIR)
    TOOLS_DIR.mkdir(parents=True)
    
    # Connect and discover tools
    async with MCPClientManager(cfg) as mgr:
        await mgr.wait_ready()
        caps = mgr.get_capabilities()
        tools: Dict[str, Any] = caps.get("tools", {})
        
        # Group by server
        servers: Dict[str, List[Dict[str, Any]]] = {}
        all_tools = []
        
        for qualified_name, tool_obj in tools.items():
            if "." in qualified_name:
                prefix, bare = qualified_name.split(".", 1)
            else:
                prefix, bare = "misc", qualified_name
            
            tool_data = {
                "qualified_name": qualified_name,
                "server_prefix": prefix,
                "name": bare,
                "description": getattr(tool_obj, "description", None) or "",
                "schema": _extract_schema(tool_obj),
            }
            
            if prefix not in servers:
                servers[prefix] = []
            servers[prefix].append(tool_data)
            all_tools.append(tool_data)
        
        # Create directory structure
        for server_name, server_tools in servers.items():
            server_dir = TOOLS_DIR / server_name
            server_dir.mkdir(parents=True, exist_ok=True)
            
            # Create index.md for the server
            index_content = f"# {server_name.title()} Tools\n\n"
            index_content += f"This server provides {len(server_tools)} tools.\n\n"
            index_content += "## Available Tools\n\n"
            
            for tool in server_tools:
                name = tool["name"]
                desc_line = tool["description"].split("\n")[0][:100]
                index_content += f"- [`{name}`](./{name}.md) - {desc_line}\n"
                
                # Create individual tool .md file
                md_path = server_dir / f"{name}.md"
                md_path.write_text(_generate_tool_md(tool), encoding="utf-8")
                
                # Create individual tool .json file
                json_path = server_dir / f"{name}.json"
                json_path.write_text(
                    json.dumps(tool, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
            
            # Write server index
            (server_dir / "index.md").write_text(index_content, encoding="utf-8")
            logger.info(f"Created {len(server_tools)} tools in tools/{server_name}/")
        
        # Also write the flat tools_schema.json for backwards compatibility
        with open("tools_schema.json", "w", encoding="utf-8") as f:
            json.dump(all_tools, f, ensure_ascii=False, indent=2)
        
        # Create tools/index.md
        tools_index = "# MCP Tools Registry\n\n"
        tools_index += f"Total: {len(all_tools)} tools from {len(servers)} servers.\n\n"
        tools_index += "## Servers\n\n"
        for server_name, server_tools in sorted(servers.items()):
            tools_index += f"- [`{server_name}`](./{server_name}/index.md) ({len(server_tools)} tools)\n"
        
        (TOOLS_DIR / "index.md").write_text(tools_index, encoding="utf-8")
        
        logger.info(f"=== Done: {len(all_tools)} tools from {len(servers)} servers ===")
        logger.info(f"Output: tools/ directory + tools_schema.json")


if __name__ == "__main__":
    asyncio.run(main())
