# filesystem.get_file_info

> Retrieve detailed metadata about a file or directory.

## Signature

```python
await get_file_info(path: str)
```

## Description

Retrieve detailed metadata about a file or directory.
Includes size, timestamps, and permissions. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |

## Usage Example

```python
result = await filesystem_binding.get_file_info(
    # Add parameters here
)
```
