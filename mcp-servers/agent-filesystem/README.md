# Agent Filesystem MCP Server

Secure, modular filesystem + patching MCP server.

Design goals:
- Strict directory jail via MCP Roots (recommended) or CLI args
- Cross-platform path normalization (Windows/UNC/WSL aware)
- Atomic writes with size limits
- Deterministic patch primitives (span/lines/replace) with drift guards
- Modular library layout so modules can be reused outside MCP

## Directory Access Control

This server requires at least one allowed directory.

1) Recommended: MCP Roots
- If the client supports Roots, the server requests roots on initialization and on `roots/list_changed`.
- Client-provided roots replace the server's allowed directory list.

2) CLI args
```bash
mcp-agent-filesystem /path/to/project /another/path
```

If you start without args and the client does not provide Roots, the server will refuse to operate.

## Tools

Filesystem:
- read_text_file (head/tail)
- read_media_file (image/audio/blob)
- read_multiple_files
- write_file (utf-8/base64)
- create_directory
- list_directory
- list_directory_with_sizes
- directory_tree (excludePatterns, max_depth, max_nodes)
- move_file
- search_files (glob)
- get_file_info
- list_allowed_directories

Patching / composition:
- edit_file (structured replace, dry_run default true)
- patch_span (0-based offsets)
- patch_lines (1-based inclusive line range)
- stitch_file (assemble file from slices)

## Development

```bash
cd mcp-servers/agent-filesystem
npm install
npm run build
node dist/index.js <allowed-dir>
```
