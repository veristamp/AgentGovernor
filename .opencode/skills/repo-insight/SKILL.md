---
name: repo-insight
description: Generate a repo insight report and persist it to memory and disk
compatibility: opencode
metadata:
  impl_ref: skills:repo-insight@1
  impl_dir: skills/repo-insight
---

## What I do

- Run semantic searches over docs/code
- Produce a small JSON summary
- Store summary in memory and optionally write it to disk

## How to use

```python
import skills

async def main():
    return await skills.load("repo-insight").analyze_repo(query="routing", output_dir="output/reports", note_key="routing_docs_summary")
```
