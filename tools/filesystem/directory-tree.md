# filesystem.directory-tree

> Recursive directory tree as JSON. Supports excludePatterns globs, max_depth, max_nodes. Only works within allowed directories.

## Signature

```python
await directory-tree(path: str, excludePatterns: list = , max_depth: int = 5, max_nodes: int = 5000)
```

## Description

Recursive directory tree as JSON. Supports excludePatterns globs, max_depth, max_nodes. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |
| `excludePatterns` | array |  | - |
| `max_depth` | integer |  | - |
| `max_nodes` | integer |  | - |

## Usage Example

```python
result = await filesystem_binding.directory-tree(
    # Add parameters here
)
```
