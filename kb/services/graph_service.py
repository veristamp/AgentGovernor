# services/graph_service.py
"""
Graph Service - Core graph operations.

Handles all graph-related business logic:
- Graph summary (nodes, concepts, documents)
- Node neighbor exploration
- Document reconstruction from chunks
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json
import re

from config import get_logger

logger = get_logger("GraphService")


class GraphService:
    """
    Graph-related operations.
    
    All methods are static or take a session - no state.
    This makes testing easy and avoids global state issues.
    """
    
    @staticmethod
    async def get_summary(
        session: AsyncSession,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get high-level graph overview.
        
        Returns top concepts and documents for initial visualization.
        """
        # Get top concepts by degree
        concepts = await session.execute(text("""
            SELECT id, name, doc_count, 'CONCEPT' as type 
            FROM global_concepts 
            ORDER BY doc_count DESC 
            LIMIT :limit
        """), {"limit": limit})
        
        # Get documents
        docs = await session.execute(text("""
            SELECT id, doc_url as label, 'DOC' as type 
            FROM nodes 
            WHERE type = 'DOC' 
            LIMIT :limit
        """), {"limit": limit})
        
        nodes = []
        nodes.extend([dict(row._mapping) for row in concepts])
        nodes.extend([dict(row._mapping) for row in docs])
        
        return {"nodes": nodes, "links": []}
    
    @staticmethod
    async def get_neighbors(
        session: AsyncSession,
        node_id: int
    ) -> Dict[str, Any]:
        """
        Get immediate neighbors for a node.
        
        Used for exploring the graph on click.
        """
        edges = await session.execute(text("""
            SELECT 
                e.source_id, e.target_id, e.edge_type, e.weight,
                sn.type as source_type, sn.content as source_label,
                tn.type as target_type, tn.content as target_label,
                gc_target.name as target_concept_name,
                gc_source.name as source_concept_name
            FROM edges e
            LEFT JOIN nodes sn ON e.source_id = sn.id
            LEFT JOIN nodes tn ON e.target_id = tn.id
            LEFT JOIN global_concepts gc_target ON e.target_id = gc_target.id
            LEFT JOIN global_concepts gc_source ON e.source_id = gc_source.id
            WHERE e.source_id = :nid OR e.target_id = :nid
            LIMIT 50
        """), {"nid": node_id})
        
        nodes = {}
        links = []
        
        for row in edges:
            s_id, t_id = row.source_id, row.target_id
            
            # Resolve labels
            s_label = row.source_concept_name or (row.source_label[:30] + "..." if row.source_label else f"Node {s_id}")
            t_label = row.target_concept_name or (row.target_label[:30] + "..." if row.target_label else f"Node {t_id}")
            
            s_type = "CONCEPT" if row.source_concept_name else (row.source_type or "UNKNOWN")
            t_type = "CONCEPT" if row.target_concept_name else (row.target_type or "UNKNOWN")

            if s_id not in nodes:
                nodes[s_id] = {"id": s_id, "label": s_label, "type": s_type}
            if t_id not in nodes:
                nodes[t_id] = {"id": t_id, "label": t_label, "type": t_type}
                
            links.append({
                "source": s_id,
                "target": t_id,
                "type": row.edge_type,
                "weight": row.weight
            })
            
        return {"nodes": list(nodes.values()), "links": links}
    
    @staticmethod
    async def get_document(
        session: AsyncSession,
        file_pattern: str
    ) -> Dict[str, Any]:
        """
        Reconstruct a document from its chunks.
        
        Uses smart merging for code files.
        """
        chunks_result = await session.execute(text("""
            SELECT content, type, meta, id, doc_url 
            FROM nodes 
            WHERE doc_url LIKE :url AND type IN ('CHUNK', 'CODE', 'TABLE', 'SECTION')
            ORDER BY id ASC
        """), {"url": f"%{file_pattern}%"})
        
        all_chunks = []
        for row in chunks_result:
            meta = row.meta
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except json.JSONDecodeError:
                    meta = {}
            
            # Extract original_text for high-fidelity reconstruction
            content = row.content
            if meta and 'original_text' in meta:
                content = meta['original_text']
            
            all_chunks.append({
                "id": row.id,
                "content": content,
                "type": row.type,
                "meta": meta,
                "doc_url": row.doc_url
            })
        
        if not all_chunks:
            return {"chunks": [], "file": file_pattern, "total_chunks": 0}
        
        # Detect if this is a pure code file
        doc_url = all_chunks[0]["doc_url"]
        is_code_file = doc_url.endswith(('.py', '.js', '.ts', '.go', '.rs', '.c', '.cpp', '.java'))
        
        # Sort by processed_char_start if available
        sorted_chunks = sorted(
            all_chunks,
            key=lambda c: c["meta"].get("processed_char_start", c.get("id", 0))
        )
        
        # For code files, merge into unified blocks
        if is_code_file:
            sorted_chunks = GraphService._merge_code_chunks(sorted_chunks)
        
        return {
            "chunks": sorted_chunks,
            "file": doc_url,
            "total_chunks": len(sorted_chunks),
            "is_code_file": is_code_file
        }
    
    @staticmethod
    def _merge_code_chunks(chunks: List[Dict]) -> List[Dict]:
        """Merge all code chunks into one continuous block."""
        code_chunks = [c for c in chunks if c.get("type") in ("CODE", "CHUNK")]
        
        if len(code_chunks) <= 1:
            return chunks
        
        merged_content = "\n".join(c["content"] for c in code_chunks)
        
        return [{
            "id": code_chunks[0]["id"],
            "content": merged_content,
            "type": "CODE",
            "meta": {
                "merged": True,
                "original_count": len(code_chunks),
                "language": code_chunks[0].get("meta", {}).get("language", "python")
            },
            "doc_url": code_chunks[0]["doc_url"]
        }]
    
    @staticmethod
    async def list_files(session: AsyncSession) -> List[Dict[str, str]]:
        """List all available documents."""
        from pathlib import Path
        
        result = await session.execute(text(
            "SELECT DISTINCT doc_url FROM nodes WHERE type = 'CHUNK'"
        ))
        files = [row[0] for row in result]
        
        return [{"name": Path(f).name, "full_path": f} for f in files]
