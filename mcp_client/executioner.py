# workflow_executor.py
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
from copy import deepcopy
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Union

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
    Supports dotted paths like ${ctx.last_output}.
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


async def exec_steps(mgr: MCPClientManager, steps: Sequence[Dict[str, Any]], vars: MutableMapping[str, Any]) -> None:
    """
    Execute a list of steps. Mutates vars in-place.
    Supported steps:
      - tool: <qualified_name>
        args: { ... }          # can use ${var} placeholders
        save_as: <var_name>    # optional, saves dict result to vars[...]
      - if: <expr>
        then: [steps...]
        else: [steps...]
      - loop:
          var: item            # loop variable name
          over: [1,2,3]        # list; or {range: [start, end]} inclusive
        do: [steps...]
      - set:
          var: name
          value: <expr|literal>
      - log: <string or expr>  # prints resolved value
    """
    for idx, step in enumerate(steps):
        if not isinstance(step, Mapping):
            raise ValueError(f"Step #{idx+1} must be a mapping, got: {type(step)}")

        # ---- tool call
        if "tool" in step:
            qname = str(step["tool"])
            raw_args = step.get("args", {}) or {}
            args = _deep_interpolate(raw_args, vars)
            log.info("tool %s(%s)", qname, json.dumps(args))
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
                await exec_steps(mgr, sub, vars)
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
                await exec_steps(mgr, body, vars)
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
            log.info("log: %s", msg)
            continue

        raise ValueError(f"Unknown step type at index {idx}: {step}")


# ------------------------ main ------------------------

async def run_workflow(yaml_path: str) -> None:
    with open(yaml_path, "r", encoding="utf-8") as f:
        wf = yaml.safe_load(f) or {}

    if not isinstance(wf, Mapping):
        raise ValueError("Workflow YAML must be a mapping at top-level")

    version = wf.get("version", 1)
    if version != 1:
        raise ValueError(f"Unsupported workflow version: {version}")

    vars: Dict[str, Any] = dict(wf.get("vars") or {})
    vars.setdefault("env", dict(os.environ))  # expose env if needed

    # Load MCP servers & connect
    cfg = Config.load("mcp_servers.json")
    async with MCPClientManager(cfg) as mgr:
        await mgr.wait_ready()

        steps: List[Dict[str, Any]] = list(wf.get("steps") or [])
        await exec_steps(mgr, steps, vars)

    # Optional: write final vars snapshot (debug)
    if wf.get("write_vars_json", False):
        with open("workflow_vars_snapshot.json", "w", encoding="utf-8") as f:
            json.dump(vars, f, ensure_ascii=False, indent=2)
        log.info("Wrote workflow_vars_snapshot.json")

def main() -> None:
    p = argparse.ArgumentParser(description="Run a YAML workflow with MCP tools + logic primitives.")
    p.add_argument("yaml_path", help="Path to workflow YAML")
    args = p.parse_args()
    asyncio.run(run_workflow(args.yaml_path))

if __name__ == "__main__":
    main()
