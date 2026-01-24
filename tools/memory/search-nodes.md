# memory.search-nodes

> Search for nodes in the knowledge graph based on a query

## Signature

```python
await search-nodes(query: str)
```

## Description

Search for nodes in the knowledge graph based on a query

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `query` | string | ✓ | The search query to match against entity names, types, and observation content |

## Usage Example

```python
result = await memory_binding.search-nodes(
    # Add parameters here
)
```
