# filesystem.get-file-info

> Retrieve detailed metadata about a file or directory.

## Signature

```python
await get-file-info(path: str)
```

## Description

Retrieve detailed metadata about a file or directory.
Includes size, timestamps, and permissions. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | Path to the file |

## Usage Example

```python
result = await filesystem_binding.get-file-info(
    # Add parameters here
)
```
