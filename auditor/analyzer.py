"""
Static Auditor for Governed Code Mode (GATE 1)

This module performs pre-execution analysis of LLM-generated Python code to:
1. Parse the AST and extract all MCP tool calls
2. Build a manifest of what the code WILL do
3. Check the manifest against policy BEFORE execution
4. REJECT code that would violate policy

This is the first line of defense - code is never executed if it fails here.
"""

import ast
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"


@dataclass
class ToolCall:
    """Represents a discovered tool call in the code."""
    tool: str
    line: int
    col: int
    static_args: Dict[str, Any] = field(default_factory=dict)
    dynamic_args: List[str] = field(default_factory=list)


@dataclass
class Manifest:
    """The derived manifest from static analysis."""
    tools: List[str]
    skills: List[str]
    tool_calls: List[ToolCall]
    has_loops: bool
    has_conditionals: bool
    max_depth: int
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tools": self.tools,
            "skills": self.skills,
            "tool_calls": [asdict(tc) for tc in self.tool_calls],
            "has_loops": self.has_loops,
            "has_conditionals": self.has_conditionals,
            "max_depth": self.max_depth,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class MCPCallVisitor(ast.NodeVisitor):
    """
    AST visitor that extracts all mcp.use() calls.
    
    Looks for patterns like:
        await mcp.use("tool.name", arg1=value1, arg2=value2)
    """
    
    def __init__(self):
        self.tool_calls: List[ToolCall] = []
        self.has_loops = False
        self.has_conditionals = False
        self.max_depth = 0
        self._current_depth = 0
        self.errors: List[str] = []
        self.warnings: List[str] = []
        # Map variable name -> kebab-case skill id from skills.load("...")
        self._skill_vars: Dict[str, str] = {}

    def visit_Assign(self, node: ast.Assign) -> Any:
        skill_id = self._extract_loaded_skill_id(node.value)
        if skill_id:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._skill_vars[target.id] = skill_id
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        skill_id = self._extract_loaded_skill_id(node.value)
        if skill_id and isinstance(node.target, ast.Name):
            self._skill_vars[node.target.id] = skill_id
        self.generic_visit(node)
    
    def visit_For(self, node: ast.For) -> Any:
        self.has_loops = True
        self._current_depth += 1
        self.max_depth = max(self.max_depth, self._current_depth)
        self.generic_visit(node)
        self._current_depth -= 1
    
    def visit_While(self, node: ast.While) -> Any:
        self.has_loops = True
        self._current_depth += 1
        self.max_depth = max(self.max_depth, self._current_depth)
        self.generic_visit(node)
        self._current_depth -= 1
    
    def visit_If(self, node: ast.If) -> Any:
        self.has_conditionals = True
        self._current_depth += 1
        self.max_depth = max(self.max_depth, self._current_depth)
        self.generic_visit(node)
        self._current_depth -= 1
    
    def visit_Await(self, node: ast.Await) -> Any:
        """Check if this is an await mcp.use(...) call."""
        if isinstance(node.value, ast.Call):
            self._check_mcp_call(node.value)
        self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call) -> Any:
        """Also check direct calls (in case await is implicit)."""
        self._check_mcp_call(node)
        self.generic_visit(node)
    
    def _check_mcp_call(self, node: ast.Call) -> None:
        """
        Check if this call is:
        1. mcp.use("tool.name", ...) - direct tool call
        2. skill.method(...) - skill call (e.g., filesystem.list_files)
        """
        if not isinstance(node.func, ast.Attribute):
            return
        
        # Pattern 1: mcp.use("tool.name", ...) (blocked in skills-only mode)
        if node.func.attr == 'use' and isinstance(node.func.value, ast.Name) and node.func.value.id == 'mcp':
            self.errors.append(
                f"Line {node.lineno}: Direct mcp.use() calls are not allowed in skills-only mode"
            )
            self._extract_mcp_use(node)
            return
        
        # Pattern 2: skill.method(...) via either:
        # - await skillVar.method(...) where skillVar was bound from skills.load("...")
        # - await skills.load("...").method(...)
        base_expr = node.func.value
        base_name: Optional[str] = None
        if isinstance(base_expr, ast.Name):
            base_name = base_expr.id
        elif isinstance(base_expr, ast.Call):
            base_name = self._extract_loaded_skill_id(base_expr)
        if base_name is not None:
            method_name = node.func.attr
            
            # Skip common non-skill modules
            if base_name in ('mcp', 'skills', 'asyncio', 'json', 'os', 'sys', 'print', 'str', 'int', 'list', 'dict'):
                return
            
            # This looks like a skill call
            skill_id = self._skill_vars.get(base_name, base_name)
            tool_name = f"{skill_id}.{method_name}"
            
            # Extract arguments
            static_args, dynamic_args = self._extract_args(node)
            
            self.tool_calls.append(ToolCall(
                tool=tool_name,
                line=node.lineno,
                col=node.col_offset,
                static_args=static_args,
                dynamic_args=dynamic_args,
            ))

    def _extract_loaded_skill_id(self, node: Optional[ast.AST]) -> Optional[str]:
        """Detect `var = skills.load("repo-insight")` style bindings."""
        if not isinstance(node, ast.Call):
            return None
        if not isinstance(node.func, ast.Attribute):
            return None
        if not (isinstance(node.func.value, ast.Name) and node.func.value.id == 'skills'):
            return None
        if node.func.attr not in ('load', 'get'):
            return None

        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            return node.args[0].value

        for kw in node.keywords:
            if kw.arg in ('name', 'skill', 'skill_id', 'skillId') and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value

        return None
    
    def _extract_mcp_use(self, node: ast.Call) -> None:
        """Extract tool info from mcp.use() call."""
        if not node.args:
            self.errors.append(f"Line {node.lineno}: mcp.use() missing tool name argument")
            return
        
        tool_arg = node.args[0]
        
        # Extract tool name (ast.Constant is used for all literals in Python 3.8+)
        if isinstance(tool_arg, ast.Constant) and isinstance(tool_arg.value, str):
            tool_name = tool_arg.value
        else:
            # Dynamic tool name - can't statically analyze
            self.warnings.append(
                f"Line {node.lineno}: Dynamic tool name cannot be statically analyzed"
            )
            tool_name = "__dynamic__"
        
        # Extract arguments
        static_args, dynamic_args = self._extract_args(node)
        
        self.tool_calls.append(ToolCall(
            tool=tool_name,
            line=node.lineno,
            col=node.col_offset,
            static_args=static_args,
            dynamic_args=dynamic_args,
        ))
    
    def _extract_args(self, node: ast.Call) -> tuple:
        """Extract static and dynamic arguments from a call."""
        static_args: Dict[str, Any] = {}
        dynamic_args: List[str] = []
        
        for keyword in node.keywords:
            if keyword.arg is None:
                # **kwargs - can't analyze
                dynamic_args.append("**kwargs")
                continue
            
            value = self._extract_value(keyword.value)
            if value is not None:
                static_args[keyword.arg] = value
            else:
                dynamic_args.append(keyword.arg)
        
        return static_args, dynamic_args
    
    def _extract_value(self, node: ast.expr) -> Optional[Any]:
        """
        Try to extract a static value from an AST node.
        Returns None if the value is dynamic.
        
        Note: Python 3.8+ uses ast.Constant for all literals (str, num, bool, None).
        """
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.List):
            values = [self._extract_value(el) for el in node.elts]
            if None in values:
                return None
            return values
        elif isinstance(node, ast.Dict):
            keys = [self._extract_value(k) if k else None for k in node.keys]
            values = [self._extract_value(v) for v in node.values]
            if None in keys or None in values:
                return None
            return dict(zip(keys, values))
        else:
            # Dynamic value (variables, function calls, etc.)
            return None


