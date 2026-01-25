# filesystem.move-file

> Move/rename a file or directory. Fails if destination exists. Only works within allowed directories.

## Signature

```python
await move-file(source: str, destination: str)
```

## Description

Move/rename a file or directory. Fails if destination exists. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `source` | string | ✓ | - |
| `destination` | string | ✓ | - |

## Usage Example

```python
result = await filesystem_binding.move-file(
    # Add parameters here
)
```
