#!/usr/bin/env python3
"""
Main entrypoint for the AMCP Agent.

Supports two modes:
1. YAML Mode (legacy): Generates and executes YAML workflows
2. Code Mode (new): Generates and executes Python code in sandbox

This script orchestrates:
1. Run the planner to get a validated plan (YAML or Code).
2. Prompt the user to confirm execution.
3. Execute the plan.
4. Prompt the user to save the successful result.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import yaml
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --- Import modular components ---
from Agent import config
# Import both planner loops
from run_planner import run_planner_loop, run_code_planner_loop

# --- Import Execution Components ---
from mcp_client.manager import MCPClientManager
from mcp_client.config import Config as MCPConfig
from mcp_client.workflow_executor import run_workflow_graph
from mcp_client.sandbox.executor import execute_code_plan

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s agent :: %(message)s"
)
log = logging.getLogger("agent")


async def execute_yaml_plan(plan: Dict[str, Any]):
    """
    Connects to MCP servers and executes a YAML plan.
    (Legacy mode)
    """
    log.info("--- EXECUTING YAML PLAN ---")
    
    global_vars: Dict[str, Any] = {
        "vars": dict(plan.get("vars") or {}),
        "env": dict(os.environ),
        "steps": {} 
    }
    
    log.info("Loading MCP server configuration from mcp_servers.json...")
    cfg = MCPConfig.load("mcp_servers.json") 
    if not cfg.mcp_servers:
        log.warning("No MCP servers found in mcp_servers.json. Execution may fail.")

    async with MCPClientManager(cfg) as mgr:
        await mgr.wait_ready()
        log.info("MCP Client Manager connected and ready.")
        
        steps: Dict[str, Dict[str, Any]] = dict(plan.get("steps") or {})
        if not steps:
            log.error("No steps found in the plan. Nothing to execute.")
            return None

        await run_workflow_graph(mgr, steps, global_vars)
    
    log.info("--- ✅ YAML PLAN EXECUTION COMPLETE ---")
    
    final_steps_output = global_vars.get("steps", {})
    return final_steps_output


async def execute_code_plan_wrapper(code: str, manifest: Dict[str, Any]) -> Any:
    """
    Connects to MCP servers and executes Python code in the sandbox.
    (Governed Code Mode)
    """
    log.info("--- EXECUTING CODE IN SANDBOX ---")
    
    # Extract allowed servers from manifest
    io_calls = manifest.get("io_calls", [])
    allowed_servers = set()
    for call in io_calls:
        if "." in call:
            server = call.split(".")[0]
            allowed_servers.add(server)
    
    if not allowed_servers:
        # Try to extract from code as fallback
        import re
        binding_pattern = r'await\s+(\w+)\.'
        matches = re.findall(binding_pattern, code)
        allowed_servers = set(matches)
    
    allowed_servers_list = list(allowed_servers)
    log.info(f"Allowed servers from manifest: {allowed_servers_list}")
    
    log.info("Loading MCP server configuration from mcp_servers.json...")
    cfg = MCPConfig.load("mcp_servers.json")
    if not cfg.mcp_servers:
        log.warning("No MCP servers found in mcp_servers.json. Execution may fail.")
    
    async with MCPClientManager(cfg) as mgr:
        await mgr.wait_ready()
        log.info("MCP Client Manager connected and ready.")
        
        # Execute in sandbox
        result = await execute_code_plan(mgr, code, allowed_servers_list)
    
    log.info("--- ✅ CODE EXECUTION COMPLETE ---")
    return result


def save_workflow(goal: str, plan_dict: Dict[str, Any]):
    """
    Saves a successful YAML workflow to the 'workflows' directory.
    (Legacy mode)
    """
    try:
        log.info("Saving YAML workflow...")
        
        plan_dict["description"] = goal
        
        filename = f"wf_{uuid.uuid4().hex[:10]}.yaml"
        save_path = Path("workflows") / filename
        
        save_path.parent.mkdir(exist_ok=True)
        
        with open(save_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(plan_dict, f, sort_keys=False, default_flow_style=False)
            
        log.info(f"--- ✅ Workflow saved to {save_path} ---")
        log.info("Run 'uv run upsert.py' to add it to the RAG database.")
        
    except Exception as e:
        log.error(f"Failed to save workflow: {e}", exc_info=True)


def save_skill(goal: str, code: str, manifest: Dict[str, Any]):
    """
    Saves a successful Python code as a skill to the 'skills' directory.
    (Governed Code Mode)
    """
    try:
        log.info("Saving as Python skill...")
        
        # Generate a skill name from the goal
        skill_name = re.sub(r'[^a-z0-9]+', '-', goal.lower())[:30].strip('-')
        if not skill_name:
            skill_name = f"skill-{uuid.uuid4().hex[:6]}"
        
        skill_dir = Path("skills") / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        
        # Extract bindings from manifest
        bindings = manifest.get("io_calls", [])
        bindings_yaml = "\n".join(f"  - {b}" for b in bindings) if bindings else "  - none"
        
        # Create SKILL.md
        skill_md_content = f"""---
