# filesystem.write-file

> Create or overwrite a file with new content asynchronously.

## Signature

```python
await write-file(path: str, content: str, encoding: str = "utf-8", max_bytes: float = 2000000)
```

## Description

Create or overwrite a file with new content asynchronously.

Args:
    path: Path to the file
    content: Content to write (string or base64-encoded for binary)
    encoding: "utf-8" for text files (default), "base64" for binary files

For binary files, pass base64-encoded content and set encoding="base64".
Overwrites existing files without warning. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | Path to the file |
| `content` | string | ✓ | Content to write (string or base64-encoded for binary) |
| `encoding` | string |  | "utf-8" for text files (default), "base64" for binary files |
| `max_bytes` | number |  | Maximum bytes to write |

## Usage Example

```python
result = await filesystem_binding.write-file(
    # Add parameters here
)
```
