# docs-to-files

## Purpose
Fetch documentation from Context7 and persist it to a local file. This skill resolves a library name to a Context7-compatible ID when needed, retrieves documentation for a topic, creates the output directory, and writes the docs to disk.

## Interface
- `fetch_and_store(library, topic, output_dir, file_name=None, mode="code")`

## Fanout
- context7.resolve-library-id
- context7.query-docs
- filesystem.create-directory
- filesystem.write-file

## Examples

```python
import skills

async def main():
    result = await skills.load("docs-to-files").fetch_and_store(
        library="/vercel/next.js",
        topic="routing",
        output_dir="output/docs",
    )
    return result
```
