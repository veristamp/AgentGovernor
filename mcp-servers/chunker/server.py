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

from chunker import create_chunker, ChunkerSettings, ChunkType

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, str]]:
    logger.info("Starting Chunker MCP server")
    yield {"status": "running"}
    logger.info("Shutting down Chunker MCP server")


mcp = FastMCP(name="chunker", lifespan=server_lifespan)


class ProcessFileArgs(BaseModel):
    file_path: str
    output_path: Optional[str] = None
    overlap_tokens: int = 300
    max_tokens_text: int = 2000
    split_code_max_lines: int = 50
    split_table_rows: int = 100
    use_treesitter: bool = True
    emit_heading_chunks: bool = True
    inject_headers: bool = True
    include_chunks: bool = False


class ProcessDirectoryArgs(BaseModel):
    directory: str
    recursive: bool = False
    extensions: Optional[List[str]] = None
    output_suffix: str = "_structured.json"
    overlap_tokens: int = 300
    max_tokens_text: int = 2000
    split_code_max_lines: int = 50
    split_table_rows: int = 100
    use_treesitter: bool = True
    emit_heading_chunks: bool = True
    inject_headers: bool = True
    include_results: bool = False


class ProcessContentArgs(BaseModel):
    content: str
    filename: str
    overlap_tokens: int = 300
    max_tokens_text: int = 2000
    split_code_max_lines: int = 50
    split_table_rows: int = 100
    use_treesitter: bool = True
    emit_heading_chunks: bool = True
    inject_headers: bool = True
    include_chunks: bool = False


def build_settings(args: Any) -> ChunkerSettings:
    return ChunkerSettings(
        max_tokens_text=args.max_tokens_text,
        overlap_tokens=args.overlap_tokens,
        min_keep_tokens=1,
        emit_heading_chunks=args.emit_heading_chunks,
        inject_headers=args.inject_headers,
        split_code_max_lines=args.split_code_max_lines,
        split_table_rows=args.split_table_rows,
        use_treesitter=args.use_treesitter,
        max_tokens_by_type={
            ChunkType.TEXT.value: args.max_tokens_text,
            ChunkType.CODE.value: args.max_tokens_text,
            ChunkType.TABLE.value: args.max_tokens_text,
        },
    )


def summarize_result(result: Any) -> Dict[str, Any]:
    return {
        "source": result.source,
        "metadata": result.metadata,
        "total_chunks": result.total_chunks,
        "stats": result.stats.to_dict(),
    }


@mcp.tool()
async def chunk_file(
    file_path: str,
    ctx: Context,
    output_path: Optional[str] = None,
    overlap_tokens: int = 300,
    max_tokens_text: int = 2000,
    split_code_max_lines: int = 50,
    split_table_rows: int = 100,
    use_treesitter: bool = True,
    emit_heading_chunks: bool = True,
    inject_headers: bool = True,
    include_chunks: bool = False,
) -> Dict[str, Any]:
    """Chunk a single file into structured JSON output."""
    try:
        args = ProcessFileArgs(
            file_path=file_path,
            output_path=output_path,
            overlap_tokens=overlap_tokens,
            max_tokens_text=max_tokens_text,
            split_code_max_lines=split_code_max_lines,
            split_table_rows=split_table_rows,
            use_treesitter=use_treesitter,
            emit_heading_chunks=emit_heading_chunks,
            inject_headers=inject_headers,
            include_chunks=include_chunks,
        )
    except ValidationError as exc:
        return {"error": f"Invalid arguments: {exc}"}

    path = Path(args.file_path).expanduser()
    if not path.exists():
        return {"error": f"File not found: {path}"}
    if not path.is_file():
        return {"error": f"Not a file: {path}"}

    settings = build_settings(args)
    chunker = create_chunker(settings=settings)
    resolved_output = args.output_path or str(path.parent / f"{path.stem}_structured.json")
    result = chunker.process_file(path, resolved_output)

    payload = summarize_result(result)
    payload["output_path"] = resolved_output
    if args.include_chunks:
        payload["result"] = result.to_dict()
    return payload


@mcp.tool()
async def chunk_directory(
    directory: str,
    ctx: Context,
    recursive: bool = False,
    extensions: Optional[List[str]] = None,
    output_suffix: str = "_structured.json",
    overlap_tokens: int = 300,
    max_tokens_text: int = 2000,
    split_code_max_lines: int = 50,
    split_table_rows: int = 100,
    use_treesitter: bool = True,
    emit_heading_chunks: bool = True,
    inject_headers: bool = True,
    include_results: bool = False,
) -> Dict[str, Any]:
    """Chunk all supported files in a directory."""
    try:
        args = ProcessDirectoryArgs(
            directory=directory,
            recursive=recursive,
            extensions=extensions,
            output_suffix=output_suffix,
            overlap_tokens=overlap_tokens,
            max_tokens_text=max_tokens_text,
            split_code_max_lines=split_code_max_lines,
            split_table_rows=split_table_rows,
            use_treesitter=use_treesitter,
            emit_heading_chunks=emit_heading_chunks,
            inject_headers=inject_headers,
            include_results=include_results,
        )
    except ValidationError as exc:
        return {"error": f"Invalid arguments: {exc}"}

    dir_path = Path(args.directory).expanduser()
    if not dir_path.exists():
        return {"error": f"Directory not found: {dir_path}"}
    if not dir_path.is_dir():
        return {"error": f"Not a directory: {dir_path}"}

    settings = build_settings(args)
    chunker = create_chunker(settings=settings)
    batch = chunker.process_directory(
        dir_path,
        extensions=args.extensions,
        output_suffix=args.output_suffix,
        recursive=args.recursive,
        settings=settings,
    )

    outputs = []
    for source in batch.results.keys():
        source_path = Path(source)
        output_path = source_path.with_name(f"{source_path.stem}{args.output_suffix}")
        outputs.append({"source": str(source_path), "output_path": str(output_path)})

    payload: Dict[str, Any] = {
        "files_processed": batch.files_processed,
        "total_stats": batch.total_stats.to_dict(),
        "outputs": outputs,
    }

    if args.include_results:
        payload["results"] = {k: summarize_result(v) for k, v in batch.results.items()}

    return payload


@mcp.tool()
async def chunk_content(
    content: str,
    filename: str,
    ctx: Context,
    overlap_tokens: int = 300,
    max_tokens_text: int = 2000,
    split_code_max_lines: int = 50,
    split_table_rows: int = 100,
    use_treesitter: bool = True,
    emit_heading_chunks: bool = True,
    inject_headers: bool = True,
    include_chunks: bool = False,
) -> Dict[str, Any]:
    """Chunk raw content without reading from disk."""
    try:
        args = ProcessContentArgs(
            content=content,
            filename=filename,
            overlap_tokens=overlap_tokens,
            max_tokens_text=max_tokens_text,
            split_code_max_lines=split_code_max_lines,
            split_table_rows=split_table_rows,
            use_treesitter=use_treesitter,
            emit_heading_chunks=emit_heading_chunks,
            inject_headers=inject_headers,
            include_chunks=include_chunks,
        )
    except ValidationError as exc:
        return {"error": f"Invalid arguments: {exc}"}

    settings = build_settings(args)
    chunker = create_chunker(settings=settings)
    result = chunker.process_content(args.content, args.filename, settings=settings)

    payload = summarize_result(result)
    if args.include_chunks:
        payload["result"] = result.to_dict()
    return payload


@mcp.resource("status://chunker")
def get_chunker_status() -> str:
    """Return chunker server status."""
    return "Chunker server running"


if __name__ == "__main__":
    mcp.run(transport="stdio")
