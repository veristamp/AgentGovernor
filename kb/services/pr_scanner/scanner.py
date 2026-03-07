# services/pr_scanner/scanner.py
"""
PR Scanner - Main orchestrator for PR review automation.

Uses the Judgment pipeline to analyze each file change in a PR,
aggregates results, and produces a final verdict.
"""

import time
from datetime import datetime
from typing import List, Optional, Any
from pathlib import Path

from config import get_logger
from judgment import (
    JudgmentManager, 
    JudgmentConfig, 
    JudgmentResult,
    RiskLevel,
    create_judgment_manager,
)
from .core import (
    PRVerdictReport, PRVerdict, PRRiskLevel,
    FileReviewResult, FileChange, FileChangeType,
    PRScannerConfig,
)
from .diff_parser import parse_diff, filter_changes

logger = get_logger("PRScanner")


# =============================================================================
# RISK MAPPING
# =============================================================================

def judgment_risk_to_pr_risk(risk: RiskLevel) -> PRRiskLevel:
    """Map Judgment RiskLevel to PRRiskLevel."""
    mapping = {
        RiskLevel.LOW: PRRiskLevel.LOW,
        RiskLevel.MEDIUM: PRRiskLevel.MEDIUM,
        RiskLevel.HIGH: PRRiskLevel.HIGH,
        RiskLevel.CRITICAL: PRRiskLevel.CRITICAL,
    }
    return mapping.get(risk, PRRiskLevel.MEDIUM)


# =============================================================================
# PR SCANNER
# =============================================================================

