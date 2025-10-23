import asyncio
from mcp_client.manager import MCPClientManager
from mcp_client.config import Config

async def main():
    config = Config(mcp_servers={"filesystem": {"command": "python", "args": ["s2.py"]}})
    async with MCPClientManager(config) as manager:
        result = await manager.execute_action({
            "action_type": "tool",
            "action_name": "view_directory_ui",
            "arguments": {"path": "."}
        })
        print(result)  # Should show UI resource info and saved file path.

if __name__ == "__main__":
    asyncio.run(main())