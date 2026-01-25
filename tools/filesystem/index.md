# Filesystem Tools

This server provides 16 tools.

## Available Tools

- [`read-text-file`](./read-text-file.md) - Read the complete contents of a file as UTF-8 text. Use head/tail to read only part of the file. Onl
- [`read-media-file`](./read-media-file.md) - Read an image/audio/binary file and return base64 data with MIME type. Only works within allowed dir
- [`read-multiple-files`](./read-multiple-files.md) - Read the contents of multiple text files. Continues on per-file errors. Only works within allowed di
- [`write-file`](./write-file.md) - Create or overwrite a file. Supports utf-8 text or base64 content. Atomic write. Only works within a
- [`create-directory`](./create-directory.md) - Create a directory (recursively). Only works within allowed directories.
- [`list-directory`](./list-directory.md) - List directory entries. Only works within allowed directories.
- [`list-directory-with-sizes`](./list-directory-with-sizes.md) - List directory entries with sizes and summary. Only works within allowed directories.
- [`directory-tree`](./directory-tree.md) - Recursive directory tree as JSON. Supports excludePatterns globs, max_depth, max_nodes. Only works w
- [`move-file`](./move-file.md) - Move/rename a file or directory. Fails if destination exists. Only works within allowed directories.
- [`search-files`](./search-files.md) - Recursively search for paths matching a glob pattern, relative to the search root. Only works within
- [`get-file-info`](./get-file-info.md) - Get file/directory metadata. Only works within allowed directories.
- [`list-allowed-directories`](./list-allowed-directories.md) - Show current allowed directories.
- [`edit-file`](./edit-file.md) - Structured replace edits for text files. Returns a unified diff. Use dry_run=true first.
- [`patch-span`](./patch-span.md) - Replace a 0-based character span [start:end] with new content. Optional sha256 guard on selected sli
- [`patch-lines`](./patch-lines.md) - Replace a 1-based inclusive line range with new content. Optional sha256 guard on selected slice. Us
- [`stitch-file`](./stitch-file.md) - Assemble a new file from character slices of existing files. Each graft copies [start:end] from a so
