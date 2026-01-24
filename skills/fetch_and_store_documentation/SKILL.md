# fetch_and_store_documentation

Fetch documentation from a URL and store it in a file.

## Interface

```python
fetch_and_store(url, file_path)
```

## Examples

```python
import skills

async def main():
    result = await skills.load("fetch_and_store_documentation").fetch_and_store(
        url="https://example.com/documentation",
        file_path="output/documentation.txt",
    )
    return result
```
