"""
Sandboxed Python Executor for Governed Code Mode.

This module executes LLM-generated Python code in a restricted sandbox where:
1. All I/O is trapped and routed through MCPClientManager
2. Dangerous builtins (eval, exec, open, etc.) are removed
3. Skill modules can be imported (from skills import X)
4. Raw bindings are available (await filesystem.list_directory())

This is the "Zero-Trust Chassis" from the architecture.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any, Dict, List

from mcp_client.manager import MCPClientManager
from .bindings import create_bindings
from .skill_injector import load_skill_modules, create_import_handler

log = logging.getLogger("sandbox.executor")


# Safe builtins - explicitly allowlisted
# Excludes: eval, exec, compile, open, __import__, globals, locals, vars, dir, etc.
SAFE_BUILTINS: Dict[str, Any] = {
    # Constants
    'True': True,
    'False': False,
    'None': None,
    
    # Type constructors
    'bool': bool,
    'int': int,
    'float': float,
    'str': str,
    'list': list,
    'dict': dict,
    'set': set,
    'tuple': tuple,
    'bytes': bytes,
    'bytearray': bytearray,
    'frozenset': frozenset,
    
    # Iterators and generators
    'range': range,
    'enumerate': enumerate,
    'zip': zip,
    'map': map,
    'filter': filter,
    'reversed': reversed,
    'iter': iter,
    'next': next,
    
    # Math and comparison
    'abs': abs,
    'min': min,
    'max': max,
    'sum': sum,
    'round': round,
    'pow': pow,
    'divmod': divmod,
    
    # Sequence operations
    'len': len,
    'sorted': sorted,
    'all': all,
    'any': any,
    
    # String/repr
    'repr': repr,
    'ascii': ascii,
    'chr': chr,
    'ord': ord,
    'format': format,
    
    # Object introspection (safe subset)
    'isinstance': isinstance,
    'issubclass': issubclass,
    'type': type,
    'id': id,
    'hash': hash,
    'callable': callable,
    'hasattr': hasattr,
    'getattr': getattr,
    'setattr': setattr,
    
    # Printing (redirected to logging)
    'print': lambda *args, **kwargs: log.info(f"SANDBOX PRINT: {' '.join(str(a) for a in args)}"),
    
    # Exceptions (needed for try/except)
    'Exception': Exception,
    'ValueError': ValueError,
    'TypeError': TypeError,
    'KeyError': KeyError,
    'IndexError': IndexError,
    'AttributeError': AttributeError,
    'RuntimeError': RuntimeError,
    'StopIteration': StopIteration,
}


class SandboxExecutionError(Exception):
    """Raised when sandbox execution fails."""
    pass


async def execute_code_plan(
    mgr: MCPClientManager,
    code: str,
    allowed_servers: List[str]
) -> Any:
    """
    Execute LLM-generated Python code in a restricted sandbox.
    
    All I/O is trapped and routed through MCPClientManager.
    No dangerous operations (eval, open, import) are allowed.
    
    Args:
        mgr: The MCPClientManager for executing trapped calls
        code: The LLM-generated Python code (must define async main())
        allowed_servers: List of server prefixes allowed (e.g., ["filesystem", "memory"])
    
    Returns:
        The result of calling main()
    
    Raises:
        SandboxExecutionError: If execution fails
    
    Example:
        code = '''
        # PLAN: List files in current directory
        
        async def main():
            files = await filesystem.list_directory(path=".")
            return files
        '''
        result = await execute_code_plan(mgr, code, ["filesystem"])
    """
    log.info("=== SANDBOX EXECUTION START ===")
    log.info(f"Allowed servers: {allowed_servers}")
    log.debug(f"Code to execute:\n{code[:500]}...")
    
    # --- 1. Validate code structure ---
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        log.error(f"Syntax error in code: {e}")
        raise SandboxExecutionError(f"Code has syntax error: {e}")
    
    # Check that main() is defined
    has_main = False
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "main":
            has_main = True
            break
    
    if not has_main:
        log.error("Code does not define async main()")
        raise SandboxExecutionError("Code must define 'async def main()'")
    
    # --- 2. Create I/O trap function ---
    call_log: List[Dict[str, Any]] = []  # Audit log of all calls
    
    async def trap_io(qualified_name: str, args: Dict[str, Any]) -> Any:
        """
        Trap I/O calls and route to MCPClientManager.
        This is the Policy Enforcement Point.
        """
        log.info(f"I/O TRAP: {qualified_name}")
        
        # Record call for audit
        call_log.append({
            "tool": qualified_name,
            "args_keys": list(args.keys()),
        })
        
        # Build the action for MCPClientManager
        action = {
            "action_type": "tool",
            "action_name": qualified_name,
            "arguments": args
        }
        
        try:
            result = await mgr.execute_action(action)
            log.debug(f"I/O RESULT: {qualified_name} -> success")
            return result
        except Exception as e:
            log.error(f"I/O ERROR: {qualified_name} -> {type(e).__name__}: {e}")
            raise
    
    # --- 3. Create binding proxies ---
    bindings = create_bindings(allowed_servers, trap_io)
    log.info(f"Created {len(bindings)} binding proxies")
    
    # --- 3b. Load skill modules (with bindings injected) ---
    skills_dir = Path("skills")
    skills = load_skill_modules(skills_dir, bindings)
    log.info(f"Loaded skills namespace: {skills}")
    
    # Create custom import handler for skill imports
    skill_import = create_import_handler(skills)
    
    # --- 4. Build restricted globals ---
    # Include the skill import handler in builtins
    sandbox_builtins = SAFE_BUILTINS.copy()
    sandbox_builtins['__import__'] = skill_import
    
    restricted_globals: Dict[str, Any] = {
        "__builtins__": sandbox_builtins,
        "__name__": "__sandbox__",
        **bindings,  # Raw bindings (filesystem, memory, etc.)
        "skills": skills,  # Skill modules namespace
    }
    
    # --- 5. Execute the code ---
    try:
        log.info("Executing code in sandbox...")
        exec(code, restricted_globals)
    except Exception as e:
        log.error(f"Code execution failed: {type(e).__name__}: {e}")
        raise SandboxExecutionError(f"Code execution failed: {e}")
    
    # --- 6. Call main() ---
    main_fn = restricted_globals.get("main")
    if main_fn is None:
        log.error("main() not found after exec")
        raise SandboxExecutionError("main() function not found after execution")
    
    try:
        log.info("Calling main()...")
        result = await main_fn()
        log.info(f"main() returned: {type(result).__name__}")
    except Exception as e:
        log.error(f"main() raised: {type(e).__name__}: {e}")
        raise SandboxExecutionError(f"main() raised: {e}")
    
    # --- 7. Log audit trail ---
    log.info(f"=== SANDBOX EXECUTION COMPLETE ===")
    log.info(f"Total I/O calls: {len(call_log)}")
    for i, call in enumerate(call_log, 1):
        log.debug(f"  {i}. {call['tool']}({call['args_keys']})")
    
    return result


async def validate_code_safety(code: str) -> List[str]:
    """
    Quick safety validation before execution.
    Returns list of errors (empty if safe).
    
    This is a lightweight pre-check. The full CodeAuditor provides
    more detailed analysis including manifest derivation.
    """
    errors = []
    
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"Syntax error: {e}"]
    
    for node in ast.walk(tree):
        # Check for imports
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, 'module', '') or ''
            names = [a.name for a in getattr(node, 'names', [])]
            for name in [module] + names:
                if name:
                    errors.append(f"Imports not allowed: {name}")
        
        # Check for dangerous calls
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                fname = node.func.id
                if fname in {'eval', 'exec', 'compile', '__import__', 'open'}:
                    errors.append(f"Dangerous call not allowed: {fname}")
    
    return errors
