#!/usr/bin/env python3
# planner_loop.py
# Minimal iterative "Scratchpad" loop for PlanYAML generation via LM Studio (OpenAI-compatible).
# deps: pip install pyyaml requests

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml

# ------------------------- Config -------------------------

LM_BASE = os.getenv("LM_STUDIO_BASE", "http://localhost:1234/v1")
DEFAULT_MODEL = os.getenv("LM_MODEL", "your-model-name")
TIMEOUT = int(os.getenv("LM_TIMEOUT", "60"))

# ----------------- Capability Registry (edit) -----------------

CAPS: Dict[str, Dict[str, Any]] = {
    "github:list_prs": {
        "args": {"repo": str, "state": str, "limit": int},
        "required": ["repo"],
        "defaults": {"state": "open", "limit": 50},
        "output": "PRListHandle",
    },
    "github:get_pr": {
        "args": {"id": int},
        "required": ["id"],
        "defaults": {},
        "output": "PRHandle",
    },
    "slm:compact": {
        "args": {"input": "HandleOrText", "target": str},
        "required": ["input"],
        "defaults": {"target": "summary"},
        "output": "MarkdownHandle",
    },
    "text:extract": {
        "args": {"input": "HandleOrText", "pattern": str},
        "required": ["input", "pattern"],
        "defaults": {},
        "output": "TextHandle",
    },
    "slack:post_message": {
        "args": {"channel": str, "input": "HandleOrText"},
        "required": ["channel", "input"],
        "defaults": {},
        "output": "MessageHandle",
    },
    "http:get": {
        "args": {"url": str, "headers": dict},
        "required": ["url"],
        "defaults": {"headers": {}},
        "output": "HttpBodyHandle",
    },
    "store:write_file": {
        "args": {"path": str, "input": "HandleOrText"},
        "required": ["path", "input"],
        "defaults": {},
        "output": "FileHandle",
    },
    "graph:walk": {
        "args": {"start_node": str, "edge_type": str, "depth": int},
        "required": ["start_node", "edge_type"],
        "defaults": {"depth": 1},
        "output": "NodeSetHandle",
    },
}

# ---------------------- Prompt (RICECO) ----------------------

def build_riceco(goal: str) -> str:
    role = (
        "You are **The Orchestrator**. Your job is to compile a user goal into a "
        "deterministic **PlanYAML** workflow that calls approved primitives. "
        "You never execute code or explain reasoning; you only emit a valid PlanYAML plan."
    )

    instruction = f"""Given the GOAL, produce the smallest correct workflow:
- Prefer a single node when one tool suffices.
- Otherwise compose 2–6 nodes with clear dataflow.
- Always pass handles, not payloads (use "@handle" or "${{item}}").
- If required inputs are missing, declare them under "inputs:" and reference them as "${{inputs.name}}".
GOAL: "{goal}"."""

    # Primitive signatures
    prim_lines: List[str] = []
    for cap, spec in CAPS.items():
        sig_parts = []
        for k, typ in spec["args"].items():
            tname = typ.__name__ if isinstance(typ, type) else str(typ)
            if k in spec["defaults"]:
                sig_parts.append(f'{k}:{tname}="{spec["defaults"][k]}"')
            else:
                sig_parts.append(f"{k}:{tname}")
        prim_lines.append(f"- `{cap}({', '.join(sig_parts)}) -> {spec['output']}`")
    primitives = "\n".join(prim_lines)

    context = f"""Approved primitives (capabilities):
{primitives}

PlanYAML 1.0 (strict subset):
- Top-level keys: "version", "inputs" (optional), "nodes".
- Node keys: "id", "cap", "args", "out"; optional control keys: "foreach", "if".
- Handle reference: "@<handleName>"; foreach item reference: "${{item}}".
- Allowed predicate: if: "size(@handle) > INT".
- All strings must be quoted; no anchors/aliases/tags; no comments.
- ABAC/policy/budgets are injected later—do not include them."""

    examples = textwrap.dedent("""\
    Example A:
    ```yaml
    version: 1
    inputs:
      repo: {type: "RepoSlug"}
    nodes:
      - id: list
        cap: github:list_prs
        args: { repo: "${inputs.repo}", state: "open", limit: 50 }
        out: prs
      - id: compact
        cap: slm:compact
        args: { input: "@prs", target: "summary" }
        out: summary
      - id: notify
        cap: slack:post_message
        args: { channel: "#dev", input: "@summary" }
        out: msg
    ```

    Example B:
    ```yaml
    version: 1
    inputs:
      url: {type: "Url"}
    nodes:
      - id: fetch
        cap: http:get
        args: { url: "${inputs.url}" }
        out: body
      - id: grab
        cap: text:extract
        args: { input: "@body", pattern: "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}" }
        out: email
      - id: save
        cap: store:write_file
        args: { path: "out/email.txt", input: "@email" }
        out: file
    ```

    Example C:
    ```yaml
    version: 1
    inputs:
      repo: {type: "RepoSlug"}
    nodes:
      - id: find_owner
        cap: graph:walk
        args: { start_node: "repo:${inputs.repo}", edge_type: "has_owner", depth: 1 }
        out: owner
      - id: ping
        cap: slack:post_message
        args: { channel: "#owners", input: "@owner" }
        out: msg
    ```
    """)

    constraints = """Constraints:
- Emit only one fenced code block with valid YAML. No prose.
- Use only the approved primitives. Do not invent args or caps.
- **Use the *minimum number of nodes* required to satisfy the GOAL. Do not add extra steps from the examples.**
- Prefer 1–4 nodes. Use "foreach" and "if" sparingly and only as specified.
- Every string is quoted. Each node has a unique "id" and "out".
- If you reference "${inputs.*}", you MUST declare an "inputs:" block with those keys and types."""

    output_fmt = """Output format:
Return exactly one fenced YAML block:

```yaml
version: 1
inputs:
  # declare only if needed, else omit
nodes:
  # 1–6 nodes following the rules above
```"""

    return f"""R — Role
{role}

I — Instruction
{instruction}

C — Context
{context}

E — Examples
{examples}

CO — Constraints
{constraints}

O — Output
{output_fmt}
"""

