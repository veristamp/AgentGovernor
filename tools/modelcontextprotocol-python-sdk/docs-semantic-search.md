# modelcontextprotocol-python-sdk.docs-semantic-search

> Search through repository modelcontextprotocol/python-sdk documentation using semantic similarity to find relevant information, guides, API documentation, README content, and explanatory materials. This tool specifically targets documentation files (markdown, rst, etc.) rather than code, making it ideal for understanding project setup, architecture decisions, usage instructions, and conceptual explanations. Use this when you need context about how the repository works rather than examining the actual code implementation.

## Signature

```python
await docs-semantic-search(query: str)
```

## Description

Search through repository modelcontextprotocol/python-sdk documentation using semantic similarity to find relevant information, guides, API documentation, README content, and explanatory materials. This tool specifically targets documentation files (markdown, rst, etc.) rather than code, making it ideal for understanding project setup, architecture decisions, usage instructions, and conceptual explanations. Use this when you need context about how the repository works rather than examining the actual code implementation.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `query` | string | ✓ | A natural language query describing the documentation or information you're seeking. Focus on concepts, setup procedures, architecture, or usage patterns. Examples: 'how to set up the development environment', 'API authentication methods', 'project architecture overview', 'contributing guidelines', 'deployment instructions', 'configuration options' |

## Usage Example

```python
result = await modelcontextprotocol-python-sdk_binding.docs-semantic-search(
    # Add parameters here
)
```
