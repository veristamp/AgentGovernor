"""
Memory/Knowledge Graph Skill Library.

These functions are injected into the sandbox and use binding proxies internally.
The `_binding` object is injected at runtime by the skill injector.

Usage in sandbox:
    from skills import memory
    await memory.remember("user_preference", "dark_mode", ["User prefers dark mode"])
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional


async def remember(name: str, entity_type: str, observations: List[str]) -> Dict[str, Any]:
    """
    Create or update an entity in the knowledge graph.
    
    Args:
        name: Unique name for the entity
        entity_type: Category (e.g., "Person", "Preference", "Project")
        observations: List of facts about this entity
    
    Returns:
        Result dict from the operation
    """
    return await _binding.create_entities(entities=[{
        "name": name,
        "entityType": entity_type,
        "observations": observations
    }])


async def remember_many(entities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create multiple entities at once.
    
    Args:
        entities: List of entity dicts with 'name', 'entityType', 'observations'
    
    Returns:
        Result dict from the operation
    """
    return await _binding.create_entities(entities=entities)


async def relate(from_entity: str, to_entity: str, relation: str) -> Dict[str, Any]:
    """
    Create a relationship between two entities.
    
    Args:
        from_entity: Name of the source entity
        to_entity: Name of the target entity
        relation: Type of relationship (e.g., "works_on", "knows", "uses")
    
    Returns:
        Result dict from the operation
    """
    return await _binding.create_relations(relations=[{
        "from": from_entity,
        "to": to_entity,
        "relationType": relation
    }])


async def relate_many(relations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create multiple relationships at once.
    
    Args:
        relations: List of relation dicts with 'from', 'to', 'relationType'
    
    Returns:
        Result dict from the operation
    """
    return await _binding.create_relations(relations=relations)


async def search(query: str) -> List[Dict[str, Any]]:
    """
    Search for entities matching a query string.
    
    Args:
        query: Search query
    
    Returns:
        List of matching entity dicts
    """
    return await _binding.search_nodes(query=query)


async def recall(names: List[str]) -> List[Dict[str, Any]]:
    """
    Retrieve full details of specific entities by name.
    
    Args:
        names: List of entity names to retrieve
    
    Returns:
        List of entity dicts with full details
    """
    return await _binding.open_nodes(names=names)


async def recall_one(name: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a single entity by name.
    
    Args:
        name: Entity name to retrieve
    
    Returns:
        Entity dict or None if not found
    """
    results = await _binding.open_nodes(names=[name])
    return results[0] if results else None


async def forget(names: List[str]) -> Dict[str, Any]:
    """
    Delete entities from the knowledge graph.
    
    Args:
        names: List of entity names to delete
    
    Returns:
        Result dict from the operation
    """
    return await _binding.delete_entities(names=names)


async def forget_one(name: str) -> Dict[str, Any]:
    """
    Delete a single entity from the knowledge graph.
    
    Args:
        name: Entity name to delete
    
    Returns:
        Result dict from the operation
    """
    return await _binding.delete_entities(names=[name])


async def unrelate(from_entity: str, to_entity: str, relation: str) -> Dict[str, Any]:
    """
    Remove a relationship between two entities.
    
    Args:
        from_entity: Name of the source entity
        to_entity: Name of the target entity
        relation: Type of relationship to remove
    
    Returns:
        Result dict from the operation
    """
    return await _binding.delete_relations(relations=[{
        "from": from_entity,
        "to": to_entity,
        "relationType": relation
    }])


async def store(key: str, value: Any) -> Dict[str, Any]:
    """
    Simple key-value storage using the knowledge graph.
    
    Args:
        key: Storage key
        value: Value to store (will be converted to string)
    
    Returns:
        Result dict from the operation
    """
    import json
    value_str = json.dumps(value) if not isinstance(value, str) else value
    return await _binding.create_entities(entities=[{
        "name": f"__kv__{key}",
        "entityType": "KeyValue",
        "observations": [value_str]
    }])


async def retrieve(key: str) -> Optional[Any]:
    """
    Retrieve a value from simple key-value storage.
    
    Args:
        key: Storage key
    
    Returns:
        Stored value (parsed from JSON if applicable) or None
    """
    import json
    results = await _binding.open_nodes(names=[f"__kv__{key}"])
    if not results or not results[0].get('observations'):
        return None
    value_str = results[0]['observations'][0]
    try:
        return json.loads(value_str)
    except:
        return value_str


async def add_observation(name: str, observation: str) -> Dict[str, Any]:
    """
    Add a new observation to an existing entity.
    
    Args:
        name: Entity name
        observation: New fact to add
    
    Returns:
        Result dict from the operation
    """
    return await _binding.add_observations(observations=[{
        "entityName": name,
        "contents": [observation]
    }])


async def read_graph() -> Dict[str, Any]:
    """
    Get the entire knowledge graph.
    
    Returns:
        Dict with all entities and relations
    """
    return await _binding.read_graph()


async def summarize() -> Dict[str, Any]:
    """
    Get a summary of the knowledge graph.
    
    Returns:
        Dict with entity count, relation count, and entity types
    """
    graph = await _binding.read_graph()
    entities = graph.get("entities", [])
    relations = graph.get("relations", [])
    
    # Count entity types
    types = {}
    for e in entities:
        t = e.get("entityType", "unknown")
        types[t] = types.get(t, 0) + 1
    
    return {
        "entity_count": len(entities),
        "relation_count": len(relations),
        "entity_types": types
    }

