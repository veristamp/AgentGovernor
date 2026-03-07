# services/pr_scanner/__init__.py
"""
PR Scanner Service - Automated Pull Request Review.

Uses the Judgment pipeline to automatically review PRs on GitHub/GitLab,
providing structured feedback, risk assessment, and auto-labeling.

Simple usage:
    from services.pr_scanner import PRScanner, create_pr_scanner
    
    scanner = create_pr_scanner(project_root="f:/kb")
    report = await scanner.scan_diff(diff_text, pr_number=123)
    
    print(report.summary)
    # ✅ APPROVE: 5/5 files passed (low risk)

With GitHub integration:
    from services.pr_scanner import PRService, create_pr_service
    
    service = create_pr_service(github_token="ghp_...")
    report = await service.scan_and_comment("owner/repo", 123)

Architecture:
    ┌────────────────────────────────────────────────────────────────┐
    │  PRService                   (High Level - Full Integration)   │
    │  - Fetch PR from GitHub/GitLab                                 │
    │  - Scan with PRScanner                                         │
    │  - Post formatted comment                                      │
    ├────────────────────────────────────────────────────────────────┤
    │  PRScanner                   (Mid Level - Core Logic)          │
    │  - Parse diff into FileChanges                                 │
    │  - Run JudgmentManager on each file                            │
    │  - Aggregate into PRVerdictReport                              │
    ├────────────────────────────────────────────────────────────────┤
    │  Components                  (Low Level - Utilities)           │
    │  - DiffParser: Unified diff → FileChange                       │
    │  - PRCommentFormatter: Report → Markdown                       │
    │  - GitHubProvider: GitHub API calls                            │
    ├────────────────────────────────────────────────────────────────┤
    │  Core                        (Data Structures)                 │
    │  - PRVerdict, PRRiskLevel, FileChange                          │
    │  - FileReviewResult, PRVerdictReport                           │
    │  - PRScannerConfig                                             │
    └────────────────────────────────────────────────────────────────┘
"""

# Core data structures
from .core import (
    PRVerdict,
    PRRiskLevel,
    FileChangeType,
    DiffHunk,
    FileChange,
    FileReviewResult,
    PRVerdictReport,
    PRScannerConfig,
)

# Diff parsing
from .diff_parser import (
    DiffParser,
    parse_diff,
    filter_changes,
)

# Main scanner
from .scanner import (
    PRScanner,
    create_pr_scanner,
)

# Formatting
from .formatter import (
    PRCommentFormatter,
    format_pr_comment,
    format_inline_comment,
)

# Providers
from .providers import (
    GitProvider,
    PRInfo,
    GitHubProvider,
    create_github_provider,
)

# High-level service
from .service import (
    PRService,
    create_pr_service,
)

__all__ = [
    # Core
    "PRVerdict",
    "PRRiskLevel",
    "FileChangeType",
    "DiffHunk",
    "FileChange",
    "FileReviewResult",
    "PRVerdictReport",
    "PRScannerConfig",
    
    # Diff Parser
    "DiffParser",
    "parse_diff",
    "filter_changes",
    
    # Scanner
    "PRScanner",
    "create_pr_scanner",
    
    # Formatter
    "PRCommentFormatter",
    "format_pr_comment",
    "format_inline_comment",
    
    # Providers
    "GitProvider",
    "PRInfo",
    "GitHubProvider",
    "create_github_provider",
    
    # Service
    "PRService",
    "create_pr_service",
]
