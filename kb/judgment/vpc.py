# judgment/vpc.py
"""
Verified Patch Contract (VPC) - Audit logging for code mutations.

This module provides structured logging for all patch operations,
creating a traceable, replayable history of every code change
(whether applied or rejected).

The VPC is the foundation for:
- Trust: Prove what the agent did and didn't do
- Rollback: Reconstruct previous states
- Learning: Analyze rejection patterns to improve prompts
- Compliance: Audit trail for regulated environments

Usage:
    from judgment.vpc import PatchLogger, PatchRecord
    
    logger = PatchLogger()
    
    # Log a patch attempt
    record = await logger.log_patch(
        file_path="src/main.py",
        chunk_metadata={...},
        old_content="...",
        new_content="...",
        receipt={...}  # From patcher
    )
    
    # Query history
    history = await logger.get_file_history("src/main.py", limit=10)
"""

import hashlib
import uuid
import time
import difflib
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
from enum import Enum

from config import get_logger

logger = get_logger("VPC")


# =============================================================================
# ENUMS AND DATACLASSES
# =============================================================================

class PatchDecision(Enum):
    """Final decision for a patch."""
    APPLIED = "applied"
    REJECTED = "rejected"
    DRY_RUN = "dry_run"


class RejectionGate(Enum):
    """Which gate rejected the patch."""
    VALIDATOR = "validator"
    CRITIC = "critic"
    ORACLE = "oracle"
    IMMUNE = "immune"
    DRIFT = "drift"  # Content drift detection
    ERROR = "error"  # Unexpected error


