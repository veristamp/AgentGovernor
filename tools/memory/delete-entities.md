# memory.delete-entities

> Delete multiple entities and their associated relations from the knowledge graph

## Signature

```python
await delete-entities(entityNames: list)
```

## Description

Delete multiple entities and their associated relations from the knowledge graph

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `entityNames` | array | ✓ | An array of entity names to delete |

## Usage Example

```python
result = await memory_binding.delete-entities(
    # Add parameters here
)
```
