# filesystem.search-files

> Recursively search for paths matching a glob pattern, relative to the search root. Only works within allowed directories.

## Signature

```python
await search-files(path: str, pattern: str, excludePatterns: list = , limit: int = 5000)
```

## Description

Recursively search for paths matching a glob pattern, relative to the search root. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |
| `pattern` | string | ✓ | - |
| `excludePatterns` | array |  | - |
| `limit` | integer |  | - |

## Usage Example

```python
result = await filesystem_binding.search-files(
    # Add parameters here
)
```