def analyze_code(code: str) -> Manifest:
    """
    Analyze Python code and extract a manifest of what it will do.
    
    Args:
        code: Python source code
    
    Returns:
        Manifest with extracted tool calls and metadata
    """
    errors: List[str] = []
    
    # Parse the code
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return Manifest(
            tools=[],
            skills=[],
            tool_calls=[],
            has_loops=False,
            has_conditionals=False,
            max_depth=0,
            errors=[f"Syntax error: {e}"],
        )
    
    # Check for async def main()
    has_main = False
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "main":
            has_main = True
            break
    
    if not has_main:
        errors.append("Code must define 'async def main()'")
    
    # Visit the AST to extract MCP calls
    visitor = MCPCallVisitor()
    visitor.visit(tree)
    
    # Extract unique tool names
    tools = list(set(tc.tool for tc in visitor.tool_calls if tc.tool != "__dynamic__"))

    skill_refs = []
    for tool in tools:
        if tool.count('.') == 1:
            skill_id = tool.split('.', 1)[0]
            manifest_path = SKILLS_DIR / skill_id / "manifest.json"
            if not manifest_path.exists():
                errors.append(f"Skill manifest not found for '{skill_id}'")
                continue
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"Invalid manifest.json for skill '{skill_id}': {exc}")
                continue
            if not isinstance(manifest_data, dict):
                errors.append(f"Manifest for skill '{skill_id}' must be a JSON object")
                continue
            manifest_skill_id = str(manifest_data.get("skillId", skill_id))
            manifest_version = str(manifest_data.get("version", 1))
            skill_refs.append(f"skills:{manifest_skill_id}@{manifest_version}")

    if not visitor.tool_calls:
        errors.append("No skills invoked. Workflows must call skills (not raw tools).")


    # Combine errors
    all_errors = errors + visitor.errors
    
    return Manifest(
        tools=sorted(tools),
        skills=sorted(set(skill_refs)),

        tool_calls=visitor.tool_calls,
        has_loops=visitor.has_loops,
        has_conditionals=visitor.has_conditionals,
        max_depth=visitor.max_depth,
        errors=all_errors,
        warnings=visitor.warnings,
    )

