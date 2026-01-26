# skills.docs-to-files.fetch-and-store

> Resolve a library id, fetch docs, and write a markdown file.

## Signature

```python
await docs-to-files.fetch-and-store(library: str, topic: str, output_dir: str, file_name: str = None, mode: str = None)
```

## Description

Resolve a library id, fetch docs, and write a markdown file.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `library` | string | ✓ | - |
| `topic` | string | ✓ | - |
| `output_dir` | string | ✓ | - |
| `file_name` | string |  | - |
| `mode` | string |  | - |

## Usage Example

```python
result = await skills_binding.docs-to-files.fetch-and-store(
    # Add parameters here
)
```
