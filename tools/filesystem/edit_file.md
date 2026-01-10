# filesystem.edit_file

> Make line-based edits to a text file with flexible matching.

## Signature

```python
await edit_file(path: str, edits: list, dry_run: bool = True)
```

## Description

Make line-based edits to a text file with flexible matching.
Returns a git-style diff and a UI preview.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |
| `edits` | array | ✓ | - |
| `dry_run` | boolean |  | - |

## Usage Example

```python
result = await filesystem_binding.edit_file(
    # Add parameters here
)
```
