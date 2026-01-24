# filesystem.read-file

> Read the complete contents of a file asynchronously.

## Signature

```python
await read-file(path: str, encoding: str = "utf-8")
```

## Description

Read the complete contents of a file asynchronously.

Args:
    path: Path to the file
    encoding: "utf-8" for text files (default), "base64" for binary files (xlsx, images, pdf)

For binary files like Excel, use encoding="base64" to get base64-encoded content.
Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | Path to the file |
| `encoding` | string |  | "utf-8" for text files (default), "base64" for binary files (xlsx, images, pdf) |

## Usage Example

```python
result = await filesystem_binding.read-file(
    # Add parameters here
)
```
