# context7.query-docs

> Retrieves and queries up-to-date documentation and code examples from Context7 for any programming library or framework.

## Signature

```python
await query-docs(libraryId: str, query: str)
```

## Description

Retrieves and queries up-to-date documentation and code examples from Context7 for any programming library or framework.

You must call 'resolve-library-id' first to obtain the exact Context7-compatible library ID required to use this tool, UNLESS the user explicitly provides a library ID in the format '/org/project' or '/org/project/version' in their query.

IMPORTANT: Do not call this tool more than 3 times per question. If you cannot find what you need after 3 calls, use the best information you have.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `libraryId` | string | ✓ | Exact Context7-compatible library ID (e.g., '/mongodb/docs', '/vercel/next.js', '/supabase/supabase', '/vercel/next.js/v14.3.0-canary.87') retrieved from 'resolve-library-id' or directly from user query in the format '/org/project' or '/org/project/version'. |
| `query` | string | ✓ | The question or task you need help with. Be specific and include relevant details. Good: 'How to set up authentication with JWT in Express.js' or 'React useEffect cleanup function examples'. Bad: 'auth' or 'hooks'. IMPORTANT: Do not include any sensitive or confidential information such as API keys, passwords, credentials, or personal data in your query. |

## Usage Example

```python
result = await context7_binding.query-docs(
    # Add parameters here
)
```
