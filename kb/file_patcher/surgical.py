# file_patcher/surgical.py
"""
Surgical Patcher - Byte-precise chunk editing with Vector Ripple.

Edits EXISTING files by replacing chunks while maintaining vector DB consistency.

Usage:
    from file_patcher import SurgicalPatcher
    
    patcher = SurgicalPatcher(qdrant_client=client)
    
    receipt = await patcher.patch(
        file_path="src/main.py",
        collection="kb_chunks",
        chunk={"id": 123, "index": 5, "processed_char_start": 100, ...},
        new_content="new code here",
        session_maker=db_session
    )
"""

from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from config import get_logger, DATABASE_CONFIG
from .core import apply_patch, ripple, update_embedding, read_file, write_file, PatchDelta
from .guards import run_judgment_pipeline

logger = get_logger("SurgicalPatcher")


@dataclass
class PatchReceipt:
    """Result of a surgical patch operation."""
    success: bool = False
    file_path: str = ""
    chunk_id: Optional[int] = None
    chunk_index: Optional[int] = None
    delta: Optional[Dict[str, int]] = None
    downstream_updated: int = 0
    embedding_updated: bool = False
    validation: Optional[Dict] = None
    critique: Optional[Dict] = None
    impact: Optional[Dict] = None
    tests: Optional[Dict] = None
    error: Optional[str] = None
    warnings: list = field(default_factory=list)
    dry_run: bool = False
    staged_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "file_path": self.file_path,
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "deltas": self.delta,
            "downstream_updated": self.downstream_updated,
            "embedding_updated": self.embedding_updated,
            "validation": self.validation,
            "critique": self.critique,
            "impact": self.impact,
            "tests": self.tests,
            "error": self.error,
            "warnings": self.warnings,
            "dry_run": self.dry_run,
            "staged_path": self.staged_path
        }


