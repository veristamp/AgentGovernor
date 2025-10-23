from __future__ import annotations
from typing import Dict, Any

def format_capabilities(tools: Dict[str, Any], resources: Dict[str, Any], prompts: Dict[str, Any]) -> str:
    parts = []
    if tools:
        parts.append("Tools:")
        for name, item in tools.items():
            desc = getattr(item, 'description', '') or ''
            args = ""
            schema = getattr(item, 'inputSchema', None)
            if isinstance(schema, dict) and 'properties' in schema:
                req = set(schema.get('required', []))
                props = [f"{k} ({v.get('type','?')}{' req' if k in req else ''})" for k,v in schema['properties'].items()]
                args = f" [Args: {', '.join(props)}]"
            parts.append(f"  {name}: {desc}{args}")
    if resources:
        parts.append("Resources:")
        for name, item in resources.items():
            desc = getattr(item, 'description', '') or ''
            parts.append(f"  {name}: {desc}")
    if prompts:
        parts.append("Prompts:")
        for name, item in prompts.items():
            desc = getattr(item, 'description', '') or ''
            parts.append(f"  {name}: {desc}")
    return "\n".join(parts) if parts else "No capabilities."
