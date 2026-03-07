""" 
Skill Static Auditor (Gate 1)

Rejects skills that attempt raw IO, network, or process access outside bindings.

Configuration:
- By default, the analyzer uses a conservative denylist.
- You can override/extend rules with a JSON config file.
- Config path resolution order:
  1) CLI: --config <path>
  2) Env: MCP_SKILL_GATE_CONFIG
  3) Default: ./policy/skill_gate.json (if present)

Config JSON keys (all optional):
  forbidden_imports: string[]
  forbidden_calls: string[]
  forbidden_prefixes: string[]
  forbidden_attr_suffixes: string[]
  allowed_imports: string[]
  allowed_calls: string[]
  allowed_prefixes: string[]
  allowed_attr_suffixes: string[]
"""

from __future__ import annotations

import ast
import json
import os
import sys
from argparse import ArgumentParser
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional, Set, Tuple


DEFAULT_FORBIDDEN_IMPORTS = {
    "aiohttp",
    "requests",
    "httpx",
    "urllib",
    "urllib.request",
    "urllib3",
    "socket",
    "subprocess",
    "ftplib",
    "paramiko",
}

DEFAULT_FORBIDDEN_CALLS = {
    "open",
    "mcp.use",
}

DEFAULT_FORBIDDEN_ATTR_SUFFIXES = {
    ".open",
    ".read_text",
    ".write_text",
    ".read_bytes",
    ".write_bytes",
    ".mkdir",
    ".makedirs",
    ".remove",
    ".rmdir",
    ".unlink",
    ".rename",
}

DEFAULT_FORBIDDEN_PREFIXES = (
    "requests.",
    "httpx.",
    "urllib.",
    "socket.",
    "subprocess.",
    "ftplib.",
    "paramiko.",
    "os.system",
    "os.popen",
    "os.spawn",
    "os.exec",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "os.rename",
    "os.replace",
    "os.makedirs",
    "shutil.",
)


@dataclass
class SkillGateConfig:
    forbidden_imports: Set[str]
    forbidden_calls: Set[str]
    forbidden_prefixes: Tuple[str, ...]
    forbidden_attr_suffixes: Set[str]
    allowed_imports: Set[str]
    allowed_calls: Set[str]
    allowed_prefixes: Tuple[str, ...]
    allowed_attr_suffixes: Set[str]


def _load_config_from_path(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def load_skill_gate_config(config_path: Optional[str] = None) -> SkillGateConfig:
    config: dict = {}

    # 1) CLI arg
    if config_path:
        config = _load_config_from_path(Path(config_path))
    else:
        # 2) Env var
        env_path = os.environ.get("MCP_SKILL_GATE_CONFIG")
        if env_path:
            config = _load_config_from_path(Path(env_path))
        else:
            # 3) Default repo path
            default_path = Path.cwd() / "policy" / "skill_gate.json"
            config = _load_config_from_path(default_path)

    forbidden_imports = set(DEFAULT_FORBIDDEN_IMPORTS)
    forbidden_calls = set(DEFAULT_FORBIDDEN_CALLS)
    forbidden_prefixes = list(DEFAULT_FORBIDDEN_PREFIXES)
    forbidden_attr_suffixes = set(DEFAULT_FORBIDDEN_ATTR_SUFFIXES)

    allowed_imports: Set[str] = set()
    allowed_calls: Set[str] = set()
    allowed_prefixes: List[str] = []
    allowed_attr_suffixes: Set[str] = set()

    if isinstance(config.get("forbidden_imports"), list):
        forbidden_imports = set(str(x) for x in config["forbidden_imports"])
    if isinstance(config.get("forbidden_calls"), list):
        forbidden_calls = set(str(x) for x in config["forbidden_calls"])
    if isinstance(config.get("forbidden_prefixes"), list):
        forbidden_prefixes = [str(x) for x in config["forbidden_prefixes"]]
    if isinstance(config.get("forbidden_attr_suffixes"), list):
        forbidden_attr_suffixes = set(str(x) for x in config["forbidden_attr_suffixes"])

    if isinstance(config.get("allowed_imports"), list):
        allowed_imports = set(str(x) for x in config["allowed_imports"])
    if isinstance(config.get("allowed_calls"), list):
        allowed_calls = set(str(x) for x in config["allowed_calls"])
    if isinstance(config.get("allowed_prefixes"), list):
        allowed_prefixes = [str(x) for x in config["allowed_prefixes"]]
    if isinstance(config.get("allowed_attr_suffixes"), list):
        allowed_attr_suffixes = set(str(x) for x in config["allowed_attr_suffixes"])

    return SkillGateConfig(
        forbidden_imports=forbidden_imports,
        forbidden_calls=forbidden_calls,
        forbidden_prefixes=tuple(forbidden_prefixes),
        forbidden_attr_suffixes=forbidden_attr_suffixes,
        allowed_imports=allowed_imports,
        allowed_calls=allowed_calls,
        allowed_prefixes=tuple(allowed_prefixes),
        allowed_attr_suffixes=allowed_attr_suffixes,
    )


@dataclass
class SkillAuditResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "errors": self.errors,
            "warnings": self.warnings,
            "allowed": len(self.errors) == 0,
        }


