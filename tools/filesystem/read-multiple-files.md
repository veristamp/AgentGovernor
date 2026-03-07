# filesystem.read-multiple-files

> Read the contents of multiple text files. Continues on per-file errors. Only works within allowed directories.

## Signature

```python
await read-multiple-files(paths: list)
```

## Description

Read the contents of multiple text files. Continues on per-file errors. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `paths` | array | ✓ | - |

## Usage Example

```python
result = await filesystem_binding.read-multiple-files(
    # Add parameters here
)
```
