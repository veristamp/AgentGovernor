# judgment/immune.py
"""
Immune System - Test-verified patch safety.

This is the fourth layer of "Senior Engineer in a Box":
- Run relevant tests BEFORE committing a patch
- Sandbox execution with timeouts
- Auto-revert on failure
- Feedback loop for retries

The principle: "I will not write unless tests prove it's correct."

Usage:
    from judgment.immune import ImmuneSystem, TestResult
    
    immune = ImmuneSystem(project_root="f:/kb")
    
    # Run tests related to a symbol
    result = immune.run_tests_for_symbol("apply_surgical_patch")
    
    # Or run specific test files
    result = immune.run_test_files(["tests/test_patcher.py"])
    
    if not result.passed:
        print(f"Tests failed: {result.summary}")
"""

import subprocess
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import shutil

from config import get_logger

logger = get_logger("Immune")


# =============================================================================
# ENUMS AND DATACLASSES
# =============================================================================

class TestStatus(Enum):
    """Status of a test run."""
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"       # Test execution error (not assertion failure)
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    NOT_RUN = "not_run"


@dataclass
class TestResult:
    """Result of running tests."""
    status: TestStatus
    passed: bool
    test_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    duration_ms: int = 0
    output: str = ""
    failed_tests: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    
    @property
    def summary(self) -> str:
        """Human-readable summary."""
        if self.status == TestStatus.PASSED:
            return f"✅ All {self.passed_count} tests passed ({self.duration_ms}ms)"
        elif self.status == TestStatus.FAILED:
            failed_list = ", ".join(self.failed_tests[:3])
            if len(self.failed_tests) > 3:
                failed_list += f" (+{len(self.failed_tests) - 3} more)"
            return f"❌ {self.failed_count} tests failed: {failed_list}"
        elif self.status == TestStatus.TIMEOUT:
            return f"⏰ Test execution timed out after {self.duration_ms}ms"
        elif self.status == TestStatus.ERROR:
            return f"💥 Test error: {self.error_message or 'Unknown error'}"
        elif self.status == TestStatus.SKIPPED:
            return "⏭️ Tests skipped"
        else:
            return "🔘 Tests not run"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "passed": self.passed,
            "test_count": self.test_count,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "error_count": self.error_count,
            "skipped_count": self.skipped_count,
            "duration_ms": self.duration_ms,
            "failed_tests": self.failed_tests[:10],
            "error_message": self.error_message,
            "summary": self.summary,
        }


@dataclass
class PatchVerification:
    """Complete verification result for a patch."""
    test_result: TestResult
    files_tested: List[str] = field(default_factory=list)
    symbols_tested: List[str] = field(default_factory=list)
    should_apply: bool = False
    reason: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_result": self.test_result.to_dict(),
            "files_tested": self.files_tested,
            "symbols_tested": self.symbols_tested,
            "should_apply": self.should_apply,
            "reason": self.reason,
        }


# =============================================================================
# PYTEST OUTPUT PARSING
# =============================================================================

def parse_pytest_output(output: str) -> Tuple[int, int, int, int, List[str]]:
    """
    Parse pytest output to extract test counts.
    
    Returns: (total, passed, failed, errors, failed_test_names)
    """
    total = 0
    passed = 0
    failed = 0
    errors = 0
    failed_tests = []
    
    # Look for the summary line like "5 passed, 2 failed, 1 error in 1.23s"
    summary_pattern = r'(\d+)\s+passed'
    match = re.search(summary_pattern, output)
    if match:
        passed = int(match.group(1))
    
    failed_pattern = r'(\d+)\s+failed'
    match = re.search(failed_pattern, output)
    if match:
        failed = int(match.group(1))
    
    error_pattern = r'(\d+)\s+error'
    match = re.search(error_pattern, output)
    if match:
        errors = int(match.group(1))
    
    skipped_pattern = r'(\d+)\s+skipped'
    skipped = 0
    match = re.search(skipped_pattern, output)
    if match:
        skipped = int(match.group(1))
    
    total = passed + failed + errors + skipped
    
    # Extract failed test names
    # Format: "FAILED tests/test_foo.py::test_bar - AssertionError"
    failed_test_pattern = r'FAILED\s+([^\s]+)'
    failed_tests = re.findall(failed_test_pattern, output)
    
    return total, passed, failed, errors, failed_tests


