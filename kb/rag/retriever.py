# rag/retriever.py
"""
Context Retriever - The Graph-Powered RAG Engine

Replaces manual Python-side joins with Single-Query Graph Traversal.
Uses Postgres RPCs for efficient context assembly.

The Key Insight:
- Old Way: Vector search → Python loop → N queries per chunk
- New Way: Vector search → Single RPC → Full context in one shot

Usage:
    retriever = ContextRetriever(pg_session)

    # From vector search results
    context = await retriever.assemble_rag_context(
        search_results=qdrant_results,
        question="How do I configure URL seeds?"
    )

    # Feed to LLM
    response = llm.generate(context, question)
"""

import json

from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from config import ChunkKeys as K, get_logger

logger = get_logger("rag.retriever")


@dataclass
class EnrichedChunk:
    """A chunk with full graph context."""

    chunk_id: int
    content: str
    source: str
    section_path: str
    parent_context: Optional[str] = None
    prev_chunk: Optional[str] = None
    next_chunk: Optional[str] = None
    concepts: List[Dict[str, Any]] = None
    score: float = 0.0

    # Surgical Patching Metadata
    token_count: int = 0
    char_start: int = 0
    char_end: int = 0
    line_start: int = 0
    line_end: int = 0
    doc_url: str = ""

    def to_prompt_format(
        self, include_flow: bool = False, include_concepts: bool = True
    ) -> str:
        """Format for LLM prompt."""
        lines = []
        lines.append(f"[CHUNK_ID: {self.chunk_id}] (Source: {self.source})")

        if self.section_path:
            lines.append(f"**Section:** {self.section_path}")

        if self.parent_context:
            lines.append(f"**Context:** {self.parent_context[:200]}...")

        lines.append("")
        lines.append(self.content)

        if include_flow and (self.prev_chunk or self.next_chunk):
            if self.prev_chunk:
                lines.append(f"\n*Previous:* {self.prev_chunk[:100]}...")
            if self.next_chunk:
                lines.append(f"*Next:* {self.next_chunk[:100]}...")

        if include_concepts and self.concepts:
            concept_names = [c.get("name", "") for c in self.concepts[:5]]
            lines.append(f"\n*Related:* {', '.join(concept_names)}")

        return "\n".join(lines)

    def generate_ide_url(self, editor_scheme: str = "vscode") -> str:
        """Generate a deep link to open this chunk in an IDE."""
        # vscode://file/{full_path}:{line}
        if not self.doc_url:
            return ""

        # Ensure absolute path (doc_url usually is)
        path = self.doc_url.replace("\\", "/")
        if not path.startswith("/"):
            path = "/" + path

        return f"{editor_scheme}://file{path}:{self.line_start}"

    def get_git_blame(self) -> Optional[Dict[str, Any]]:
        """Run git blame for this chunk's lines to find Author and Intent."""
        import subprocess
        import os
        from datetime import datetime

        if not self.doc_url or not os.path.exists(self.doc_url):
            return None

        try:
            # git blame -L start,end --porcelain -- file
            # Limit to the first line of the chunk to get the "creator" of this block
            cmd = [
                "git",
                "blame",
                "-L",
                f"{self.line_start},{self.line_start}",
                "--line-porcelain",
                "--",
                os.path.basename(self.doc_url),
            ]

            # Run command in file's directory
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=os.path.dirname(self.doc_url),
                check=False,
            )

            if result.returncode != 0:
                print(f"Git blame failed: {result.stderr}")
                return None

            # Parse the output
            lines = result.stdout.splitlines()
            info = {}
            for line in lines:
                if line.startswith("author "):
                    info["author"] = line[7:]
                elif line.startswith("author-time "):
                    ts = int(line[12:])
                    info["date"] = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                elif line.startswith("summary "):
                    info["commit_msg"] = line[8:]

            return info

        except Exception as e:
            print(f"Git blame error: {e}")
            return None


