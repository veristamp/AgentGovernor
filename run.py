#!/usr/bin/env python3
"""
Main entrypoint for the AMCP Agent Planner.

This script orchestrates the modular components to:
1. Run the planner to get a validated YAML plan.
2. Prompt the user to confirm execution.
3. Execute the plan.
4. Prompt the user to save the successful workflow.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import yaml
import uuid  # Added for unique filenames
from pathlib import Path  # Added for saving files
from typing import Any, Dict, List, Optional

# --- Import modular components ---
from Agent import config
# Import the planner loop from run_planner
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
    
    # 1. Set up global vars (as expected by run_workflow_graph)
    global_vars: Dict[str, Any] = {
        "vars": dict(plan.get("vars") or {}),
        "env": dict(os.environ),
        "steps": {} 
    }
    
    # 2. Load MCP servers & connect
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

        # 3. Call the imported executor
        await run_workflow_graph(mgr, steps, global_vars)
    
    log.info("--- ✅ PLAN EXECUTION COMPLETE ---")
    
    # 4. Print final state
    final_steps_output = global_vars.get("steps", {})
    log.info("Final step outputs (JSON):")
    try:
        print(json.dumps(final_steps_output, indent=2, default=str))
    except Exception as e:
        log.error(f"Could not serialize final step outputs: {e}")
        print(final_steps_output)

def save_workflow(goal: str, plan_dict: Dict[str, Any]):
    """
    Saves the successful workflow to the 'workflows' directory.
    Adds the original goal as the 'description'.
    """
    try:
        log.info("Saving workflow...")
        
        # 1. Add the goal as the description
        plan_dict["description"] = goal
        
        # 2. Create a unique filename
        filename = f"wf_{uuid.uuid4().hex[:10]}.yaml"
        save_path = Path("workflows") / filename
        
        # 3. Ensure the directory exists
        save_path.parent.mkdir(exist_ok=True)
        
        # 4. Save the modified YAML
        with open(save_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(plan_dict, f, sort_keys=False, default_flow_style=False)
            
        log.info(f"--- ✅ Workflow saved successfully to {save_path} ---")
        log.info("You can run 'uv run -m upsert' to add it to the RAG database.")
        
    except Exception as e:
        log.error(f"Failed to save workflow: {e}", exc_info=True)


def main():
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="AMCP Agent Planner: Goal -> Validated YAML -> Execution",
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
                confirm = input("Press [Enter] to execute this plan, or [Ctrl+C] to cancel...")
                if confirm.lower() == 'c':
                    raise KeyboardInterrupt
        except KeyboardInterrupt:
            log.info("\nExecution cancelled by user.")
            sys.exit(0)
        
        # --- EXECUTE ---
        execution_success = False
        try:
            asyncio.run(execute_plan(final_plan))
            execution_success = True # Set flag if no exception
        except Exception as e:
            log.critical("--- ❌ PLAN EXECUTION FAILED ---")
            log.critical(f"Error: {e}", exc_info=True)
            sys.exit(1)

        # --- SAVE (NEW) ---
        if execution_success:
            try:
                if not args.yes:
                    save = input("Do you want to save this successful workflow for RAG? [y/n]: ").lower().strip()
                if args.yes or save == 'y':
                    # Pass the original goal and the dictionary version of the plan
                    save_workflow(args.goal, final_plan)
                else:
                    log.info("Workflow not saved.")
            except KeyboardInterrupt:
                log.info("\nNot saving workflow.")
        
        sys.exit(0)

    else:
        log.critical("--- ❌ FAILED TO GENERATE A VALID PLAN ---")
        sys.exit(1)

if __name__ == "__main__":
    main()