# ---------------------- YAML helpers ----------------------

def extract_yaml_block(text: str) -> Optional[str]:
    """Pull the first fenced YAML block from model output; fallback to any fenced block; else raw text."""
    m = re.search(r"```yaml\s*(.+?)\s*```", text, flags=re.S | re.I)
    if not m:
        m = re.search(r"```yml\s*(.+?)\s*```", text, flags=re.S | re.I)
    if not m:
        m = re.search(r"```\s*(.+?)\s*```", text, flags=re.S | re.I)
    return m.group(1).strip() if m else None

class ValidationError(Exception):
    pass

def validate_planyaml(raw_yaml: str) -> Tuple[Dict[str, Any], List[str]]:
    """Parse & validate PlanYAML against the strict subset and CAPS."""
    errors: List[str] = []
    try:
        plan = yaml.safe_load(raw_yaml)
    except Exception as e:
        raise ValidationError(f"YAML parse error: {e}")

    if not isinstance(plan, dict):
        raise ValidationError("Top-level must be a mapping (dict).")

    if plan.get("version") != 1:
        errors.append('Top-level "version" must be 1.')

    nodes = plan.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        errors.append('"nodes" must be a non-empty list.')

    # inputs presence if referenced
    raw_refs = re.findall(r"\$\{inputs\.([a-zA-Z0-9_]+)\}", raw_yaml)
    inputs = plan.get("inputs", {}) if "inputs" in plan else {}
    if raw_refs and not isinstance(inputs, dict):
        errors.append('You referenced "${inputs.*}" but "inputs" is missing or not a map.')
    for ref in raw_refs:
        if ref not in inputs:
            errors.append(f'Missing inputs declaration for "{ref}".')

    # Node checks
    seen_ids, seen_outs = set(), set()
    if isinstance(nodes, list):
        for idx, n in enumerate(nodes):
            if not isinstance(n, dict):
                errors.append(f"Node {idx} is not a map.")
                continue

            nid = n.get("id")
            cap = n.get("cap")
            args = n.get("args", {})
            out = n.get("out")

            if nid in (None, ""):
                errors.append(f"Node {idx} missing 'id'.")
            elif nid in seen_ids:
                errors.append(f"Duplicate node id '{nid}'.")
            else:
                seen_ids.add(nid)

            if cap not in CAPS:
                errors.append(f"Node '{nid}': unknown cap '{cap}'.")
                continue

            spec = CAPS[cap]
            if not isinstance(args, dict):
                errors.append(f"Node '{nid}': 'args' must be a map.")
            else:
                # required args
                for rq in spec["required"]:
                    if rq not in args:
                        errors.append(f"Node '{nid}': missing required arg '{rq}'.")
                # arg-level checks
                for ak, av in args.items():
                    if ak not in spec["args"]:
                        errors.append(f"Node '{nid}': unknown arg '{ak}'.")
                        continue
                    typ = spec["args"][ak]
                    # allow handle or interpolation strings
                    if isinstance(av, str) and (av.startswith("@") or "${" in av):
                        pass
                    elif typ == "HandleOrText":
                        if not isinstance(av, (str, dict)):
                            errors.append(f"Node '{nid}': arg '{ak}' should be HandleOrText or reference.")
                    elif typ == dict:
                        if not isinstance(av, dict):
                            errors.append(f"Node '{nid}': arg '{ak}' must be an object.")
                    elif typ == int:
                        if not isinstance(av, int):
                            errors.append(f"Node '{nid}': arg '{ak}' must be int.")
                    elif typ == str:
                        if not isinstance(av, str):
                            errors.append(f"Node '{nid}': arg '{ak}' must be string.")

            if out in (None, ""):
                errors.append(f"Node '{nid}': missing 'out'.")
            elif out in seen_outs:
                errors.append(f"Duplicate out handle '{out}'.")
            else:
                seen_outs.add(out)

    return plan, errors

