#!/usr/bin/env python3

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, List, Union
from mcp.server.fastmcp import FastMCP, Context
import os
import sys
import stat
import argparse
import logging
from pathlib import Path
import json
import re
from difflib import unified_diff
import aiofiles
from pydantic import BaseModel, ValidationError
import urllib.parse
from functools import wraps
import base64
from config import get_logger
def create_ui_resource(options: dict) -> dict:
    """Create a UIResource object compatible with MCP-UI spec.

    Args:
        options: Dict with keys:
            - uri: string (required)
            - content: dict with 'type' and content (required)
            - encoding: 'text' or 'blob' (required)
            - metadata: optional dict

    Returns:
        Dict representing the UIResource
    """
    uri = options.get("uri")
    if not uri:
        raise ValueError("URI is required for UIResource")

    content = options.get("content")
    if not content or "type" not in content:
        raise ValueError("Content with type is required")

    encoding = options.get("encoding", "text")
    if encoding not in ["text", "blob"]:
        raise ValueError("Encoding must be 'text' or 'blob'")

    # Determine mimeType based on content type
    content_type = content.get("type")
    mime_type_map = {
        "rawHtml": "text/html",
        "externalUrl": "text/uri-list",
        "remoteDom": "application/vnd.mcp-ui.remote-dom"
    }
    mime_type = mime_type_map.get(content_type, "text/plain")

    # Build the resource dict
    resource = {
        "uri": uri,
        "mimeType": mime_type
    }

    # Handle content based on type and encoding
    if content_type == "rawHtml":
        html_string = content.get("htmlString", "")
        if encoding == "text":
            resource["text"] = html_string
        else:
            resource["blob"] = base64.b64encode(html_string.encode('utf-8')).decode('utf-8')
    elif content_type == "externalUrl":
        url = content.get("iframeUrl", "")
        if encoding == "text":
            resource["text"] = url
        else:
            resource["blob"] = base64.b64encode(url.encode('utf-8')).decode('utf-8')
    elif content_type == "remoteDom":
        script = content.get("script", "")
        if encoding == "text":
            resource["text"] = script
        else:
            resource["blob"] = base64.b64encode(script.encode('utf-8')).decode('utf-8')
    else:
        raise ValueError(f"Unsupported content type: {content_type}")

    # Add optional metadata
    metadata = options.get("metadata")
    if metadata:
        resource["metadata"] = metadata

    return {"resource": resource}
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = get_logger("file_patcher.filesystem")

parser = argparse.ArgumentParser(description="Secure Filesystem MCP Server")
parser.add_argument("dirs", nargs="*", help="Allowed directories (defaults to current directory if none provided)")
args = parser.parse_args()
default_dir = Path(".").resolve()
provided_dirs = [Path(d).resolve() for d in args.dirs] if args.dirs else [default_dir]

# If no directories provided via command line, try to be more permissive for MCP usage
# Check if we're being run in an MCP context (no explicit dirs specified)
if len(args.dirs) == 0:
    # For MCP usage, allow the current directory and common development paths
    allowed_directories = [default_dir]
    # Also allow parent directories for better MCP compatibility
    current_path = default_dir
    for _ in range(3):  # Allow up to 3 levels up
        parent = current_path.parent
        if parent != current_path:  # Avoid infinite loop
            allowed_directories.append(parent)
            current_path = parent
        else:
            break
else:
    allowed_directories = [d for d in provided_dirs if os.path.isdir(d) and os.access(d, os.R_OK)] or [default_dir]

# Normalize paths
def normalize_path(p: str) -> str:
    return str(Path(p).resolve())

def expand_home(filepath: str) -> str:
    return os.path.expanduser(filepath)

def _is_within(path: str, root: str) -> bool:
    return os.path.commonpath([os.path.abspath(path), os.path.abspath(root)]) == os.path.abspath(root)

def validate_path_sync(requested_path: str) -> str:
    # expand ~ and normalize
    requested_path = expand_home(requested_path)
    absolute = normalize_path(requested_path)
    if not allowed_directories:
        raise Exception("No allowed directories configured")
    # guard against traversal and symlinks out of jail
    if not any(_is_within(absolute, str(d)) for d in allowed_directories):
        raise Exception(f"Access denied - path outside allowed directories: {absolute}")
    real_path = os.path.realpath(absolute)
    if not any(_is_within(real_path, str(d)) for d in allowed_directories):
        raise Exception("Access denied - symlink target outside allowed directories")
    return real_path

