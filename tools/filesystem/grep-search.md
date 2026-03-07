# filesystem.grep-search

> Search files for a regex pattern. Returns matching lines and file paths. Only works within allowed directories.

## Signature

```python
await grep-search(path: str, pattern: str, excludePatterns: list = , limit: int = 5000)
```

## Description

Search files for a regex pattern. Returns matching lines and file paths. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |
| `pattern` | string | ✓ | - |
| `excludePatterns` | array |  | - |
| `limit` | integer |  | - |

## Usage Example

```python
result = await filesystem_binding.grep-search(
    # Add parameters here
)
```
