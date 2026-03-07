# filesystem.edit-file

> Structured replace edits for text files. Returns a unified diff. Use dry_run=true first.

## Signature

```python
await edit-file(path: str, edits: list, dry_run: bool = true, require_all: bool = true)
```

## Description

Structured replace edits for text files. Returns a unified diff. Use dry_run=true first.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |
| `edits` | array | ✓ | - |
| `dry_run` | boolean |  | - |
| `require_all` | boolean |  | - |

## Usage Example

```python
result = await filesystem_binding.edit-file(
    # Add parameters here
)
```
