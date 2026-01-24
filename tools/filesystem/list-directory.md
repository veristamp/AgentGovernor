# filesystem.list-directory

> Get a detailed listing of directory contents.

## Signature

```python
await list-directory(path: str)
```

## Description

Get a detailed listing of directory contents.
Prefixes entries with [DIR] or [FILE]. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | Path to the directory |

## Usage Example

```python
result = await filesystem_binding.list-directory(
    # Add parameters here
)
```
