# filesystem.directory_tree

> Get a recursive tree view of files and directories as JSON.

## Signature

```python
await directory_tree(path: str, max_depth: int = 5, max_nodes: int = 5000)
```

## Description

Get a recursive tree view of files and directories as JSON.
Includes 'name' and 'type', with 'children' for directories. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |
| `max_depth` | integer |  | - |
| `max_nodes` | integer |  | - |

## Usage Example

```python
result = await filesystem_binding.directory_tree(
    # Add parameters here
)
```
