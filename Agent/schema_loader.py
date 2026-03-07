"""
Schema Loader for Dynamic Skill Synthesis.

Loads tools_schema.json and provides utilities to generate:
1. Auto-documentation for skill context
2. Binding lists for skills
3. Virtual skills for servers without SKILL.md

This is the single source of truth for all MCP tool definitions.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

log = logging.getLogger("schema_loader")

# --- Global Schema Cache ---
TOOLS_SCHEMA_PATH = Path("tools_schema.json")
TOOLS_LIST: List[Dict[str, Any]] = []
TOOLS_MAP: Dict[str, List[Dict[str, Any]]] = {}  # server_prefix -> [tools]


def load_schema(schema_path: Path = TOOLS_SCHEMA_PATH) -> Dict[str, List[Dict[str, Any]]]:
    """
    Load tools_schema.json and group by server prefix.
    
    Returns:
        Dict mapping server_prefix to list of tool definitions
    """
    global TOOLS_LIST, TOOLS_MAP
    
    if TOOLS_MAP:
        return TOOLS_MAP  # Already loaded
    
    if not schema_path.exists():
        log.warning(f"Tools schema not found: {schema_path}")
        return TOOLS_MAP
    
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            TOOLS_LIST = json.load(f)
        
        # Group by server prefix
        for tool in TOOLS_LIST:
            prefix = tool.get("server_prefix", "unknown")
            if prefix not in TOOLS_MAP:
                TOOLS_MAP[prefix] = []
            TOOLS_MAP[prefix].append(tool)
        
        log.info(f"Loaded {len(TOOLS_LIST)} tools from {len(TOOLS_MAP)} servers")
        
    except Exception as e:
        log.error(f"Failed to load tools schema: {e}")
    
    return TOOLS_MAP


def get_server_tools(server_name: str) -> List[Dict[str, Any]]:
    """Get all tools for a specific server."""
    if not TOOLS_MAP:
        load_schema()
    return TOOLS_MAP.get(server_name, [])


def get_all_servers() -> List[str]:
    """Get list of all server names."""
    if not TOOLS_MAP:
        load_schema()
    return list(TOOLS_MAP.keys())


def format_tool_signature(tool: Dict[str, Any]) -> str:
    """
    Generate a Python-style signature for a tool.
    
    Example: read_file(path: str, encoding: str = "utf-8")
    """
    name = tool.get("name", "unknown")
    schema = tool.get("schema", {})
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    
    args = []
    for param_name, param_def in props.items():
        param_type = param_def.get("type", "any")
        
        # Map JSON types to Python types
        type_map = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "array": "list",
            "object": "dict"
        }
        py_type = type_map.get(param_type, param_type)
        
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


def generate_tool_docs(server_name: str) -> str:
    """
    Generate markdown documentation for all tools in a server.
    
    Returns:
        Markdown string with tool signatures and descriptions
    """
    tools = get_server_tools(server_name)
    if not tools:
        return ""
    
    lines = [
        "\n## Available Tools (Auto-Generated from Schema)\n"
    ]
    
    for tool in tools:
        qualified = tool.get("qualified_name", "unknown")
        sig = format_tool_signature(tool)
        desc = tool.get("description", "").replace("\n", " ")[:200]
        
        lines.append(f"### `{qualified}`")
        lines.append(f"```python")
        lines.append(f"await {sig}")
        lines.append(f"```")
        lines.append(f"{desc}")
        lines.append("")
    
    return "\n".join(lines)


def generate_bindings_list(server_name: str) -> List[str]:
    """
    Generate list of qualified binding names for a server.
    
    Returns:
        List of strings like ["filesystem.read_file", "filesystem.write_file"]
    """
    tools = get_server_tools(server_name)
    return [t.get("qualified_name") for t in tools if t.get("qualified_name")]


# --- Initialize on import ---
load_schema()
