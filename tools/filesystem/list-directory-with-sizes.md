# filesystem.list-directory-with-sizes

> List directory entries with sizes and summary. Only works within allowed directories.

## Signature

```python
await list-directory-with-sizes(path: str, sortBy: str = "name")
```

## Description

List directory entries with sizes and summary. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |
| `sortBy` | string |  | - |

## Usage Example

```python
result = await filesystem_binding.list-directory-with-sizes(
    # Add parameters here
)
```