async def validate_path(requested_path: str) -> str:
    # async façade so tools can 'await' consistently
    return validate_path_sync(requested_path)

# Server lifecycle
@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, str]]:
    if not allowed_directories:
        logger.error("No valid directories available after filtering")
        raise Exception("No valid directories available")
    logger.info(f"Starting secure filesystem server with allowed directories: {', '.join(map(str, allowed_directories))}")
    yield {"status": "running"}
    logger.info("Shutting down filesystem server")

# Create MCP server
mcp = FastMCP(name="secure-filesystem-server", lifespan=server_lifespan)

# Input schemas
class ReadFileArgs(BaseModel):
    path: str
    encoding: str = "utf-8"  # Use 'base64' for binary files

class ReadMultipleFilesArgs(BaseModel):
    paths: List[str]

class WriteFileArgs(BaseModel):
    path: str
    content: str
    encoding: str = "utf-8"  # Use 'base64' for binary files

class EditOperation(BaseModel):
    oldText: str
    newText: str

class EditFileArgs(BaseModel):
    path: str
    edits: List[EditOperation]
    dry_run: bool = False

class CreateDirectoryArgs(BaseModel):
    path: str

class ListDirectoryArgs(BaseModel):
    path: str

class DirectoryTreeArgs(BaseModel):
    path: str

class MoveFileArgs(BaseModel):
    source: str
    destination: str

class SearchFilesArgs(BaseModel):
    path: str
    pattern: str
    exclude_patterns: List[str] = []

class GetFileInfoArgs(BaseModel):
    path: str

class SetAllowedDirectoriesArgs(BaseModel):
    directories: List[str]

# File info structure
class FileInfo:
    def __init__(self, path: str):
        stats = os.stat(path)
        self.size = stats.st_size
        self.created = stats.st_ctime
        self.modified = stats.st_mtime
        self.accessed = stats.st_atime
        self.is_directory = stat.S_ISDIR(stats.st_mode)
        self.is_file = stat.S_ISREG(stats.st_mode)
        self.permissions = oct(stats.st_mode)[-3:]

# Utilities
async def _search_files_impl(root_path: str, pattern: str, exclude_patterns: List[str] = [], limit: int = 5000) -> List[str]:
    results = []
    pattern = pattern.lower()
    for root, dirs, files in os.walk(root_path):
        try:
            await validate_path(root)
            for name in dirs + files:
                full_path = os.path.join(root, name)
                relative_path = os.path.relpath(full_path, root_path)
                # use re.search (not match) so excludes like "delta" work anywhere in path
                if any(re.search(ex, relative_path) for ex in exclude_patterns):
                    continue
                if pattern in name.lower():
                    results.append(full_path)
                if len(results) >= limit:
                    break
        except Exception as e:
            logger.debug(f"Skipping invalid path {root}: {e}")
    return results

def normalize_line_endings(text: str) -> str:
    return text.replace('\r\n', '\n')

def create_unified_diff(original: str, modified: str, filepath: str) -> str:
    original_lines = normalize_line_endings(original).splitlines()
    modified_lines = normalize_line_endings(modified).splitlines()
    diff = unified_diff(original_lines, modified_lines, fromfile=filepath, tofile=filepath, lineterm="")
    return "\n".join(diff)

