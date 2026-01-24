---
name: docs-to-files
description: Resolve a library and fetch docs to a local file
compatibility: opencode
metadata:
  impl_ref: skills:docs-to-files@1
  impl_dir: skills/docs-to-files
---

## What I do

- Resolve a Context7 library ID (if needed)
- Fetch docs for a topic
- Write the docs to `output_dir`

## How to use

```python
import skills

async def main():
    return await skills.load("docs-to-files").fetch_and_store(library="/vercel/next.js", topic="routing", output_dir="output/docs")
```
