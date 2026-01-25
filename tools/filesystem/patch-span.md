# filesystem.patch-span

> Replace a 0-based character span [start:end] with new content. Optional sha256 guard on selected slice. Use dry_run=true first.

## Signature

```python
await patch-span(path: str, start: int, end: int, new_content: str, expected_sha256: str = None, allow_drift: bool = false, dry_run: bool = true)
```

## Description

Replace a 0-based character span [start:end] with new content. Optional sha256 guard on selected slice. Use dry_run=true first.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | ✓ | - |
| `start` | integer | ✓ | - |
| `end` | integer | ✓ | - |
| `new_content` | string | ✓ | - |
| `expected_sha256` | string |  | - |
| `allow_drift` | boolean |  | - |
| `dry_run` | boolean |  | - |

## Usage Example

```python
result = await filesystem_binding.patch-span(
    # Add parameters here
)
```
