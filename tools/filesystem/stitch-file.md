# filesystem.stitch-file

> ADVANCED: Assemble a new file from character slices of existing files. Each graft copies [start:end] from a source. Requires precise byte offset calculation. Use dry_run=true first. Prefer patch_lines for most operations.

## Signature

```python
await stitch-file(grafts: list, output_path: str, overwrite: bool = false, dry_run: bool = true)
```

## Description

ADVANCED: Assemble a new file from character slices of existing files. Each graft copies [start:end] from a source. Requires precise byte offset calculation. Use dry_run=true first. Prefer patch_lines for most operations.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `grafts` | array | ✓ | - |
| `output_path` | string | ✓ | - |
| `overwrite` | boolean |  | - |
| `dry_run` | boolean |  | - |

## Usage Example

```python
result = await filesystem_binding.stitch-file(
    # Add parameters here
)
```
