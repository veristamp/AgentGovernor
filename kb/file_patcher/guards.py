# file_patcher/guards.py
"""
Judgment Guards - Shared safety gates for all file mutations.

The key principle: "Write operations go through guards, not direct I/O."

Uses the unified JudgmentManager for all validation.
"""

import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from config import get_logger

logger = get_logger("Guards")


# =============================================================================
# JUDGMENT MANAGER FACTORY
# =============================================================================

def _create_judgment_manager(
    project_root: Optional[str] = None,
    session_maker: Optional[Any] = None,
    validate_syntax: bool = True,
    run_critic: bool = False,
    run_impact: bool = False,
    run_tests: bool = False
):
    """Create a configured judgment manager."""
    from judgment import create_judgment_manager
    
    return create_judgment_manager(
        project_root=project_root,
        session_maker=session_maker,
        validate_syntax=validate_syntax,
        check_duplicates=False,  # Skip for patching (already indexed)
        run_critic=run_critic,
        run_impact=run_impact,
        run_tests=run_tests
    )


# =============================================================================
# ASYNC JUDGMENT PIPELINE
# =============================================================================

async def run_judgment_pipeline(
    file_path: str,
    old_content: str,
    new_content: str,
    validate_syntax: bool = True,
    run_critic: bool = False,
    run_impact: bool = False,
    run_tests: bool = False,
    project_root: Optional[str] = None,
    chunk_metadata: Optional[Dict[str, Any]] = None,
    session_maker: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Run the judgment pipeline on a proposed change.
    
    Args:
        file_path: Target file path
        old_content: Original content (empty for new files)
        new_content: Proposed new content
        validate_syntax: Run tree-sitter validation
        run_critic: Run diff discipline checks
        run_impact: Run blast radius analysis
        run_tests: Run related tests
        project_root: Project root for test discovery
        chunk_metadata: Optional chunk info
        session_maker: Optional DB session maker
        
    Returns:
        Dict with approval status and gate results
    """
    manager = _create_judgment_manager(
        project_root=project_root,
        session_maker=session_maker,
        validate_syntax=validate_syntax,
        run_critic=run_critic,
        run_impact=run_impact,
        run_tests=run_tests
    )
    
    # Use the new evaluate() API
    result = await manager.evaluate(
        file_path=file_path,
        old_content=old_content,
        new_content=new_content,
        chunk_metadata=chunk_metadata,
        dry_run=True  # Don't log by default
    )
    
    # Convert to gate_results format for compatibility
    gate_results = {}
    if result.validation:
        gate_results["validator"] = result.validation.to_dict()
    if result.critique:
        gate_results["critic"] = result.critique.to_dict()
    if result.impact:
        gate_results["oracle"] = result.impact.to_dict()
    if result.verification:
        gate_results["immune"] = result.verification.to_dict()
    
    return {
        "approved": result.approved,
        "gate_results": gate_results,
        "rejected_by_gate": result.rejected_by.value if result.rejected_by else None,
        "rejection_reason": result.errors[0] if result.errors else None,
        "duration_ms": result.duration_ms,
        "warnings": result.warnings,
    }


# =============================================================================
# ASYNC GUARDED FILE WRITER
# =============================================================================

async def guarded_write(
    file_path: str,
    new_content: str,
    old_content: Optional[str] = None,
    dry_run: bool = False,
    validate_syntax: bool = True,
    run_critic: bool = False,
    run_impact: bool = False,
    run_tests: bool = False,
    project_root: Optional[str] = None,
    chunk_metadata: Optional[Dict[str, Any]] = None,
    session_maker: Optional[Any] = None,
    request_id: Optional[str] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Write to file with judgment gates.
    
    This is the SAFE way to write files.
    
    Args:
        file_path: Target file path
        new_content: Content to write
        old_content: Original content (read if not provided)
        dry_run: Validate without writing
        validate_syntax: Run syntax validation
        run_critic: Run diff critic
        run_impact: Run impact analysis
        run_tests: Run tests
        project_root: Project root for tests
        chunk_metadata: Optional chunk metadata
        session_maker: DB session maker
        request_id: Request ID for logging
        
    Returns:
        (success, receipt_dict)
    """
    import os
    
    receipt = {
        "success": False,
        "file_path": file_path,
        "dry_run": dry_run,
        "bytes_written": 0,
        "validation": None,
        "critique": None,
        "impact": None,
        "tests": None,
        "error": None,
        "warnings": []
    }
    
    # Read existing content if not provided
    if old_content is None:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                old_content = f.read()
        else:
            old_content = ""
    
    # Create manager with specified gates
    manager = _create_judgment_manager(
        project_root=project_root,
        session_maker=session_maker,
        validate_syntax=validate_syntax,
        run_critic=run_critic,
        run_impact=run_impact,
        run_tests=run_tests
    )
    
    # Evaluate
    result = await manager.evaluate(
        file_path=file_path,
        old_content=old_content,
        new_content=new_content,
        chunk_metadata=chunk_metadata or {},
        dry_run=dry_run
    )
    
    # Copy results to receipt
    receipt["validation"] = result.validation.to_dict() if result.validation else None
    receipt["critique"] = result.critique.to_dict() if result.critique else None
    receipt["impact"] = result.impact.to_dict() if result.impact else None
    receipt["tests"] = result.verification.to_dict() if result.verification else None
    receipt["warnings"] = result.warnings
    
    if not result.approved:
        receipt["error"] = result.errors[0] if result.errors else "Judgment failed"
        receipt["rejected_by_gate"] = result.rejected_by.value if result.rejected_by else None
        return False, receipt
    
    # Dry run - don't write
    if dry_run:
        receipt["success"] = True
        return True, receipt
    
    # Write to disk
    try:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        receipt["success"] = True
        receipt["bytes_written"] = len(new_content)
        logger.info(f"✅ Wrote {len(new_content)} bytes to {file_path}")
        
    except Exception as e:
        receipt["error"] = str(e)
        logger.exception(f"Write failed: {file_path}")
    
    return receipt["success"], receipt


# =============================================================================
# SYNC HELPERS
# =============================================================================

def validate_syntax_only(file_path: str, content: str) -> Tuple[bool, Optional[str]]:
    """Quick synchronous syntax check."""
    from judgment import create_validator
    
    validator = create_validator()
    language = validator.get_language(file_path)
    
    if not language:
        return True, None  # Unknown language, allow
    
    result = validator.validate_syntax(content, language)
    return result.valid, result.error


def critique_only(
    old_content: str,
    new_content: str,
    chunk_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Quick synchronous diff critique."""
    from judgment import create_critic
    
    critic = create_critic()
    critique = critic.critique_patch(old_content, new_content, chunk_metadata or {})
    return critique.to_dict()
