"""
Filesystem Skill Library.

These functions are injected into the sandbox and use binding proxies internally.
The `_binding` object is injected at runtime by the skill injector.

NOTE: list_directory returns string format "[DIR] name\n[FILE] name"
      This lib parses that output into structured data.

Usage in sandbox:
    from skills import filesystem
    files = await filesystem.list_files(".")
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional


def _parse_listing(listing: str) -> List[Dict[str, Any]]:
    """
    Parse the list_directory output string into structured data.
    
    Input format: "[DIR] folder\n[FILE] file.txt"
    Output: [{"name": "folder", "type": "directory"}, {"name": "file.txt", "type": "file"}]
    """
    items = []
    for line in listing.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('[DIR]'):
            name = line[5:].strip()
            items.append({"name": name, "type": "directory"})
        elif line.startswith('[FILE]'):
            name = line[6:].strip()
            items.append({"name": name, "type": "file"})
    return items


async def list_files(path: str = ".") -> List[str]:
    """
    List all files (not directories) at the given path.
    
    Returns:
        List of filenames
    """
    listing = await _binding.list_directory(path=path)
    items = _parse_listing(listing)
    return [f['name'] for f in items if f['type'] == 'file']


async def list_dirs(path: str = ".") -> List[str]:
    """
    List all directories at the given path.
    
    Returns:
        List of directory names
    """
    listing = await _binding.list_directory(path=path)
    items = _parse_listing(listing)
    return [f['name'] for f in items if f['type'] == 'directory']


async def list_all(path: str = ".") -> List[Dict[str, Any]]:
    """
    List all items (files and directories) at the given path.
    
    Returns:
        List of item info dicts with 'name' and 'type'
    """
    listing = await _binding.list_directory(path=path)
    return _parse_listing(listing)


async def find_by_extension(path: str, ext: str) -> List[str]:
    """
    Find all files with the given extension.
    
    Args:
        path: Directory to search
        ext: Extension to match (e.g., ".py", ".json")
    
    Returns:
        List of filenames matching the extension
    """
    if not ext.startswith('.'):
        ext = '.' + ext
    files = await list_files(path)
    return [f for f in files if f.endswith(ext)]


async def read(path: str) -> str:
    """
    Read the contents of a text file.
    
    Args:
        path: Path to the file
    
    Returns:
        File contents as a string
    """
    return await _binding.read_file(path=path)


async def write(path: str, content: str) -> str:
    """
    Write content to a file. Creates the file if it doesn't exist.
    
    Args:
        path: Path to write to
        content: String content to write
    
    Returns:
        Success message
    """
    return await _binding.write_file(path=path, content=content)


async def append(path: str, content: str) -> str:
    """
    Append content to a file. Creates the file if it doesn't exist.
    
    Args:
        path: Path to append to
        content: String content to append
    
    Returns:
        Success message
    """
    try:
        existing = await _binding.read_file(path=path)
    except:
        existing = ""
    return await _binding.write_file(path=path, content=existing + content)


async def exists(path: str) -> bool:
    """
    Check if a file or directory exists.
    
    Args:
        path: Path to check
    
    Returns:
        True if exists, False otherwise
    """
    try:
        await _binding.get_file_info(path=path)
        return True
    except:
        return False


async def info(path: str) -> str:
    """
    Get detailed information about a file or directory.
    
    Args:
        path: Path to get info for
    
    Returns:
        Info string with size, modified, type, etc.
    """
    return await _binding.get_file_info(path=path)


async def search(path: str, pattern: str) -> List[str]:
    """
    Search for files matching a pattern.
    
    Args:
        path: Directory to search in
        pattern: Pattern to match (e.g., "*.py" or just "py")
    
    Returns:
        List of matching file paths
    """
    result = await _binding.search_files(path=path, pattern=pattern)
    if result == "No matches found":
        return []
    return result.strip().split('\n')


async def mkdir(path: str) -> str:
    """
    Create a directory (and parent directories if needed).
    
    Args:
        path: Path of directory to create
    
    Returns:
        Success message
    """
    return await _binding.create_directory(path=path)


async def move(source: str, destination: str) -> str:
    """
    Move or rename a file or directory.
    
    Args:
        source: Source path
        destination: Destination path
    
    Returns:
        Success message
    """
    return await _binding.move_file(source=source, destination=destination)


async def count_lines(path: str) -> int:
    """
    Count the number of lines in a text file.
    
    Args:
        path: Path to the file
    
    Returns:
        Number of lines
    """
    content = await _binding.read_file(path=path)
    return len(content.split('\n'))


async def read_json(path: str) -> Any:
    """
    Read and parse a JSON file.
    
    Args:
        path: Path to the JSON file
    
    Returns:
        Parsed JSON data
    """
    import json
    content = await _binding.read_file(path=path)
    return json.loads(content)


async def write_json(path: str, data: Any, indent: int = 2) -> str:
    """
    Write data to a JSON file.
    
    Args:
        path: Path to write to
        data: Data to serialize as JSON
        indent: Indentation level (default 2)
    
    Returns:
        Success message
    """
    import json
    content = json.dumps(data, indent=indent)
    return await _binding.write_file(path=path, content=content)
