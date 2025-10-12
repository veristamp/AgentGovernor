# MCP Capabilities

## Tools

### Crawl4AI API.ask

This end point is design for any questions about Crawl4ai library. It returns a plain text markdown with extensive information about Crawl4ai. 
You can use this as a context for any AI assistant. Use this endpoint for AI assistants to retrieve library context for decision making or code generation tasks.
Alway is BEST practice you provide a query to filter the context. Otherwise the lenght of the response will be very long.

Parameters:
- context_type: Specify "code" for code context, "doc" for documentation context, or "all" for both.
- query: RECOMMENDED search query to filter paragraphs using BM25. You can leave this empty to get all the context.
- score_ratio: Minimum score as a fraction of the maximum score for filtering results.
- max_results: Maximum number of results to return. Default is 20.

Returns:
- JSON response with the requested context.
- If "code" is specified, returns the code context.
- If "doc" is specified, returns the documentation context.
- If "all" is specified, returns both code and documentation contexts.

### Crawl4AI API.crawl

Crawl a list of URLs and return the results as JSON.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| browser_config | unknown | No |  |

| crawler_config | unknown | No |  |

| urls | array | Yes |  |



### Crawl4AI API.execute_js

Execute a sequence of JavaScript snippets on the specified URL.
Return the full CrawlResult JSON (first result).
Use this when you need to interact with dynamic pages using JS.
REMEMBER: Scripts accept a list of separated JS snippets to execute and execute them in order.
IMPORTANT: Each script should be an expression that returns a value. It can be an IIFE or an async function. You can think of it as such.
    Your script will replace '{script}' and execute in the browser context. So provide either an IIFE or a sync/async function that returns a value.
Return Format:
    - The return result is an instance of CrawlResult, so you have access to markdown, links, and other stuff. If this is enough, you don't need to call again for other endpoints.

    ```python
    class CrawlResult(BaseModel):
        url: str
        html: str
        success: bool
        cleaned_html: Optional[str] = None
        media: Dict[str, List[Dict]] = {}
        links: Dict[str, List[Dict]] = {}
        downloaded_files: Optional[List[str]] = None
        js_execution_result: Optional[Dict[str, Any]] = None
        screenshot: Optional[str] = None
        pdf: Optional[bytes] = None
        mhtml: Optional[str] = None
        _markdown: Optional[MarkdownGenerationResult] = PrivateAttr(default=None)
        extracted_content: Optional[str] = None
        metadata: Optional[dict] = None
        error_message: Optional[str] = None
        session_id: Optional[str] = None
        response_headers: Optional[dict] = None
        status_code: Optional[int] = None
        ssl_certificate: Optional[SSLCertificate] = None
        dispatch_result: Optional[DispatchResult] = None
        redirected_url: Optional[str] = None
        network_requests: Optional[List[Dict[str, Any]]] = None
        console_messages: Optional[List[Dict[str, Any]]] = None

    class MarkdownGenerationResult(BaseModel):
        raw_markdown: str
        markdown_with_citations: str
        references_markdown: str
        fit_markdown: Optional[str] = None
        fit_html: Optional[str] = None
    ```

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| scripts | array | Yes | List of separated JavaScript snippets to execute |

| url | string | Yes |  |



### Crawl4AI API.html

Crawls the URL, preprocesses the raw HTML for schema extraction, and returns the processed HTML.
Use when you need sanitized HTML structures for building schemas or further processing.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| url | string | Yes |  |



### Crawl4AI API.md



| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| c | unknown | No | Cache‑bust / revision counter |

| f | unknown | No | Content‑filter strategy: fit, raw, bm25, or llm |

| provider | unknown | No | LLM provider override (e.g., 'anthropic/claude-3-opus') |

| q | unknown | No | Query string used by BM25/LLM filters |

| url | string | Yes | Absolute http/https URL to fetch |



### Crawl4AI API.pdf

Generate a PDF document of the specified URL,
Use when you need a printable or archivable snapshot of the page. It is recommended to provide an output path to save the PDF.
Then in result instead of the PDF you will get a path to the saved file.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| output_path | unknown | No |  |

| url | string | Yes |  |



### Crawl4AI API.screenshot

Capture a full-page PNG screenshot of the specified URL, waiting an optional delay before capture,
Use when you need an image snapshot of the rendered page. Its recommened to provide an output path to save the screenshot.
Then in result instead of the screenshot you will get a path to the saved file.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| output_path | unknown | No |  |

