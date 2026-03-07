# chunker.chunk-directory

> Chunk all supported files in a directory.

## Signature

```python
await chunk-directory(directory: str, recursive: bool = false, extensions: any = null, output_suffix: str = "_structured.json", overlap_tokens: int = 300, max_tokens_text: int = 2000, split_code_max_lines: int = 50, split_table_rows: int = 100, use_treesitter: bool = true, emit_heading_chunks: bool = true, inject_headers: bool = true, include_results: bool = false)
```

## Description

Chunk all supported files in a directory.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `directory` | string | ✓ | - |
| `recursive` | boolean |  | - |
| `extensions` | any |  | - |
| `output_suffix` | string |  | - |
| `overlap_tokens` | integer |  | - |
| `max_tokens_text` | integer |  | - |
| `split_code_max_lines` | integer |  | - |
| `split_table_rows` | integer |  | - |
| `use_treesitter` | boolean |  | - |
| `emit_heading_chunks` | boolean |  | - |
| `inject_headers` | boolean |  | - |
| `include_results` | boolean |  | - |

## Usage Example

```python
result = await chunker_binding.chunk-directory(
    # Add parameters here
)
```
