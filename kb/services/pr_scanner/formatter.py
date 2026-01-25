# services/pr_scanner/formatter.py
"""
PR Comment Formatter - Beautiful, human-readable PR review comments.

Generates GitHub/GitLab compatible markdown comments with:
- Executive summary
- Per-file breakdown
- Actionable feedback
- Risk indicators
"""

from typing import List, Optional
from datetime import datetime

from config import get_logger
from .core import (
    PRVerdictReport, PRVerdict, PRRiskLevel,
    FileReviewResult, FileChange
)

logger = get_logger("PRFormatter")


# =============================================================================
# EMOJI MAPS
# =============================================================================

VERDICT_EMOJI = {
    PRVerdict.APPROVE: "✅",
    PRVerdict.REQUEST_CHANGES: "❌",
    PRVerdict.COMMENT: "💬",
}

RISK_EMOJI = {
    PRRiskLevel.LOW: "🟢",
    PRRiskLevel.MEDIUM: "🟡",
    PRRiskLevel.HIGH: "🟠",
    PRRiskLevel.CRITICAL: "🔴",
}

GATE_ICONS = {
    "validator": "🔍",
    "linter": "📋",
    "critic": "📏",
    "oracle": "🔮",
    "immune": "🧪",
}


# =============================================================================
# PR COMMENT FORMATTER
# =============================================================================