| screenshot_wait_for | unknown | No |  |

| url | string | Yes |  |



### memory-server.add_observations

Add new observations to existing entities in the knowledge graph

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| observations | array | Yes |  |



### memory-server.create_entities

Create multiple new entities in the knowledge graph

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| entities | array | Yes |  |



### memory-server.create_relations

Create multiple new relations between entities in the knowledge graph. Relations should be in active voice

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| relations | array | Yes |  |



### memory-server.delete_entities

Delete multiple entities and their associated relations from the knowledge graph

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| entityNames | array | Yes |  |



### memory-server.delete_observations

Delete specific observations from entities in the knowledge graph

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| deletions | array | Yes |  |



### memory-server.delete_relations

Delete multiple relations from the knowledge graph

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| relations | array | Yes |  |



### memory-server.open_nodes

Open specific nodes in the knowledge graph by their names

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| names | array | Yes |  |



### memory-server.read_graph

Read the entire knowledge graph

| Argument | Type | Required | Description |

|----------|------|----------|-------------|



### memory-server.search_nodes

Search for nodes in the knowledge graph based on a query

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| query | string | Yes |  |



### secure-filesystem-server.create_directory

Create a new directory or ensure it exists.
Creates nested directories if needed. Only works within allowed directories.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| path | string | Yes |  |



### secure-filesystem-server.directory_tree

Get a recursive tree view of files and directories as JSON.
Includes 'name' and 'type', with 'children' for directories. Only works within allowed directories.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| path | string | Yes |  |



### secure-filesystem-server.edit_file

Make line-based edits to a text file with flexible matching.
Returns a git-style diff and a UI preview.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| dry_run | boolean | No |  |

| edits | array | Yes |  |

| path | string | Yes |  |



### secure-filesystem-server.get_file_info

Retrieve detailed metadata about a file or directory.
Includes size, timestamps, and permissions. Only works within allowed directories.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| path | string | Yes |  |



### secure-filesystem-server.list_allowed_directories

Returns the list of directories this server can access.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|



### secure-filesystem-server.list_directory

Get a detailed listing of directory contents.
Prefixes entries with [DIR] or [FILE]. Only works within allowed directories.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| path | string | Yes |  |



### secure-filesystem-server.move_file

Move or rename files and directories.
Fails if destination exists. Only works within allowed directories.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| destination | string | Yes |  |

| source | string | Yes |  |



### secure-filesystem-server.read_file

Read the complete contents of a file asynchronously.
Supports UTF-8 encoding and raises detailed errors if the file cannot be read.
Only works within allowed directories.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| path | string | Yes |  |



### secure-filesystem-server.read_multiple_files

Read the contents of multiple files asynchronously.
Returns each file's content prefixed with its path, separated by '---'.
Continues on individual file errors. Only works within allowed directories.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| paths | array | Yes |  |



### secure-filesystem-server.search_files

Recursively search for files matching a pattern.
Case-insensitive, returns full paths. Only works within allowed directories.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| exclude_patterns | array | No |  |

| path | string | Yes |  |

| pattern | string | Yes |  |



### secure-filesystem-server.set_allowed_directories

Update the list of allowed directories at runtime.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| directories | array | Yes |  |



### secure-filesystem-server.view_directory_ui

Renders an interactive UI to display the contents of a directory.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| path | string | Yes |  |



### secure-filesystem-server.write_file

Create or overwrite a file with new content asynchronously.
Overwrites existing files without warning. Only works within allowed directories.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| content | string | Yes |  |

| path | string | Yes |  |



### terminal.run_command

Run a shell command asynchronously with a timeout.

| Argument | Type | Required | Description |

|----------|------|----------|-------------|

| command | string | Yes |  |

| directory | string | No |  |

| timeout | number | No |  |

| truncate_after | integer | No |  |



## Resources

### secure-filesystem-server.get_server_status

Return server status with allowed directories.

### terminal.get_terminal_status

Return terminal server status.

## Prompts

### secure-filesystem-server.edit_file_content

Prompt to edit a file, showing a preview and asking for confirmation.

### secure-filesystem-server.read_and_summarize_file

Prompt to read and summarize a file, structured as a conversation.

### secure-filesystem-server.search_and_list_files

Prompt to search for files matching a pattern, with optional path.

### secure-filesystem-server.write_content_to_file

Prompt to write content to a file, with confirmation step.

### terminal.execute_terminal_command

Prompt to run a terminal command with confirmation.