class SkillAuditVisitor(ast.NodeVisitor):
    def __init__(self, config: SkillGateConfig) -> None:
        self.errors: List[str] = []
        self._config = config

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.name
            if self._is_forbidden_import(name):
                self.errors.append(f"Line {node.lineno}: Forbidden import '{name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if self._is_forbidden_import(module):
            self.errors.append(f"Line {node.lineno}: Forbidden import '{module}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call_name = self._resolve_call_name(node.func)
        if call_name:
            if self._is_allowed_call(call_name):
                self.generic_visit(node)
                return

            if call_name in self._config.forbidden_calls:
                self.errors.append(f"Line {node.lineno}: Forbidden call '{call_name}'")
            for prefix in self._config.forbidden_prefixes:
                if call_name.startswith(prefix):
                    self.errors.append(f"Line {node.lineno}: Forbidden call '{call_name}'")
                    break
            for suffix in self._config.forbidden_attr_suffixes:
                if call_name.endswith(suffix):
                    self.errors.append(f"Line {node.lineno}: Forbidden call '{call_name}'")
                    break
        self.generic_visit(node)

    def _is_forbidden_import(self, module: str) -> bool:
        if self._is_allowed_import(module):
            return False

        if module in self._config.forbidden_imports:
            return True
        return any(module.startswith(f"{name}.") for name in self._config.forbidden_imports)

    def _is_allowed_import(self, module: str) -> bool:
        if not self._config.allowed_imports:
            return False
        if module in self._config.allowed_imports:
            return True
        return any(module.startswith(f"{name}.") for name in self._config.allowed_imports)

    def _is_allowed_call(self, call_name: str) -> bool:
        if call_name in self._config.allowed_calls:
            return True
        for prefix in self._config.allowed_prefixes:
            if call_name.startswith(prefix):
                return True
        for suffix in self._config.allowed_attr_suffixes:
            if call_name.endswith(suffix):
                return True
        return False

    def _resolve_call_name(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parts = []
            current: Optional[ast.AST] = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
                return ".".join(reversed(parts))
        return None


def analyze_skill(code: str, config: SkillGateConfig) -> SkillAuditResult:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return SkillAuditResult(errors=[f"Syntax error: {exc}"])

    visitor = SkillAuditVisitor(config)
    visitor.visit(tree)
    return SkillAuditResult(errors=visitor.errors)


def main() -> None:
    parser = ArgumentParser(add_help=False)
    parser.add_argument("--config", dest="config", default=None)
    args, _ = parser.parse_known_args()

    config = load_skill_gate_config(args.config)
    code = sys.stdin.read()
    result = analyze_skill(code, config)
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
