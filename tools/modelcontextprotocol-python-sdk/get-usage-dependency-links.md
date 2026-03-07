# modelcontextprotocol-python-sdk.get-usage-dependency-links

> Generate a comprehensive adjacency list showing all functionalities that would be affected by changes to a specific code entity. This performs deep dependency analysis through the code graph of the repository modelcontextprotocol/python-sdk to identify the complete impact radius of modifications. Essential for impact analysis, refactoring planning, and understanding code coupling. The result shows which functionalities depend on the target entity either directly or through a chain of dependencies, formatted as 'file_path::functionality_name' pairs.

## Signature

```python
await get-usage-dependency-links(name: str, path: str = None)
```

## Description

Generate a comprehensive adjacency list showing all functionalities that would be affected by changes to a specific code entity. This performs deep dependency analysis through the code graph of the repository modelcontextprotocol/python-sdk to identify the complete impact radius of modifications. Essential for impact analysis, refactoring planning, and understanding code coupling. The result shows which functionalities depend on the target entity either directly or through a chain of dependencies, formatted as 'file_path::functionality_name' pairs.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | string | ✓ | The exact name of the functionality to analyze dependencies for. Names are case-sensitive. For methods, include the parent class name as 'ClassName.methodName'. This will be the root node for dependency traversal. Examples: 'DatabaseService.connect', 'validateUserInput', 'PaymentProcessor.processTransaction' |
| `path` | string |  | The origin file path where the functionality is defined. Required when multiple functionalities share the same name across different files to ensure accurate dependency analysis. Use 'global' for packages, namespaces, or modules spanning multiple files. Examples: 'src/database/connection.service.ts', 'global', 'lib/validation/input.validator.js' |

## Usage Example

```python
result = await modelcontextprotocol-python-sdk_binding.get-usage-dependency-links(
    # Add parameters here
)
```
