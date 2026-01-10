# filesystem.move_file

> Move or rename files and directories.

## Signature

```python
await move_file(source: str, destination: str)
```

## Description

Move or rename files and directories.
Fails if destination exists. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `source` | string | ✓ | - |
| `destination` | string | ✓ | - |

## Usage Example

```python
result = await filesystem_binding.move_file(
    # Add parameters here
)
```
