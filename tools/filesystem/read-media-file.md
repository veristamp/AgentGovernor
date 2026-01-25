# filesystem.read-media-file

> Read an image/audio/binary file and return base64 data with MIME type. Only works within allowed directories.

## Signature

```python
await read-media-file(path: str)
```

## Description

Read an image/audio/binary file and return base64 data with MIME type. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |

## Usage Example

```python
result = await filesystem_binding.read-media-file(
    # Add parameters here
)
```
