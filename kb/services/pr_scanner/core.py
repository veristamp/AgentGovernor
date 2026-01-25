# services/pr_scanner/core.py
"""
Core Data Structures for PR Scanner.

Contains all enums, dataclasses, and type definitions used across the PR scanner.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List
from datetime import datetime


# =============================================================================
# ENUMS
# =============================================================================

class PRVerdict(Enum):
    """Final verdict for a Pull Request."""
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    COMMENT = "comment"  # Neutral - just observations


class PRRiskLevel(Enum):
    """Overall risk level for a PR."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    
    def __lt__(self, other):
        order = [PRRiskLevel.LOW, PRRiskLevel.MEDIUM, PRRiskLevel.HIGH, PRRiskLevel.CRITICAL]
        return order.index(self) < order.index(other)


class FileChangeType(Enum):
    """Type of file change in a PR."""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


# =============================================================================
# FILE CHANGE STRUCTURES
# =============================================================================

@dataclass
class DiffHunk:
    """A single hunk within a file diff."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    content: str  # The actual diff lines
    header: str = ""  # @@ -1,5 +1,7 @@


@dataclass
class FileChange:
    """A changed file in a PR."""
    path: str
    change_type: FileChangeType
    old_path: Optional[str] = None  # For renames
    hunks: List[DiffHunk] = field(default_factory=list)
    old_content: str = ""
    new_content: str = ""
    language: Optional[str] = None
    
    @property
    def lines_added(self) -> int:
        return sum(1 for h in self.hunks for line in h.content.split('\n') if line.startswith('+') and not line.startswith('+++'))
    
    @property
    def lines_removed(self) -> int:
        return sum(1 for h in self.hunks for line in h.content.split('\n') if line.startswith('-') and not line.startswith('---'))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "change_type": self.change_type.value,
            "old_path": self.old_path,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "language": self.language,
        }


# =============================================================================
# REVIEW RESULT STRUCTURES
# =============================================================================

@dataclass
class FileReviewResult:
    """Review result for a single file."""
    file_path: str
    approved: bool
    
    # Gate results
    syntax_valid: bool = True
    syntax_errors: List[str] = field(default_factory=list)
    
    duplicate_warnings: List[Dict[str, Any]] = field(default_factory=list)
    
    critic_approved: bool = True
    critic_score: float = 100.0
    critic_violations: List[Dict[str, Any]] = field(default_factory=list)
    
    impact_risk: str = "low"
    impact_callers: int = 0
    impact_warnings: List[str] = field(default_factory=list)
    
    test_passed: Optional[bool] = None
    test_summary: str = ""
    
    # Summary
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "approved": self.approved,
            "syntax_valid": self.syntax_valid,
            "syntax_errors": self.syntax_errors,
            "duplicate_warnings": self.duplicate_warnings,
            "critic_approved": self.critic_approved,
            "critic_score": self.critic_score,
            "critic_violations": self.critic_violations,
            "impact_risk": self.impact_risk,
            "impact_callers": self.impact_callers,
            "impact_warnings": self.impact_warnings,
            "test_passed": self.test_passed,
            "test_summary": self.test_summary,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class PRVerdictReport:
    """Complete PR review verdict."""
    verdict: PRVerdict
    risk_level: PRRiskLevel
    
    # PR metadata
    pr_number: int = 0
    repo: str = ""
    base_branch: str = ""
    head_branch: str = ""
    
    # File results
    files_reviewed: int = 0
    files_approved: int = 0
    files_rejected: int = 0
    file_results: List[FileReviewResult] = field(default_factory=list)
    
    # Aggregated stats
    total_lines_added: int = 0
    total_lines_removed: int = 0
    
    # Aggregated issues
    critical_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    
    # Labels to apply
    labels: List[str] = field(default_factory=list)
    
    # Timing
    scan_duration_ms: int = 0
    scanned_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "risk_level": self.risk_level.value,
            "pr_number": self.pr_number,
            "repo": self.repo,
            "base_branch": self.base_branch,
            "head_branch": self.head_branch,
            "files_reviewed": self.files_reviewed,
            "files_approved": self.files_approved,
            "files_rejected": self.files_rejected,
            "file_results": [f.to_dict() for f in self.file_results],
            "total_lines_added": self.total_lines_added,
            "total_lines_removed": self.total_lines_removed,
            "critical_issues": self.critical_issues,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "labels": self.labels,
            "scan_duration_ms": self.scan_duration_ms,
            "scanned_at": self.scanned_at.isoformat() if self.scanned_at else None,
        }
    
    @property
    def summary(self) -> str:
        """Human-readable one-line summary."""
        icon = "✅" if self.verdict == PRVerdict.APPROVE else "❌" if self.verdict == PRVerdict.REQUEST_CHANGES else "💬"
        return f"{icon} {self.verdict.value.upper()}: {self.files_approved}/{self.files_reviewed} files passed ({self.risk_level.value} risk)"


# =============================================================================
# CONFIG
# =============================================================================

@dataclass
class PRScannerConfig:
    """Configuration for PR Scanner."""
    # Gates to run (mirrors JudgmentConfig)
    validate_syntax: bool = True
    check_duplicates: bool = True
    run_critic: bool = True
    run_impact: bool = True
    run_tests: bool = False  # Expensive, off by default
    
    # PR-specific settings
    max_files_per_pr: int = 100
    max_lines_per_file: int = 5000
    skip_patterns: List[str] = field(default_factory=lambda: [
        "*.lock", "*.min.js", "*.min.css", 
        "package-lock.json", "yarn.lock", "poetry.lock"
    ])
    
    # Auto-labeling
    auto_label: bool = True
    label_mapping: Dict[str, str] = field(default_factory=lambda: {
        "critical": "⚠️ critical-risk",
        "high": "🟠 high-risk",
        "needs_tests": "🧪 needs-tests",
        "large_pr": "📦 large-pr",
    })
    
    # Thresholds
    large_pr_threshold: int = 500  # lines changed
    max_risk_to_approve: str = "high"  # critical = auto-reject
    
    # Project context
    project_root: Optional[str] = None
