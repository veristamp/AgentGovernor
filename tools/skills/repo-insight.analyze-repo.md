# skills.repo-insight.analyze-repo

> Search docs and code graph for insights, then store a summary.

## Signature

```python
await repo-insight.analyze-repo(query: str, output_dir: str, note_key: str, write_report: bool = None)
```

## Description

Search docs and code graph for insights, then store a summary.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `query` | string | ✓ | - |
| `output_dir` | string | ✓ | - |
| `note_key` | string | ✓ | - |
| `write_report` | boolean |  | - |

## Usage Example

```python
result = await skills_binding.repo-insight.analyze-repo(
    # Add parameters here
)
```
