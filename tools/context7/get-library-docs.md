# context7.get-library-docs

> Fetches up-to-date documentation for a library. You must call 'resolve-library-id' first to obtain the exact Context7-compatible library ID required to use this tool, UNLESS the user explicitly provides a library ID in the format '/org/project' or '/org/project/version' in their query. Use mode='code' (default) for API references and code examples, or mode='info' for conceptual guides, narrative information, and architectural questions.

## Signature

```python
await get-library-docs(context7CompatibleLibraryID: str, mode: str = "code", topic: str = None, page: int = None)
```

## Description

Fetches up-to-date documentation for a library. You must call 'resolve-library-id' first to obtain the exact Context7-compatible library ID required to use this tool, UNLESS the user explicitly provides a library ID in the format '/org/project' or '/org/project/version' in their query. Use mode='code' (default) for API references and code examples, or mode='info' for conceptual guides, narrative information, and architectural questions.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `context7CompatibleLibraryID` | string | ✓ | Exact Context7-compatible library ID (e.g., '/mongodb/docs', '/vercel/next.js', '/supabase/supabase', '/vercel/next.js/v14.3.0-canary.87') retrieved from 'resolve-library-id' or directly from user query in the format '/org/project' or '/org/project/version'. |
| `mode` | string |  | Documentation mode: 'code' for API references and code examples (default), 'info' for conceptual guides, narrative information, and architectural questions. |
| `topic` | string |  | Topic to focus documentation on (e.g., 'hooks', 'routing'). |
| `page` | integer |  | Page number for pagination (start: 1, default: 1). If the context is not sufficient, try page=2, page=3, page=4, etc. with the same topic. |

## Usage Example

```python
result = await context7_binding.get-library-docs(
    # Add parameters here
)
```
