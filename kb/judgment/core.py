# judgment/core.py
"""
Core Data Structures for Judgment System.

Shared enums, dataclasses, and utilities used across all gates.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List


# =============================================================================
# ENUMS
# =============================================================================

class GateType(Enum):
    """Types of judgment gates."""
    VALIDATOR = "validator"   # Syntax checking
    LINTER = "linter"         # Duplication detection
    CRITIC = "critic"         # Diff discipline
    ORACLE = "oracle"         # Impact analysis
    IMMUNE = "immune"         # Test verification
    VPC = "vpc"               # Audit logging


class Decision(Enum):
    """Patch decision outcomes."""
    APPROVED = "approved"
    REJECTED = "rejected"
    DRY_RUN = "dry_run"


class RiskLevel(Enum):
    """Risk levels for impact analysis."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    
    def __lt__(self, other):
        order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
        return order.index(self) < order.index(other)


class Severity(Enum):
    """Violation severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# =============================================================================
# GATE RESULTS
# =============================================================================

@dataclass
class GateResult:
    """Base result for any gate."""
    passed: bool = True
    gate: Optional[GateType] = None
    message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "gate": self.gate.value if self.gate else None,
            "message": self.message,
            "warnings": self.warnings
        }


@dataclass
class JudgmentResult:
    """
    Complete judgment result for a patch.
    
    This is the main output of JudgmentManager.evaluate().
    """
    # Decision
    approved: bool = False
    decision: Decision = Decision.REJECTED
    rejected_by: Optional[GateType] = None
    
    # Gate results (filled as gates run)
    validation: Optional[Any] = None  # ValidationResult
    duplicates: List[Dict] = field(default_factory=list)
    critique: Optional[Any] = None  # Critique
    impact: Optional[Any] = None  # ImpactReport
    verification: Optional[Any] = None  # PatchVerification
    
    # Audit
    patch_record: Optional[Any] = None  # PatchRecord
    
    # Summary
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration_ms: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "decision": self.decision.value,
            "rejected_by": self.rejected_by.value if self.rejected_by else None,
            "validation": self.validation.to_dict() if self.validation else None,
            "duplicates": self.duplicates,
            "critique": self.critique.to_dict() if self.critique else None,
            "impact": self.impact.to_dict() if self.impact else None,
            "verification": self.verification.to_dict() if self.verification else None,
            "warnings": self.warnings,
            "errors": self.errors,
            "duration_ms": self.duration_ms
        }
    
    @property
    def summary(self) -> str:
        """Human-readable summary."""
        icon = "✅" if self.approved else "❌"
        if self.rejected_by:
            return f"{icon} [{self.decision.value.upper()}] Rejected by {self.rejected_by.value}"
        return f"{icon} [{self.decision.value.upper()}]"


# =============================================================================
# JUDGMENT CONFIG
# =============================================================================

@dataclass
class JudgmentConfig:
    """Configuration for judgment system."""
    # Gates to run
    validate_syntax: bool = True
    check_duplicates: bool = True
    run_critic: bool = False  # Off by default (can be noisy)
    run_impact: bool = False  # Off by default (uses ripgrep)
    run_tests: bool = False   # Off by default (expensive)
    
    # Behavior
    strict_mode: bool = True  # Reject on any syntax error
    parallel_gates: bool = True  # Run gates 1-3 in parallel
    
    # Thresholds
    max_risk_level: RiskLevel = RiskLevel.HIGH  # Reject at CRITICAL
    duplicate_threshold: float = 0.85
    
    # Project
    project_root: Optional[str] = None


# =============================================================================
# UTILITIES
# =============================================================================

def get_language_from_path(file_path: str) -> Optional[str]:
    """Get tree-sitter language from file extension."""
    from pathlib import Path
    
    ext = Path(file_path).suffix.lstrip(".")
    
    EXTENSION_MAP = {
        "py": "python",
        "js": "javascript",
        "jsx": "javascript",
        "ts": "typescript",
        "tsx": "tsx",
        "go": "go",
        "rs": "rust",
        "java": "java",
        "c": "c",
        "cpp": "cpp",
        "h": "c",
        "hpp": "cpp",
        "rb": "ruby",
        "sh": "bash",
        "bash": "bash"
    }
    
    return EXTENSION_MAP.get(ext)
