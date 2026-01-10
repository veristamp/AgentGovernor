# filesystem.read_multiple_files

> Read the contents of multiple files asynchronously.

## Signature

```python
await read_multiple_files(paths: list)
```

## Description

Read the contents of multiple files asynchronously.
Returns each file's content prefixed with its path, separated by '---'.
Continues on individual file errors. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `paths` | array | ✓ | - |

## Usage Example

```python
result = await filesystem_binding.read_multiple_files(
    # Add parameters here
)
```
