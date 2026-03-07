#!/usr/bin/env python3

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, AsyncIterator

import logging
from pydantic import BaseModel, ValidationError

from mcp.server.fastmcp import FastMCP, Context

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT_DIR = Path(__file__).resolve().parents[2]
KB_DIR = ROOT_DIR / "kb"
if str(KB_DIR) not in sys.path:
    sys.path.insert(0, str(KB_DIR))

from concept_harvester import create_concept_manager, HarvesterConfig, InjectionConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, str]]:
    logger.info("Starting Concept Harvester MCP server")
    yield {"status": "running"}
    logger.info("Shutting down Concept Harvester MCP server")


mcp = FastMCP(name="concept-harvester", lifespan=server_lifespan)


class BaseConfigArgs(BaseModel):
    model_name: Optional[str] = None
    base_threshold: Optional[float] = None
    max_text_chars: Optional[int] = None
    include_scores: Optional[bool] = None


class TagChunkArgs(BaseConfigArgs):
    chunk: Dict[str, Any]
    root_topic: Optional[str] = None
    disambiguate_noise: bool = True


class TagBatchArgs(BaseConfigArgs):
    chunks: List[Dict[str, Any]]
    root_topic: Optional[str] = None
    disambiguate_noise: bool = True


class HarvestChunkArgs(BaseConfigArgs):
    chunk: Dict[str, Any]
    root_topic: Optional[str] = None


class HarvestBatchArgs(BaseConfigArgs):
    chunks: List[Dict[str, Any]]
    root_topic: Optional[str] = None


def build_manager(args: BaseConfigArgs):
    config_kwargs: Dict[str, Any] = {}
    if args.model_name is not None:
        config_kwargs["model_name"] = args.model_name
    if args.base_threshold is not None:
        config_kwargs["base_threshold"] = args.base_threshold
    if args.max_text_chars is not None:
        config_kwargs["max_text_chars"] = args.max_text_chars

    harvester_config = HarvesterConfig(**config_kwargs)
    if args.include_scores is not None:
        harvester_config.include_scores = args.include_scores

    injection_config = InjectionConfig()
    return create_concept_manager(harvester_config=harvester_config, injection_config=injection_config)


def ensure_resolution_available(manager) -> Optional[Dict[str, str]]:
    if manager.resolver.pg_session is None:
        return {
            "error": "Resolution requires a Postgres session (pg_session). Use tag_chunk or tag_batch for extraction-only."
        }
    return None


@mcp.tool()
async def tag_chunk(
    chunk: Dict[str, Any],
    ctx: Context,
    root_topic: Optional[str] = None,
    disambiguate_noise: bool = True,
    model_name: Optional[str] = None,
    base_threshold: Optional[float] = None,
    max_text_chars: Optional[int] = None,
    include_scores: Optional[bool] = None,
) -> Dict[str, Any]:
    """Extract concepts from a single chunk (no DB resolution)."""
    try:
        args = TagChunkArgs(
            chunk=chunk,
            root_topic=root_topic,
            disambiguate_noise=disambiguate_noise,
            model_name=model_name,
            base_threshold=base_threshold,
            max_text_chars=max_text_chars,
            include_scores=include_scores,
        )
    except ValidationError as exc:
        return {"error": f"Invalid arguments: {exc}"}

    manager = build_manager(args)
    concepts = manager.tag_chunk(args.chunk, args.root_topic, args.disambiguate_noise)
    return {"concepts": concepts, "count": len(concepts)}


@mcp.tool()
async def tag_batch(
    chunks: List[Dict[str, Any]],
    ctx: Context,
    root_topic: Optional[str] = None,
    disambiguate_noise: bool = True,
    model_name: Optional[str] = None,
    base_threshold: Optional[float] = None,
    max_text_chars: Optional[int] = None,
    include_scores: Optional[bool] = None,
) -> Dict[str, Any]:
    """Extract concepts from multiple chunks (no DB resolution)."""
    try:
        args = TagBatchArgs(
            chunks=chunks,
            root_topic=root_topic,
            disambiguate_noise=disambiguate_noise,
            model_name=model_name,
            base_threshold=base_threshold,
            max_text_chars=max_text_chars,
            include_scores=include_scores,
        )
    except ValidationError as exc:
        return {"error": f"Invalid arguments: {exc}"}

    manager = build_manager(args)
    results: Dict[str, Any] = {}
    for chunk in args.chunks:
        chunk_id = str(chunk.get("id", ""))
        concepts = manager.tag_chunk(chunk, args.root_topic, args.disambiguate_noise)
        results[chunk_id] = {"concepts": concepts, "count": len(concepts)}

    return {"results": results, "chunks_processed": len(args.chunks)}


@mcp.tool()
async def harvest_chunk(
    chunk: Dict[str, Any],
    ctx: Context,
    root_topic: Optional[str] = None,
    model_name: Optional[str] = None,
    base_threshold: Optional[float] = None,
    max_text_chars: Optional[int] = None,
    include_scores: Optional[bool] = None,
) -> Dict[str, Any]:
    """Extract and resolve concepts to weighted graph edges (requires DB)."""
    try:
        args = HarvestChunkArgs(
            chunk=chunk,
            root_topic=root_topic,
            model_name=model_name,
            base_threshold=base_threshold,
            max_text_chars=max_text_chars,
            include_scores=include_scores,
        )
    except ValidationError as exc:
        return {"error": f"Invalid arguments: {exc}"}

    manager = build_manager(args)
    error = ensure_resolution_available(manager)
    if error:
        return error

    edges = await manager.harvest_chunk(args.chunk, args.root_topic)
    return {"edges": [edge.__dict__ for edge in edges], "count": len(edges)}


@mcp.tool()
async def harvest_batch(
    chunks: List[Dict[str, Any]],
    ctx: Context,
    root_topic: Optional[str] = None,
    model_name: Optional[str] = None,
    base_threshold: Optional[float] = None,
    max_text_chars: Optional[int] = None,
    include_scores: Optional[bool] = None,
) -> Dict[str, Any]:
    """Batch extract and resolve concepts to graph edges (requires DB)."""
    try:
        args = HarvestBatchArgs(
            chunks=chunks,
            root_topic=root_topic,
            model_name=model_name,
            base_threshold=base_threshold,
            max_text_chars=max_text_chars,
            include_scores=include_scores,
        )
    except ValidationError as exc:
        return {"error": f"Invalid arguments: {exc}"}

    manager = build_manager(args)
    error = ensure_resolution_available(manager)
    if error:
        return error

    result = await manager.harvest_batch(args.chunks, args.root_topic)
    edges = {
        str(chunk_id): [edge.__dict__ for edge in chunk_edges]
        for chunk_id, chunk_edges in result.edges.items()
    }
    return {
        "edges": edges,
        "stats": result.stats.__dict__,
        "chunks_processed": result.stats.chunks_processed,
    }


@mcp.resource("status://concept-harvester")
def get_concept_harvester_status() -> str:
    """Return concept harvester server status."""
    return "Concept Harvester server running"


if __name__ == "__main__":
    mcp.run(transport="stdio")
