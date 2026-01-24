# filesystem.move-file

> Move or rename files and directories.

## Signature

```python
await move-file(source: str, destination: str)
```

## Description

Move or rename files and directories.
Fails if destination exists. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `source` | string | ✓ | Source path |
| `destination` | string | ✓ | Destination path |

## Usage Example

```python
result = await filesystem_binding.move-file(
    # Add parameters here
)
```
