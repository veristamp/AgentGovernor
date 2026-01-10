---
name: filesystem
description: "File system operations skill for reading, writing, and managing files and directories."
version: 2
author: AgentGovernor
license: MIT
---

# Filesystem Skill

High-level file operations for common patterns. Use this skill when you need to work with files.

> **Raw Tool Docs:** See `tools/filesystem/` for complete API schemas.

## When to Use This Skill

- Reading/writing text files
- Listing directory contents
- Searching for files by pattern
- Getting file metadata
- Managing directories

## Available Helpers

Import this skill to use convenient helper functions:

```python
from skills import filesystem
```

| Function | Description |
|----------|-------------|
| `list_files(path)` | List only files (not directories) |
| `list_dirs(path)` | List only directories |
| `list_all(path)` | List all items |
| `find_by_extension(path, ext)` | Find files with specific extension |
| `read(path)` | Read file contents |
| `write(path, content)` | Write to file |
| `append(path, content)` | Append to file |
| `exists(path)` | Check if path exists |
| `info(path)` | Get file/directory metadata |
| `search(path, pattern)` | Glob pattern search |
| `mkdir(path)` | Create directory |
| `move(src, dest)` | Move/rename |
| `count_lines(path)` | Count lines in file |
| `read_json(path)` | Read and parse JSON |
| `write_json(path, data)` | Write JSON to file |

## Example Usage

```python
from skills import filesystem

async def main():
    # Find all Python files
    py_files = await filesystem.find_by_extension(".", ".py")
    
    # Count total lines
    total = 0
    for f in py_files:
        total += await filesystem.count_lines(f)
    
    return {"files": len(py_files), "lines": total}
```

## Common Patterns

### List and Filter
```python
files = await filesystem.list_files(".")
python_files = [f for f in files if f.endswith('.py')]
```

### Read-Process-Write
```python
content = await filesystem.read("input.txt")
processed = content.upper()
await filesystem.write("output.txt", processed)
```

### JSON Configuration
```python
config = await filesystem.read_json("config.json")
config["updated"] = True
await filesystem.write_json("config.json", config)
```
