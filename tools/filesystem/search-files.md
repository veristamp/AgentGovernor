# filesystem.search-files

> Recursively search for files matching a pattern.

## Signature

```python
await search-files(path: str, pattern: str, exclude_patterns: list = )
```

## Description

Recursively search for files matching a pattern.
Case-insensitive, returns full paths. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | Path to search in |
| `pattern` | string | ✓ | Search pattern |
| `exclude_patterns` | array |  | Patterns to exclude |

## Usage Example

```python
result = await filesystem_binding.search-files(
    # Add parameters here
)
```
