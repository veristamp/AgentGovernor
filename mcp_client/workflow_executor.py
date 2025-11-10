# workflow_executor.py
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
from copy import deepcopy
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Union, Set

import yaml

from mcp_client.config import Config
from mcp_client.manager import MCPClientManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s workflow :: %(message)s"
)
log = logging.getLogger("workflow")

Json = Union[dict, list, str, int, float, bool, None]


# ------------------------ small helpers ------------------------

_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_\.]*)\}")

def _deep_interpolate(value: Any, vars: Mapping[str, Any]) -> Any:
    """
    Walk value (str/list/dict) and replace ${var} with vars[var].
    Supports dotted paths like ${vars.my_var}, ${env.OS},
    and ${steps.step_id.output}.
    """
    def _get_path(path: str, scope: Mapping[str, Any]) -> Any:
        cur: Any = scope
        for part in path.split("."):
            if isinstance(cur, Mapping) and part in cur:
                cur = cur[part]
            else:
                return None
        return cur

    if isinstance(value, str):
        def repl(m: re.Match) -> str:
            key = m.group(1)
            v = _get_path(key, vars)
            return "" if v is None else str(v)
        return _VAR_PATTERN.sub(repl, value)
    elif isinstance(value, list):
        return [_deep_interpolate(v, vars) for v in value]
    elif isinstance(value, dict):
        return {k: _deep_interpolate(v, vars) for k, v in value.items()}
    else:
        return value


def _is_truthy(v: Any) -> bool:
    if isinstance(v, str):
        return v.lower() not in {"", "false", "0", "no", "none", "null"}
    return bool(v)


# ------------------------ expression engine ------------------------

def eval_expr(expr: Any, vars: Mapping[str, Any]) -> Any:
    """
    Tiny expression evaluator for logic blocks.

    Supported forms (examples):
      - literals: true/false, numbers, strings
      - {"var": "name"}                     -> variables by name (dotted ok)
      - {"equals": [a, b]}
      - {"contains": [list_or_str, item_or_substr]}
      - {"gt": [a, b]}, {"lt": [a, b]}, {"ge": [a, b]}, {"le": [a, b]}
      - {"and": [e1, e2, ...]}, {"or": [e1, e2, ...]}, {"not": e}
      - strings can include ${var} which are interpolated before compare
    """
    def get_var(path: str) -> Any:
        cur: Any = vars
        for part in path.split("."):
            if isinstance(cur, Mapping) and part in cur:
                cur = cur[part]
            else:
                return None
        return cur

    if isinstance(expr, (str, int, float, bool)) or expr is None:
        return _deep_interpolate(expr, vars)

    if isinstance(expr, list):
        return [_deep_interpolate(v, vars) for v in expr]

    if not isinstance(expr, dict) or not expr:
        return expr

    # single-key operators
    if "var" in expr:
        return get_var(str(expr["var"]))

    if "not" in expr:
        return not _is_truthy(eval_expr(expr["not"], vars))

    if "and" in expr:
        return all(_is_truthy(eval_expr(e, vars)) for e in expr["and"])

    if "or" in expr:
        return any(_is_truthy(eval_expr(e, vars)) for e in expr["or"])

    if "equals" in expr:
        a, b = expr["equals"]
        a = eval_expr(a, vars)
        b = eval_expr(b, vars)
        return a == b

    if "contains" in expr:
        a, b = expr["contains"]
        a = eval_expr(a, vars)
        b = eval_expr(b, vars)
        try:
            return b in a
        except Exception:
            return False

    def _cmp(op: str, a: Any, b: Any) -> bool:
        try:
            if op == "gt":  return a > b
            if op == "ge":  return a >= b
            if op == "lt":  return a < b
            if op == "le":  return a <= b
        except Exception:
            return False
        return False

    for op in ("gt", "ge", "lt", "le"):
        if op in expr:
            a, b = expr[op]
            a = eval_expr(a, vars)
            b = eval_expr(b, vars)
            return _cmp(op, a, b)

    # fallback: interpolate whatever was passed
    return _deep_interpolate(expr, vars)


# ------------------------ step executors ------------------------

