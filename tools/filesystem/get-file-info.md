# filesystem.get-file-info

> Get file/directory metadata. Only works within allowed directories.

## Signature

```python
await get-file-info(path: str)
```

## Description

Get file/directory metadata. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |

## Usage Example

```python
result = await filesystem_binding.get-file-info(
    # Add parameters here
)
```
