# conceptharvester.harvest-chunk

> Extract and resolve concepts to weighted graph edges (requires DB).

## Signature

```python
await harvest-chunk(chunk: dict, root_topic: any = null, model_name: any = null, base_threshold: any = null, max_text_chars: any = null, include_scores: any = null)
```

## Description

Extract and resolve concepts to weighted graph edges (requires DB).

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `chunk` | object | ✓ | - |
| `root_topic` | any |  | - |
| `model_name` | any |  | - |
| `base_threshold` | any |  | - |
| `max_text_chars` | any |  | - |
| `include_scores` | any |  | - |

## Usage Example

```python
result = await conceptharvester_binding.harvest-chunk(
    # Add parameters here
)
```
