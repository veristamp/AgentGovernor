# filesystem.create-directory

> Create a new directory or ensure it exists.

## Signature

```python
await create-directory(path: str)
```

## Description

Create a new directory or ensure it exists.
Creates nested directories if needed. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | Path to the directory |

## Usage Example

```python
result = await filesystem_binding.create-directory(
    # Add parameters here
)
```
