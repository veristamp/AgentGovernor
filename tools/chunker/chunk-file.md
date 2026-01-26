# chunker.chunk-file

> Chunk a single file into structured JSON output.

## Signature

```python
await chunk-file(file_path: str, output_path: any = null, overlap_tokens: int = 300, max_tokens_text: int = 2000, split_code_max_lines: int = 50, split_table_rows: int = 100, use_treesitter: bool = true, emit_heading_chunks: bool = true, inject_headers: bool = true, include_chunks: bool = false)
```

## Description

Chunk a single file into structured JSON output.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `file_path` | string | ✓ | - |
| `output_path` | any |  | - |
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
result = await chunker_binding.chunk-file(
    # Add parameters here
)
```
