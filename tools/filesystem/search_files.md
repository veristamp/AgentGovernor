# filesystem.search_files

> Recursively search for files matching a pattern.

## Signature

```python
await search_files(path: str, pattern: str, exclude_patterns: list = [])
```

## Description

Recursively search for files matching a pattern.
Case-insensitive, returns full paths. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |
| `pattern` | string | ✓ | - |
| `exclude_patterns` | array |  | - |

## Usage Example

```python
result = await filesystem_binding.search_files(
    # Add parameters here
)
```
