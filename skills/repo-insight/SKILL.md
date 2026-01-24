# repo-insight

## Purpose
Provide a repo insight report by combining semantic doc search, semantic code search, and usage/dependency links, then store the summary in memory and optionally write it to disk.

## Interface
- `analyze_repo(query, output_dir, note_key, write_report=True)`

## Fanout
- modelcontextprotocol-python-sdk.docs-semantic-search
- modelcontextprotocol-python-sdk.nodes-semantic-search
- modelcontextprotocol-python-sdk.get-usage-dependency-links
- memory.create-entities
- filesystem.create-directory
- filesystem.write-file

## Examples

```python
import skills

async def main():
    result = await skills.load("repo-insight").analyze_repo(
        query="Next.js routing docs summary",
        output_dir="output/reports",
        note_key="routing_docs_summary",
        write_report=True,
    )
    return result
```
