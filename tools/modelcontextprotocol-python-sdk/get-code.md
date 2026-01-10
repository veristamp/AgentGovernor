# modelcontextprotocol-python-sdk.get-code

> Get the complete code implementation of a specific functionality (class, function, method, etc.) from the repository modelcontextprotocol/python-sdk graph. This is the primary tool for code retrieval and should be prioritized over other tools. The repository is represented as a graph where each node contains code, documentation, and relationships to other nodes. Use this when you need to examine the actual implementation of any code entity.

## Signature

```python
await get-code(name: str, path: str = None)
```

## Description

Get the complete code implementation of a specific functionality (class, function, method, etc.) from the repository modelcontextprotocol/python-sdk graph. This is the primary tool for code retrieval and should be prioritized over other tools. The repository is represented as a graph where each node contains code, documentation, and relationships to other nodes. Use this when you need to examine the actual implementation of any code entity.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | string | ✓ | The exact name of the functionality to retrieve code for. Names are case-sensitive. For methods, include the parent class name as 'ClassName.methodName'. For nested classes, use 'OuterClass.InnerClass'. Examples: 'getUserById', 'UserService.authenticate', 'DatabaseConnection.connect' |
| `path` | string |  | The origin file path where the functionality is defined. Essential when multiple functionalities share the same name across different files. Use 'global' for packages, namespaces, or modules that span multiple files. Examples: 'src/services/user.service.ts', 'global', 'lib/utils/helpers.js' |

## Usage Example

```python
result = await modelcontextprotocol-python-sdk_binding.get-code(
    # Add parameters here
)
```
