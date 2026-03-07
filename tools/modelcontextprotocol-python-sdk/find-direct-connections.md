# modelcontextprotocol-python-sdk.find-direct-connections

> Explore the immediate relationships of a functionality within the code graph from the repository modelcontextprotocol/python-sdk. This reveals first-level connections including: parent functionalities that reference this node, child functionalities that this node directly calls or uses, declaration/definition relationships, and usage patterns. Essential for understanding code dependencies and architecture. The repository is represented as a connected graph where each node (function, class, file, etc.) has relationships with other nodes.

## Signature

```python
await find-direct-connections(name: str, path: str = None)
```

## Description

Explore the immediate relationships of a functionality within the code graph from the repository modelcontextprotocol/python-sdk. This reveals first-level connections including: parent functionalities that reference this node, child functionalities that this node directly calls or uses, declaration/definition relationships, and usage patterns. Essential for understanding code dependencies and architecture. The repository is represented as a connected graph where each node (function, class, file, etc.) has relationships with other nodes.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | string | ✓ | The exact name of the functionality to analyze connections for. Names are case-sensitive. For methods, include the parent class name as 'ClassName.methodName'. Examples: 'processPayment', 'UserController.createUser', 'validateInput' |
| `path` | string |  | The origin file path of the functionality. Critical when multiple functionalities have identical names in different files. Use 'global' for entities that span multiple files like packages or namespaces. Examples: 'src/controllers/payment.controller.ts', 'global', 'utils/validation.js' |

## Usage Example

```python
result = await modelcontextprotocol-python-sdk_binding.find-direct-connections(
    # Add parameters here
)
```
