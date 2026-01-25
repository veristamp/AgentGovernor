# judgment/__init__.py
"""
Judgment System - "Senior Engineer in a Box"

Automated safety gates for code modifications.

Simple usage:
    from judgment import create_judgment_manager
    
    judgment = create_judgment_manager(session_maker=db)
    
    result = await judgment.evaluate(
        file_path="src/main.py",
        old_content="...",
        new_content="..."
    )
    
    if result.approved:
        # Apply the patch
        ...

The judgment pipeline runs 5 gates in sequence:
1. **Validator** - Syntax validation (tree-sitter)
2. **Linter** - Duplication detection (semantic)
3. **Critic** - Diff discipline (scope, size, safety)
4. **Oracle** - Impact analysis (callers, tests, blast radius)
5. **Immune** - Test verification (run tests before commit)

Layer Structure:
┌─────────────────────────────────────────────────────────────────┐
│  JudgmentManager              (High Level - evaluate())         │
├─────────────────────────────────────────────────────────────────┤
│  GATES                        (Mid Level - Individual Gates)    │
│  Validator | Linter | Critic | Oracle | Immune                  │
├─────────────────────────────────────────────────────────────────┤
│  core.py                      (Low Level - Data Structures)     │
│  GateType | Decision | RiskLevel | JudgmentResult               │
├─────────────────────────────────────────────────────────────────┤
│  VPC (PatchLogger)            (Audit Trail)                     │
└─────────────────────────────────────────────────────────────────┘
"""

# Core data structures
from .core import (
    GateType,
    Decision,
    RiskLevel,
    Severity,
    GateResult,
    JudgmentResult,
    JudgmentConfig,
    get_language_from_path,
)

# Manager (main API)
from .manager import (
    JudgmentManager,
    create_judgment_manager,
    PatchEvaluation,  # Legacy alias
)

# Gate 1: Syntax Validation
from .validator import (
    PatchValidator,
    create_validator,
    validate_before_patch,
    ValidationResult,
    PreviewResult,
)

# Gate 1b: Semantic Linter
from .linter import (
    SemanticLinter,
    create_linter,
    LintResult,
    DuplicateMatch,
)

# Gate 2: Diff Critic
from .critic import (
    DiffCritic,
    create_critic,
    Critique,
    Violation,
    DiffStats,
)

# Gate 3: Impact Oracle
from .oracle import (
    ImpactOracle,
    create_oracle,
    ImpactReport,
    Caller,
    TestCoverage,
)

# Gate 4: Immune System
from .immune import (
    ImmuneSystem,
    create_immune_system,
    TestResult,
    PatchVerification,
    TestStatus,
)

# VPC: Audit Logging
from .vpc import (
    PatchLogger,
    PatchRecord,
    create_patch_logger,
    PatchDecision,
    RejectionGate,
)

__all__ = [
    # Core
    "GateType",
    "Decision", 
    "RiskLevel",
    "Severity",
    "GateResult",
    "JudgmentResult",
    "JudgmentConfig",
    "get_language_from_path",
    
    # Manager (main API)
    "JudgmentManager",
    "create_judgment_manager",
    "PatchEvaluation",
    
    # Gate 1: Validator
    "PatchValidator",
    "create_validator",
    "validate_before_patch",
    "ValidationResult",
    "PreviewResult",
    
    # Gate 1b: Linter
    "SemanticLinter",
    "create_linter",
    "LintResult",
    "DuplicateMatch",
    
    # Gate 2: Critic
    "DiffCritic",
    "create_critic",
    "Critique",
    "Violation",
    "DiffStats",
    
    # Gate 3: Oracle
    "ImpactOracle",
    "create_oracle",
    "ImpactReport",
    "Caller",
    "TestCoverage",
    
    # Gate 4: Immune
    "ImmuneSystem",
    "create_immune_system",
    "TestResult",
    "PatchVerification", 
    "TestStatus",
    
    # VPC
    "PatchLogger",
    "PatchRecord",
    "create_patch_logger",
    "PatchDecision",
    "RejectionGate",
]
