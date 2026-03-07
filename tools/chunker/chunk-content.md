# chunker.chunk-content

> Chunk raw content without reading from disk.

## Signature

```python
await chunk-content(content: str, filename: str, overlap_tokens: int = 300, max_tokens_text: int = 2000, split_code_max_lines: int = 50, split_table_rows: int = 100, use_treesitter: bool = true, emit_heading_chunks: bool = true, inject_headers: bool = true, include_chunks: bool = false)
```

## Description

Chunk raw content without reading from disk.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `content` | string | ✓ | - |
| `filename` | string | ✓ | - |
| `overlap_tokens` | integer |  | - |
| `max_tokens_text` | integer |  | - |
| `split_code_max_lines` | integer |  | - |
| `split_table_rows` | integer |  | - |
| `use_treesitter` | boolean |  | - |
| `emit_heading_chunks` | boolean |  | - |
| `inject_headers` | boolean |  | - |
| `include_chunks` | boolean |  | - |

## Usage Example

```python
result = await chunker_binding.chunk-content(
    # Add parameters here
)
```
