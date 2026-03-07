# judgment/manager.py
"""
Judgment Manager - Unified interface for patch safety gates.

Simple usage:
    from judgment import create_judgment_manager
    
    judgment = create_judgment_manager(session_maker=db)
    result = await judgment.evaluate(file_path, old, new)
    
    if result.approved:
        # Apply patch
"""

import time
import asyncio
from typing import Dict, Any, Optional, List

from config import get_logger
from .core import GateType, Decision, RiskLevel, JudgmentResult, JudgmentConfig

logger = get_logger("JudgmentManager")


# Legacy alias for backwards compatibility
PatchEvaluation = JudgmentResult


class JudgmentManager:
    """
    Unified manager for patch safety evaluation.
    
    Runs all gates in order:
    1. Validate syntax (fast)
    2. Check duplicates (fast)
    3. Critique diff (fast)
    4. Analyze impact (medium)
    5. Run tests (slow, optional)
    6. Log to audit (always)
    """
    
    def __init__(
        self,
        config: Optional[JudgmentConfig] = None,
        session_maker: Optional[Any] = None,
        qdrant_client: Optional[Any] = None
    ):
        """
        Initialize the judgment manager.
        
        Args:
            config: JudgmentConfig with gate settings
            session_maker: DB session maker for VPC logging
            qdrant_client: Qdrant client for semantic linting
        """
        self.config = config or JudgmentConfig()
        self.session_maker = session_maker
        self.qdrant_client = qdrant_client
        
        # Lazy-loaded gates
        self._validator = None
        self._linter = None
        self._critic = None
        self._oracle = None
        self._immune = None
        self._logger = None
    
    # =========================================================================
    # MAIN API
    # =========================================================================
    
    async def evaluate(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
        chunk_metadata: Optional[Dict[str, Any]] = None,
        intent: Optional[str] = None,
        dry_run: bool = False
    ) -> JudgmentResult:
        """
        Evaluate a patch through all enabled gates.
        
        Args:
            file_path: Path to the file being patched
            old_content: Original content
            new_content: New content
            chunk_metadata: Optional chunk info
            intent: Optional description of intent
            dry_run: If True, don't persist to audit log
            
        Returns:
            JudgmentResult with approval status
        """
        start = time.time()
        result = JudgmentResult()
        chunk_metadata = chunk_metadata or {}
        
        # Ensure offsets exist for existing files
        import os
        if os.path.exists(file_path) and "processed_char_start" not in chunk_metadata:
            chunk_metadata["processed_char_start"] = 0
            chunk_metadata["processed_char_end"] = len(old_content)
        
        try:
            # Run gates 1-4 in parallel
            v, d, c, i = await asyncio.gather(
                self._run_validator(file_path, new_content, chunk_metadata),
                self._run_linter(file_path, new_content),
                self._run_critic(old_content, new_content, chunk_metadata, intent),
                self._run_oracle(file_path, old_content, new_content, chunk_metadata),
                return_exceptions=True
            )
            
            # Handle exceptions
            if isinstance(v, Exception): raise v
            if isinstance(d, Exception): d = []
            if isinstance(c, Exception): c = None
            if isinstance(i, Exception): i = None
            
            # Gate 1: Validator
            result.validation = v
            if v and not v.valid:
                result.rejected_by = GateType.VALIDATOR
                result.errors.append(f"Syntax error: {v.error}")
                return self._finalize(result, start, file_path, old_content, new_content, chunk_metadata, dry_run)
            
            # Gate 1b: Linter
            result.duplicates = d or []
            if d and any(any(m["score"] > 0.98 for m in dup["matches"]) for dup in d):
                result.warnings.append("⚠️ High semantic duplication detected")
            
            # Gate 2: Critic
            result.critique = c
            if c and not c.approved:
                result.rejected_by = GateType.CRITIC
                for v in c.violations:
                    if v.severity.value == "error":
                        result.errors.append(v.message)
                    else:
                        result.warnings.append(v.message)
                return self._finalize(result, start, file_path, old_content, new_content, chunk_metadata, dry_run)
            
            # Gate 3: Oracle
            result.impact = i
            if i and i.risk_level == RiskLevel.CRITICAL:
                result.rejected_by = GateType.ORACLE
                result.errors.append(f"Critical risk: {i.summary}")
                return self._finalize(result, start, file_path, old_content, new_content, chunk_metadata, dry_run)
            
            if i and i.risk_level == RiskLevel.HIGH:
                result.warnings.append(f"High risk: {i.caller_count} callers affected")
            
        except Exception as e:
            logger.exception("Gate pipeline failed")
            result.rejected_by = GateType.VALIDATOR
            result.errors.append(f"Pipeline error: {e}")
            return self._finalize(result, start, file_path, old_content, new_content, chunk_metadata, dry_run)
        
        # Gate 4: Immune (sequential, expensive)
        if self.config.run_tests:
            try:
                symbols = [c.symbol for c in (result.impact.callers[:5] if result.impact else [])]
                test_files = result.impact.tests.test_files if result.impact else None
                
                verification = self._get_immune().verify_patch(
                    file_path=file_path,
                    changed_symbols=symbols,
                    test_files=test_files
                )
                result.verification = verification
                
                if not verification.should_apply:
                    result.rejected_by = GateType.IMMUNE
                    result.errors.append(f"Tests failed: {verification.reason}")
                    return self._finalize(result, start, file_path, old_content, new_content, chunk_metadata, dry_run)
                    
            except Exception as e:
                logger.warning(f"Test verification skipped: {e}")
                result.warnings.append(f"Tests skipped: {e}")
        
        # All gates passed
        result.approved = True
        result.decision = Decision.DRY_RUN if dry_run else Decision.APPROVED
        
        return self._finalize(result, start, file_path, old_content, new_content, chunk_metadata, dry_run)
    
    # Legacy alias
    async def evaluate_patch(self, **kwargs) -> JudgmentResult:
        """Legacy alias for evaluate()."""
        return await self.evaluate(**kwargs)
    
    # =========================================================================
    # QUICK CHECKS
    # =========================================================================
    
    def validate_only(self, file_path: str, content: str):
        """Quick syntax check (sync)."""
        language = self._get_validator().get_language(file_path)
        if language:
            return self._get_validator().validate_syntax(content, language)
        return None
    
    def critique_only(self, old: str, new: str, chunk: Optional[Dict] = None):
        """Quick diff critique (sync)."""
        return self._get_critic().critique_patch(old, new, chunk)
    
    # =========================================================================
    # INTERNAL
    # =========================================================================
    
    def _finalize(self, result, start, file_path, old, new, chunk, dry_run):
        """Finalize result and log."""
        result.duration_ms = int((time.time() - start) * 1000)
        
        if not result.approved:
            result.decision = Decision.REJECTED
        
        # Log to VPC (fire and forget)
        if self.session_maker and not dry_run:
            asyncio.create_task(self._log_result(result, file_path, old, new, chunk))
        
        return result
    
    async def _log_result(self, result, file_path, old, new, chunk):
        """Log to audit trail."""
        try:
            receipt = {
                "success": result.approved,
                "error": result.errors[0] if result.errors else None,
                "validation": result.validation.to_dict() if result.validation else None,
                "critique": result.critique.to_dict() if result.critique else None,
                "impact": result.impact.to_dict() if result.impact else None,
            }
            
            result.patch_record = await self._get_logger().log_patch(
                file_path=file_path,
                chunk_metadata=chunk,
                old_content=old,
                new_content=new,
                receipt=receipt,
                start_time=time.time(),
                persist=True
            )
        except Exception as e:
            logger.warning(f"Audit log failed: {e}")
    
    async def _run_validator(self, file_path, new_content, chunk):
        """Run validator gate."""
        if not self.config.validate_syntax:
            return None
        
        import os
        validator = self._get_validator()
        
        if not os.path.exists(file_path):
            language = validator.get_language(file_path)
            if language:
                return validator.validate_syntax(new_content, language)
            return None
        
        preview = validator.validate_patch_preview(file_path, chunk, new_content)
        return preview.validation
    
    async def _run_linter(self, file_path, new_content):
        """Run linter gate."""
        if not self.config.check_duplicates:
            return []
        
        return await self._get_linter().analyze_text(
            text=new_content,
            filename=file_path,
            threshold=self.config.duplicate_threshold
        )
    
    async def _run_critic(self, old, new, chunk, intent):
        """Run critic gate."""
        if not self.config.run_critic or not old.strip():
            return None
        
        return await asyncio.to_thread(
            self._get_critic().critique_patch,
            old_content=old,
            new_content=new,
            chunk_metadata=chunk,
            intent=intent
        )
    
    async def _run_oracle(self, file_path, old, new, chunk):
        """Run oracle gate."""
        if not self.config.run_impact:
            return None
        
        return await self._get_oracle().analyze_impact_async(
            file_path=file_path,
            old_content=old,
            new_content=new,
            chunk_metadata=chunk
        )
    
    # =========================================================================
    # LAZY GETTERS
    # =========================================================================
    
    def _get_validator(self):
        if self._validator is None:
            from .validator import create_validator
            self._validator = create_validator(strict_mode=self.config.strict_mode)
        return self._validator
    
    def _get_linter(self):
        if self._linter is None:
            from .linter import create_linter
            self._linter = create_linter(qdrant_client=self.qdrant_client)
        return self._linter
    
    def _get_critic(self):
        if self._critic is None:
            from .critic import create_critic
            self._critic = create_critic()
        return self._critic
    
    def _get_oracle(self):
        if self._oracle is None:
            from .oracle import create_oracle
            self._oracle = create_oracle(
                project_root=self.config.project_root,
                qdrant_client=self.qdrant_client
            )
        return self._oracle
    
    def _get_immune(self):
        if self._immune is None:
            from .immune import create_immune_system
            self._immune = create_immune_system(project_root=self.config.project_root)
        return self._immune
    
    def _get_logger(self):
        if self._logger is None:
            from .vpc import create_patch_logger
            self._logger = create_patch_logger(session_maker=self.session_maker)
        return self._logger


# =============================================================================
# FACTORY
# =============================================================================

def create_judgment_manager(
    session_maker: Optional[Any] = None,
    qdrant_client: Optional[Any] = None,
    project_root: Optional[str] = None,
    strict_mode: bool = True,
    run_tests: bool = False,
    **kwargs
) -> JudgmentManager:
    """
    Create a JudgmentManager.
    
    Args:
        session_maker: DB session for VPC logging
        qdrant_client: Qdrant client for linting
        project_root: Project root for oracle/immune
        strict_mode: Reject any syntax error
        run_tests: Run tests before approving
        **kwargs: Additional JudgmentConfig fields
    """
    config = JudgmentConfig(
        strict_mode=strict_mode,
        run_tests=run_tests,
        project_root=project_root,
        **{k: v for k, v in kwargs.items() if hasattr(JudgmentConfig, k)}
    )
    
    return JudgmentManager(
        config=config,
        session_maker=session_maker,
        qdrant_client=qdrant_client
    )
