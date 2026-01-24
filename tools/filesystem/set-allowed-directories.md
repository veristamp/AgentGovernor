# filesystem.set-allowed-directories

> Update the list of allowed directories at runtime.

## Signature

```python
await set-allowed-directories(directories: list)
```

## Description

Update the list of allowed directories at runtime.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `directories` | array | ✓ | List of directories |

## Usage Example

```python
result = await filesystem_binding.set-allowed-directories(
    # Add parameters here
)
```
