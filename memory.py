#!/usr/bin/env python3

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any
from contextlib import asynccontextmanager

# MCP imports
from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field

# Define memory file path using environment variable with fallback
default_memory_path = Path(__file__).parent / 'memory.json'
MEMORY_FILE_PATH = os.getenv('MEMORY_FILE_PATH')
if MEMORY_FILE_PATH:
    if not os.path.isabs(MEMORY_FILE_PATH):
        MEMORY_FILE_PATH = str(Path(__file__).parent / MEMORY_FILE_PATH)
else:
    MEMORY_FILE_PATH = str(default_memory_path)

# We are storing our memory using entities, relations, and observations in a graph structure
class Entity(BaseModel):
    name: str = Field(..., description="The name of the entity")
    entityType: str = Field(..., description="The type of the entity")
    observations: List[str] = Field(..., description="An array of observation contents associated with the entity")

class Relation(BaseModel):
    from_: str = Field(..., alias='from', description="The name of the entity where the relation starts")
    to: str = Field(..., description="The name of the entity where the relation ends")
    relationType: str = Field(..., description="The type of the relation")

class ObservationUpdate(BaseModel):
    entityName: str = Field(..., description="The name of the entity to add the observations to")
    contents: List[str] = Field(..., description="An array of observation contents to add")

class Deletion(BaseModel):
    entityName: str = Field(..., description="The name of the entity containing the observations")
    observations: List[str] = Field(..., description="An array of observations to delete")

class KnowledgeGraph:
    def __init__(self, entities: List[Entity] = None, relations: List[Relation] = None):
        self.entities = entities or []
        self.relations = relations or []

