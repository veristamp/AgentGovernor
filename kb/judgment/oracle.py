# judgment/oracle.py
"""
Impact Oracle - Blast radius analysis for code changes.

This is the third layer of "Senior Engineer in a Box":
- "What else depends on this?"
- "What will break if I change this?"
- "What tests cover this code?"

This is what separates a senior engineer from a junior:
they always ask about impact BEFORE making changes.

Usage:
    from judgment.oracle import ImpactOracle
    
    oracle = ImpactOracle()
    report = await oracle.analyze_impact(file_path, chunk_metadata, new_content)
    
    print(f"Risk: {report.risk_level}")
    print(f"Files affected: {len(report.affected_files)}")
    for caller in report.callers:
        print(f"  - {caller.file}:{caller.line} calls {caller.symbol}")
"""

import asyncio
import subprocess
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple

from config import get_logger

logger = get_logger("Oracle")


# =============================================================================
# ENUMS AND DATACLASSES
# =============================================================================

class RiskLevel(Enum):
    """Risk level of a code change."""
    LOW = "low"          # Internal function, few callers
    MEDIUM = "medium"    # Some callers, tests exist
    HIGH = "high"        # Many callers, public API
    CRITICAL = "critical"  # Core infrastructure, no tests


@dataclass
class Caller:
    """A location that calls/imports the target symbol."""
    file: str
    line: int
    symbol: str
    context: str = ""  # The line of code
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "symbol": self.symbol,
            "context": self.context[:100] if self.context else "",
        }


@dataclass 
class TestCoverage:
    """Test coverage information for a code region."""
    test_files: List[str] = field(default_factory=list)
    test_count: int = 0
    coverage_pct: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_files": self.test_files[:10],  # Limit for display
            "test_count": self.test_count,
            "coverage_pct": self.coverage_pct,
        }


@dataclass
class ImpactReport:
    """Complete impact analysis report."""
    risk_level: RiskLevel
    affected_files: List[str] = field(default_factory=list)
    callers: List[Caller] = field(default_factory=list)
    importers: List[str] = field(default_factory=list)  # Files that import this module
    tests: TestCoverage = field(default_factory=TestCoverage)
    symbols_changed: List[str] = field(default_factory=list)
    is_public_api: bool = False
    is_exported: bool = False
    warnings: List[str] = field(default_factory=list)
    
    @property
    def caller_count(self) -> int:
        return len(self.callers)
    
    @property
    def summary(self) -> str:
        """Generate a human-readable summary."""
        lines = [
            f"Risk Level: {self.risk_level.value.upper()}",
            f"Files Affected: {len(self.affected_files)}",
            f"Direct Callers: {self.caller_count}",
            f"Importers: {len(self.importers)}",
            f"Test Files: {self.tests.test_count}",
        ]
        
        if self.is_public_api:
            lines.append("⚠️ PUBLIC API - Breaking change risk")
        
        if self.caller_count > 0:
            lines.append("\nTop Callers:")
            for caller in self.callers[:5]:
                lines.append(f"  {caller.file}:{caller.line}")
        
        if self.warnings:
            lines.append("\nWarnings:")
            for w in self.warnings:
                lines.append(f"  ⚠️ {w}")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_level": self.risk_level.value,
            "affected_files": self.affected_files[:20],
            "callers": [c.to_dict() for c in self.callers[:20]],
            "importers": self.importers[:20],
            "tests": self.tests.to_dict(),
            "symbols_changed": self.symbols_changed,
            "is_public_api": self.is_public_api,
            "is_exported": self.is_exported,
            "warnings": self.warnings,
            "caller_count": self.caller_count,
            "summary": self.summary,
        }


# =============================================================================
# SYMBOL EXTRACTION
# =============================================================================

