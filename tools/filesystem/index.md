# Filesystem Tools

This server provides 13 tools.

## Available Tools

- [`read_file`](./read_file.md) - Read the complete contents of a file asynchronously.
- [`read_multiple_files`](./read_multiple_files.md) - Read the contents of multiple files asynchronously.
- [`write_file`](./write_file.md) - Create or overwrite a file with new content asynchronously.
- [`edit_file`](./edit_file.md) - Make line-based edits to a text file with flexible matching.
- [`create_directory`](./create_directory.md) - Create a new directory or ensure it exists.
- [`list_directory`](./list_directory.md) - Get a detailed listing of directory contents.
- [`view_directory_ui`](./view_directory_ui.md) - Renders an interactive UI to display the contents of a directory.
- [`directory_tree`](./directory_tree.md) - Get a recursive tree view of files and directories as JSON.
- [`move_file`](./move_file.md) - Move or rename files and directories.
- [`search_files`](./search_files.md) - Recursively search for files matching a pattern.
- [`get_file_info`](./get_file_info.md) - Retrieve detailed metadata about a file or directory.
- [`list_allowed_directories`](./list_allowed_directories.md) - Returns the list of directories this server can access.
- [`set_allowed_directories`](./set_allowed_directories.md) - Update the list of allowed directories at runtime.
