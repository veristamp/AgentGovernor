import asyncio
import json
from mcp_client import MCPClientManager, Config

async def generate_capabilities_md():
    config = Config.load("mcp_servers.json")
    
    async with MCPClientManager(config) as manager:
        await manager.wait_ready()
        
        if not manager.group:
            return "# MCP Capabilities\n\nNo servers connected or capabilities available."
        
        md_content = ["# MCP Capabilities\n"]
        
        # Aggregate and format
        for category, items in [("Tools", manager.group.tools), ("Resources", manager.group.resources), ("Prompts", manager.group.prompts)]:
            if items:
                md_content.append(f"## {category}\n")
                for name, item in sorted(items.items()):  # Sort for consistency
                    desc = getattr(item, 'description', 'No description available.')
                    md_content.append(f"### {name}\n")
                    md_content.append(f"{desc}\n")
                    
                    if category == "Tools" and hasattr(item, 'inputSchema'):
                        schema = item.inputSchema
                        if isinstance(schema, dict) and 'properties' in schema:
                            md_content.append("| Argument | Type | Required | Description |\n")
                            md_content.append("|----------|------|----------|-------------|\n")
                            required = schema.get('required', [])
                            for arg_name, arg_info in sorted(schema['properties'].items()):
                                arg_type = arg_info.get('type', 'unknown')
                                arg_desc = arg_info.get('description', '')
                                is_req = 'Yes' if arg_name in required else 'No'
                                md_content.append(f"| {arg_name} | {arg_type} | {is_req} | {arg_desc} |\n")
                            md_content.append("\n")  # Space after table
                    elif category == "Resources" or category == "Prompts":
                        # For resources/prompts, add any extra info if available
                        if hasattr(item, 'inputSchema') and item.inputSchema:
                            md_content.append("**Input Schema:**\n")
                            md_content.append(f"```json\n{json.dumps(item.inputSchema, indent=2)}\n```\n")
        
        return "\n".join(md_content)

async def main():
    md = await generate_capabilities_md()
    with open("mcp_capabilities.md", "w") as f:
        f.write(md)
    print("Generated mcp_capabilities.md")

if __name__ == "__main__":
    asyncio.run(main())