# ---------------------- LM Studio client ----------------------

def chat_complete(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    base: str = LM_BASE,
) -> str:
    url = f"{base}/chat/completions"
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    resp = requests.post(url, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]

# ------------------- Iterative scratchpad loop -------------------

REPAIR_INSTRUCTIONS = """Repair this PlanYAML to the strict subset:
- If any "${inputs.*}" is referenced, add an "inputs:" map declaring those keys and simple types.
- Every node must have unique "id" and "out"; use only approved caps and args.
- Keep strings quoted; remove comments/anchors.
Return only a single fenced YAML block with the corrected plan.
Original:
"""

def run_loop(
    goal: str,
    model: str,
    max_iters: int = 3,
    temperature: float = 0.2,
    base: str = LM_BASE,
    verbose: bool = True,
    print_json: bool = False,
) -> int:
    riceco = build_riceco(goal)
    system_prompt = "You produce valid PlanYAML workflows only."

    # Draft
    reply = chat_complete(model, system_prompt, riceco, temperature=temperature, base=base)
    yaml_block = extract_yaml_block(reply) or reply.strip()
    if verbose:
        print("\n--- Model Draft ---\n", reply)

    last_plan: Optional[Dict[str, Any]] = None

    # Validate & repair
    for attempt in range(1, max_iters + 1):
        try:
            plan, errs = validate_planyaml(yaml_block)
            last_plan = plan  # <-- use the parsed plan (fixes unused warning & enables printing)
        except ValidationError as e:
            errs = [str(e)]
            last_plan = None

        if not errs:
            print("\n✅ Valid PlanYAML:")
            print("```yaml")
            print(yaml_block)
            print("```")
            if print_json and last_plan is not None:
                # Canonical JSON view of the parsed plan (useful for debugging / diff)
                print("\nParsed plan (canonical JSON):")
                print(json.dumps(last_plan, indent=2, sort_keys=True))
            return 0

        # else: ask model to repair
        print(f"\n⚠️  Validation errors (attempt {attempt}/{max_iters}):")
        for e in errs:
            print(" -", e)

        repair_prompt = (
            REPAIR_INSTRUCTIONS
            + "```\n"
            + yaml_block
            + "\n```\n\nErrors:\n"
            + "\n".join(f"- {e}" for e in errs)
        )
        reply = chat_complete(model, system_prompt, repair_prompt, temperature=temperature, base=base)
        yaml_block = extract_yaml_block(reply) or reply.strip()
        if verbose:
            print("\n--- Model Repair ---\n", reply)

    # Final failure
    print("\n❌ Could not obtain a valid plan after retries. Last attempt:")
    print("```yaml")
    print(yaml_block)
    print("```")
    if print_json and last_plan is not None:
        print("\nLast parsed (possibly invalid) plan JSON:")
        print(json.dumps(last_plan, indent=2, sort_keys=True))
    return 1

# ----------------------------- CLI -----------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Iterative PlanYAML generator/validator for LM Studio.")
    ap.add_argument("--goal", required=True, help='User goal, e.g., "Summarize open PRs for repo alpha and post to #dev"')
    ap.add_argument("--model", default=DEFAULT_MODEL, help="Model name served by LM Studio")
    ap.add_argument("--iters", type=int, default=3, help="Max repair iterations")
    ap.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature")
    ap.add_argument("--base", default=LM_BASE, help="Base URL for OpenAI-compatible API")
    ap.add_argument("--print-json", action="store_true", help="Print canonical parsed plan JSON on success/failure")
    args = ap.parse_args()

    rc = run_loop(
        goal=args.goal,
        model=args.model,
        max_iters=args.iters,
        temperature=args.temperature,
        base=args.base,
        verbose=True,
        print_json=args.print_json,
    )
    sys.exit(rc)

if __name__ == "__main__":
    main()
