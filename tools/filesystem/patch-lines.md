# filesystem.patch-lines

> Replace a 1-based inclusive line range with new content. Optional sha256 guard on selected slice. Use dry_run=true first.

## Signature

```python
await patch-lines(path: str, start_line: int, end_line: int, new_content: str, expected_sha256: str = None, allow_drift: bool = false, dry_run: bool = true)
```

## Description

Replace a 1-based inclusive line range with new content. Optional sha256 guard on selected slice. Use dry_run=true first.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |
| `start_line` | integer | ✓ | - |
| `end_line` | integer | ✓ | - |
| `new_content` | string | ✓ | - |
| `expected_sha256` | string |  | - |
| `allow_drift` | boolean |  | - |
| `dry_run` | boolean |  | - |

## Usage Example

```python
result = await filesystem_binding.patch-lines(
    # Add parameters here
)
```
