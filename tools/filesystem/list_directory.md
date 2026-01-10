# filesystem.list_directory

> Get a detailed listing of directory contents.

## Signature

```python
await list_directory(path: str)
```

## Description

Get a detailed listing of directory contents.
Prefixes entries with [DIR] or [FILE]. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |

## Usage Example

```python
result = await filesystem_binding.list_directory(
    # Add parameters here
)
```