def extract_function_names(content: str, language: str = "python") -> List[str]:
    """Extract function/method names from code content."""
    functions = []
    
    if language in ("python", "py"):
        # Python: def function_name(
        pattern = r'\bdef\s+(\w+)\s*\('
        functions.extend(re.findall(pattern, content))
        
        # Python: class ClassName
        pattern = r'\bclass\s+(\w+)'
        functions.extend(re.findall(pattern, content))
    
    elif language in ("javascript", "typescript", "js", "ts"):
        # JS: function name(, const name = (, name: function(
        patterns = [
            r'\bfunction\s+(\w+)\s*\(',
            r'\bconst\s+(\w+)\s*=\s*(?:async\s*)?\(',
            r'\b(\w+)\s*:\s*(?:async\s*)?function',
            r'\bclass\s+(\w+)',
        ]
        for pattern in patterns:
            functions.extend(re.findall(pattern, content))
    
    elif language in ("go",):
        # Go: func Name(
        pattern = r'\bfunc\s+(\w+)\s*\('
        functions.extend(re.findall(pattern, content))
    
    elif language in ("rust", "rs"):
        # Rust: fn name(, pub fn name(
        pattern = r'\bfn\s+(\w+)\s*[<(]'
        functions.extend(re.findall(pattern, content))
    
    # Deduplicate while preserving order
    seen = set()
    return [f for f in functions if f not in seen and not seen.add(f)]


def extract_class_names(content: str, language: str = "python") -> List[str]:
    """Extract class names from code content."""
    classes = []
    
    if language in ("python", "py"):
        pattern = r'\bclass\s+(\w+)'
        classes.extend(re.findall(pattern, content))
    
    elif language in ("javascript", "typescript", "js", "ts"):
        patterns = [
            r'\bclass\s+(\w+)',
            r'\binterface\s+(\w+)',
            r'\btype\s+(\w+)\s*=',
        ]
        for pattern in patterns:
            classes.extend(re.findall(pattern, content))
    
    return list(set(classes))


# =============================================================================
# RIPGREP INTEGRATION
# =============================================================================

def run_ripgrep(
    pattern: str,
    search_path: str,
    file_types: Optional[List[str]] = None,
    max_results: int = 50
) -> List[Tuple[str, int, str]]:
    """
    Run ripgrep to find pattern matches.
    
    Returns list of (file, line_number, context) tuples.
    """
    cmd = ["rg", "--json", "-n", pattern, search_path]
    
    if file_types:
        for ft in file_types:
            cmd.extend(["--type", ft])
    
    cmd.extend(["--max-count", str(max_results)])
    
    results = []
    
    try:
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30  # Prevent hanging
        )
        
        import json
        for line in process.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "match":
                    match_data = data.get("data", {})
                    path = match_data.get("path", {}).get("text", "")
                    line_number = match_data.get("line_number", 0)
                    lines = match_data.get("lines", {})
                    context = lines.get("text", "").strip() if isinstance(lines, dict) else str(lines).strip()
                    
                    results.append((path, line_number, context))
                    
                    if len(results) >= max_results:
                        break
            except json.JSONDecodeError:
                continue
                
    except subprocess.TimeoutExpired:
        logger.warning("Ripgrep timed out")
    except FileNotFoundError:
        logger.warning("Ripgrep not found, falling back to basic search")
    except Exception as e:
        logger.warning(f"Ripgrep failed: {e}")
    
    return results


def find_callers_with_ripgrep(
    symbol_name: str,
    search_path: str,
    file_types: Optional[List[str]] = None
) -> List[Caller]:
    """Find all locations that call a function/method."""
    # Search for function calls: symbol_name(
    pattern = rf'\b{re.escape(symbol_name)}\s*\('
    
    results = run_ripgrep(pattern, search_path, file_types)
    
    callers = []
    for file, line, context in results:
        callers.append(Caller(
            file=file,
            line=line,
            symbol=symbol_name,
            context=context
        ))
    
    return callers


def find_importers_with_ripgrep(
    module_name: str,
    search_path: str
) -> List[str]:
    """Find all files that import a module."""
    patterns = [
        rf'import\s+{re.escape(module_name)}',
        rf'from\s+{re.escape(module_name)}\s+import',
        rf'require\(["\'].*{re.escape(module_name)}["\']',
    ]
    
    importers = set()
    
    for pattern in patterns:
        results = run_ripgrep(pattern, search_path)
        for file, _, _ in results:
            importers.add(file)
    
    return list(importers)


