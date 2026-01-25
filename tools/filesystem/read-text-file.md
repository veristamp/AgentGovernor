# filesystem.read-text-file

> Read the complete contents of a file as UTF-8 text. Use head/tail to read only part of the file. Only works within allowed directories.

## Signature

```python
await read-text-file(path: str, head: int = None, tail: int = None)
```

## Description

Read the complete contents of a file as UTF-8 text. Use head/tail to read only part of the file. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |
| `head` | integer |  | - |
| `tail` | integer |  | - |

## Usage Example

```python
result = await filesystem_binding.read-text-file(
    # Add parameters here
)
```
