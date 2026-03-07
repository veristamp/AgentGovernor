# judgment/critic.py
"""
Diff Critic - Enforces patch discipline for senior-level code changes.

This is the second layer of "Senior Engineer in a Box":
- Minimal, focused changes
- No whitespace drift
- No scope violations
- No hidden refactors in bugfixes

The goal is to make AI-generated patches REVIEWABLE by humans.
The #1 reason AI PRs get rejected is noise - touching too many lines,
reformatting unrelated code, sneaking in refactors.

Usage:
    from judgment.critic import DiffCritic, Critique
    
    critic = DiffCritic()
    critique = critic.critique_patch(old_content, new_content, chunk_metadata)
    
    if not critique.approved:
        for violation in critique.violations:
            print(f"[{violation.severity}] {violation.rule}: {violation.message}")
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional, Set
import difflib
import re

from config import get_logger

logger = get_logger("Critic")


# =============================================================================
# ENUMS AND DATACLASSES
# =============================================================================

class Severity(Enum):
    """Violation severity levels."""
    INFO = "info"       # Noted but allowed
    WARNING = "warning"  # Flagged for review
    ERROR = "error"      # Rejected - must fix


class ViolationType(Enum):
    """Types of patch discipline violations."""
    PATCH_TOO_LARGE = "patch_too_large"
    SCOPE_VIOLATION = "scope_violation"
    WHITESPACE_DRIFT = "whitespace_drift"
    NEW_DEPENDENCY = "new_dependency"
    REMOVED_DEPENDENCY = "removed_dependency"
    REFACTOR_IN_BUGFIX = "refactor_in_bugfix"
    COMMENT_REMOVAL = "comment_removal"
    LOGGING_REMOVED = "logging_removed"
    ERROR_HANDLING_REMOVED = "error_handling_removed"


@dataclass
class Violation:
    """A single patch discipline violation."""
    rule: ViolationType
    severity: Severity
    message: str
    line_number: Optional[int] = None
    suggestion: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule.value,
            "severity": self.severity.value,
            "message": self.message,
            "line_number": self.line_number,
            "suggestion": self.suggestion,
        }


@dataclass
class DiffStats:
    """Statistics about a diff."""
    lines_added: int = 0
    lines_removed: int = 0
    lines_changed: int = 0
    chars_added: int = 0
    chars_removed: int = 0
    old_line_count: int = 0
    new_line_count: int = 0
    
    @property
    def change_ratio(self) -> float:
        """Ratio of lines changed to original line count."""
        if self.old_line_count == 0:
            return float('inf') if self.new_line_count > 0 else 0
        return (self.lines_added + self.lines_removed) / self.old_line_count
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "lines_changed": self.lines_changed,
            "chars_added": self.chars_added,
            "chars_removed": self.chars_removed,
            "old_line_count": self.old_line_count,
            "new_line_count": self.new_line_count,
            "change_ratio": round(self.change_ratio, 2),
        }


@dataclass
class Critique:
    """Result of patch critique."""
    approved: bool
    score: float  # 0-100, higher is better
    violations: List[Violation] = field(default_factory=list)
    stats: DiffStats = field(default_factory=DiffStats)
    feedback: str = ""  # Human-readable feedback for the agent
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "score": self.score,
            "violations": [v.to_dict() for v in self.violations],
            "stats": self.stats.to_dict(),
            "feedback": self.feedback,
        }
    
    def get_agent_feedback(self) -> str:
        """Generate structured feedback for the LLM agent to retry."""
        if self.approved:
            return f"Patch approved (score: {self.score:.0f}/100)"
        
        lines = [
            f"Patch rejected (score: {self.score:.0f}/100). Issues found:",
        ]
        
        for v in self.violations:
            if v.severity == Severity.ERROR:
                lines.append(f"  ❌ {v.message}")
                if v.suggestion:
                    lines.append(f"     Fix: {v.suggestion}")
        
        for v in self.violations:
            if v.severity == Severity.WARNING:
                lines.append(f"  ⚠️ {v.message}")
        
        lines.append("")
        lines.append("Please retry with a more focused change.")
        
        return "\n".join(lines)


# =============================================================================
# IMPORT DETECTION
# =============================================================================

# Patterns for detecting imports in various languages
IMPORT_PATTERNS = {
    # Python
    r"^import\s+(\S+)": "python_import",
    r"^from\s+(\S+)\s+import": "python_from",
    
    # JavaScript/TypeScript
    r"^import\s+.*\s+from\s+['\"]([^'\"]+)['\"]": "js_import_from",
    r"^import\s+['\"]([^'\"]+)['\"]": "js_import_side_effect",
    r"^const\s+\w+\s*=\s*require\(['\"]([^'\"]+)['\"]\)": "js_require",
    
    # Go
    r'^import\s+"([^"]+)"': "go_import_single",
    r'^\s+"([^"]+)"': "go_import_block",  # Inside import ( )
    
    # Rust
    r"^use\s+(\S+)": "rust_use",
    
    # Java
    r"^import\s+([\w.]+);": "java_import",
}


def extract_imports(content: str) -> Set[str]:
    """Extract all import statements from content."""
    imports = set()
    
    for line in content.split("\n"):
        line = line.strip()
        for pattern, _ in IMPORT_PATTERNS.items():
            match = re.match(pattern, line)
            if match:
                imports.add(match.group(1))
    
    return imports


# =============================================================================
# DIFF CRITIC CLASS
# =============================================================================

class DiffCritic:
    """
    Analyzes patches for quality and adherence to senior-level discipline.
    
    Enforces rules:
    1. Size Discipline: Changes should be proportional to intent
    2. Scope Containment: Don't touch unrelated code
    3. Format Stability: Don't reformat unrelated lines
    4. Dependency Awareness: Flag new/removed imports
    5. Safety Preservation: Don't remove error handling/logging
    """
    
    def __init__(
        self,
        max_change_ratio: float = 3.0,  # Max 3x the target chunk size
        max_whitespace_only_lines: int = 2,  # Allowed formatting changes
        flag_new_dependencies: bool = True,
        flag_removed_safety: bool = True,
    ):
        """
        Initialize the critic.
        
        Args:
            max_change_ratio: Maximum ratio of changed lines to original
            max_whitespace_only_lines: Tolerance for whitespace changes
            flag_new_dependencies: Whether to flag new imports
            flag_removed_safety: Whether to flag removed error handling
        """
        self.max_change_ratio = max_change_ratio
        self.max_whitespace_only_lines = max_whitespace_only_lines
        self.flag_new_dependencies = flag_new_dependencies
        self.flag_removed_safety = flag_removed_safety
    
    def compute_diff_stats(
        self, 
        old_content: str, 
        new_content: str
    ) -> DiffStats:
        """Compute detailed statistics about a diff."""
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()
        
        stats = DiffStats(
            old_line_count=len(old_lines),
            new_line_count=len(new_lines),
            chars_added=max(0, len(new_content) - len(old_content)),
            chars_removed=max(0, len(old_content) - len(new_content)),
        )
        
        # Use SequenceMatcher for detailed diff
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "insert":
                stats.lines_added += (j2 - j1)
            elif tag == "delete":
                stats.lines_removed += (i2 - i1)
            elif tag == "replace":
                stats.lines_changed += max(i2 - i1, j2 - j1)
        
        return stats
    
    def detect_whitespace_only_changes(
        self,
        old_content: str,
        new_content: str
    ) -> List[int]:
        """
        Find lines that only differ by whitespace.
        
        Returns list of line numbers with whitespace-only changes.
        """
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()
        
        whitespace_lines = []
        
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                # Check if the changes are whitespace-only
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    old_stripped = old_lines[i].strip() if i < len(old_lines) else ""
                    new_stripped = new_lines[j].strip() if j < len(new_lines) else ""
                    
                    if old_stripped == new_stripped and old_lines[i] != new_lines[j]:
                        whitespace_lines.append(j + 1)  # 1-indexed
        
        return whitespace_lines
    
    def detect_removed_patterns(
        self,
        old_content: str,
        new_content: str
    ) -> Dict[str, List[str]]:
        """
        Detect removed safety-critical patterns.
        
        Returns dict of pattern_type -> list of removed lines.
        """
        removed = {
            "error_handling": [],
            "logging": [],
            "comments": [],
            "assertions": [],
        }
        
        old_lines = set(old_content.splitlines())
        new_lines = set(new_content.splitlines())
        
        deleted_lines = old_lines - new_lines
        
        for line in deleted_lines:
            line_stripped = line.strip()
            
            # Error handling
            if any(kw in line_stripped.lower() for kw in ["try:", "except", "catch", "finally", "raise", "throw"]):
                removed["error_handling"].append(line_stripped)
            
            # Logging
            if any(kw in line_stripped.lower() for kw in ["logger.", "logging.", "console.log", "print(", "console.error"]):
                removed["logging"].append(line_stripped)
            
            # Comments (non-trivial)
            if line_stripped.startswith(("#", "//", "/*", "*")) and len(line_stripped) > 10:
                removed["comments"].append(line_stripped)
            
            # Assertions
            if any(kw in line_stripped for kw in ["assert ", "Assert.", "expect(", "should."]):
                removed["assertions"].append(line_stripped)
        
        return removed
    
    def critique_patch(
        self,
        old_content: str,
        new_content: str,
        chunk_metadata: Optional[Dict[str, Any]] = None,
        intent: Optional[str] = None
    ) -> Critique:
        """
        Analyze a patch and return a critique.
        
        Args:
            old_content: Original content being replaced
            new_content: New content to insert
            chunk_metadata: Optional chunk context
            intent: Optional description of what the patch is supposed to do
            
        Returns:
            Critique with approval status, violations, and feedback
        """
        violations = []
        score = 100.0  # Start perfect, deduct for violations
        
        # 1. Compute diff stats
        stats = self.compute_diff_stats(old_content, new_content)
        
        # 2. Check change ratio
        if stats.change_ratio > self.max_change_ratio:
            violations.append(Violation(
                rule=ViolationType.PATCH_TOO_LARGE,
                severity=Severity.ERROR,
                message=f"Patch is {stats.change_ratio:.1f}x the target size (max: {self.max_change_ratio}x)",
                suggestion=f"Break this into smaller changes. Target ~{stats.old_line_count} lines."
            ))
            score -= 30
        elif stats.change_ratio > 2.0:
            violations.append(Violation(
                rule=ViolationType.PATCH_TOO_LARGE,
                severity=Severity.WARNING,
                message=f"Patch is {stats.change_ratio:.1f}x the target size",
            ))
            score -= 10
        
        # 3. Check whitespace drift
        whitespace_lines = self.detect_whitespace_only_changes(old_content, new_content)
        if len(whitespace_lines) > self.max_whitespace_only_lines:
            violations.append(Violation(
                rule=ViolationType.WHITESPACE_DRIFT,
                severity=Severity.WARNING,
                message=f"Changed whitespace on {len(whitespace_lines)} lines with no content change",
                suggestion="Keep formatting changes separate from logic changes."
            ))
            score -= 5 * len(whitespace_lines)
        
        # 4. Check for new/removed dependencies
        if self.flag_new_dependencies:
            old_imports = extract_imports(old_content)
            new_imports = extract_imports(new_content)
            
            added_imports = new_imports - old_imports
            removed_imports = old_imports - new_imports
            
            for imp in added_imports:
                violations.append(Violation(
                    rule=ViolationType.NEW_DEPENDENCY,
                    severity=Severity.WARNING,
                    message=f"Added new import: {imp}",
                    suggestion="Ensure this dependency is in the project."
                ))
                score -= 5
            
            for imp in removed_imports:
                violations.append(Violation(
                    rule=ViolationType.REMOVED_DEPENDENCY,
                    severity=Severity.INFO,
                    message=f"Removed import: {imp}",
                ))
        
        # 5. Check for removed safety patterns
        if self.flag_removed_safety:
            removed = self.detect_removed_patterns(old_content, new_content)
            
            if removed["error_handling"]:
                violations.append(Violation(
                    rule=ViolationType.ERROR_HANDLING_REMOVED,
                    severity=Severity.ERROR,
                    message=f"Removed {len(removed['error_handling'])} error handling line(s)",
                    suggestion="Error handling should not be removed without explicit reason."
                ))
                score -= 20
            
            if removed["logging"]:
                violations.append(Violation(
                    rule=ViolationType.LOGGING_REMOVED,
                    severity=Severity.WARNING,
                    message=f"Removed {len(removed['logging'])} logging statement(s)",
                    suggestion="Consider if logging is still needed for debugging."
                ))
                score -= 10
            
            if len(removed["comments"]) > 3:
                violations.append(Violation(
                    rule=ViolationType.COMMENT_REMOVAL,
                    severity=Severity.WARNING,
                    message=f"Removed {len(removed['comments'])} comment(s)",
                    suggestion="Preserve documentation unless explicitly updating it."
                ))
                score -= 5
        
        # 6. Ensure score is bounded
        score = max(0, min(100, score))
        
        # 7. Determine approval
        has_errors = any(v.severity == Severity.ERROR for v in violations)
        approved = not has_errors and score >= 50
        
        # 8. Generate feedback
        critique = Critique(
            approved=approved,
            score=score,
            violations=violations,
            stats=stats,
        )
        critique.feedback = critique.get_agent_feedback()
        
        logger.info(f"Critique: score={score:.0f}, approved={approved}, violations={len(violations)}")
        
        return critique


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_critic(**kwargs) -> DiffCritic:
    """Factory function to create a DiffCritic instance."""
    return DiffCritic(**kwargs)


def quick_critique(old_content: str, new_content: str) -> Dict[str, Any]:
    """
    Quick critique for simple use cases.
    
    Returns dict with approval status and feedback.
    """
    critic = DiffCritic()
    result = critic.critique_patch(old_content, new_content)
    return result.to_dict()