class SurgicalPatcher:
    """
    Surgical editor for code chunks.
    
    Features:
    - Distributed locking (prevents concurrent edits)
    - Judgment pipeline (syntax, critic, impact, tests)
    - Vector Ripple (updates downstream offsets)
    - VFS staging (optional write to staging area)
    """
    
    def __init__(
        self,
        qdrant_client: Optional[Any] = None,
        qdrant_url: Optional[str] = None,
        staging_dir: str = "f:/kb/.staging",
        agent_id: str = "system"
    ):
        """
        Initialize the patcher.
        
        Args:
            qdrant_client: Pre-configured Qdrant client
            qdrant_url: Qdrant URL (used if client not provided)
            staging_dir: Directory for VFS staging
            agent_id: Agent identifier for lock ownership
        """
        self._qdrant = qdrant_client
        self._qdrant_url = qdrant_url or DATABASE_CONFIG.qdrant_url
        self._staging_dir = Path(staging_dir)
        self._staging_dir.mkdir(parents=True, exist_ok=True)
        self._agent_id = agent_id
        self._lock_timeout = 60.0
    
    @property
    def qdrant(self):
        """Lazy-load Qdrant client."""
        if self._qdrant is None:
            from qdrant_client import QdrantClient
            self._qdrant = QdrantClient(url=self._qdrant_url)
        return self._qdrant
    
    async def patch(
        self,
        file_path: str,
        collection: str,
        chunk: Dict[str, Any],
        new_content: str,
        embed_fn: Optional[callable] = None,
        session_maker: Optional[Any] = None,
        dry_run: bool = False,
        staged: bool = False,
        validate: bool = True,
        critique: bool = False,
        impact: bool = False,
        test: bool = False
    ) -> PatchReceipt:
        """
        Perform a surgical edit with safety gates.
        
        Args:
            file_path: Path to the source file
            collection: Qdrant collection name
            chunk: Chunk dict with id, index, and offsets
            new_content: New text for this chunk
            embed_fn: Optional embedding function
            session_maker: DB session maker for distributed lock
            dry_run: Validate without writing
            staged: Write to staging area instead of real path
            validate: Run syntax validation
            critique: Run diff critique
            impact: Run impact analysis
            test: Run related tests
            
        Returns:
            PatchReceipt with results
        """
        receipt = PatchReceipt(
            file_path=file_path,
            chunk_id=chunk.get("id"),
            chunk_index=chunk.get("index")
        )
        
        # Extract offsets
        start = chunk.get("processed_char_start") or chunk.get("char_start")
        end = chunk.get("processed_char_end") or chunk.get("char_end")
        
        if start is None or end is None:
            receipt.error = "Missing character offsets in chunk"
            return receipt
        
        # Require session_maker for distributed locking
        if not session_maker:
            receipt.error = "Session maker required for distributed locking"
            return receipt
        
        async with session_maker() as session:
            try:
                # 1. Acquire lock
                if not await self._acquire_lock(session, file_path):
                    receipt.error = f"File locked by another agent: {file_path}"
                    return receipt
                
                # 2. Read original file
                original, err = read_file(file_path)
                if err:
                    receipt.error = err
                    return receipt
                
                # 3. Get old content for judgment
                old_content = chunk.get("original_text", chunk.get("text", ""))
                
                # 4. Run judgment pipeline
                judgment = await run_judgment_pipeline(
                    file_path=file_path,
                    old_content=old_content,
                    new_content=new_content,
                    validate_syntax=validate,
                    run_critic=critique,
                    run_impact=impact,
                    run_tests=test,
                    project_root=str(Path(file_path).parent.parent),
                    chunk_metadata=chunk,
                    session_maker=session_maker
                )
                
                # Copy gate results
                gate_results = judgment.get("gate_results", {})
                receipt.validation = gate_results.get("validator")
                receipt.critique = gate_results.get("critic")
                receipt.impact = gate_results.get("oracle")
                receipt.tests = gate_results.get("immune")
                receipt.warnings = judgment.get("warnings", [])
                
                if not judgment.get("approved"):
                    receipt.error = judgment.get("rejection_reason", "Judgment rejected")
                    return receipt
                
                # 5. Apply the patch
                result = apply_patch(
                    original=original,
                    start=start,
                    end=end,
                    new_content=new_content,
                    expected=old_content
                )
                
                if not result.success:
                    receipt.error = result.error
                    return receipt
                
                receipt.delta = result.delta.to_dict()
                
                # 6. Dry run - don't write
                if dry_run:
                    receipt.success = True
                    receipt.dry_run = True
                    return receipt
                
                # 7. Write file (real or staged)
                if staged:
                    import hashlib
                    path_hash = hashlib.md5(file_path.encode()).hexdigest()[:8]
                    target = str(self._staging_dir / f"{path_hash}_{Path(file_path).name}")
                    receipt.staged_path = target
                else:
                    target = file_path
                
                success, err = write_file(target, result.patched_content)
                if not success:
                    receipt.error = err
                    return receipt
                
                # 8. Update embedding
                if embed_fn:
                    receipt.embedding_updated = await update_embedding(
                        client=self.qdrant,
                        collection=collection,
                        chunk_id=chunk["id"],
                        new_content=new_content,
                        embed_fn=embed_fn
                    )
                
                # 9. Vector Ripple
                file_source = chunk.get("source", Path(file_path).name)
                receipt.downstream_updated = await ripple(
                    client=self.qdrant,
                    collection=collection,
                    source=file_source,
                    after_index=chunk["index"],
                    delta=result.delta
                )
                
                receipt.success = True
                logger.info(
                    f"✅ Surgical edit: {Path(file_path).name} "
                    f"(rippled: {receipt.downstream_updated})"
                )
                
            except Exception as e:
                logger.exception("Surgical patch failed")
                receipt.error = str(e)
                
            finally:
                await self._release_lock(session, file_path)
        
        return receipt
    
    async def _acquire_lock(self, session, file_path: str) -> bool:
        """Acquire distributed lock."""
        from sqlalchemy import delete, insert
        from datetime import datetime, timedelta
        from db.schema import FileLock
        
        now = datetime.utcnow()
        expires = now + timedelta(seconds=self._lock_timeout)
        
        # Clean expired
        await session.execute(
            delete(FileLock).where(
                (FileLock.file_path == file_path) & (FileLock.expires_at < now)
            )
        )
        
        # Try acquire
        try:
            await session.execute(
                insert(FileLock).values(
                    file_path=file_path,
                    owner_id=self._agent_id,
                    expires_at=expires
                )
            )
            await session.commit()
            return True
        except Exception:
            await session.rollback()
            return False
    
    async def _release_lock(self, session, file_path: str):
        """Release distributed lock."""
        from sqlalchemy import delete
        from db.schema import FileLock
        
        await session.execute(
            delete(FileLock).where(
                (FileLock.file_path == file_path) & (FileLock.owner_id == self._agent_id)
            )
        )
        await session.commit()


# =============================================================================
# LEGACY COMPATIBILITY
# =============================================================================

def apply_surgical_patch(
    file_path: str,
    chunk_metadata: Dict[str, Any],
    new_content: str,
    settings: Optional[Any] = None,
    dry_run: bool = False
):
    """
    Legacy function for backwards compatibility.
    
    Use SurgicalPatcher.patch() for new code.
    """
    original, err = read_file(file_path)
    if err:
        return False, {}, err
    
    start = chunk_metadata.get("processed_char_start") or chunk_metadata.get("char_start")
    end = chunk_metadata.get("processed_char_end") or chunk_metadata.get("char_end")
    
    if start is None or end is None:
        return False, {}, "Missing offsets"
    
    result = apply_patch(
        original=original,
        start=start,
        end=end,
        new_content=new_content,
        expected=chunk_metadata.get("original_text", chunk_metadata.get("text"))
    )
    
    if not result.success:
        return False, {}, result.error
    
    if not dry_run:
        success, err = write_file(file_path, result.patched_content)
        if not success:
            return False, result.delta.to_dict(), err
    
    return True, result.delta.to_dict(), None


def create_patcher(qdrant_url: Optional[str] = None) -> SurgicalPatcher:
    """Factory function for SurgicalPatcher."""
    return SurgicalPatcher(qdrant_url=qdrant_url)
