# filesystem.stitch-file

> Assemble a new file from character slices of existing files. Each graft copies [start:end] from a source. Use dry_run=true first.

## Signature

```python
await stitch-file(grafts: list, output_path: str, overwrite: bool = false, dry_run: bool = true)
```

## Description

Assemble a new file from character slices of existing files. Each graft copies [start:end] from a source. Use dry_run=true first.

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
