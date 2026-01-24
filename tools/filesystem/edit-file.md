# filesystem.edit-file

> Make line-based edits to a text file with flexible matching.

## Signature

```python
await edit-file(path: str, edits: list, dry_run: bool = true)
```

## Description

Make line-based edits to a text file with flexible matching.
Returns a git-style diff and a UI preview.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | Path to the file |
| `edits` | array | ✓ | List of edit operations |
| `dry_run` | boolean |  | Whether to perform a dry run |

## Usage Example

```python
result = await filesystem_binding.edit-file(
    # Add parameters here
)
```
