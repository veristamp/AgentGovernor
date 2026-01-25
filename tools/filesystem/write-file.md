# filesystem.write-file

> Create or overwrite a file. Supports utf-8 text or base64 content. Atomic write. Only works within allowed directories.

## Signature

```python
await write-file(path: str, content: str, encoding: str = "utf-8", max_bytes: int = 2000000, overwrite: bool = true)
```

## Description

Create or overwrite a file. Supports utf-8 text or base64 content. Atomic write. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |
| `content` | string | ✓ | - |
| `encoding` | string |  | - |
| `max_bytes` | integer |  | - |
| `overwrite` | boolean |  | - |

## Usage Example

```python
result = await filesystem_binding.write-file(
    # Add parameters here
)
```