@dataclass
class PatchRecord:
    """
    A complete record of a patch attempt.
    
    This is the Pydantic-like model that gets serialized to the database.
    """
    patch_id: str
    file_path: str
    
    # Target
    chunk_id: Optional[int] = None
    chunk_index: Optional[int] = None
    
    # Content
    old_content_hash: str = ""
    new_content_hash: str = ""
    char_start: int = 0
    char_end: int = 0
    bytes_changed: int = 0
    lines_changed: int = 0
    diff_summary: str = ""
    
    # Gate Results
    validator_result: Optional[Dict[str, Any]] = None
    critic_result: Optional[Dict[str, Any]] = None
    oracle_result: Optional[Dict[str, Any]] = None
    immune_result: Optional[Dict[str, Any]] = None
    
    # Symbols
    symbols_changed: List[str] = field(default_factory=list)
    
    # Decision
    decision: str = "rejected"
    decision_reason: str = ""
    rejected_by_gate: Optional[str] = None
    
    # Git (filled later)
    git_commit_sha: Optional[str] = None
    git_branch: Optional[str] = None
    
    # Provenance
    agent_session_id: Optional[str] = None
    request_id: Optional[str] = None
    
    # Timing
    created_at: Optional[datetime] = None
    duration_ms: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        if data.get("created_at"):
            data["created_at"] = data["created_at"].isoformat()
        return data
    
    @property
    def summary(self) -> str:
        """Human-readable summary."""
        status_icon = "✅" if self.decision == "applied" else "❌" if self.decision == "rejected" else "🔍"
        return f"{status_icon} [{self.decision.upper()}] {self.file_path} ({self.bytes_changed} bytes)"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def compute_diff_summary(old_content: str, new_content: str, max_chars: int = 2000) -> str:
    """Generate a truncated unified diff."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    
    diff = difflib.unified_diff(old_lines, new_lines, fromfile="old", tofile="new", lineterm="")
    diff_text = "".join(diff)
    
    if len(diff_text) > max_chars:
        diff_text = diff_text[:max_chars] + f"\n... (truncated, {len(diff_text) - max_chars} more chars)"
    
    return diff_text


def extract_symbols_from_receipt(receipt: Dict[str, Any]) -> List[str]:
    """Extract changed symbols from a patcher receipt."""
    symbols = []
    
    # From oracle result
    if receipt.get("impact") and receipt["impact"].get("symbols_changed"):
        symbols.extend(receipt["impact"]["symbols_changed"])
    
    return list(set(symbols))


def determine_rejection_gate(receipt: Dict[str, Any]) -> Optional[str]:
    """Determine which gate rejected the patch."""
    error = receipt.get("error", "")
    
    if "validation" in error.lower() or "syntax" in error.lower():
        return RejectionGate.VALIDATOR.value
    elif "critic" in error.lower():
        return RejectionGate.CRITIC.value
    elif "impact" in error.lower() or "risk" in error.lower():
        return RejectionGate.ORACLE.value
    elif "test" in error.lower() or "immune" in error.lower():
        return RejectionGate.IMMUNE.value
    elif "drift" in error.lower() or "mismatch" in error.lower():
        return RejectionGate.DRIFT.value
    elif error:
        return RejectionGate.ERROR.value
    
    return None


# =============================================================================
# PATCH LOGGER CLASS
# =============================================================================

class PatchLogger:
    """
    Logs patch operations to the database.
    
    Provides both synchronous (in-memory) and asynchronous (database) logging.
    """
    
    def __init__(
        self,
        session_maker: Optional[Any] = None,
        agent_session_id: Optional[str] = None
    ):
        """
        Initialize the patch logger.
        
        Args:
            session_maker: SQLAlchemy async session maker
            agent_session_id: Optional session ID for grouping patches
        """
        self._session_maker = session_maker
        self.agent_session_id = agent_session_id or str(uuid.uuid4())[:8]
        
        # In-memory buffer for when DB is not available
        self._buffer: List[PatchRecord] = []
    
    def create_record(
        self,
        file_path: str,
        chunk_metadata: Dict[str, Any],
        old_content: str,
        new_content: str,
        receipt: Dict[str, Any],
        start_time: Optional[float] = None,
        request_id: Optional[str] = None
    ) -> PatchRecord:
        """
        Create a PatchRecord from patcher inputs and receipt.
        
        This is the main entry point for creating audit records.
        """
        # Generate patch ID
        patch_id = str(uuid.uuid4())
        
        # Compute hashes
        old_hash = compute_content_hash(old_content)
        new_hash = compute_content_hash(new_content)
        
        # Compute diff
        diff_summary = compute_diff_summary(old_content, new_content)
        
        # Calculate size changes
        bytes_changed = abs(len(new_content) - len(old_content))
        old_line_count = len(old_content.splitlines())
        new_line_count = len(new_content.splitlines())
        lines_changed = abs(new_line_count - old_line_count)
        
        # Determine decision
        if receipt.get("success"):
            decision = PatchDecision.APPLIED.value
        elif receipt.get("error") and "dry_run" not in receipt.get("error", "").lower():
            decision = PatchDecision.REJECTED.value
        else:
            decision = PatchDecision.DRY_RUN.value
        
        # Calculate duration
        duration_ms = 0
        if start_time:
            duration_ms = int((time.time() - start_time) * 1000)
        
        # Extract symbols
        symbols = extract_symbols_from_receipt(receipt)
        
        # Determine rejection gate
        rejected_by = None if receipt.get("success") else determine_rejection_gate(receipt)
        
        return PatchRecord(
            patch_id=patch_id,
            file_path=file_path,
            chunk_id=chunk_metadata.get("id"),
            chunk_index=chunk_metadata.get("index"),
            old_content_hash=old_hash,
            new_content_hash=new_hash,
            char_start=chunk_metadata.get("processed_char_start", 0),
            char_end=chunk_metadata.get("processed_char_end", 0),
            bytes_changed=bytes_changed,
            lines_changed=lines_changed,
            diff_summary=diff_summary,
            validator_result=receipt.get("validation"),
            critic_result=receipt.get("critique"),
            oracle_result=receipt.get("impact"),
            immune_result=receipt.get("tests"),
            symbols_changed=symbols,
            decision=decision,
            decision_reason=receipt.get("error", "Patch applied successfully"),
            rejected_by_gate=rejected_by,
            agent_session_id=self.agent_session_id,
            request_id=request_id,
            created_at=datetime.utcnow(),
            duration_ms=duration_ms
        )
    
    def log_to_buffer(self, record: PatchRecord) -> None:
        """Log a record to the in-memory buffer."""
        self._buffer.append(record)
        logger.info(f"Patch logged: {record.summary}")
    
    async def log_to_database(self, record: PatchRecord) -> bool:
        """
        Log a record to the database.
        
        Returns True if successfully persisted.
        """
        if not self._session_maker:
            logger.warning("No session maker configured, using buffer only")
            self.log_to_buffer(record)
            return False
        
        try:
            from db import PatchHistory
            
            async with self._session_maker() as session:
                history = PatchHistory(
                    patch_id=record.patch_id,
                    file_path=record.file_path,
                    chunk_id=record.chunk_id,
                    chunk_index=record.chunk_index,
                    old_content_hash=record.old_content_hash,
                    new_content_hash=record.new_content_hash,
                    char_start=record.char_start,
                    char_end=record.char_end,
                    bytes_changed=record.bytes_changed,
                    lines_changed=record.lines_changed,
                    diff_summary=record.diff_summary,
                    validator_result=record.validator_result,
                    critic_result=record.critic_result,
                    oracle_result=record.oracle_result,
                    immune_result=record.immune_result,
                    symbols_changed=record.symbols_changed,
                    decision=record.decision,
                    decision_reason=record.decision_reason,
                    rejected_by_gate=record.rejected_by_gate,
                    git_commit_sha=record.git_commit_sha,
                    git_branch=record.git_branch,
                    agent_session_id=record.agent_session_id,
                    request_id=record.request_id,
                    duration_ms=record.duration_ms
                )
                session.add(history)
                await session.commit()
                
            logger.info(f"Patch persisted to DB: {record.patch_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to persist patch: {e}")
            self.log_to_buffer(record)
            return False
    
    async def log_patch(
        self,
        file_path: str,
        chunk_metadata: Dict[str, Any],
        old_content: str,
        new_content: str,
        receipt: Dict[str, Any],
        start_time: Optional[float] = None,
        request_id: Optional[str] = None,
        persist: bool = True
    ) -> PatchRecord:
        """
        Main entry point: Create and log a patch record.
        
        Args:
            file_path: Path to the patched file
            chunk_metadata: Chunk metadata dict
            old_content: Original content
            new_content: New content
            receipt: Patcher receipt dict
            start_time: Optional start time for duration calculation
            request_id: Optional request ID for tracing
            persist: If True, attempt to persist to database
            
        Returns:
            The created PatchRecord
        """
        record = self.create_record(
            file_path=file_path,
            chunk_metadata=chunk_metadata,
            old_content=old_content,
            new_content=new_content,
            receipt=receipt,
            start_time=start_time,
            request_id=request_id
        )
        
        if persist and self._session_maker:
            await self.log_to_database(record)
        else:
            self.log_to_buffer(record)
        
        return record
    
    def log_patch_sync(
        self,
        file_path: str,
        chunk_metadata: Dict[str, Any],
        old_content: str,
        new_content: str,
        receipt: Dict[str, Any],
        start_time: Optional[float] = None,
        request_id: Optional[str] = None
    ) -> PatchRecord:
        """
        Synchronous version: Create and log to buffer only.
        
        For use in non-async contexts.
        """
        record = self.create_record(
            file_path=file_path,
            chunk_metadata=chunk_metadata,
            old_content=old_content,
            new_content=new_content,
            receipt=receipt,
            start_time=start_time,
            request_id=request_id
        )
        
        self.log_to_buffer(record)
        return record
    
    async def get_file_history(
        self,
        file_path: str,
        limit: int = 10,
        include_rejected: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get patch history for a specific file.
        
        Returns list of patch records as dicts.
        """
        if not self._session_maker:
            # Return from buffer
            matches = [r for r in self._buffer if r.file_path == file_path]
            if not include_rejected:
                matches = [r for r in matches if r.decision == "applied"]
            return [r.to_dict() for r in matches[-limit:]]
        
        try:
            from db import PatchHistory
            from sqlalchemy import select, desc
            
            async with self._session_maker() as session:
                query = select(PatchHistory).where(
                    PatchHistory.file_path == file_path
                )
                
                if not include_rejected:
                    query = query.where(PatchHistory.decision == "applied")
                
                query = query.order_by(desc(PatchHistory.created_at)).limit(limit)
                
                result = await session.execute(query)
                rows = result.scalars().all()
                
                return [
                    {
                        "patch_id": r.patch_id,
                        "file_path": r.file_path,
                        "decision": r.decision,
                        "decision_reason": r.decision_reason,
                        "bytes_changed": r.bytes_changed,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in rows
                ]
                
        except Exception as e:
            logger.error(f"Failed to query history: {e}")
            return []
    
    async def get_session_history(
        self,
        session_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get all patches from a session."""
        session_id = session_id or self.agent_session_id
        
        if not self._session_maker:
            matches = [r for r in self._buffer if r.agent_session_id == session_id]
            return [r.to_dict() for r in matches[-limit:]]
        
        try:
            from db import PatchHistory
            from sqlalchemy import select, desc
            
            async with self._session_maker() as session:
                query = select(PatchHistory).where(
                    PatchHistory.agent_session_id == session_id
                ).order_by(desc(PatchHistory.created_at)).limit(limit)
                
                result = await session.execute(query)
                rows = result.scalars().all()
                
                return [
                    {
                        "patch_id": r.patch_id,
                        "file_path": r.file_path,
                        "decision": r.decision,
                        "rejected_by_gate": r.rejected_by_gate,
                        "bytes_changed": r.bytes_changed,
                        "duration_ms": r.duration_ms,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in rows
                ]
                
        except Exception as e:
            logger.error(f"Failed to query session history: {e}")
            return []
    
    def get_buffer(self) -> List[PatchRecord]:
        """Get in-memory buffer contents."""
        return self._buffer.copy()
    
    def clear_buffer(self) -> int:
        """Clear the in-memory buffer. Returns count of cleared records."""
        count = len(self._buffer)
        self._buffer.clear()
        return count
    
    async def flush_buffer_to_db(self) -> int:
        """Flush buffered records to database. Returns count of persisted records."""
        if not self._session_maker:
            return 0
        
        persisted = 0
        for record in self._buffer:
            if await self.log_to_database(record):
                persisted += 1
        
        self._buffer.clear()
        return persisted


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_patch_logger(
    session_maker: Optional[Any] = None,
    agent_session_id: Optional[str] = None
) -> PatchLogger:
    """Factory function to create a PatchLogger."""
    return PatchLogger(
        session_maker=session_maker,
        agent_session_id=agent_session_id
    )


def quick_log_patch(
    file_path: str,
    old_content: str,
    new_content: str,
    success: bool,
    error: Optional[str] = None
) -> PatchRecord:
    """
    Quick logging for simple cases.
    
    Returns a PatchRecord without database persistence.
    """
    logger_instance = PatchLogger()
    
    chunk_metadata = {
        "id": None,
        "index": 0,
        "processed_char_start": 0,
        "processed_char_end": len(old_content)
    }
    
    receipt = {
        "success": success,
        "error": error
    }
    
    return logger_instance.log_patch_sync(
        file_path=file_path,
        chunk_metadata=chunk_metadata,
        old_content=old_content,
        new_content=new_content,
        receipt=receipt
    )
