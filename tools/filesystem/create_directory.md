# filesystem.create_directory

> Create a new directory or ensure it exists.

## Signature

```python
await create_directory(path: str)
```

## Description

Create a new directory or ensure it exists.
Creates nested directories if needed. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |

## Usage Example

```python
result = await filesystem_binding.create_directory(
    # Add parameters here
)
```