def parse_pytest_json(output: str) -> Dict[str, Any]:
    """Parse pytest JSON output (if using --json flag)."""
    # This would parse structured JSON output
    # For now, we use text parsing which is more universal
    import json
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {}


# =============================================================================
# IMMUNE SYSTEM CLASS
# =============================================================================

class ImmuneSystem:
    """
    Test-based verification for patches.
    
    Runs relevant tests before allowing patches to be applied.
    Acts as the final safety gate - "tests must pass".
    
    Features:
    - Discovers tests using Oracle's test finder
    - Runs tests in subprocess with timeout
    - Parses pytest output for pass/fail
    - Provides structured feedback for retry
    """
    
    def __init__(
        self,
        project_root: Optional[str] = None,
        timeout_seconds: int = 60,
        pytest_cmd: str = "uv run pytest",
        min_tests_required: int = 0,  # 0 = allow if no tests exist
        fail_on_no_tests: bool = False,
    ):
        """
        Initialize the immune system.
        
        Args:
            project_root: Root directory of the project
            timeout_seconds: Max time to run tests
            pytest_cmd: Command to run pytest (supports uv, poetry, etc.)
            min_tests_required: Minimum tests that must exist
            fail_on_no_tests: If True, reject patches with no test coverage
        """
        self.project_root = project_root or os.getcwd()
        self.timeout_seconds = timeout_seconds
        self.pytest_cmd = pytest_cmd
        self.min_tests_required = min_tests_required
        self.fail_on_no_tests = fail_on_no_tests
    
    def run_test_files(
        self,
        test_files: List[str],
        extra_args: Optional[List[str]] = None
    ) -> TestResult:
        """
        Run specific test files.
        
        Args:
            test_files: List of test file paths
            extra_args: Additional pytest arguments
            
        Returns:
            TestResult with pass/fail status
        """
        if not test_files:
            return TestResult(
                status=TestStatus.NOT_RUN,
                passed=True,  # No tests = pass (unless fail_on_no_tests)
                error_message="No test files provided"
            )
        
        # Build command
        cmd_parts = self.pytest_cmd.split()
        cmd_parts.extend(["-v", "--tb=short"])
        
        if extra_args:
            cmd_parts.extend(extra_args)
        
        # Add test files
        for tf in test_files:
            if os.path.exists(tf):
                cmd_parts.append(tf)
            elif os.path.exists(os.path.join(self.project_root, tf)):
                cmd_parts.append(os.path.join(self.project_root, tf))
        
        # If no valid files, skip
        actual_files = cmd_parts[len(self.pytest_cmd.split()) + 2 + len(extra_args or []):]
        if not actual_files:
            return TestResult(
                status=TestStatus.NOT_RUN,
                passed=True,
                error_message="No valid test files found"
            )
        
        return self._run_pytest(cmd_parts)
    
    def run_tests_for_symbol(
        self,
        symbol_name: str,
        test_files: Optional[List[str]] = None
    ) -> TestResult:
        """
        Run tests relevant to a specific symbol.
        
        If test_files not provided, uses Oracle to find them.
        
        Args:
            symbol_name: Function/class name to test
            test_files: Optional pre-discovered test files
            
        Returns:
            TestResult
        """
        if test_files is None:
            # Use Oracle to find tests
            from .oracle import find_related_tests
            test_files = find_related_tests(symbol_name, self.project_root)
        
        if not test_files:
            logger.info(f"No tests found for symbol: {symbol_name}")
            return TestResult(
                status=TestStatus.NOT_RUN,
                passed=not self.fail_on_no_tests,
                error_message=f"No tests found for {symbol_name}"
            )
        
        logger.info(f"Running {len(test_files)} test file(s) for {symbol_name}")
        return self.run_test_files(test_files)
    
    def run_tests_for_file(
        self,
        file_path: str
    ) -> TestResult:
        """
        Run tests related to a source file.
        
        Discovers tests by:
        1. Module name matching (foo.py -> test_foo.py)
        2. Symbol extraction + Oracle lookup
        
        Args:
            file_path: Path to the source file
            
        Returns:
            TestResult
        """
        # Strategy 1: Look for matching test file
        source_name = Path(file_path).stem
        test_patterns = [
            f"test_{source_name}.py",
            f"{source_name}_test.py",
            f"tests/test_{source_name}.py",
            f"tests/{source_name}_test.py",
        ]
        
        found_tests = []
        for pattern in test_patterns:
            full_path = os.path.join(self.project_root, pattern)
            if os.path.exists(full_path):
                found_tests.append(full_path)
        
        # Strategy 2: Use Oracle for symbol-based discovery
        if not found_tests:
            from .oracle import extract_function_names, find_related_tests
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            symbols = extract_function_names(content, "python")
            for symbol in symbols[:5]:  # Limit to avoid too many searches
                tests = find_related_tests(symbol, self.project_root)
                found_tests.extend(tests)
            
            found_tests = list(set(found_tests))
        
        if not found_tests:
            logger.info(f"No tests found for file: {file_path}")
            return TestResult(
                status=TestStatus.NOT_RUN,
                passed=not self.fail_on_no_tests,
                error_message=f"No tests found for {Path(file_path).name}"
            )
        
        return self.run_test_files(found_tests)
    
    def verify_patch(
        self,
        file_path: str,
        changed_symbols: List[str],
        test_files: Optional[List[str]] = None
    ) -> PatchVerification:
        """
        Full verification pipeline for a patch.
        
        This is the main entry point for the patcher integration.
        
        Args:
            file_path: Path to the file being patched
            changed_symbols: Symbols affected by the patch
            test_files: Optional pre-discovered test files (from Oracle)
            
        Returns:
            PatchVerification with decision
        """
        # 1. Collect test files
        all_test_files = list(test_files or [])
        
        # 2. Also discover tests based on symbols
        for symbol in changed_symbols[:5]:
            from .oracle import find_related_tests
            symbol_tests = find_related_tests(symbol, self.project_root)
            all_test_files.extend(symbol_tests)
        
        all_test_files = list(set(all_test_files))
        
        # 3. Run tests
        if all_test_files:
            logger.info(f"Verifying patch: running {len(all_test_files)} test file(s)")
            test_result = self.run_test_files(all_test_files)
        else:
            # No tests - decide based on policy
            test_result = TestResult(
                status=TestStatus.NOT_RUN,
                passed=not self.fail_on_no_tests,
                error_message="No tests found for modified symbols"
            )
        
        # 4. Make decision
        should_apply = test_result.passed
        
        if test_result.status == TestStatus.PASSED:
            reason = f"All {test_result.passed_count} tests passed"
        elif test_result.status == TestStatus.NOT_RUN:
            if self.fail_on_no_tests:
                reason = "Rejected: No test coverage for this change"
                should_apply = False
            else:
                reason = "Allowed: No tests found (policy allows)"
                should_apply = True
        elif test_result.status == TestStatus.FAILED:
            reason = f"Rejected: {test_result.failed_count} tests failed"
            should_apply = False
        elif test_result.status == TestStatus.TIMEOUT:
            reason = "Rejected: Test execution timed out"
            should_apply = False
        else:
            reason = f"Rejected: Test error - {test_result.error_message}"
            should_apply = False
        
        return PatchVerification(
            test_result=test_result,
            files_tested=all_test_files,
            symbols_tested=changed_symbols,
            should_apply=should_apply,
            reason=reason
        )
    
    def _run_pytest(self, cmd_parts: List[str]) -> TestResult:
        """
        Execute pytest and parse results.
        
        Args:
            cmd_parts: Command as list of strings
            
        Returns:
            TestResult
        """
        start_time = time.time()
        
        try:
            logger.debug(f"Running: {' '.join(cmd_parts)}")
            
            process = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                cwd=self.project_root
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            output = process.stdout + "\n" + process.stderr
            
            # Parse results
            total, passed, failed, errors, failed_tests = parse_pytest_output(output)
            
            if process.returncode == 0:
                status = TestStatus.PASSED
                is_passed = True
            else:
                status = TestStatus.FAILED if failed > 0 else TestStatus.ERROR
                is_passed = False
            
            return TestResult(
                status=status,
                passed=is_passed,
                test_count=total,
                passed_count=passed,
                failed_count=failed,
                error_count=errors,
                duration_ms=duration_ms,
                output=output[-5000:],  # Truncate output
                failed_tests=failed_tests,
                error_message=None if is_passed else f"Exit code: {process.returncode}"
            )
            
        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start_time) * 1000)
            return TestResult(
                status=TestStatus.TIMEOUT,
                passed=False,
                duration_ms=duration_ms,
                error_message=f"Timeout after {self.timeout_seconds}s"
            )
            
        except FileNotFoundError as e:
            return TestResult(
                status=TestStatus.ERROR,
                passed=False,
                error_message=f"Command not found: {e}"
            )
            
        except Exception as e:
            logger.exception("Test execution failed")
            return TestResult(
                status=TestStatus.ERROR,
                passed=False,
                error_message=str(e)
            )
    
    def run_quick_sanity_check(self, file_path: str) -> TestResult:
        """
        Run a quick sanity check on a Python file.
        
        Just checks if the file can be imported without syntax/import errors.
        Much faster than running full tests.
        
        Args:
            file_path: Path to Python file
            
        Returns:
            TestResult
        """
        if not file_path.endswith('.py'):
            return TestResult(
                status=TestStatus.SKIPPED,
                passed=True,
                error_message="Not a Python file"
            )
        
        start_time = time.time()
        
        try:
            # Use py_compile for basic syntax check
            cmd = ["python", "-m", "py_compile", file_path]
            
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                cwd=self.project_root
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            if process.returncode == 0:
                return TestResult(
                    status=TestStatus.PASSED,
                    passed=True,
                    test_count=1,
                    passed_count=1,
                    duration_ms=duration_ms
                )
            else:
                return TestResult(
                    status=TestStatus.FAILED,
                    passed=False,
                    test_count=1,
                    failed_count=1,
                    duration_ms=duration_ms,
                    output=process.stderr,
                    error_message=process.stderr.strip()[:200]
                )
                
        except Exception as e:
            return TestResult(
                status=TestStatus.ERROR,
                passed=False,
                error_message=str(e)
            )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_immune_system(**kwargs) -> ImmuneSystem:
    """Factory function to create an ImmuneSystem instance."""
    return ImmuneSystem(**kwargs)


def quick_test_check(
    test_files: List[str],
    project_root: Optional[str] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Quick test check for simple use cases.
    
    Returns dict with pass/fail status.
    """
    immune = ImmuneSystem(
        project_root=project_root,
        timeout_seconds=timeout
    )
    result = immune.run_test_files(test_files)
    return result.to_dict()


def verify_before_patch(
    file_path: str,
    changed_symbols: List[str],
    test_files: Optional[List[str]] = None,
    project_root: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Quick verification check for use in patcher.py.
    
    Returns:
        Tuple of (should_apply, reason)
    """
    immune = ImmuneSystem(project_root=project_root)
    verification = immune.verify_patch(file_path, changed_symbols, test_files)
    return verification.should_apply, verification.reason
