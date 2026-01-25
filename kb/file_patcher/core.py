# file_patcher/core.py
"""
Core Low-Level Primitives for File Patching.

These are the building blocks used by higher-level operations:
- apply_patch: Byte-precise content replacement
- assemble: Byte-copy from multiple sources
- ripple: Update downstream metadata in Qdrant

Users typically don't call these directly - use FilePatcherManager instead.
"""

from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass

from config import get_logger

logger = get_logger("PatcherCore")


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class PatchDelta:
    """Change metrics from a patch operation."""
    char_delta: int = 0
    line_delta: int = 0
    token_delta: int = 0
    
    def to_dict(self) -> Dict[str, int]:
        return {
            "char": self.char_delta,
            "line": self.line_delta,
            "token": self.token_delta
        }


@dataclass 
class PatchResult:
    """Result of a patch operation."""
    success: bool
    patched_content: Optional[str] = None
    delta: Optional[PatchDelta] = None
    error: Optional[str] = None


# =============================================================================
# APPLY PATCH (Byte-Precise Edit)
# =============================================================================

def apply_patch(
    original: str,
    start: int,
    end: int,
    new_content: str,
    expected: Optional[str] = None
) -> PatchResult:
    """
    Apply a byte-precise patch to content.
    
    Args:
        original: Original file content
        start: Start offset (char/byte)
        end: End offset (char/byte)
        new_content: Replacement content
        expected: Expected original text (for drift detection)
        
    Returns:
        PatchResult with patched content and deltas
    """
    # Validate offsets
    if start < 0 or end > len(original) or start > end:
        return PatchResult(
            success=False,
            error=f"Invalid offsets: start={start}, end={end}, len={len(original)}"
        )
    
    # Extract original chunk
    original_chunk = original[start:end]
    
    # Check for content drift
    if expected and expected != original_chunk:
        logger.warning(f"Content drift detected at [{start}:{end}]")
        # Continue anyway with warning, or reject:
        # return PatchResult(success=False, error="Content drift detected")
    
    # Apply patch
    patched = original[:start] + new_content + original[end:]
    
    # Calculate deltas
    delta = PatchDelta(
        char_delta=len(new_content) - len(original_chunk),
        line_delta=new_content.count('\n') - original_chunk.count('\n'),
        token_delta=(len(new_content.split()) - len(original_chunk.split()))  # Rough
    )
    
    return PatchResult(
        success=True,
        patched_content=patched,
        delta=delta
    )


# =============================================================================
# ASSEMBLE (Byte-Copy from Multiple Sources)
# =============================================================================

def assemble(
    grafts: List[Dict[str, Any]],
    sources: Dict[str, str]
) -> Tuple[str, Dict[str, int]]:
    """
    Assemble content from multiple source grafts.
    
    Args:
        grafts: List of {"source": str, "start": int, "end": int, "glue": str?}
        sources: Map of source_path -> content
        
    Returns:
        (assembled_content, stats)
    """
    parts = []
    stats = {"grafts": 0, "bytes": 0, "glue_lines": 0}
    
    for graft in grafts:
        source_path = graft.get("source") or graft.get("source_path")
        start = graft.get("start", 0)
        end = graft.get("end", 0)
        
        if source_path not in sources:
            raise ValueError(f"Source not found: {source_path}")
        
        # Extract chunk
        chunk = sources[source_path][start:end]
        parts.append(chunk)
        stats["bytes"] += len(chunk)
        stats["grafts"] += 1
        
        # Optional glue
        glue = graft.get("glue")
        if glue:
            parts.append(glue)
            stats["glue_lines"] += glue.count('\n') + 1
    
    return "\n".join(parts), stats


# =============================================================================
# VECTOR RIPPLE (Metadata-Only Updates)
# =============================================================================

async def ripple(
    client,
    collection: str,
    source: str,
    after_index: int,
    delta: PatchDelta
) -> int:
    """
    Update downstream chunk metadata after an edit.
    
    This is the "Silent State Update" - we update coordinates
    without re-embedding, preserving semantic coherence.
    
    Args:
        client: Qdrant client
        collection: Collection name
        source: File source identifier
        after_index: Start index (exclusive)
        delta: Offset changes to apply
        
    Returns:
        Number of chunks updated
    """
    from qdrant_client.models import Filter, FieldCondition, Range, MatchValue
    
    # Find downstream chunks
    downstream_filter = Filter(must=[
        FieldCondition(key="source", match=MatchValue(value=source)),
        FieldCondition(key="index", range=Range(gt=after_index))
    ])
    
    try:
        results, _ = await client.scroll(
            collection_name=collection,
            scroll_filter=downstream_filter,
            limit=500,
            with_payload=True
        )
        
        updated = 0
        for point in results:
            payload = point.payload or {}
            
            # Apply delta to all coordinate fields
            new_payload = {
                "processed_char_start": payload.get("processed_char_start", 0) + delta.char_delta,
                "processed_char_end": payload.get("processed_char_end", 0) + delta.char_delta,
                "start_line": payload.get("start_line", 0) + delta.line_delta,
                "end_line": payload.get("end_line", 0) + delta.line_delta,
            }
            
            await client.set_payload(
                collection_name=collection,
                points=[point.id],
                payload=new_payload
            )
            updated += 1
        
        logger.debug(f"Ripple: Updated {updated} downstream chunks")
        return updated
        
    except Exception as e:
        logger.warning(f"Ripple failed: {e}")
        return 0


# =============================================================================
# EMBEDDING UPDATE
# =============================================================================

async def update_embedding(
    client,
    collection: str,
    chunk_id: int,
    new_content: str,
    embed_fn: callable
) -> bool:
    """
    Update the embedding vector for a chunk.
    
    Args:
        client: Qdrant client
        collection: Collection name
        chunk_id: Point ID
        new_content: New text content
        embed_fn: Function(text) -> List[float]
        
    Returns:
        Success status
    """
    try:
        from qdrant_client.models import PointVectors
        
        new_embedding = embed_fn(new_content)
        
        await client.update_vectors(
            collection_name=collection,
            points=[PointVectors(id=chunk_id, vector=new_embedding)]
        )
        
        logger.debug(f"Updated embedding for chunk {chunk_id}")
        return True
        
    except Exception as e:
        logger.warning(f"Embedding update failed: {e}")
        return False


# =============================================================================
# FILE I/O
# =============================================================================

def read_file(path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Read file content.
    
    Returns:
        (content, error)
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read(), None
    except FileNotFoundError:
        return None, f"File not found: {path}"
    except Exception as e:
        return None, f"Read error: {e}"


def write_file(path: str, content: str) -> Tuple[bool, Optional[str]]:
    """
    Write content to file.
    
    Returns:
        (success, error)
    """
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True, None
    except Exception as e:
        return False, f"Write error: {e}"