def find_related_tests(
    symbol_name: str,
    search_path: str
) -> List[str]:
    """Find test files that might cover a symbol."""
    # Search in test directories
    test_patterns = [
        rf'def test_.*{re.escape(symbol_name.lower())}',
        rf'it\(["\'].*{re.escape(symbol_name)}',
        rf'{re.escape(symbol_name)}\(',  # Direct usage in tests
    ]
    
    test_files = set()
    
    for pattern in test_patterns:
        results = run_ripgrep(pattern, search_path)
        for file, _, _ in results:
            # Only include files that look like tests
            if "test" in file.lower() or "spec" in file.lower():
                test_files.add(file)
    
    return list(test_files)


# =============================================================================
# IMPACT ORACLE CLASS
# =============================================================================

class ImpactOracle:
    """
    Analyzes the impact of code changes.
    
    Answers:
    - Who calls this function?
    - Who imports this module?
    - What tests cover this?
    - Is this a public API?
    - What's the blast radius?
    """
    
    def __init__(
        self,
        project_root: Optional[str] = None,
        pg_session: Optional[Any] = None,
        qdrant_client: Optional[Any] = None
    ):
        """
        Initialize the oracle.
        
        Args:
            project_root: Root directory for ripgrep searches
            pg_session: Optional Postgres session for graph queries
            qdrant_client: Optional Qdrant client for semantic search
        """
        self.project_root = project_root or os.getcwd()
        self.pg_session = pg_session
        self.qdrant_client = qdrant_client
    
    def _get_language(self, file_path: str) -> str:
        """Get language from file extension."""
        ext = Path(file_path).suffix.lower().lstrip(".")
        ext_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "tsx": "typescript",
            "jsx": "javascript",
            "go": "go",
            "rs": "rust",
        }
        return ext_map.get(ext, "python")
    
    def _detect_public_api(self, file_path: str, content: str) -> bool:
        """Detect if the code is part of a public API."""
        # Check file location
        path_lower = file_path.lower()
        
        # Public API indicators
        public_patterns = [
            "/api/", "/routes/", "/endpoints/",
            "server.py", "app.py", "main.py",
            "__init__.py",
            "/public/", "/exports/",
        ]
        
        if any(p in path_lower for p in public_patterns):
            return True
        
        # Check for export statements
        content_lower = content.lower()
        if any(kw in content_lower for kw in ["__all__", "export default", "export {", "@app.route", "@router."]):
            return True
        
        return False
    
    def _detect_exported(self, file_path: str, content: str) -> bool:
        """Detect if symbols are exported from package."""
        # Check if file is __init__.py
        if file_path.endswith("__init__.py"):
            return True
        
        # Check for __all__
        if "__all__" in content:
            return True
        
        # Check for export statements (JS/TS)
        if re.search(r'\bexport\s+(default|{)', content):
            return True
        
        return False
    
    def analyze_impact(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
        chunk_metadata: Optional[Dict[str, Any]] = None
    ) -> ImpactReport:
        """
        Analyze the impact of a code change.
        
        Args:
            file_path: Path to the file being changed
            old_content: Original content
            new_content: New content after patch
            chunk_metadata: Optional chunk context
            
        Returns:
            ImpactReport with blast radius analysis
        """
        language = self._get_language(file_path)
        
        # 1. Extract symbols being changed
        old_symbols = set(extract_function_names(old_content, language))
        new_symbols = set(extract_function_names(new_content, language))
        
        # Symbols that are modified or removed
        changed_symbols = old_symbols  # Assume all old symbols are potentially affected
        removed_symbols = old_symbols - new_symbols
        
        symbols_list = list(changed_symbols)
        
        # 2. Find callers for each changed symbol
        all_callers: List[Caller] = []
        affected_files: Set[str] = set()
        
        for symbol in changed_symbols:
            if len(symbol) < 3:  # Skip very short names (likely noise)
                continue
                
            callers = find_callers_with_ripgrep(
                symbol,
                self.project_root,
                file_types=["py", "js", "ts", "go", "rust"]  # Note: 'rust' not 'rs'
            )
            
            # Filter out the source file itself
            callers = [c for c in callers if not c.file.endswith(Path(file_path).name)]
            
            all_callers.extend(callers)
            affected_files.update(c.file for c in callers)
        
        # 3. Find importers of this module
        module_name = Path(file_path).stem
        importers = find_importers_with_ripgrep(module_name, self.project_root)
        importers = [i for i in importers if i != file_path]
        affected_files.update(importers)
        
        # 4. Find related tests
        test_files = []
        for symbol in symbols_list[:5]:  # Limit to avoid too many searches
            tests = find_related_tests(symbol, self.project_root)
            test_files.extend(tests)
        test_files = list(set(test_files))
        
        # 5. Detect public API
        is_public = self._detect_public_api(file_path, old_content)
        is_exported = self._detect_exported(file_path, old_content)
        
        # 6. Build warnings
        warnings = []
        
        if removed_symbols:
            warnings.append(f"Removing symbols: {', '.join(removed_symbols)}")
        
        if is_public and changed_symbols:
            warnings.append("Modifying public API - potential breaking change")
        
        if len(all_callers) > 10:
            warnings.append(f"High caller count ({len(all_callers)}) - test thoroughly")
        
        if not test_files:
            warnings.append("No tests found for modified symbols")
        
        # 7. Calculate risk level
        risk = self._calculate_risk(
            caller_count=len(all_callers),
            importer_count=len(importers),
            test_count=len(test_files),
            is_public=is_public,
            has_removed_symbols=bool(removed_symbols)
        )
        
        return ImpactReport(
            risk_level=risk,
            affected_files=list(affected_files),
            callers=all_callers,
            importers=importers,
            tests=TestCoverage(
                test_files=test_files,
                test_count=len(test_files)
            ),
            symbols_changed=symbols_list,
            is_public_api=is_public,
            is_exported=is_exported,
            warnings=warnings
        )
    
    def _calculate_risk(
        self,
        caller_count: int,
        importer_count: int,
        test_count: int,
        is_public: bool,
        has_removed_symbols: bool
    ) -> RiskLevel:
        """Calculate overall risk level."""
        score = 0
        
        # Caller count
        if caller_count > 20:
            score += 3
        elif caller_count > 5:
            score += 2
        elif caller_count > 0:
            score += 1
        
        # Importer count
        if importer_count > 10:
            score += 2
        elif importer_count > 0:
            score += 1
        
        # Public API
        if is_public:
            score += 2
        
        # Removed symbols
        if has_removed_symbols:
            score += 2
        
        # No tests - higher risk
        if test_count == 0 and (caller_count > 0 or is_public):
            score += 2
        
        # Determine level
        if score >= 7:
            return RiskLevel.CRITICAL
        elif score >= 5:
            return RiskLevel.HIGH
        elif score >= 3:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    async def analyze_impact_async(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
        chunk_metadata: Optional[Dict[str, Any]] = None
    ) -> ImpactReport:
        """Async version of analyze_impact (for FastAPI integration)."""
        # Run the sync version in a thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.analyze_impact(file_path, old_content, new_content, chunk_metadata)
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_oracle(
    project_root: Optional[str] = None,
    **kwargs
) -> ImpactOracle:
    """Factory function to create an ImpactOracle instance."""
    return ImpactOracle(project_root=project_root, **kwargs)


def quick_impact_check(
    file_path: str,
    old_content: str,
    new_content: str
) -> Dict[str, Any]:
    """
    Quick impact check for simple use cases.
    
    Returns dict with risk level and summary.
    """
    oracle = ImpactOracle()
    report = oracle.analyze_impact(file_path, old_content, new_content)
    return report.to_dict()
