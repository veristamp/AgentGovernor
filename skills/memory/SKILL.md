---
name: memory
description: "Knowledge graph operations for storing and retrieving entities and relationships."
version: 2
author: AgentGovernor
license: MIT
---

# Memory/Knowledge Graph Skill

Persistent storage of entities and relationships using a knowledge graph.

> **Raw Tool Docs:** See `tools/memory/` for complete API schemas.

## When to Use This Skill

- Storing user preferences or context
- Building knowledge graphs from data
- Remembering facts across sessions
- Creating relationships between concepts

## Available Helpers

```python
from skills import memory
```

| Function | Description |
|----------|-------------|
| `remember(name, type, facts)` | Store an entity with observations |
| `relate(from_name, to_name, relation)` | Create a relationship |
| `search(query)` | Search for matching entities |
| `recall(name)` | Get a specific entity by name |
| `recall_many(names)` | Get multiple entities |
| `forget(name)` | Delete an entity |
| `forget_relation(from_n, to_n, rel)` | Delete a relationship |
| `add_observation(name, fact)` | Add fact to existing entity |
| `get_related(name)` | Get all entities related to one |
| `read_graph()` | Get entire knowledge graph |
| `summarize()` | Get stats about the graph |

## Example Usage

```python
from skills import memory

async def main():
    # Remember a user preference
    await memory.remember(
        "user-prefs", 
        "Preferences",
        ["Prefers dark mode", "Timezone: PST"]
    )
    
    # Create a relationship
    await memory.relate("user-prefs", "dark-theme", "uses")
    
    # Search later
    results = await memory.search("dark mode")
    
    return {"found": len(results)}
```

## Common Patterns

### Store and Recall
```python
await memory.remember("project-x", "Project", ["Started Jan 2024"])
info = await memory.recall("project-x")
```

### Build Knowledge Graph
```python
# Create entities
await memory.remember("Alice", "Person", ["Team lead"])
await memory.remember("Bob", "Person", ["Developer"])
await memory.remember("Project", "Project", ["Mobile app"])

# Create relationships
await memory.relate("Alice", "Project", "leads")
await memory.relate("Bob", "Project", "develops")
```

### Search and Extend
```python
results = await memory.search("developer")
for entity in results:
    await memory.add_observation(entity["name"], "Active in 2024")
```