class ContextRetriever:
    """
    Graph-powered context retriever using Postgres RPCs.

    Combines:
    - Vector search results (from Qdrant)
    - Hard graph context (parent, prev/next)
    - Soft graph context (concepts)

    Into a single enriched context for the LLM.
    """

    def __init__(
        self,
        pg_session,
        include_flow: bool = True,
        include_concepts: bool = True,
        max_concept_count: int = 5,
    ):
        """
        Initialize the retriever.

        Args:
            pg_session: SQLAlchemy async session
            include_flow: Include prev/next chunks
            include_concepts: Include related concepts
            max_concept_count: Max concepts to include per chunk
        """
        self.pg_session = pg_session
        self.include_flow = include_flow
        self.include_concepts = include_concepts
        self.max_concept_count = max_concept_count

    async def get_full_context(self, chunk_id: int) -> Optional[EnrichedChunk]:
        """
        Fetch full context for a chunk using the Postgres RPC.

        This replaces multiple Python queries with a single DB call.
        """
        if not self.pg_session:
            logger.warning("No Postgres session - returning minimal context")
            return None

        from sqlalchemy import text

        try:
            # Call the RPC
            result = await self.pg_session.execute(
                text("""
                    SELECT * FROM get_full_context(
                        :chunk_id,
                        :include_flow,
                        :include_concepts
                    )
                """),
                {
                    "chunk_id": chunk_id,
                    "include_flow": self.include_flow,
                    "include_concepts": self.include_concepts,
                },
            )

            row = result.fetchone()

            if not row:
                return None

            # Parse concepts JSON
            concepts = []
            if row.related_concepts:
                try:
                    concepts = (
                        json.loads(row.related_concepts)
                        if isinstance(row.related_concepts, str)
                        else row.related_concepts
                    )
                except:
                    pass

            return EnrichedChunk(
                chunk_id=row.chunk_id,
                content=row.chunk_content or "",
                source=row.section_path.split(" > ")[0] if row.section_path else "",
                doc_url=row.doc_url if hasattr(row, "doc_url") else "",
                section_path=row.section_path or "",
                parent_context=row.parent_context,
                prev_chunk=row.prev_chunk_text,
                next_chunk=row.next_chunk_text,
                concepts=concepts[: self.max_concept_count],
                token_count=row.meta.get(K.TOKEN_COUNT, 0)
                if hasattr(row, "meta") and row.meta
                else 0,
                char_start=row.meta.get(K.CHAR_START, 0)
                if hasattr(row, "meta") and row.meta
                else 0,
                char_end=row.meta.get(K.CHAR_END, 0)
                if hasattr(row, "meta") and row.meta
                else 0,
                line_start=row.meta.get(K.LINE_START, 0)
                if hasattr(row, "meta") and row.meta
                else 0,
                line_end=row.meta.get(K.LINE_END, 0)
                if hasattr(row, "meta") and row.meta
                else 0,
            )

        except Exception as e:
            logger.warning(f"RPC call failed for chunk {chunk_id}: {e}")
            return None

    async def enrich_search_results(
        self, search_results: List[Dict[str, Any]]
    ) -> List[EnrichedChunk]:
        """
        Enrich vector search results with graph context.

        Args:
            search_results: List of dicts with 'id' and 'score' from Qdrant

        Returns:
            List of EnrichedChunk objects
        """
        enriched = []

        for result in search_results:
            chunk_id = result.get("id")
            score = result.get("score", 0.0)

            if not chunk_id:
                continue

            # Try RPC first
            context = await self.get_full_context(chunk_id)

            if context:
                context.score = score
                enriched.append(context)
            else:
                # Fallback: create minimal chunk from search result
                enriched.append(
                    EnrichedChunk(
                        chunk_id=chunk_id,
                        content=result.get(K.TEXT, ""),
                        source=result.get(K.SOURCE_NAME, ""),
                        section_path=result.get(K.SECTION_PATH, ""),
                        score=score,
                        # Fallback has no line/char data unless in payload
                    )
                )

        return enriched

    async def assemble_rag_context(
        self,
        search_results: List[Dict[str, Any]],
        question: str,
        system_prompt: Optional[str] = None,
        max_chunks: int = 5,
    ) -> str:
        """
        Assemble complete RAG context from search results.

        This is the main entry point for the retrieval pipeline.

        Args:
            search_results: Vector search results from Qdrant
            question: User's question
            system_prompt: Optional system prompt
            max_chunks: Maximum chunks to include

        Returns:
            Formatted prompt ready for LLM
        """
        # Default system prompt
        if not system_prompt:
            system_prompt = """You are a helpful assistant for technical documentation.
When answering questions:
1. Use information from the provided context
2. ALWAYS cite your sources using [cite:CHUNK_ID] format
3. Be accurate and helpful

The context below shows chunks with their IDs. Use those exact IDs when citing."""

        # Enrich search results
        enriched = await self.enrich_search_results(search_results[:max_chunks])

        # Sort by score (highest first) or token_start for KV cache
        enriched.sort(key=lambda x: x.score, reverse=True)

        # Format chunks
        chunks_text = []
        for chunk in enriched:
            chunks_text.append(
                chunk.to_prompt_format(
                    include_flow=self.include_flow,
                    include_concepts=self.include_concepts,
                )
            )

        # Assemble final prompt
        prompt = f"""{system_prompt}

## Context

{chr(10).join(chunks_text)}

---

## User Query

{question}"""

        return prompt

    async def find_related_documents(
        self, chunk_id: int, min_shared_concepts: int = 2, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find related documents via the Hub-Hop pattern.

        Uses shared concepts to find semantically related content
        across different documents.
        """
        if not self.pg_session:
            return []

        from sqlalchemy import text

        try:
            result = await self.pg_session.execute(
                text("""
                    SELECT * FROM find_related_documents(
                        :chunk_id,
                        :min_shared,
                        :limit_count
                    )
                """),
                {
                    "chunk_id": chunk_id,
                    "min_shared": min_shared_concepts,
                    "limit_count": limit,
                },
            )

            rows = result.fetchall()

            return [
                {
                    "chunk_id": row.related_chunk_id,
                    "doc_url": row.related_doc_url,
                    "shared_count": row.shared_concept_count,
                    "shared_concepts": row.shared_concepts,
                }
                for row in rows
            ]

        except Exception as e:
            logger.warning(f"Hub-hop query failed: {e}")
            return []

    async def find_chunks_by_concepts(
        self, concept_names: List[str], limit: int = 20
    ) -> List[EnrichedChunk]:
        """
        Identify chunks that mention a set of high-level concepts.
        This is the inverse of the extraction process.
        """
        if not concept_names:
            return []

        import json

        concept_json = json.dumps(concept_names)

        from sqlalchemy import text

        try:
            result = await self.pg_session.execute(
                text("""
                    SELECT * FROM find_chunks_by_concepts(
                        CAST(:concept_json AS JSONB),
                        :limit_count
                    )
                """),
                {"concept_json": concept_json, "limit_count": limit},
            )

            rows = result.fetchall()

            enriched = []
            for row in rows:
                enriched.append(
                    EnrichedChunk(
                        chunk_id=row.chunk_id,
                        content=row.content or "",
                        source=row.doc_url or "",
                        section_path=row.section_path or "",
                        doc_url=row.doc_url or "",  # <--- Was missing
                        score=float(row.match_count),  # Use match count as score
                        token_count=row.meta.get(K.TOKEN_COUNT, 0) if row.meta else 0,
                        char_start=row.meta.get(K.CHAR_START, 0) if row.meta else 0,
                        char_end=row.meta.get(K.CHAR_END, 0) if row.meta else 0,
                        line_start=row.meta.get(K.LINE_START, 0) if row.meta else 0,
                        line_end=row.meta.get(K.LINE_END, 0) if row.meta else 0,
                    )
                )
            return enriched

        except Exception as e:
            print(f"DEBUG: SQL Error: {e}")
            logger.warning(f"Find chunks by concepts failed: {e}")
            return []

    async def identify_chunks_for_task(
        self, task_description: str, harvester: Optional[Any] = None, limit: int = 15
    ) -> List[EnrichedChunk]:
        """
        Identify which "Gifts" (chunks) are needed for a task using Concept Harvesting.

        Workflow:
        1. Extract concepts from task description using Harvester
        2. Query DB for chunks mentioning these concepts (Hub-Hop)
        3. Combine with direct vector search (optional but recommended)
        """
        # 1. Extract concepts
        if harvester is None:
            from concept_harvester import ConceptHarvester

            harvester = ConceptHarvester()

        raw_concepts = harvester.batch_extract([task_description])[0]
        concept_names = [c["name"] for c in raw_concepts if c.get("score", 0) > 0.4]

        logger.info(f"Task Concepts: {concept_names}")

        # 2. Find chunks by concepts (The Soft Graph way)
        concept_chunks = await self.find_chunks_by_concepts(concept_names, limit=limit)

        # 3. Dedup and return
        return concept_chunks

    def generate_stitcher_recipe(
        self,
        chunks: List[EnrichedChunk],
        output_path: str,
        glue_logic: Optional[Dict[int, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate a "Recipe" for the FrankensteinStitcher.

        Args:
            chunks: List of EnrichedChunks to include
            output_path: Final destination of the stitched file
            glue_logic: Dict mapping chunk_id to "glue" (AI generated code between chunks)

        Returns:
            A list of graft dictionaries
        """
        recipe = []
        glue_logic = glue_logic or {}

        for chunk in chunks:
            graft = {
                "source_path": chunk.source,
                "start": chunk.char_start,
                "end": chunk.char_end,
                "chunk_id": chunk.chunk_id,
                "glue": glue_logic.get(chunk.chunk_id),
            }
            recipe.append(graft)

        return recipe


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


async def create_retriever(pg_session=None) -> ContextRetriever:
    """
    Create a retriever, optionally with Postgres.

    Usage:
        retriever = await create_retriever(pg_session)
        context = await retriever.assemble_rag_context(results, question)
    """
    return ContextRetriever(pg_session)


def format_search_results_for_retriever(qdrant_results) -> List[Dict[str, Any]]:
    """
    Convert Qdrant results to the format expected by ContextRetriever.

    Usage:
        results = client.query_points(...)
        formatted = format_search_results_for_retriever(results)
        context = await retriever.assemble_rag_context(formatted, question)
    """
    formatted = []

    for hit in (
        qdrant_results.points if hasattr(qdrant_results, "points") else qdrant_results
    ):
        formatted.append(
            {
                "id": hit.id,
                "score": hit.score,
                "text": hit.payload.get(K.TEXT, "") if hasattr(hit, "payload") else "",
                "source": hit.payload.get(K.SOURCE_NAME, "")
                if hasattr(hit, "payload")
                else "",
                "section_path": hit.payload.get(K.SECTION_PATH, "")
                if hasattr(hit, "payload")
                else "",
            }
        )

    return formatted
