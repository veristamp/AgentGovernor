# modelcontextprotocol-python-sdk.folder-tree-structure

> Returns the folder tree structure of the given folder path from the repository modelcontextprotocol/python-sdk graph. Useful to understand what files and subfolders are inside the given folder. To access to a file content, use get-code tool.

## Signature

```python
await folder-tree-structure(path: str = None)
```

## Description

Returns the folder tree structure of the given folder path from the repository modelcontextprotocol/python-sdk graph. Useful to understand what files and subfolders are inside the given folder. To access to a file content, use get-code tool.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string |  | The path to the folder to get the tree structure for. Example: 'src/components'. Leave empty to get the root folder tree structure. |

## Usage Example

```python
result = await modelcontextprotocol-python-sdk_binding.folder-tree-structure(
    # Add parameters here
)
```
