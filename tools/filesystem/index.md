# Filesystem Tools

This server provides 13 tools.

## Available Tools

- [`read-file`](./read-file.md) - Read the complete contents of a file asynchronously.
- [`read-multiple-files`](./read-multiple-files.md) - Read the contents of multiple files asynchronously.
- [`write-file`](./write-file.md) - Create or overwrite a file with new content asynchronously.
- [`edit-file`](./edit-file.md) - Make line-based edits to a text file with flexible matching.
- [`create-directory`](./create-directory.md) - Create a new directory or ensure it exists.
- [`list-directory`](./list-directory.md) - Get a detailed listing of directory contents.
- [`view-directory-ui`](./view-directory-ui.md) - Renders an interactive UI to display the contents of a directory.
- [`directory-tree`](./directory-tree.md) - Get a recursive tree view of files and directories as JSON.
- [`move-file`](./move-file.md) - Move or rename files and directories.
- [`search-files`](./search-files.md) - Recursively search for files matching a pattern.
- [`get-file-info`](./get-file-info.md) - Retrieve detailed metadata about a file or directory.
- [`list-allowed-directories`](./list-allowed-directories.md) - Returns the list of directories this server can access.
- [`set-allowed-directories`](./set-allowed-directories.md) - Update the list of allowed directories at runtime.
