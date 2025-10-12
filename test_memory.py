import asyncio
import json
from mcp_client_manager2 import MCPClientManager, Config

async def test_memory_server_tools():
    # Load config (assumes mcp_servers.json with "Memory" server for stdio)
    config = Config.load("mcp_servers.json")
    
    async with MCPClientManager(config) as manager:
        await manager.wait_ready()
        
        if not manager.group or not manager.group.tools:
            print("No tools available. Check connection to Memory server.")
            return
        
        # Filter only Memory server tools
        memory_tools = {k: v for k, v in manager.group.tools.items() if 'memory-server' in k}
        if not memory_tools:
            print("No Memory server tools found. Ensure 'Memory' is configured in mcp_servers.json.")
            return
        
        print("Testing Memory MCP Server tools...\n")
        
        # Test read_graph (no args)
        action = {
            "action_type": "tool",
            "action_name": "memory-server.read_graph",
            "arguments": {}
        }
        result = await manager.execute_action(action)
        print(f"read_graph():\n{result}\n")
        
        # Test create_entities
        action = {
            "action_type": "tool",
            "action_name": "memory-server.create_entities",
            "arguments": {
                "entities": [
                    {
                        "name": "test_user",
                        "entityType": "person",
                        "observations": ["Likes Python", "Uses MCP"]
                    }
                ]
            }
        }
        result = await manager.execute_action(action)
        print(f"create_entities(sample):\n{result}\n")
        
        # Test create_relations
        action = {
            "action_type": "tool",
            "action_name": "memory-server.create_relations",
            "arguments": {
                "relations": [
                    {
                        "from": "test_user",
                        "to": "xAI",
                        "relationType": "works_at"
                    }
                ]
            }
        }
        result = await manager.execute_action(action)
        print(f"create_relations(sample):\n{result}\n")
        
        # Test add_observations
        action = {
            "action_type": "tool",
            "action_name": "memory-server.add_observations",
            "arguments": {
                "observations": [
                    {
                        "entityName": "test_user",
                        "contents": ["Test observation 1", "Test observation 2"]
                    }
                ]
            }
        }
        result = await manager.execute_action(action)
        print(f"add_observations(sample):\n{result}\n")
        
        # Test search_nodes
        action = {
            "action_type": "tool",
            "action_name": "memory-server.search_nodes",
            "arguments": {"query": "test"}
        }
        result = await manager.execute_action(action)
        print(f"search_nodes('test'):\n{result}\n")
        
        # Test open_nodes
        action = {
            "action_type": "tool",
            "action_name": "memory-server.open_nodes",
            "arguments": {"names": ["test_user"]}
        }
        result = await manager.execute_action(action)
        print(f"open_nodes(['test_user']):\n{result}\n")
        
        # Test delete_entities (cleanup)
        action = {
            "action_type": "tool",
            "action_name": "memory-server.delete_entities",
            "arguments": {"entityNames": ["test_user"]}
        }
        result = await manager.execute_action(action)
        print(f"delete_entities(['test_user']):\n{result}\n")
        
        # Final read_graph to verify cleanup
        action = {
            "action_type": "tool",
            "action_name": "memory-server.read_graph",
            "arguments": {}
        }
        result = await manager.execute_action(action)
        print(f"read_graph() after cleanup:\n{result}\n")
        
        print("All Memory server tests completed.")

if __name__ == "__main__":
    asyncio.run(test_memory_server_tools())