class PRCommentFormatter:
    """
    Formats PRVerdictReport into beautiful Markdown comments.
    
    Designed for GitHub PR comments but compatible with GitLab MR notes.
    """
    
    def __init__(self, include_details: bool = True, max_files_detailed: int = 10):
        """
        Initialize formatter.
        
        Args:
            include_details: Include per-file details
            max_files_detailed: Max files to show detailed breakdown
        """
        self.include_details = include_details
        self.max_files_detailed = max_files_detailed
    
    def format(self, report: PRVerdictReport) -> str:
        """
        Format a PRVerdictReport as a Markdown comment.
        
        Args:
            report: The verdict report to format
            
        Returns:
            Markdown-formatted string
        """
        sections = [
            self._format_header(report),
            self._format_summary(report),
            self._format_critical_issues(report),
            self._format_file_breakdown(report),
            self._format_warnings(report),
            self._format_suggestions(report),
            self._format_footer(report),
        ]
        
        return "\n\n".join(s for s in sections if s)
    
    def _format_header(self, report: PRVerdictReport) -> str:
        """Format the header with verdict badge."""
        emoji = VERDICT_EMOJI.get(report.verdict, "❓")
        risk_emoji = RISK_EMOJI.get(report.risk_level, "⚪")
        
        verdict_text = report.verdict.value.replace("_", " ").upper()
        
        header = f"## {emoji} PR Review: **{verdict_text}**\n\n"
        header += f"| Metric | Value |\n|--------|-------|\n"
        header += f"| Risk Level | {risk_emoji} {report.risk_level.value.upper()} |\n"
        header += f"| Files Reviewed | {report.files_reviewed} |\n"
        header += f"| Files Passed | {report.files_approved}/{report.files_reviewed} |\n"
        header += f"| Lines Changed | +{report.total_lines_added} / -{report.total_lines_removed} |\n"
        header += f"| Scan Duration | {report.scan_duration_ms}ms |"
        
        return header
    
    def _format_summary(self, report: PRVerdictReport) -> str:
        """Format executive summary."""
        if report.verdict == PRVerdict.APPROVE:
            return (
                "### ✨ Summary\n\n"
                "All automated checks passed. This PR is ready for human review."
            )
        elif report.verdict == PRVerdict.REQUEST_CHANGES:
            issues = len(report.critical_issues)
            return (
                "### ⚠️ Summary\n\n"
                f"**{issues} critical issue(s)** must be addressed before this PR can be merged.\n"
                "Please review the issues below and push fixes."
            )
        else:
            return (
                "### 💭 Summary\n\n"
                "This PR has some observations that may warrant attention.\n"
                "No blocking issues found, but consider the notes below."
            )
    
    def _format_critical_issues(self, report: PRVerdictReport) -> str:
        """Format critical issues section."""
        if not report.critical_issues:
            return ""
        
        lines = ["### 🚨 Critical Issues\n"]
        lines.append("The following must be fixed:\n")
        
        for issue in report.critical_issues:
            lines.append(f"- ❌ {issue}")
        
        return "\n".join(lines)
    
    def _format_file_breakdown(self, report: PRVerdictReport) -> str:
        """Format per-file breakdown."""
        if not self.include_details or not report.file_results:
            return ""
        
        lines = ["### 📁 File Review\n"]
        
        # Show failed files first
        failed = [f for f in report.file_results if not f.approved]
        passed = [f for f in report.file_results if f.approved]
        
        # Limit to max_files_detailed
        files_to_show = failed + passed[:self.max_files_detailed - len(failed)]
        
        if failed:
            lines.append("<details open>\n<summary>❌ Failed Files</summary>\n")
            for f in failed:
                lines.append(self._format_file_result(f, expanded=True))
            lines.append("</details>\n")
        
        if passed:
            visible_passed = passed[:self.max_files_detailed - len(failed)]
            hidden_count = len(passed) - len(visible_passed)
            
            lines.append("<details>\n<summary>✅ Passed Files</summary>\n")
            for f in visible_passed:
                lines.append(self._format_file_result(f, expanded=False))
            if hidden_count > 0:
                lines.append(f"\n*...and {hidden_count} more passing files*")
            lines.append("</details>")
        
        return "\n".join(lines)
    
    def _format_file_result(self, result: FileReviewResult, expanded: bool = False) -> str:
        """Format a single file result."""
        icon = "✅" if result.approved else "❌"
        lines = [f"\n#### {icon} `{result.file_path}`\n"]
        
        if not result.approved or expanded:
            # Show gates status
            gates = []
            
            if not result.syntax_valid:
                gates.append(f"- {GATE_ICONS['validator']} **Syntax**: Failed")
                for err in result.syntax_errors[:3]:
                    gates.append(f"  - {err}")
            else:
                gates.append(f"- {GATE_ICONS['validator']} Syntax: ✓ Valid")
            
            if result.duplicate_warnings:
                gates.append(f"- {GATE_ICONS['linter']} **Duplicates**: {len(result.duplicate_warnings)} found")
            
            if not result.critic_approved:
                gates.append(f"- {GATE_ICONS['critic']} **Critic**: Score {result.critic_score:.0f}/100")
                for v in result.critic_violations[:3]:
                    msg = v.get("message", str(v))
                    gates.append(f"  - {msg}")
            else:
                gates.append(f"- {GATE_ICONS['critic']} Critic: ✓ Score {result.critic_score:.0f}/100")
            
            if result.impact_risk in ("high", "critical"):
                gates.append(f"- {GATE_ICONS['oracle']} **Impact**: {result.impact_risk.upper()} ({result.impact_callers} callers)")
            elif result.impact_callers > 0:
                gates.append(f"- {GATE_ICONS['oracle']} Impact: {result.impact_risk} ({result.impact_callers} callers)")
            
            if result.test_passed is not None:
                test_icon = "✓" if result.test_passed else "✗"
                gates.append(f"- {GATE_ICONS['immune']} Tests: {test_icon} {result.test_summary}")
            
            lines.extend(gates)
        
        return "\n".join(lines)
    
    def _format_warnings(self, report: PRVerdictReport) -> str:
        """Format warnings section."""
        if not report.warnings:
            return ""
        
        lines = ["### ⚠️ Warnings\n"]
        for warning in report.warnings[:10]:
            lines.append(f"- {warning}")
        
        if len(report.warnings) > 10:
            lines.append(f"\n*...and {len(report.warnings) - 10} more warnings*")
        
        return "\n".join(lines)
    
    def _format_suggestions(self, report: PRVerdictReport) -> str:
        """Format suggestions section."""
        if not report.suggestions:
            return ""
        
        lines = ["### 💡 Suggestions\n"]
        for suggestion in report.suggestions[:5]:
            lines.append(f"- {suggestion}")
        
        return "\n".join(lines)
    
    def _format_footer(self, report: PRVerdictReport) -> str:
        """Format footer with metadata."""
        scanned_at = report.scanned_at or datetime.utcnow()
        timestamp = scanned_at.strftime("%Y-%m-%d %H:%M UTC")
        
        footer = "---\n"
        footer += f"*🤖 Automated review by **Veristamp PR Scanner** | {timestamp}*"
        
        if report.labels:
            footer += f"\n*Labels: {', '.join(report.labels)}*"
        
        return footer


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def format_pr_comment(report: PRVerdictReport, **kwargs) -> str:
    """
    Quick function to format a PR verdict report.
    
    Args:
        report: The verdict report
        **kwargs: Passed to PRCommentFormatter
        
    Returns:
        Markdown comment string
    """
    formatter = PRCommentFormatter(**kwargs)
    return formatter.format(report)


def format_inline_comment(file_result: FileReviewResult, line: int) -> str:
    """
    Format an inline comment for a specific line.
    
    Args:
        file_result: Review result for the file
        line: Line number for the comment
        
    Returns:
        Short inline comment
    """
    issues = []
    
    for err in file_result.syntax_errors:
        if str(line) in err:
            issues.append(f"🔍 {err}")
    
    for v in file_result.critic_violations:
        if v.get("line_number") == line:
            issues.append(f"📏 {v.get('message', '')}")
    
    return "\n".join(issues) if issues else ""