async def run_tool(mgr: MCPClientManager, qualified_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Call an MCP tool and return its normalized result."""
    action = {
        "action_type": "tool",
        "action_name": qualified_name,
        "arguments": args or {},
    }
    res = await mgr.execute_action(action)
    # normalize to dict so we can capture
    if isinstance(res, dict):
        return res
    return {"output": str(res)}


async def exec_sequential_steps(mgr: MCPClientManager, steps: Sequence[Dict[str, Any]], vars: MutableMapping[str, Any]) -> None:
    """
    Execute a list of steps SEQUENTIALLY. Mutates vars in-place.
    This is the original 'exec_steps' logic, preserved for 'if' and 'loop' blocks.
    """
    for idx, step in enumerate(steps):
        if not isinstance(step, Mapping):
            raise ValueError(f"Step #{idx+1} must be a mapping, got: {type(step)}")

        # ---- tool call
        if "tool" in step:
            qname = str(step["tool"])
            raw_args = step.get("args", {}) or {}
            args = _deep_interpolate(raw_args, vars)
            log.info("  (seq) tool %s(%s)", qname, json.dumps(args))
            result = await run_tool(mgr, qname, args)
            if "save_as" in step and step["save_as"]:
                vars[str(step["save_as"])] = result
            # Always update "last_output" for convenience
            vars["last_output"] = result
            continue

        # ---- if
        if "if" in step:
            cond = eval_expr(step["if"], vars)
            branch = "then" if _is_truthy(cond) else "else"
            sub = step.get(branch) or []
            if sub:
                await exec_sequential_steps(mgr, sub, vars)
            continue

        # ---- loop
        if "loop" in step:
            spec = step["loop"]
            if not isinstance(spec, Mapping):
                raise ValueError("loop must be a mapping with keys: var, over|range")
            loop_var = str(spec.get("var", "item"))

            # over: literal list or expression that evaluates to list
            if "over" in spec:
                it = eval_expr(spec["over"], vars)
                if not isinstance(it, Sequence) or isinstance(it, (str, bytes)):
                    raise ValueError("loop.over must evaluate to a list/sequence")
                iterable = list(it)
            elif "range" in spec:
                rspec = spec["range"]
                if not (isinstance(rspec, Sequence) and len(rspec) in (2, 3)):
                    raise ValueError("loop.range must be [start, end] or [start, end, step]")
                start, end = int(rspec[0]), int(rspec[1])
                stepv = int(rspec[2]) if len(rspec) == 3 else 1
                iterable = list(range(start, end + (1 if stepv > 0 else -1), stepv))
            else:
                raise ValueError("loop needs either 'over' or 'range'")

            body = step.get("do") or []
            for i, val in enumerate(iterable):
                vars[loop_var] = val
                vars[f"{loop_var}_index"] = i
                await exec_sequential_steps(mgr, body, vars)
            continue

        # ---- set
        if "set" in step:
            st = step["set"]
            if not isinstance(st, Mapping) or "var" not in st:
                raise ValueError("set step requires keys: var, value")
            name = str(st["var"])
            vars[name] = eval_expr(st.get("value"), vars)
            continue

        # ---- log
        if "log" in step:
            msg = eval_expr(step["log"], vars)
            msg = _deep_interpolate(msg, vars)
            log.info("  (seq) log: %s", msg)
            continue

        raise ValueError(f"Unknown step type at index {idx}: {step}")


async def _execute_single_step(
    mgr: MCPClientManager,
    step_id: str,
    all_steps: Dict[str, Dict[str, Any]],
    global_vars: MutableMapping[str, Any],
    step_events: Dict[str, asyncio.Event],
) -> None:
    """
    Executes a single step node after its dependencies are met.
    This is the target for an asyncio.Task.
    """
    step_config = all_steps[step_id]

    # --- 1. Wait for dependencies ---
    dependencies: List[str] = step_config.get("depends_on", [])
    if dependencies:
        log.info("Step '%s' waiting for: %s", step_id, ", ".join(dependencies))
        wait_tasks = []
        for dep_id in dependencies:
            if dep_id not in all_steps:
                raise ValueError(f"Step '{step_id}' has unknown dependency '{dep_id}'")
            wait_tasks.append(step_events[dep_id].wait())
        await asyncio.gather(*wait_tasks)
        log.info("Step '%s' dependencies met.", step_id)

    # --- 2. Execute Step ---
    try:
        log.info("Step '%s' starting...", step_id)
        result: Any = None
        
        # Interpolate config *just in time*
        config = _deep_interpolate(step_config, global_vars)

        if "tool" in config:
            qname = str(config["tool"])
            args = config.get("args", {}) or {}
            log.info("Step '%s' tool %s(%s)", step_id, qname, json.dumps(args))
            result = await run_tool(mgr, qname, args)

        elif "if" in config:
            cond = eval_expr(config["if"], global_vars)
            branch = "then" if _is_truthy(cond) else "else"
            sub = config.get(branch) or []
            if sub:
                await exec_sequential_steps(mgr, sub, global_vars)
            result = global_vars.get("last_output") # Capture result from branch

        elif "loop" in config:
            spec = config["loop"]
            loop_var = str(spec.get("var", "item"))
            
            if "over" in spec:
                it = eval_expr(spec["over"], global_vars)
                iterable = list(it)
            elif "range" in spec:
                rspec = spec["range"]
                start, end = int(rspec[0]), int(rspec[1])
                stepv = int(rspec[2]) if len(rspec) == 3 else 1
                iterable = list(range(start, end + (1 if stepv > 0 else -1), stepv))
            else:
                raise ValueError("loop needs 'over' or 'range'")

            body = config.get("do") or []
            for i, val in enumerate(iterable):
                # Create a local scope for loop vars
                loop_vars = {**global_vars, loop_var: val, f"{loop_var}_index": i}
                await exec_sequential_steps(mgr, body, loop_vars)
                # Note: This simple version doesn't merge loop_vars back.
                # 'set' steps inside a loop will modify the main global_vars.
            result = global_vars.get("last_output") # Capture result from loop

        elif "set" in config:
            st = config["set"]
            name = str(st["var"])
            value = eval_expr(st.get("value"), global_vars)
            # 'set' modifies the 'vars' sub-map directly
            global_vars["vars"][name] = value
            result = value

        elif "log" in config:
            msg = eval_expr(config["log"], global_vars)
            msg = _deep_interpolate(msg, global_vars) # Interpolate again
            log.info("Step '%s' log: %s", step_id, msg)
            result = msg
        
        else:
            raise ValueError(f"Unknown step type in node '{step_id}': {config}")

        # --- 3. Store results and signal completion ---
        log.info("Step '%s' finished.", step_id)
        global_vars["steps"][step_id] = result
        global_vars["last_output"] = result # Update for sequential blocks

    except Exception as e:
        log.error("Step '%s' FAILED: %s", step_id, e, exc_info=True)
        global_vars["steps"][step_id] = {"error": str(e)}
        # Re-raise to be caught by asyncio.gather
        raise
    
    finally:
        # Signal completion (success or fail) to unblock dependents
        step_events[step_id].set()


async def run_workflow_graph(
    mgr: MCPClientManager,
    all_steps: Dict[str, Dict[str, Any]],
    global_vars: MutableMapping[str, Any]
) -> None:
    """
    Executes a workflow defined as a Directed Acyclic Graph (DAG).
    """
    step_events: Dict[str, asyncio.Event] = {
        step_id: asyncio.Event() for step_id in all_steps
    }

    tasks = [
        asyncio.create_task(
            _execute_single_step(mgr, step_id, all_steps, global_vars, step_events)
        )
        for step_id in all_steps
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Check for any exceptions that weren't handled
    failed_steps = 0
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            step_id = list(all_steps.keys())[i]
            log.error("--- Workflow FAILED at step '%s' ---", step_id)
            failed_steps += 1
            # Exception already logged in _execute_single_step
            
    if failed_steps > 0:
        log.error("%d step(s) failed. Workflow incomplete.", failed_steps)
    else:
        log.info("Workflow graph execution complete.")


# ------------------------ main ------------------------

async def run_workflow(yaml_path: str) -> None:
    with open(yaml_path, "r", encoding="utf-8") as f:
        wf = yaml.safe_load(f) or {}

    if not isinstance(wf, Mapping):
        raise ValueError("Workflow YAML must be a mapping at top-level")

    version = wf.get("version", 1)
    if version != 1:
        raise ValueError(f"Unsupported workflow version: {version}")

    # Global context map:
    # - vars:   User-defined variables
    # - env:    Environment variables
    # - steps:  Output of each step, by step_id
    global_vars: Dict[str, Any] = {
        "vars": dict(wf.get("vars") or {}),
        "env": dict(os.environ),
        "steps": {} # Will be populated by the graph runner
    }

    # Load MCP servers & connect
    cfg = Config.load("mcp_servers.json")
    async with MCPClientManager(cfg) as mgr:
        await mgr.wait_ready()

        steps: Dict[str, Dict[str, Any]] = dict(wf.get("steps") or {})
        if not steps:
            log.info("No steps found in workflow.")
            return

        await run_workflow_graph(mgr, steps, global_vars)

    # Optional: write final vars snapshot (debug)
    if wf.get("write_vars_json", False):
        log.info("Writing final context to workflow_vars_snapshot.json")
        try:
            with open("workflow_vars_snapshot.json", "w", encoding="utf-8") as f:
                json.dump(global_vars, f, ensure_ascii=False, indent=2, default=str)
            log.info("Wrote workflow_vars_snapshot.json")
        except TypeError as e:
            log.error("Failed to serialize snapshot: %s", e)


def main() -> None:
    p = argparse.ArgumentParser(description="Run a YAML workflow (DAG) with MCP tools + logic primitives.")
    p.add_argument("yaml_path", help="Path to workflow YAML")
    args = p.parse_args()
    asyncio.run(run_workflow(args.yaml_path))

if __name__ == "__main__":
    main()