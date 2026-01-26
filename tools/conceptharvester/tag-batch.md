# conceptharvester.tag-batch

> Extract concepts from multiple chunks (no DB resolution).

## Signature

```python
await tag-batch(chunks: list, root_topic: any = null, disambiguate_noise: bool = true, model_name: any = null, base_threshold: any = null, max_text_chars: any = null, include_scores: any = null)
```

## Description

Extract concepts from multiple chunks (no DB resolution).

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `chunks` | array | ✓ | - |
| `root_topic` | any |  | - |
| `disambiguate_noise` | boolean |  | - |
| `model_name` | any |  | - |
| `base_threshold` | any |  | - |
| `max_text_chars` | any |  | - |
| `include_scores` | any |  | - |

## Usage Example

```python
result = await conceptharvester_binding.tag-batch(
    # Add parameters here
)
```
