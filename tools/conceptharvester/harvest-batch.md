# conceptharvester.harvest-batch

> Batch extract and resolve concepts to graph edges (requires DB).

## Signature

```python
await harvest-batch(chunks: list, root_topic: any = null, model_name: any = null, base_threshold: any = null, max_text_chars: any = null, include_scores: any = null)
```

## Description

Batch extract and resolve concepts to graph edges (requires DB).

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `chunks` | array | ✓ | - |
| `root_topic` | any |  | - |
| `model_name` | any |  | - |
| `base_threshold` | any |  | - |
| `max_text_chars` | any |  | - |
| `include_scores` | any |  | - |

## Usage Example

```python
result = await conceptharvester_binding.harvest-batch(
    # Add parameters here
)
```