# The KnowledgeGraphManager class contains all operations to interact with the knowledge graph
class KnowledgeGraphManager:
    def load_graph(self) -> KnowledgeGraph:
        try:
            with open(MEMORY_FILE_PATH, 'r', encoding='utf-8') as f:
                data = f.read()
            lines = [line.strip() for line in data.split('\n') if line.strip()]
            entities = []
            relations = []
            for line in lines:
                item = json.loads(line)
                item_type = item.pop('type', None)  # Remove 'type' if present
                if item_type == 'entity':
                    entities.append(Entity(**item))
                elif item_type == 'relation':
                    relations.append(Relation(**item))
            return KnowledgeGraph(entities=entities, relations=relations)
        except FileNotFoundError:
            return KnowledgeGraph()
        except Exception as e:
            raise e

    def save_graph(self, graph: KnowledgeGraph):
        lines = []
        for e in graph.entities:
            entity_dict = e.model_dump(mode='json', by_alias=True)
            entity_dict['type'] = 'entity'
            lines.append(json.dumps(entity_dict))
        for r in graph.relations:
            relation_dict = r.model_dump(mode='json', by_alias=True)
            relation_dict['type'] = 'relation'
            lines.append(json.dumps(relation_dict))
        with open(MEMORY_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

    def create_entities(self, entities: List[Entity]) -> List[Entity]:
        graph = self.load_graph()
        new_entities = [e for e in entities if not any(existing.name == e.name for existing in graph.entities)]
        graph.entities.extend(new_entities)
        self.save_graph(graph)
        return new_entities

    def create_relations(self, relations: List[Relation]) -> List[Relation]:
        graph = self.load_graph()
        new_relations = [r for r in relations if not any(
            existing.from_ == r.from_ and existing.to == r.to and existing.relationType == r.relationType
            for existing in graph.relations
        )]
        graph.relations.extend(new_relations)
        self.save_graph(graph)
        return new_relations

    def add_observations(self, observations: List[ObservationUpdate]) -> List[Dict[str, Any]]:
        graph = self.load_graph()
        results = []
        for o in observations:
            entity = next((e for e in graph.entities if e.name == o.entityName), None)
            if not entity:
                raise ValueError(f"Entity with name {o.entityName} not found")
            new_obs = [content for content in o.contents if content not in entity.observations]
            entity.observations.extend(new_obs)
            results.append({'entityName': o.entityName, 'addedObservations': new_obs})
        self.save_graph(graph)
        return results

    def delete_entities(self, entity_names: List[str]):
        graph = self.load_graph()
        graph.entities = [e for e in graph.entities if e.name not in entity_names]
        graph.relations = [r for r in graph.relations if r.from_ not in entity_names and r.to not in entity_names]
        self.save_graph(graph)

    def delete_observations(self, deletions: List[Deletion]):
        graph = self.load_graph()
        for d in deletions:
            entity = next((e for e in graph.entities if e.name == d.entityName), None)
            if entity:
                entity.observations = [o for o in entity.observations if o not in d.observations]
        self.save_graph(graph)

    def delete_relations(self, relations: List[Relation]):
        graph = self.load_graph()
        graph.relations = [r for r in graph.relations if not any(
            existing.from_ == r.from_ and existing.to == r.to and existing.relationType == r.relationType
            for existing in relations
        )]
        self.save_graph(graph)

    def read_graph(self) -> KnowledgeGraph:
        return self.load_graph()

    def search_nodes(self, query: str) -> KnowledgeGraph:
        graph = self.load_graph()
        filtered_entities = [e for e in graph.entities if (
            query.lower() in e.name.lower() or
            query.lower() in e.entityType.lower() or
            any(query.lower() in o.lower() for o in e.observations)
        )]
        filtered_entity_names = {e.name for e in filtered_entities}
        filtered_relations = [r for r in graph.relations if r.from_ in filtered_entity_names and r.to in filtered_entity_names]
        return KnowledgeGraph(entities=filtered_entities, relations=filtered_relations)

    def open_nodes(self, names: List[str]) -> KnowledgeGraph:
        graph = self.load_graph()
        filtered_entities = [e for e in graph.entities if e.name in names]
        filtered_entity_names = {e.name for e in filtered_entities}
        filtered_relations = [r for r in graph.relations if r.from_ in filtered_entity_names and r.to in filtered_entity_names]
        return KnowledgeGraph(entities=filtered_entities, relations=filtered_relations)

knowledge_graph_manager = KnowledgeGraphManager()

@asynccontextmanager
async def server_lifespan(server: FastMCP) -> Dict[str, Any]:
    print(f"Starting Knowledge Graph MCP Server with memory file: {MEMORY_FILE_PATH}", file=sys.stderr)
    yield {"status": "running"}
    print("Shutting down Knowledge Graph MCP Server", file=sys.stderr)

# Create MCP server
mcp = FastMCP(name="memory-server", lifespan=server_lifespan)

# Tools with individual params for direct validation
@mcp.tool()
async def create_entities(entities: List[Entity], ctx: Context) -> str:
    """Create multiple new entities in the knowledge graph"""
    result = knowledge_graph_manager.create_entities(entities)
    return json.dumps([e.model_dump(mode='json', by_alias=True) for e in result], indent=2)

@mcp.tool()
async def create_relations(relations: List[Relation], ctx: Context) -> str:
    """Create multiple new relations between entities in the knowledge graph. Relations should be in active voice"""
    result = knowledge_graph_manager.create_relations(relations)
    return json.dumps([r.model_dump(mode='json', by_alias=True) for r in result], indent=2)

@mcp.tool()
async def add_observations(observations: List[ObservationUpdate], ctx: Context) -> str:
    """Add new observations to existing entities in the knowledge graph"""
    result = knowledge_graph_manager.add_observations(observations)
    return json.dumps(result, indent=2)

@mcp.tool()
async def delete_entities(entityNames: List[str], ctx: Context) -> str:
    """Delete multiple entities and their associated relations from the knowledge graph"""
    knowledge_graph_manager.delete_entities(entityNames)
    return "Entities deleted successfully"

@mcp.tool()
async def delete_observations(deletions: List[Deletion], ctx: Context) -> str:
    """Delete specific observations from entities in the knowledge graph"""
    knowledge_graph_manager.delete_observations(deletions)
    return "Observations deleted successfully"

@mcp.tool()
async def delete_relations(relations: List[Relation], ctx: Context) -> str:
    """Delete multiple relations from the knowledge graph"""
    knowledge_graph_manager.delete_relations(relations)
    return "Relations deleted successfully"

@mcp.tool()
async def read_graph(ctx: Context) -> str:
    """Read the entire knowledge graph"""
    graph = knowledge_graph_manager.read_graph()
    return json.dumps({
        'entities': [e.model_dump(mode='json', by_alias=True) for e in graph.entities],
        'relations': [r.model_dump(mode='json', by_alias=True) for r in graph.relations]
    }, indent=2)

@mcp.tool()
async def search_nodes(query: str, ctx: Context) -> str:
    """Search for nodes in the knowledge graph based on a query"""
    graph = knowledge_graph_manager.search_nodes(query)
    return json.dumps({
        'entities': [e.model_dump(mode='json', by_alias=True) for e in graph.entities],
        'relations': [r.model_dump(mode='json', by_alias=True) for r in graph.relations]
    }, indent=2)

@mcp.tool()
async def open_nodes(names: List[str], ctx: Context) -> str:
    """Open specific nodes in the knowledge graph by their names"""
    graph = knowledge_graph_manager.open_nodes(names)
    return json.dumps({
        'entities': [e.model_dump(mode='json', by_alias=True) for e in graph.entities],
        'relations': [r.model_dump(mode='json', by_alias=True) for r in graph.relations]
    }, indent=2)

if __name__ == "__main__":
    mcp.run(transport="stdio")