name: {skill_name}
description: "{goal}"
bindings:
{bindings_yaml}
version: 1
author: auto-generated
license: MIT
---

# {goal}

This skill was auto-generated from a successful execution.

## Code

```python
{code}
```

## Manifest

{json.dumps(manifest, indent=2)}
"""
        
        skill_md_path = skill_dir / "SKILL.md"
        with open(skill_md_path, "w", encoding="utf-8") as f:
            f.write(skill_md_content)
        
        # Also save the raw code for easy reuse
        code_path = skill_dir / "main.py"
        with open(code_path, "w", encoding="utf-8") as f:
            f.write(code)
        
        log.info(f"--- ✅ Skill saved to {skill_dir} ---")
        log.info("Run 'uv run upsert.py' to add it to the RAG database.")
        
    except Exception as e:
        log.error(f"Failed to save skill: {e}", exc_info=True)


def main():
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="AMCP Agent: Goal -> Plan -> Execution",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--goal", 
        required=True, 
        help="The natural language goal for the agent."
    )
    parser.add_argument(
        "-v", "--verbose", 
        action="store_true", 
        help="Print full prompts and LLM responses."
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Automatically confirm and execute the plan without prompting."
    )
    parser.add_argument(
        "--code", "--code-mode",
        action="store_true",
        dest="code_mode",
        help="Use Governed Code Mode (Python sandbox) instead of YAML mode."
    )
    args = parser.parse_args()

    if not config.LLM_MODEL_NAME or config.LLM_MODEL_NAME == "your-local-model-name":
        log.critical("Error: LLM_MODEL_NAME is not set in Agent/config.py")
        log.critical("Please set it to the model you are serving via LM Studio (or equivalent).")
        sys.exit(1)

    if args.code_mode:
        # ========================================
        # CODE MODE (Governed Code Mode)
        # ========================================
        result = run_code_planner_loop(args.goal, args.verbose)
        
        if not result:
            log.critical("--- ❌ FAILED TO GENERATE VALID CODE ---")
            sys.exit(1)
        
        code, manifest = result
        
        log.info("--- ✅ FINAL VALIDATED CODE ---")
        print("\n" + "=" * 50)
        print("MANIFEST:", json.dumps(manifest, indent=2))
        print("=" * 50)
        print(code)
        print("=" * 50)
        
        # --- CONFIRM ---
        try:
            if not args.yes:
                confirm = input("\nPress [Enter] to execute this code, or [Ctrl+C] to cancel...")
                if confirm.lower() == 'c':
                    raise KeyboardInterrupt
        except KeyboardInterrupt:
            log.info("\nExecution cancelled by user.")
            sys.exit(0)
        
        # --- EXECUTE ---
        execution_success = False
        try:
            result = asyncio.run(execute_code_plan_wrapper(code, manifest))
            execution_success = True
            log.info("Result from main():")
            print(json.dumps(result, indent=2, default=str))
        except Exception as e:
            log.critical("--- ❌ CODE EXECUTION FAILED ---")
            log.critical(f"Error: {e}", exc_info=True)
            sys.exit(1)
        
        # --- SAVE ---
        if execution_success:
            try:
                if not args.yes:
                    save = input("Save this as a skill for future reuse? [y/n]: ").lower().strip()
                if args.yes or save == 'y':
                    save_skill(args.goal, code, manifest)
                else:
                    log.info("Skill not saved.")
            except KeyboardInterrupt:
                log.info("\nNot saving skill.")
        
        sys.exit(0)
    
    else:
        # ========================================
        # YAML MODE (Legacy)
        # ========================================
        final_plan = run_planner_loop(args.goal, args.verbose)
        
        if not final_plan:
            log.critical("--- ❌ FAILED TO GENERATE A VALID PLAN ---")
            sys.exit(1)
        
        log.info("--- ✅ FINAL VALIDATED PLAN ---")
        plan_yaml = yaml.safe_dump(final_plan, sort_keys=False, default_flow_style=False)
        print(plan_yaml)
        
        # --- CONFIRM ---
        try:
            if not args.yes:
                confirm = input("Press [Enter] to execute this plan, or [Ctrl+C] to cancel...")
                if confirm.lower() == 'c':
                    raise KeyboardInterrupt
        except KeyboardInterrupt:
            log.info("\nExecution cancelled by user.")
            sys.exit(0)
        
        # --- EXECUTE ---
        execution_success = False
        try:
            result = asyncio.run(execute_yaml_plan(final_plan))
            execution_success = True
            log.info("Final step outputs (JSON):")
            print(json.dumps(result, indent=2, default=str))
        except Exception as e:
            log.critical("--- ❌ PLAN EXECUTION FAILED ---")
            log.critical(f"Error: {e}", exc_info=True)
            sys.exit(1)

        # --- SAVE ---
        if execution_success:
            try:
                if not args.yes:
                    save = input("Save this workflow for RAG? [y/n]: ").lower().strip()
                if args.yes or save == 'y':
                    save_workflow(args.goal, final_plan)
                else:
                    log.info("Workflow not saved.")
            except KeyboardInterrupt:
                log.info("\nNot saving workflow.")
        
        sys.exit(0)


if __name__ == "__main__":
    main()