# services/patch_service.py
"""
Patch Service - VPC (Verified Patch Contract) operations.

Handles all patch history and audit operations:
- List patch attempts with filtering
- Get patch details
- Mark patches as committed
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, update
from dataclasses import dataclass

from config import get_logger

logger = get_logger("PatchService")


@dataclass
class PatchFilter:
    """Filter parameters for patch history."""
    limit: int = 50
    offset: int = 0
    decision: Optional[str] = None
    rejected_by_gate: Optional[str] = None
    file_path_contains: Optional[str] = None
    agent_session_id: Optional[str] = None
    request_id: Optional[str] = None


class PatchService:
    """
    Patch history and audit operations.
    
    All methods are static - no state needed.
    """
    
    @staticmethod
    def compute_badges(record: Dict[str, Any]) -> Dict[str, str]:
        """
        Compute display badges for a patch record.
        
        Returns decision_badge and risk_badge for UI rendering.
        """
        decision = record.get("decision", "unknown")
        rejected_by = record.get("rejected_by_gate")
        
        # Decision badge
        if decision == "applied":
            decision_badge = "✅ APPLIED"
        elif decision == "rejected":
            gate = f" ({rejected_by})" if rejected_by else ""
            decision_badge = f"❌ REJECTED{gate}"
        elif decision == "dry_run":
            decision_badge = "🔍 DRY_RUN"
        else:
            decision_badge = f"❓ {decision.upper()}"
        
        # Risk badge from oracle result
        risk_badge = "—"
        oracle = record.get("oracle_result")
        if oracle and isinstance(oracle, dict):
            risk_level = oracle.get("risk_level", "").upper()
            if risk_level:
                risk_emoji = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}
                risk_badge = f"{risk_emoji.get(risk_level, '')} {risk_level}"
        
        return {
            "decision_badge": decision_badge,
            "risk_badge": risk_badge
        }
    
    @staticmethod
    async def list_patches(
        session: AsyncSession,
        filters: PatchFilter
    ) -> Dict[str, Any]:
        """
        List patch attempts with filtering.
        
        Returns summary view without heavy JSON blobs.
        """
        from db.schema import PatchHistory
        
        query = select(
            PatchHistory.patch_id,
            PatchHistory.created_at,
            PatchHistory.file_path,
            PatchHistory.chunk_id,
            PatchHistory.decision,
            PatchHistory.rejected_by_gate,
            PatchHistory.duration_ms,
            PatchHistory.bytes_changed,
            PatchHistory.agent_session_id,
            PatchHistory.request_id,
            PatchHistory.oracle_result  # For risk badge
        ).order_by(PatchHistory.created_at.desc())
        
        # Apply filters
        if filters.decision:
            query = query.where(PatchHistory.decision == filters.decision)
        if filters.rejected_by_gate:
            query = query.where(PatchHistory.rejected_by_gate == filters.rejected_by_gate)
        if filters.file_path_contains:
            query = query.where(PatchHistory.file_path.ilike(f"%{filters.file_path_contains}%"))
        if filters.agent_session_id:
            query = query.where(PatchHistory.agent_session_id == filters.agent_session_id)
        if filters.request_id:
            query = query.where(PatchHistory.request_id == filters.request_id)
        
        # Count total before pagination
        count_query = select(PatchHistory.patch_id)
        if filters.decision:
            count_query = count_query.where(PatchHistory.decision == filters.decision)
        if filters.rejected_by_gate:
            count_query = count_query.where(PatchHistory.rejected_by_gate == filters.rejected_by_gate)
        if filters.file_path_contains:
            count_query = count_query.where(PatchHistory.file_path.ilike(f"%{filters.file_path_contains}%"))
        if filters.agent_session_id:
            count_query = count_query.where(PatchHistory.agent_session_id == filters.agent_session_id)
        if filters.request_id:
            count_query = count_query.where(PatchHistory.request_id == filters.request_id)
        
        count_result = await session.execute(count_query)
        total = len(list(count_result.scalars().all()))
        
        # Apply pagination
        query = query.offset(filters.offset).limit(filters.limit)
        
        result = await session.execute(query)
        rows = result.all()
        
        patches = []
        for row in rows:
            record = {
                "patch_id": row.patch_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "file_path": row.file_path,
                "chunk_id": row.chunk_id,
                "decision": row.decision,
                "rejected_by_gate": row.rejected_by_gate,
                "duration_ms": row.duration_ms,
                "bytes_changed": row.bytes_changed,
                "agent_session_id": row.agent_session_id,
                "request_id": row.request_id,
                "oracle_result": row.oracle_result
            }
            
            badges = PatchService.compute_badges(record)
            record["decision_badge"] = badges["decision_badge"]
            record["risk_badge"] = badges["risk_badge"]
            
            # Remove heavy field from list view
            del record["oracle_result"]
            
            patches.append(record)
        
        return {
            "patches": patches,
            "total": total,
            "limit": filters.limit,
            "offset": filters.offset
        }
    
    @staticmethod
    async def get_patch(
        session: AsyncSession,
        patch_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get full details for a specific patch.
        
        Includes complete gate results and all metadata.
        """
        from db.schema import PatchHistory
        
        query = select(PatchHistory).where(PatchHistory.patch_id == patch_id)
        result = await session.execute(query)
        row = result.scalar_one_or_none()
        
        if not row:
            return None
        
        record = {
            "patch_id": row.patch_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "file_path": row.file_path,
            "chunk_id": row.chunk_id,
            "chunk_index": row.chunk_index,
            "old_content_hash": row.old_content_hash,
            "new_content_hash": row.new_content_hash,
            "char_start": row.char_start,
            "char_end": row.char_end,
            "bytes_changed": row.bytes_changed,
            "lines_changed": row.lines_changed,
            "diff_summary": row.diff_summary,
            "validator_result": row.validator_result,
            "critic_result": row.critic_result,
            "oracle_result": row.oracle_result,
            "immune_result": row.immune_result,
            "symbols_changed": row.symbols_changed,
            "decision": row.decision,
            "decision_reason": row.decision_reason,
            "rejected_by_gate": row.rejected_by_gate,
            "git_commit_sha": row.git_commit_sha,
            "git_branch": row.git_branch,
            "agent_session_id": row.agent_session_id,
            "request_id": row.request_id,
            "duration_ms": row.duration_ms,
        }
        
        badges = PatchService.compute_badges(record)
        record["decision_badge"] = badges["decision_badge"]
        record["risk_badge"] = badges["risk_badge"]
        
        return record
    
    @staticmethod
    async def mark_committed(
        session: AsyncSession,
        patch_id: str,
        git_sha: str,
        git_branch: Optional[str] = None
    ) -> bool:
        """
        Mark a patch as committed to git.
        
        Returns True if successful, False if patch not found.
        """
        from db.schema import PatchHistory
        
        stmt = (
            update(PatchHistory)
            .where(PatchHistory.patch_id == patch_id)
            .values(
                git_commit_sha=git_sha,
                git_branch=git_branch
            )
        )
        
        result = await session.execute(stmt)
        await session.commit()
        
        return result.rowcount > 0