class PRScanner:
    """
    Main PR review scanner.
    
    Orchestrates the Judgment pipeline for each file in a PR:
    1. Parse PR diff into file changes
    2. For each file, run Judgment gates
    3. Aggregate results into PR-level verdict
    4. Generate labels and recommendations
    """
    
    def __init__(
        self,
        config: Optional[PRScannerConfig] = None,
        judgment_manager: Optional[JudgmentManager] = None,
        session_maker: Optional[Any] = None,
        qdrant_client: Optional[Any] = None,
    ):
        """
        Initialize the PR scanner.
        
        Args:
            config: PRScannerConfig with settings
            judgment_manager: Pre-configured JudgmentManager (or will create one)
            session_maker: DB session maker for VPC logging
            qdrant_client: Qdrant client for semantic linting
        """
        self.config = config or PRScannerConfig()
        self._judgment = judgment_manager
        self._session_maker = session_maker
        self._qdrant_client = qdrant_client
    
    @property
    def judgment(self) -> JudgmentManager:
        """Lazy-load judgment manager."""
        if self._judgment is None:
            judgment_config = JudgmentConfig(
                validate_syntax=self.config.validate_syntax,
                check_duplicates=self.config.check_duplicates,
                run_critic=self.config.run_critic,
                run_impact=self.config.run_impact,
                run_tests=self.config.run_tests,
                project_root=self.config.project_root,
            )
            self._judgment = create_judgment_manager(
                session_maker=self._session_maker,
                qdrant_client=self._qdrant_client,
                **judgment_config.__dict__
            )
        return self._judgment
    
    async def scan_diff(
        self,
        diff_text: str,
        pr_number: int = 0,
        repo: str = "",
        base_branch: str = "main",
        head_branch: str = "feature",
    ) -> PRVerdictReport:
        """
        Scan a PR from its diff text.
        
        Args:
            diff_text: Unified diff text
            pr_number: PR number for reporting
            repo: Repository name (owner/repo)
            base_branch: Base branch (e.g., main)
            head_branch: Head branch (e.g., feature/xyz)
            
        Returns:
            PRVerdictReport with complete review
        """
        start_time = time.time()
        logger.info(f"Scanning PR #{pr_number} in {repo}")
        
        # 1. Parse diff into file changes
        file_changes = parse_diff(diff_text, project_root=self.config.project_root)
        logger.debug(f"Found {len(file_changes)} file changes")
        
        # 2. Filter based on skip patterns and size limits
        file_changes = filter_changes(
            file_changes,
            skip_patterns=self.config.skip_patterns,
            max_lines=self.config.max_lines_per_file
        )
        
        # 3. Limit total files
        if len(file_changes) > self.config.max_files_per_pr:
            logger.warning(f"PR has {len(file_changes)} files, limiting to {self.config.max_files_per_pr}")
            file_changes = file_changes[:self.config.max_files_per_pr]
        
        # 4. Review each file
        file_results: List[FileReviewResult] = []
        for change in file_changes:
            result = await self._review_file(change)
            file_results.append(result)
        
        # 5. Aggregate results
        report = self._aggregate_results(
            file_results=file_results,
            file_changes=file_changes,
            pr_number=pr_number,
            repo=repo,
            base_branch=base_branch,
            head_branch=head_branch,
        )
        
        # 6. Add timing
        report.scan_duration_ms = int((time.time() - start_time) * 1000)
        report.scanned_at = datetime.utcnow()
        
        logger.info(f"PR scan complete: {report.summary}")
        return report
    
    async def scan_files(
        self,
        file_changes: List[FileChange],
        pr_number: int = 0,
        repo: str = "",
    ) -> PRVerdictReport:
        """
        Scan a list of pre-parsed file changes.
        
        Useful when you already have FileChange objects from an API.
        """
        start_time = time.time()
        
        file_results = []
        for change in file_changes:
            result = await self._review_file(change)
            file_results.append(result)
        
        report = self._aggregate_results(
            file_results=file_results,
            file_changes=file_changes,
            pr_number=pr_number,
            repo=repo,
        )
        
        report.scan_duration_ms = int((time.time() - start_time) * 1000)
        report.scanned_at = datetime.utcnow()
        
        return report
    
    async def _review_file(self, change: FileChange) -> FileReviewResult:
        """
        Review a single file change through the Judgment pipeline.
        
        Args:
            change: The file change to review
            
        Returns:
            FileReviewResult with all gate results
        """
        logger.debug(f"Reviewing {change.path} ({change.change_type.value})")
        
        result = FileReviewResult(
            file_path=change.path,
            approved=True,  # Innocent until proven guilty
        )
        
        # For deleted files, minimal checks
        if change.change_type == FileChangeType.DELETED:
            result.warnings.append("File deleted")
            return result
        
        # For added/modified files, run full judgment
        try:
            judgment_result = await self.judgment.evaluate(
                file_path=change.path,
                old_content=change.old_content,
                new_content=change.new_content,
                chunk_metadata={
                    "processed_char_start": 0,
                    "processed_char_end": len(change.old_content),
                },
                dry_run=True,  # Don't persist to audit log
            )
            
            # Map judgment result to file result
            result = self._map_judgment_to_file_result(change.path, judgment_result)
            
        except Exception as e:
            logger.exception(f"Failed to review {change.path}")
            result.approved = False
            result.errors.append(f"Review failed: {str(e)}")
        
        return result
    
    def _map_judgment_to_file_result(
        self, 
        file_path: str, 
        judgment: JudgmentResult
    ) -> FileReviewResult:
        """Map JudgmentResult to FileReviewResult."""
        result = FileReviewResult(
            file_path=file_path,
            approved=judgment.approved,
            errors=judgment.errors.copy(),
            warnings=judgment.warnings.copy(),
        )
        
        # Validator gate
        if judgment.validation:
            result.syntax_valid = judgment.validation.valid
            if judgment.validation.error:
                result.syntax_errors.append(judgment.validation.error)
        
        # Linter gate
        if judgment.duplicates:
            result.duplicate_warnings = judgment.duplicates
        
        # Critic gate
        if judgment.critique:
            result.critic_approved = judgment.critique.approved
            result.critic_score = judgment.critique.score
            result.critic_violations = [v.to_dict() for v in judgment.critique.violations]
        
        # Oracle gate
        if judgment.impact:
            result.impact_risk = judgment.impact.risk_level.value
            result.impact_callers = judgment.impact.caller_count
            result.impact_warnings = judgment.impact.warnings
        
        # Immune gate
        if judgment.verification:
            result.test_passed = judgment.verification.should_apply
            result.test_summary = judgment.verification.reason
        
        return result
    
    def _aggregate_results(
        self,
        file_results: List[FileReviewResult],
        file_changes: List[FileChange],
        pr_number: int = 0,
        repo: str = "",
        base_branch: str = "main",
        head_branch: str = "feature",
    ) -> PRVerdictReport:
        """
        Aggregate per-file results into PR-level verdict.
        """
        files_approved = sum(1 for f in file_results if f.approved)
        files_rejected = len(file_results) - files_approved
        
        # Collect all issues
        critical_issues = []
        warnings = []
        suggestions = []
        
        # Determine highest risk level
        highest_risk = PRRiskLevel.LOW
        
        for result in file_results:
            # Critical issues (errors)
            for err in result.errors:
                critical_issues.append(f"`{result.file_path}`: {err}")
            
            # Warnings
            for warn in result.warnings:
                warnings.append(f"`{result.file_path}`: {warn}")
            
            # Track highest risk
            if result.impact_risk:
                file_risk = PRRiskLevel[result.impact_risk.upper()]
                if file_risk > highest_risk:
                    highest_risk = file_risk
        
        # Calculate total lines changed
        total_added = sum(c.lines_added for c in file_changes)
        total_removed = sum(c.lines_removed for c in file_changes)
        
        # Determine verdict
        if files_rejected > 0:
            verdict = PRVerdict.REQUEST_CHANGES
        elif highest_risk == PRRiskLevel.CRITICAL:
            verdict = PRVerdict.REQUEST_CHANGES
            if not any("critical risk" in i.lower() for i in critical_issues):
                critical_issues.append("PR contains CRITICAL risk changes - requires senior review")
        elif warnings:
            verdict = PRVerdict.COMMENT
        else:
            verdict = PRVerdict.APPROVE
        
        # Generate labels
        labels = self._generate_labels(
            highest_risk=highest_risk,
            has_failed_tests=any(r.test_passed is False for r in file_results),
            total_lines=total_added + total_removed,
        )
        
        # Generate suggestions
        suggestions = self._generate_suggestions(file_results, file_changes)
        
        return PRVerdictReport(
            verdict=verdict,
            risk_level=highest_risk,
            pr_number=pr_number,
            repo=repo,
            base_branch=base_branch,
            head_branch=head_branch,
            files_reviewed=len(file_results),
            files_approved=files_approved,
            files_rejected=files_rejected,
            file_results=file_results,
            total_lines_added=total_added,
            total_lines_removed=total_removed,
            critical_issues=critical_issues,
            warnings=warnings,
            suggestions=suggestions,
            labels=labels,
        )
    
    def _generate_labels(
        self,
        highest_risk: PRRiskLevel,
        has_failed_tests: bool,
        total_lines: int,
    ) -> List[str]:
        """Generate auto-labels based on results."""
        if not self.config.auto_label:
            return []
        
        labels = []
        mapping = self.config.label_mapping
        
        if highest_risk == PRRiskLevel.CRITICAL and "critical" in mapping:
            labels.append(mapping["critical"])
        elif highest_risk == PRRiskLevel.HIGH and "high" in mapping:
            labels.append(mapping["high"])
        
        if has_failed_tests and "needs_tests" in mapping:
            labels.append(mapping["needs_tests"])
        
        if total_lines > self.config.large_pr_threshold and "large_pr" in mapping:
            labels.append(mapping["large_pr"])
        
        return labels
    
    def _generate_suggestions(
        self,
        file_results: List[FileReviewResult],
        file_changes: List[FileChange],
    ) -> List[str]:
        """Generate helpful suggestions."""
        suggestions = []
        
        # Check for missing tests
        code_files = [c for c in file_changes if c.language in ("python", "typescript", "javascript")]
        test_files = [c for c in file_changes if "test" in c.path.lower()]
        
        if code_files and not test_files:
            suggestions.append("Consider adding tests for the new/modified code")
        
        # Check for large files
        large_files = [r for r in file_results if r.impact_callers > 10]
        if large_files:
            suggestions.append("High-impact files detected - consider splitting the PR")
        
        # Check for high duplication
        dup_files = [r for r in file_results if len(r.duplicate_warnings) > 2]
        if dup_files:
            suggestions.append("Multiple duplications detected - consider refactoring common patterns")
        
        return suggestions


# =============================================================================
# FACTORY
# =============================================================================

def create_pr_scanner(
    project_root: Optional[str] = None,
    session_maker: Optional[Any] = None,
    qdrant_client: Optional[Any] = None,
    **kwargs
) -> PRScanner:
    """
    Factory function to create a PRScanner.
    
    Args:
        project_root: Root directory for file resolution
        session_maker: DB session for audit logging
        qdrant_client: Qdrant client for semantic linting
        **kwargs: Additional PRScannerConfig fields
        
    Returns:
        Configured PRScanner instance
    """
    config = PRScannerConfig(
        project_root=project_root,
        **{k: v for k, v in kwargs.items() if hasattr(PRScannerConfig, k)}
    )
    
    return PRScanner(
        config=config,
        session_maker=session_maker,
        qdrant_client=qdrant_client,
    )
