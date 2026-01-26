# kb/engram/navigator.py
"""
Graph Navigator - The "Hardware-Level" Memory Access Pattern

This implements the Engram navigation that replaces "context stuffing" with
programmatic graph traversal. The Agent (RLM) uses this to:

1. Get structure without loading content (O(1) lookup)
2. Navigate to specific nodes (Hub-Hop pattern)
3. Recursively expand context as needed

Key Insight: The Navigator returns POINTERS (node IDs), not content.
The Agent decides when to "dereference" and load actual content.

This mimics how hardware memory works:
- Page table lookups (get_structure) → O(1)
- Page faults (load_content) → On-demand
- TLB cache (Prefix Caching) → Hot paths stay fast
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_logger

logger = get_logger("engram.navigator")


class TraversalMode(Enum):
    """How to traverse the graph."""
    STRUCTURE_ONLY = "structure"  # Return pointers, no content
    SHALLOW = "shallow"           # Load immediate content only
    DEEP = "deep"                 # Recursive expansion


@dataclass
class NodePointer:
    """
    A lightweight reference to a graph node.
    
    This is the "inode" - contains metadata but NOT the actual content.
    The Agent must explicitly request content via load_content().
    """
    id: int
    type: str                      # CHUNK, CODE, SECTION, DOC
    doc_url: str
    section_path: Optional[str] = None
    
    # Connectivity (the "links" in the inode)
    parent_id: Optional[int] = None
    prev_id: Optional[int] = None
    next_id: Optional[int] = None
    child_ids: List[int] = field(default_factory=list)
    
    # Concept links (the "soft graph" connections)
    concept_ids: List[int] = field(default_factory=list)
    concept_names: List[str] = field(default_factory=list)
    
    # Size hints (for budget planning)
    token_count: int = 0
    char_count: int = 0
    line_start: int = 0
    line_end: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "doc_url": self.doc_url,
            "section_path": self.section_path,
            "parent_id": self.parent_id,
            "prev_id": self.prev_id,
            "next_id": self.next_id,
            "child_ids": self.child_ids,
            "concept_ids": self.concept_ids,
            "concept_names": self.concept_names,
            "token_count": self.token_count,
            "line_range": [self.line_start, self.line_end],
        }


@dataclass
class NavigatorResult:
    """Result of a navigation operation."""
    nodes: List[NodePointer]
    total_tokens: int = 0
    path_description: str = ""
    
    # For Hub-Hop results
    shared_concepts: Optional[List[str]] = None
    hop_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "total_tokens": self.total_tokens,
            "path": self.path_description,
            "shared_concepts": self.shared_concepts,
            "hop_count": self.hop_count,
        }


class GraphNavigator:
    """
    The Engram Navigator - Programmatic Graph Traversal.
    
    This is the "hardware" that the RLM (Agent) uses to access memory.
    It provides O(1) structural lookups and on-demand content loading.
    
    Key Methods:
    - get_file_structure(path) → List[NodePointer]  # The "page table"
    - get_node_context(id) → NodePointer            # Single node metadata
    - hub_hop(id) → List[NodePointer]               # Related via concepts
    - load_content(ids) → Dict[int, str]            # The "page fault handler"
    
    The Agent workflow:
    1. Get structure (fast, no tokens)
    2. Identify relevant nodes
    3. Load only those nodes' content
    4. Process with LLM
    """
    
    def __init__(self, pg_session: AsyncSession):
        self.pg_session = pg_session
        self._cache: Dict[int, NodePointer] = {}  # TLB analog
        
    # =========================================================================
    # STRUCTURE QUERIES (O(1) - No Content Loading)
    # =========================================================================
    
    async def get_file_structure(
        self, 
        file_pattern: str,
        max_depth: int = 3
    ) -> NavigatorResult:
        """
        Get the AST/structure of a file WITHOUT loading content.
        
        This is the "page table lookup" - returns NodePointers that
        the Agent can selectively expand.
        
        Args:
            file_pattern: Glob pattern for file path (e.g., "auth.ts", "%/auth/%")
            max_depth: How deep to traverse the hierarchy
            
        Returns:
            NavigatorResult with NodePointers for each structural element
        """
        result = await self.pg_session.execute(text("""
            WITH RECURSIVE tree AS (
                -- Anchor: Find root nodes matching pattern
                SELECT 
                    n.id, n.type, n.doc_url, n.section_path,
                    n.parent_id, n.prev_id, n.next_id,
                    n.meta,
                    0 as depth
                FROM nodes n
                WHERE n.doc_url LIKE :pattern
                AND n.parent_id IS NULL
                
                UNION ALL
                
                -- Recurse: Get children
                SELECT 
                    n.id, n.type, n.doc_url, n.section_path,
                    n.parent_id, n.prev_id, n.next_id,
                    n.meta,
                    t.depth + 1
                FROM nodes n
                JOIN tree t ON n.parent_id = t.id
                WHERE t.depth < :max_depth
            )
            SELECT 
                t.*,
                COALESCE(
                    (SELECT array_agg(c.id) FROM nodes c WHERE c.parent_id = t.id),
                    ARRAY[]::bigint[]
                ) as child_ids,
                COALESCE(
                    (SELECT array_agg(gc.id) FROM edges e 
                     JOIN global_concepts gc ON e.target_id = gc.id 
                     WHERE e.source_id = t.id AND e.edge_type = 'MENTIONS'),
                    ARRAY[]::integer[]
                ) as concept_ids,
                COALESCE(
                    (SELECT array_agg(gc.name) FROM edges e 
                     JOIN global_concepts gc ON e.target_id = gc.id 
                     WHERE e.source_id = t.id AND e.edge_type = 'MENTIONS'),
                    ARRAY[]::text[]
                ) as concept_names
            FROM tree t
            ORDER BY t.depth, t.id
        """), {"pattern": f"%{file_pattern}%", "max_depth": max_depth})
        
        nodes = []
        total_tokens = 0
        
        for row in result.fetchall():
            meta = row.meta or {}
            pointer = NodePointer(
                id=row.id,
                type=row.type,
                doc_url=row.doc_url,
                section_path=row.section_path,
                parent_id=row.parent_id,
                prev_id=row.prev_id,
                next_id=row.next_id,
                child_ids=list(row.child_ids) if row.child_ids else [],
                concept_ids=list(row.concept_ids) if row.concept_ids else [],
                concept_names=list(row.concept_names) if row.concept_names else [],
                token_count=meta.get("token_count", 0),
                char_count=meta.get("char_end", 0) - meta.get("char_start", 0),
                line_start=meta.get("line_start", 0),
                line_end=meta.get("line_end", 0),
            )
            nodes.append(pointer)
            total_tokens += pointer.token_count
            self._cache[pointer.id] = pointer
            
        return NavigatorResult(
            nodes=nodes,
            total_tokens=total_tokens,
            path_description=f"structure:{file_pattern}"
        )
    
    async def get_node_context(self, node_id: int) -> Optional[NodePointer]:
        """
        Get metadata for a single node (no content).
        
        This is a cache-aware lookup - checks TLB first.
        """
        if node_id in self._cache:
            return self._cache[node_id]
            
        result = await self.pg_session.execute(text("""
            SELECT 
                n.id, n.type, n.doc_url, n.section_path,
                n.parent_id, n.prev_id, n.next_id,
                n.meta,
                COALESCE(
                    (SELECT array_agg(c.id) FROM nodes c WHERE c.parent_id = n.id),
                    ARRAY[]::bigint[]
                ) as child_ids,
                COALESCE(
                    (SELECT array_agg(gc.id) FROM edges e 
                     JOIN global_concepts gc ON e.target_id = gc.id 
                     WHERE e.source_id = n.id AND e.edge_type = 'MENTIONS'),
                    ARRAY[]::integer[]
                ) as concept_ids,
                COALESCE(
                    (SELECT array_agg(gc.name) FROM edges e 
                     JOIN global_concepts gc ON e.target_id = gc.id 
                     WHERE e.source_id = n.id AND e.edge_type = 'MENTIONS'),
                    ARRAY[]::text[]
                ) as concept_names
            FROM nodes n
            WHERE n.id = :node_id
        """), {"node_id": node_id})
        
        row = result.fetchone()
        if not row:
            return None
            
        meta = row.meta or {}
        pointer = NodePointer(
            id=row.id,
            type=row.type,
            doc_url=row.doc_url,
            section_path=row.section_path,
            parent_id=row.parent_id,
            prev_id=row.prev_id,
            next_id=row.next_id,
            child_ids=list(row.child_ids) if row.child_ids else [],
            concept_ids=list(row.concept_ids) if row.concept_ids else [],
            concept_names=list(row.concept_names) if row.concept_names else [],
            token_count=meta.get("token_count", 0),
            char_count=meta.get("char_end", 0) - meta.get("char_start", 0),
            line_start=meta.get("line_start", 0),
            line_end=meta.get("line_end", 0),
        )
        self._cache[pointer.id] = pointer
        return pointer
    
    # =========================================================================
    # HUB-HOP NAVIGATION (Concept-Based Traversal)
    # =========================================================================
    
    async def hub_hop(
        self, 
        source_id: int, 
        min_shared_concepts: int = 2,
        limit: int = 10
    ) -> NavigatorResult:
        """
        Find related nodes via shared concepts (the Hub-Hop pattern).
        
        This is the "associative memory" - given a node, find semantically
        related nodes across the entire codebase.
        
        The pattern:
        1. Get concepts from source node (the "Hub")
        2. Find other nodes mentioning same concepts
        3. Rank by number of shared concepts
        
        Args:
            source_id: Starting node ID
            min_shared_concepts: Minimum overlap to consider related
            limit: Maximum results
            
        Returns:
            NavigatorResult with related NodePointers
        """
        result = await self.pg_session.execute(text("""
            SELECT * FROM find_related_documents(
                :source_id,
                :min_shared,
                :limit_count
            )
        """), {
            "source_id": source_id,
            "min_shared": min_shared_concepts,
            "limit_count": limit
        })
        
        rows = result.fetchall()
        nodes = []
        shared_concepts_all = set()
        
        for row in rows:
            # Get full node context for each related chunk
            pointer = await self.get_node_context(row.related_chunk_id)
            if pointer:
                nodes.append(pointer)
                
            # Collect shared concepts
            if row.shared_concepts:
                for concept in row.shared_concepts:
                    shared_concepts_all.add(concept)
        
        return NavigatorResult(
            nodes=nodes,
            total_tokens=sum(n.token_count for n in nodes),
            path_description=f"hub_hop:{source_id}→{len(nodes)} related",
            shared_concepts=list(shared_concepts_all),
            hop_count=1
        )
    
    async def concept_search(
        self, 
        concept_names: List[str],
        limit: int = 20
    ) -> NavigatorResult:
        """
        Find nodes by concept names directly.
        
        This is the "semantic index lookup" - given high-level concepts,
        find all nodes that mention them.
        """
        import json
        concept_json = json.dumps(concept_names)
        
        result = await self.pg_session.execute(text("""
            SELECT * FROM find_chunks_by_concepts(
                CAST(:concept_json AS JSONB),
                :limit_count
            )
        """), {"concept_json": concept_json, "limit_count": limit})
        
        nodes = []
        for row in result.fetchall():
            meta = row.meta or {}
            pointer = NodePointer(
                id=row.chunk_id,
                type="CHUNK",
                doc_url=row.doc_url or "",
                section_path=row.section_path,
                token_count=meta.get("token_count", 0),
                line_start=meta.get("line_start", 0),
                line_end=meta.get("line_end", 0),
            )
            nodes.append(pointer)
            self._cache[pointer.id] = pointer
            
        return NavigatorResult(
            nodes=nodes,
            total_tokens=sum(n.token_count for n in nodes),
            path_description=f"concept_search:[{', '.join(concept_names[:3])}...]",
            shared_concepts=concept_names
        )
    
    # =========================================================================
    # CONTENT LOADING (The "Page Fault Handler")
    # =========================================================================
    
    async def load_content(
        self, 
        node_ids: List[int],
        include_flow: bool = False
    ) -> Dict[int, Dict[str, Any]]:
        """
        Load actual content for specific nodes.
        
        This is the expensive operation - only call when you NEED the content.
        The Agent should minimize these calls by using structure queries first.
        
        Args:
            node_ids: List of node IDs to load
            include_flow: Also load prev/next chunks for context
            
        Returns:
            Dict mapping node_id → {content, prev_content, next_content, ...}
        """
        if not node_ids:
            return {}
            
        result = await self.pg_session.execute(text("""
            SELECT 
                n.id,
                n.content,
                n.type,
                n.section_path,
                n.doc_url,
                n.meta,
                pn.content as prev_content,
                nn.content as next_content
            FROM nodes n
            LEFT JOIN nodes pn ON n.prev_id = pn.id
            LEFT JOIN nodes nn ON n.next_id = nn.id
            WHERE n.id = ANY(:ids)
        """), {"ids": node_ids})
        
        contents = {}
        for row in result.fetchall():
            meta = row.meta or {}
            contents[row.id] = {
                "content": row.content or "",
                "type": row.type,
                "section_path": row.section_path,
                "doc_url": row.doc_url,
                "line_start": meta.get("line_start", 0),
                "line_end": meta.get("line_end", 0),
                "prev_content": row.prev_content if include_flow else None,
                "next_content": row.next_content if include_flow else None,
            }
            
        return contents
    
    async def load_function(
        self, 
        file_pattern: str, 
        function_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Load a specific function by name from a file.
        
        This is the "surgical read" - gets exactly one function definition,
        not the whole file.
        
        Args:
            file_pattern: File to search in
            function_name: Name of function/class to load
            
        Returns:
            Dict with content, line range, and metadata
        """
        result = await self.pg_session.execute(text("""
            SELECT 
                n.id, n.content, n.type, n.section_path, n.doc_url, n.meta
            FROM nodes n
            WHERE n.doc_url LIKE :pattern
            AND n.type = 'CODE'
            AND n.meta->>'symbols_defined' LIKE :symbol_pattern
            LIMIT 1
        """), {
            "pattern": f"%{file_pattern}%",
            "symbol_pattern": f"%{function_name}%"
        })
        
        row = result.fetchone()
        if not row:
            return None
            
        meta = row.meta or {}
        return {
            "id": row.id,
            "content": row.content,
            "type": row.type,
            "section_path": row.section_path,
            "doc_url": row.doc_url,
            "line_start": meta.get("line_start", 0),
            "line_end": meta.get("line_end", 0),
            "symbols": meta.get("symbols_defined", []),
        }
    
    # =========================================================================
    # GRAPH WALKING (Recursive Exploration)
    # =========================================================================
    
    async def walk_graph(
        self,
        start_id: int,
        max_depth: int = 2,
        max_tokens: int = 4000
    ) -> NavigatorResult:
        """
        Recursively walk the graph from a starting node.
        
        Uses the get_graph_context RPC for efficient traversal.
        Stops when token budget is exceeded.
        """
        result = await self.pg_session.execute(text("""
            SELECT * FROM get_graph_context(:start_id, :max_depth)
        """), {"start_id": start_id, "max_depth": max_depth})
        
        nodes = []
        total_tokens = 0
        
        for row in result.fetchall():
            pointer = await self.get_node_context(row.node_id)
            if not pointer:
                continue
                
            # Check budget
            if total_tokens + pointer.token_count > max_tokens:
                break
                
            nodes.append(pointer)
            total_tokens += pointer.token_count
            
        return NavigatorResult(
            nodes=nodes,
            total_tokens=total_tokens,
            path_description=f"walk:{start_id}→depth={max_depth}",
            hop_count=max_depth
        )
    
    # =========================================================================
    # CACHE MANAGEMENT
    # =========================================================================
    
    def clear_cache(self):
        """Clear the TLB cache."""
        self._cache.clear()
        
    def get_cached(self, node_id: int) -> Optional[NodePointer]:
        """Get a cached pointer without DB access."""
        return self._cache.get(node_id)
