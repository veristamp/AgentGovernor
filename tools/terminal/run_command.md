# terminal.run_command

> Run a shell command asynchronously with a timeout.

## Signature

```python
await run_command(command: str, directory: str = "~", timeout: float = 120.0, truncate_after: int = 16000)
```

## Description

Run a shell command asynchronously with a timeout.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `command` | string | ✓ | - |
| `directory` | string |  | - |
| `timeout` | number |  | - |
| `truncate_after` | integer |  | - |

## Usage Example

```python
result = await terminal_binding.run_command(
    # Add parameters here
)
```
