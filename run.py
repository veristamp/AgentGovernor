#!/usr/bin/env python3
"""
Main entrypoint for the AMCP Agent Planner & Executor.

This script:
1. Imports the planner from 'run_planner.py'.
2. Calls the planner to get a validated YAML plan.
3. Prompts the user to confirm execution.
4. Uses the 'mcp_client' to execute the plan.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import yaml
from typing import Any, Dict

# --- Import modular components ---
from Agent import config
# Import the planning logic from the other script
from run_planner import run_planner_loop

# --- Import Execution Components ---
from mcp_client.manager import MCPClientManager
# Alias MCP's Config to avoid name collision with Agent.config
from mcp_client.config import Config as MCPConfig
from mcp_client.workflow_executor import run_workflow_graph

# --- Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s planner :: %(message)s"
)
log = logging.getLogger("planner")

async def execute_plan(plan: Dict[str, Any]):
    """
    Connects to MCP servers and executes the given plan.
    """
    log.info("--- EXECUTING PLAN ---")
    
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
            return

        await run_workflow_graph(mgr, steps, global_vars)
    
    log.info("--- ✅ PLAN EXECUTION COMPLETE ---")
    
    final_steps_output = global_vars.get("steps", {})
    log.info("Final step outputs (JSON):")
    try:
        print(json.dumps(final_steps_output, indent=2, default=str))
    except Exception as e:
        log.error(f"Could not serialize final step outputs: {e}")
        print(final_steps_output)

def main():
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="AMCP Agent: Goal -> Validated YAML -> Execution",
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
    args = parser.parse_args()

    if not config.LLM_MODEL_NAME or config.LLM_MODEL_NAME == "your-local-model-name":
        log.critical("Error: LLM_MODEL_NAME is not set in Agent/config.py")
        log.critical("Please set it to the model you are serving via LM Studio (or equivalent).")
        sys.exit(1)

    # --- PLAN ---
    final_plan = run_planner_loop(args.goal, args.verbose)
    
    if final_plan:
        log.info("--- ✅ FINAL VALIDATED PLAN ---")
        plan_yaml = yaml.safe_dump(final_plan, sort_keys=False, default_flow_style=False)
        print(plan_yaml)
        
        # --- CONFIRM ---
        try:
            if not args.yes:
                input("Press [Enter] to execute this plan, or [Ctrl+C] to cancel...")
        except KeyboardInterrupt:
            log.info("\nExecution cancelled by user.")
            sys.exit(0)
        
        # --- EXECUTE ---
        try:
            asyncio.run(execute_plan(final_plan))
            sys.exit(0)
        except Exception as e:
            log.critical("--- ❌ PLAN EXECUTION FAILED ---")
            log.critical(f"Error: {e}", exc_info=True)
            sys.exit(1)

    else:
        log.critical("--- ❌ FAILED TO GENERATE A VALID PLAN ---")
        sys.exit(1)

if __name__ == "__main__":
    main()