def check_manifest_policy(
    manifest: Manifest,
    allowed_skills: Set[str],
    max_loop_depth: int = 5,
) -> List[str]:
    """
    Check if a manifest violates policy.

    Args:
        manifest: The extracted manifest
        allowed_skills: Set of skill names this identity can use
        max_loop_depth: Maximum allowed loop nesting

    Returns:
        List of policy violations (empty if OK)
    """
    violations: List[str] = []

    # Check for syntax/parse errors
    if manifest.errors:
        violations.extend(manifest.errors)

    # Check each skill against allowed list
    for skill in manifest.skills:
        if skill not in allowed_skills:
            violations.append(f"Skill '{skill}' is not allowed for this identity")

    # Check loop depth
    if manifest.max_depth > max_loop_depth:
        violations.append(
            f"Loop nesting depth ({manifest.max_depth}) exceeds maximum ({max_loop_depth})"
        )

    # Check for dynamic tool names (security risk)
    for tc in manifest.tool_calls:
        if tc.tool == "__dynamic__":
            violations.append(
                f"Line {tc.line}: Dynamic tool names are not allowed"
            )

    return violations

# ==================== CLI ====================

def main():
    """CLI for testing the static auditor."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Static Auditor for Governed Code Mode")
    parser.add_argument("file", nargs="?", help="Python file to analyze (or stdin if omitted)")
    parser.add_argument("--allowed", "-a", nargs="*", default=[], help="Allowed skill names")

    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    # Read code
    if args.file:
        with open(args.file, 'r') as f:
            code = f.read()
    else:
        code = sys.stdin.read()
    
    # Analyze
    manifest = analyze_code(code)
    
    # Check policy if allowed skills specified
    violations = []
    if args.allowed:
        violations = check_manifest_policy(manifest, set(args.allowed))
    
    # Output
    if args.json:
        output = {
            "manifest": manifest.to_dict(),
            "violations": violations,
            "allowed": len(violations) == 0,
        }
        print(json.dumps(output, indent=2))
    else:
        print("=== MANIFEST ===")
        print(f"Skills: {manifest.skills}")
        print(f"Tool calls: {len(manifest.tool_calls)}")
        print(f"Has loops: {manifest.has_loops}")
        print(f"Has conditionals: {manifest.has_conditionals}")
        print(f"Max depth: {manifest.max_depth}")
        
        if manifest.errors:
            print(f"\nErrors: {manifest.errors}")
        if manifest.warnings:
            print(f"Warnings: {manifest.warnings}")
        
        if violations:
            print(f"\n=== POLICY VIOLATIONS ===")
            for v in violations:
                print(f"  - {v}")
            sys.exit(1)
        elif args.allowed:
            print("\n=== POLICY CHECK: PASSED ===")


if __name__ == "__main__":
    main()