# Error handling decorator (fixed to preserve function name)
def handle_errors(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValidationError as e:
            return f"Error: Invalid arguments - {e}"
        except Exception as e:
            return f"Error: {str(e)}"
    return wrapper

# Tools
@mcp.tool()
@handle_errors
async def read_file(path: str, ctx: Context, encoding: str = "utf-8") -> str:
    """Read the complete contents of a file asynchronously.
    
    Args:
        path: Path to the file
        encoding: 'utf-8' for text files (default), 'base64' for binary files (xlsx, images, pdf)
    
    For binary files like Excel, use encoding='base64' to get base64-encoded content.
    Only works within allowed directories."""
    parsed = ReadFileArgs(path=path, encoding=encoding)
    valid_path = await validate_path(parsed.path)
    
    if parsed.encoding == "base64":
        # Binary mode - return base64 encoded content
        async with aiofiles.open(valid_path, 'rb') as f:
            content = await f.read()
        logger.info(f"Read binary file: {valid_path} ({len(content)} bytes)")
        return base64.b64encode(content).decode('ascii')
    else:
        # Text mode - return as string
        async with aiofiles.open(valid_path, 'r', encoding=parsed.encoding) as f:
            content = await f.read()
        logger.info(f"Read file: {valid_path}")
        return content

@mcp.tool()
@handle_errors
async def read_multiple_files(paths: List[str], ctx: Context) -> str:
    """Read the contents of multiple files asynchronously.
    Returns each file's content prefixed with its path, separated by '---'.
    Continues on individual file errors. Only works within allowed directories."""
    parsed = ReadMultipleFilesArgs(paths=paths)
    results = []
    for path in parsed.paths:
        try:
            valid_path = await validate_path(path)
            async with aiofiles.open(valid_path, 'r', encoding='utf-8') as f:
                results.append(f"{path}:\n{await f.read()}")
        except Exception as e:
            results.append(f"{path}: Error - {str(e)}")
    logger.info(f"Read multiple files: {', '.join(parsed.paths)}")
    return "\n---\n".join(results)

@mcp.tool()
@handle_errors
async def write_file(path: str, content: str, ctx: Context, encoding: str = "utf-8", max_bytes: int = 2_000_000) -> str:
    """Create or overwrite a file with new content asynchronously.
    
    Args:
        path: Path to the file
        content: Content to write (string or base64-encoded for binary)
        encoding: 'utf-8' for text files (default), 'base64' for binary files
    
    For binary files, pass base64-encoded content and set encoding='base64'.
    Overwrites existing files without warning. Only works within allowed directories."""
    parsed = WriteFileArgs(path=path, content=content, encoding=encoding)
    valid_path = await validate_path(parsed.path)
    
    if parsed.encoding == "base64":
        # Decode base64 and write as binary
        try:
            binary_content = base64.b64decode(parsed.content)
        except Exception as e:
            raise Exception(f"Invalid base64 content: {e}")
        
        if len(binary_content) > max_bytes:
            raise Exception(f"Refusing to write >{max_bytes} bytes")
        
        # Atomic write
        tmp = f"{valid_path}.tmp"
        async with aiofiles.open(tmp, "wb") as f:
            await f.write(binary_content)
        os.replace(tmp, valid_path)
        logger.info(f"Wrote {len(binary_content)} binary bytes to file: {valid_path}")
        return f"Successfully wrote {len(binary_content)} bytes to {parsed.path}"
    else:
        # Text mode
        if len(parsed.content.encode("utf-8")) > max_bytes:
            raise Exception(f"Refusing to write >{max_bytes} bytes")
        
        # Atomic write
        tmp = f"{valid_path}.tmp"
        async with aiofiles.open(tmp, "w", encoding=parsed.encoding) as f:
            await f.write(parsed.content)
        os.replace(tmp, valid_path)
        logger.info(f"Wrote {len(parsed.content)} chars to file: {valid_path}")
        return f"Successfully wrote to {parsed.path}"

@mcp.tool()
@handle_errors
async def edit_file(path: str, edits: List[Dict[str, str]], ctx: Context, dry_run: bool = True):
    """Make line-based edits to a text file with flexible matching.
    Returns a git-style diff and a UI preview."""
    parsed = EditFileArgs(path=path, edits=edits, dry_run=dry_run)
    valid_path = await validate_path(parsed.path)
    async with aiofiles.open(valid_path, 'r', encoding='utf-8') as f:
        content = normalize_line_endings(await f.read())
    
    modified_content = content
    applied = 0
    for e in parsed.edits:
        old_text, new_text = e.oldText, e.newText
        if old_text in modified_content:
            modified_content = modified_content.replace(old_text, new_text, 1)
            applied += 1
        else:
            # try block replace ignoring whitespace
            old_lines = [line.strip() for line in old_text.splitlines()]
            lines = modified_content.splitlines()
            for i in range(len(lines) - len(old_lines) + 1):
                if all(lines[i + j].strip() == old_lines[j] for j in range(len(old_lines))):
                    lines[i:i+len(old_lines)] = new_text.splitlines()
                    modified_content = '\n'.join(lines)
                    applied += 1
                    break
    if applied == 0:
        raise Exception("No edits applied (no matches found).")
    
    diff = create_unified_diff(content, modified_content, valid_path)
    if not parsed.dry_run:
        async with aiofiles.open(valid_path, 'w', encoding='utf-8') as f:
            await f.write(modified_content)
        logger.info(f"Edited file: {valid_path}")

    # Create a simple UI resource for the diff
    diff_ui = create_ui_resource({
        "uri": f"ui://diff-preview/{urllib.parse.quote(path)}",
        "content": {
            "type": "rawHtml",
            "htmlString": f"""
    <div class="diff-container">
        <h3 class="diff-title">📝 Preview for {path}</h3>
        <pre class="diff-content"><code>{diff}</code></pre>
        <p class="diff-footer"><small>Git-style diff preview.</small></p>
    </div>
    <style>
        .diff-container {{
            font-family: 'Courier New', monospace;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f8f9fa;
            border-radius: 12px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        }}
        .diff-title {{
            color: #495057;
            margin-bottom: 15px;
            font-size: 1.3em;
        }}
        .diff-content {{
            background-color: #fff;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #dee2e6;
            overflow-x: auto;
        }}
        .diff-footer {{
            text-align: center;
            margin-top: 15px;
            color: #6c757d;
        }}
    </style>
    """
        },
        "encoding": "text"
    })

    # Return a mixed response with both text and the UI
    content = [
        {"type": "text", "text": f"```diff\n{diff}\n```"},
        {"type": "resource", "resource": diff_ui["resource"]}
    ]
    return content

@mcp.tool()
@handle_errors
async def create_directory(path: str, ctx: Context) -> str:
    """Create a new directory or ensure it exists.
    Creates nested directories if needed. Only works within allowed directories."""
    parsed = CreateDirectoryArgs(path=path)
    valid_path = await validate_path(parsed.path)
    os.makedirs(valid_path, exist_ok=True)
    logger.info(f"Created directory: {valid_path}")
    return f"Successfully created directory {parsed.path}"

@mcp.tool()
@handle_errors
async def list_directory(path: str, ctx: Context) -> str:
    """Get a detailed listing of directory contents.
    Prefixes entries with [DIR] or [FILE]. Only works within allowed directories."""
    parsed = ListDirectoryArgs(path=path)
    valid_path = await validate_path(parsed.path)
    entries = os.listdir(valid_path)
    formatted = [f"[DIR] {e}" if os.path.isdir(os.path.join(valid_path, e)) else f"[FILE] {e}" for e in entries]
    logger.info(f"Listed directory: {valid_path}")
    return "\n".join(formatted)
@mcp.tool()
@handle_errors
async def view_directory_ui(path: str, ctx: Context):
    """Renders an interactive UI to display the contents of a directory."""
    # Reuse your existing validation and logic
    valid_path = await validate_path(path)
    entries = os.listdir(valid_path)

    # Build the HTML content for the UI
    html_list = ""
    for e in entries:
        entry_type = "[DIR]" if os.path.isdir(os.path.join(valid_path, e)) else "[FILE]"
        icon = "📁" if entry_type == "[DIR]" else "📄"
        html_list += f"""
        <li class="entry-item" data-path="{e}">
            <span class="entry-icon">{icon}</span>
            <span class="entry-name">{e}</span>
        </li>
        """

    html_content = f"""
    <div class="directory-container">
        <h3 class="directory-title">📂 Directory Listing: {path}</h3>
        <ul class="directory-list">
            {html_list}
        </ul>
        <div class="actions">
            <button class="refresh-btn" onclick="refreshDirectory()">
                🔄 Refresh
            </button>
        </div>
        <p class="footer"><small>This UI was generated by the Python MCP server.</small></p>
    </div>
    <style>
        .directory-container {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
            border-radius: 12px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        }}
        .directory-title {{
            color: #333;
            margin-bottom: 20px;
            font-size: 1.5em;
            text-align: center;
        }}
        .directory-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        .entry-item {{
            display: flex;
            align-items: center;
            padding: 10px 15px;
            margin-bottom: 5px;
            background-color: #fff;
            border-radius: 8px;
            transition: background-color 0.3s ease;
            cursor: pointer;
        }}
        .entry-item:hover {{
            background-color: #e0f7fa;
        }}
        .entry-icon {{
            margin-right: 10px;
            font-size: 1.2em;
        }}
        .entry-name {{
            font-weight: 500;
            color: #555;
        }}
        .actions {{
            text-align: center;
            margin-top: 20px;
        }}
        .refresh-btn {{
            background-color: #007bff;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            transition: background-color 0.3s ease;
        }}
        .refresh-btn:hover {{
            background-color: #0056b3;
        }}
        .footer {{
            text-align: center;
            margin-top: 20px;
            color: #777;
        }}
    </style>
    <script>
        function refreshDirectory() {{
            window.parent.postMessage({{type: 'intent', payload: {{'intent': 'refresh', 'params': {{'path': '{path}'}}}}}}, '*');
        }}
    </script>
    """

    # Create the UIResource object
    ui_resource = create_ui_resource({
        "uri": f"ui://directory-listing/{urllib.parse.quote(path)}",
        "content": {
            "type": "rawHtml",
            "htmlString": html_content
        },
        "encoding": "text"
    })

    logger.info(f"Generated directory UI for: {valid_path}")
    content = [
        {"type": "text", "text": "Directory listing UI generated."},
        {"type": "resource", "resource": ui_resource["resource"]}
    ]
    return content
@mcp.tool()
@handle_errors
async def directory_tree(path: str, ctx: Context, max_depth: int = 5, max_nodes: int = 5000) -> str:
    """Get a recursive tree view of files and directories as JSON.
    Includes 'name' and 'type', with 'children' for directories. Only works within allowed directories."""
    parsed = DirectoryTreeArgs(path=path)
    valid_path = await validate_path(parsed.path)
    
    seen = 0
    async def build_tree(current_path: str, depth: int) -> Dict:
        nonlocal seen
        if depth > max_depth or seen > max_nodes:
            return [{"name": "...truncated...", "type": "note"}]
        try:
            entries = os.listdir(current_path)
        except Exception as e:
            return [{"name": f"[error] {e}", "type": "note"}]
        tree = []
        for entry in entries:
            full_path = os.path.join(current_path, entry)
            entry_data = {"name": entry, "type": "directory" if os.path.isdir(full_path) else "file"}
            if os.path.isdir(full_path):
                entry_data["children"] = await build_tree(full_path, depth + 1)
            tree.append(entry_data)
            seen += 1
        return tree
    
    tree_data = await build_tree(valid_path, 0)
    logger.info(f"Generated directory tree for: {valid_path}")
    return json.dumps(tree_data, indent=2)

@mcp.tool()
@handle_errors
async def move_file(source: str, destination: str, ctx: Context) -> str:
    """Move or rename files and directories.
    Fails if destination exists. Only works within allowed directories."""
    parsed = MoveFileArgs(source=source, destination=destination)
    valid_source = await validate_path(parsed.source)
    valid_dest = await validate_path(parsed.destination)
    os.rename(valid_source, valid_dest)
    logger.info(f"Moved {valid_source} to {valid_dest}")
    return f"Successfully moved {parsed.source} to {parsed.destination}"

@mcp.tool()
@handle_errors
async def search_files(path: str, pattern: str, ctx: Context, exclude_patterns: List[str] = []) -> str:
    """Recursively search for files matching a pattern.
    Case-insensitive, returns full paths. Only works within allowed directories."""
    parsed = SearchFilesArgs(path=path, pattern=pattern, exclude_patterns=exclude_patterns)
    valid_path = await validate_path(parsed.path)
    results = await _search_files_impl(valid_path, parsed.pattern, parsed.exclude_patterns)
    logger.info(f"Searched {valid_path} for pattern '{parsed.pattern}'")
    return "\n".join(results) if results else "No matches found"

@mcp.tool()
@handle_errors
async def get_file_info(path: str, ctx: Context) -> str:
    """Retrieve detailed metadata about a file or directory.
    Includes size, timestamps, and permissions. Only works within allowed directories."""
    parsed = GetFileInfoArgs(path=path)
    valid_path = await validate_path(parsed.path)
    info = FileInfo(valid_path)
    logger.info(f"Retrieved info for: {valid_path}")
    return "\n".join([
        f"size: {info.size}",
        f"created: {info.created}",
        f"modified: {info.modified}",
        f"accessed: {info.accessed}",
        f"isDirectory: {info.is_directory}",
        f"isFile: {info.is_file}",
        f"permissions: {info.permissions}"
    ])

@mcp.tool()
@handle_errors
async def list_allowed_directories(ctx: Context) -> str:
    """Returns the list of directories this server can access."""
    logger.info("Listed allowed directories")
    return "Allowed directories:\n" + "\n".join(map(str, allowed_directories))

@mcp.tool()
@handle_errors
async def set_allowed_directories(directories: List[str], ctx: Context) -> str:
    """Update the list of allowed directories at runtime."""
    global allowed_directories
    parsed = SetAllowedDirectoriesArgs(directories=directories)
    new_dirs = [normalize_path(expand_home(dir)) for dir in parsed.directories]
    valid_dirs = []
    for dir in new_dirs:
        if not os.path.isdir(dir):
            ctx.info(f"Warning: {dir} is not a directory, skipping")
            continue
        if not os.access(dir, os.R_OK):
            ctx.info(f"Warning: No read access to {dir}, skipping")
            continue
        valid_dirs.append(dir)
    allowed_directories = valid_dirs
    logger.info(f"Updated allowed directories: {', '.join(map(str, allowed_directories))}")
    return f"Updated allowed directories to: {', '.join(map(str, allowed_directories))}"

# Improved Prompts
@mcp.prompt()
def read_and_summarize_file(path: str = "README.md") -> List[Dict[str, str]]:
    """Prompt to read and summarize a file, structured as a conversation."""
    return [
        {"role": "user", "content": f"Please read the file at '{path}' and provide a summary."},
        {"role": "assistant", "content": f"I'll use the read_file tool: read_file('{path}') and then summarize the content."}
    ]

@mcp.prompt()
def search_and_list_files(pattern: str = "*.py", path: str = None) -> str:
    """Prompt to search for files matching a pattern, with optional path."""
    base_dir = path or str(allowed_directories[0])
    return f"Search for files in '{base_dir}' matching '{pattern}' and list their paths.\nUse the search_files tool: search_files('{base_dir}', '{pattern}')"

@mcp.prompt()
def write_content_to_file(path: str = "example.txt", content: str = "Hello, World!") -> List[Dict[str, str]]:
    """Prompt to write content to a file, with confirmation step."""
    return [
        {"role": "user", "content": f"Write this to '{path}':\n{content}"},
        {"role": "assistant", "content": f"I'll use the write_file tool: write_file('{path}', '{content}'). Confirm if you'd like to proceed."}
    ]

@mcp.prompt()
def edit_file_content(path: str = "example.txt", old_text: str = "World", new_text: str = "Universe") -> List[Dict[str, str]]:
    """Prompt to edit a file, showing a preview and asking for confirmation."""
    return [
        {"role": "user", "content": f"In '{path}', replace '{old_text}' with '{new_text}'."},
        {"role": "assistant", "content": f"I'll preview the change with edit_file('{path}', [{{\"oldText\": \"{old_text}\", \"newText\": \"{new_text}\"}}], dry_run=True). Confirm to apply."}
    ]

# Improved Resources
@mcp.resource("status://server")
def get_server_status() -> str:
    """Return server status with allowed directories."""
    return f"Server running with access to: {', '.join(map(str, allowed_directories))}"

@mcp.resource("dir://{path}")
def get_directory_listing(path: str) -> str:
    """Expose directory contents as a resource."""
    # Strong validation (rejects '..', symlinks escaping, etc.)
    valid_path = validate_path_sync(path)
    entries = os.listdir(valid_path)
    return "\n".join(f"[DIR] {e}" if os.path.isdir(os.path.join(valid_path, e)) else f"[FILE] {e}" for e in entries)

@mcp.resource("file://{path}")
def get_file_content(path: str) -> str:
    """Expose file contents as a resource, read synchronously for simplicity."""
    valid_path = validate_path_sync(path)
    with open(valid_path, 'r', encoding='utf-8') as f:
        return f.read()

@mcp.resource("info://{path}")
def get_file_metadata(path: str) -> str:
    """Expose file metadata as a resource."""
    valid_path = validate_path_sync(path)
    info = FileInfo(valid_path)
    return json.dumps({
        "size": info.size,
        "created": info.created,
        "modified": info.modified,
        "accessed": info.accessed,
        "isDirectory": info.is_directory,
        "isFile": info.is_file,
        "permissions": info.permissions
    }, indent=2)

# Main execution
if __name__ == "__main__":
    mcp.run(transport="stdio")