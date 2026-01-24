# filesystem.directory-tree

> Get a recursive tree view of files and directories as JSON.

## Signature

```python
await directory-tree(path: str, max_depth: float = 5, max_nodes: float = 5000)
```

## Description

Get a recursive tree view of files and directories as JSON.
Includes 'name' and 'type', with 'children' for directories. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | Path to the directory |
| `max_depth` | number |  | Maximum depth of the tree |
| `max_nodes` | number |  | Maximum number of nodes in the tree |

## Usage Example

```python
result = await filesystem_binding.directory-tree(
    # Add parameters here
)
```
