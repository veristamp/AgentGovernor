# filesystem.read-multiple-files

> Read the contents of multiple files asynchronously.

## Signature

```python
await read-multiple-files(paths: list)
```

## Description

Read the contents of multiple files asynchronously.
Returns each file's content prefixed with its path, separated by '---'.
Continues on individual file errors. Only works within allowed directories.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `paths` | array | ✓ | Paths to the files |

## Usage Example

```python
result = await filesystem_binding.read-multiple-files(
    # Add parameters here
)
```
