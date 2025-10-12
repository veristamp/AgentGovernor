# File: mcp_inspector.py
#!/usr/bin/env python3
"""
mcp_inspector.py
FastAPI-based web UI to inspect and call MCP servers using MCPClientManager.

Usage:
  uvicorn mcp_inspector:app --reload

Place mcp_servers.json in the same directory as this script.
"""

from __future__ import annotations
from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import asyncio
import json
import logging
import traceback
from typing import Optional, Dict, Any
from pathlib import Path
from contextlib import asynccontextmanager

# Import your MCP manager & Config
from mcp_client_manager2 import MCPClientManager, Config

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("mcp_inspector")

# Base dir and template/static setup
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
static_dir = BASE_DIR / "static"

app = FastAPI(title="MCP Inspector", description="Web UI for testing MCP servers")

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
else:
    logger.info("Static directory not found; /static not mounted.")

# Globals for manager lifecycle
mcp_manager: Optional[MCPClientManager] = None          # Exposed manager (set by runner)
current_server_name: Optional[str] = None

# Runner control
_manager_runner_task: Optional[asyncio.Task] = None
_manager_stop_event: Optional[asyncio.Event] = None
_connect_lock = asyncio.Lock()

CONFIG_PATH = BASE_DIR / "mcp_servers.json"

# Lifespan: ensure cleanup on shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        # On shutdown, ensure any manager runner is stopped cleanly.
        global _manager_runner_task, _manager_stop_event
        if _manager_stop_event and _manager_runner_task:
            logger.info("Shutdown: stopping manager runner...")
            _manager_stop_event.set()
            try:
                await asyncio.wait_for(_manager_runner_task, timeout=10.0)
            except Exception:
                logger.exception("Shutdown: runner did not finish; cancelling.")
                _manager_runner_task.cancel()
                try:
                    await _manager_runner_task
                except Exception:
                    pass
        logger.info("Shutdown cleanup done.")

app.router.lifespan_context = lifespan  # apply lifespan

# Utility: load servers from config file
def load_existing_servers() -> Dict[str, Dict[str, Any]]:
    if not CONFIG_PATH.exists():
        logger.warning(f"Config file not found at: {CONFIG_PATH}")
        return {}
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read config file: {e}")
        return {}
    # Filter disabled servers
    out = {name: cfg for name, cfg in raw.items() if not cfg.get("disabled", False)}
    return out

# Background runner: runs async with manager in a single task
async def _manager_runner(manager: MCPClientManager, stop_event: asyncio.Event, server_name: str):
    """
    Run `async with manager` inside a dedicated task so entry/exit happen in same task.
    On exit, clears global manager/current_server_name.
    """
    global mcp_manager, current_server_name
    try:
        async with manager:
            mcp_manager = manager
            current_server_name = server_name

            # Wait for manager readiness but do not block forever
            try:
                await asyncio.wait_for(manager.wait_ready(), timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("Manager.wait_ready() timed out in runner; continuing but manager may be incomplete.")

            logger.info(f"Manager runner active for server '{server_name}'. Waiting for stop event...")
            await stop_event.wait()
            logger.info("Stop event set for manager runner; exiting context.")
    except Exception as e:
        logger.exception(f"Unexpected error in manager runner: {e}")
    finally:
        # Always clear globals here to avoid stale references
        mcp_manager = None
        current_server_name = None
        logger.info(f"Manager runner finished for server '{server_name}'.")

# Helper that polls until manager is set and ready (used after creating runner)
async def _wait_for_manager_ready(timeout: float = 10.0):
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        if mcp_manager is not None:
            try:
                await asyncio.wait_for(mcp_manager.wait_ready(), timeout=1.0)
            except asyncio.TimeoutError:
                # manager exists but not ready yet — keep waiting
                pass
            return
        await asyncio.sleep(0.05)
    raise asyncio.TimeoutError()

# Dependency: ensure a ready manager is available
async def get_mcp_manager() -> MCPClientManager:
    if mcp_manager is None:
        raise HTTPException(status_code=400, detail="No server connected")
    try:
        await asyncio.wait_for(mcp_manager.wait_ready(), timeout=5.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="MCP manager not ready")
    return mcp_manager

# Routes ----------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    servers = load_existing_servers()
    if not servers:
        return templates.TemplateResponse("no_servers.html", {"request": request}) if (templates is not None) else HTMLResponse("No servers configured.", status_code=200)

    if mcp_manager is None:
        return templates.TemplateResponse("server_select.html", {"request": request, "available_servers": servers})
    try:
        caps = await asyncio.wait_for(mcp_manager.list_formatted_capabilities(), timeout=10.0)
    except asyncio.TimeoutError:
        return templates.TemplateResponse("error.html", {"request": request, "error": "Timeout getting server capabilities"})
    except Exception as e:
        logger.exception("Error getting capabilities")
        return templates.TemplateResponse("error.html", {"request": request, "error": str(e)})

    return templates.TemplateResponse("inspector.html", {
        "request": request,
        "capabilities": caps,
        "connected": True,
        "current_server": current_server_name
    })

@app.get("/servers", response_class=HTMLResponse)
async def server_selection_page(request: Request):
    servers = load_existing_servers()
    return templates.TemplateResponse("server_select.html", {"request": request, "available_servers": servers})

@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    return templates.TemplateResponse("setup.html", {"request": request})

@app.post("/connect/{server_name}")
async def connect_server(server_name: str):
    """
    Connect to a server from mcp_servers.json.
    This starts a background runner task that keeps the manager context open.
    """
    global _manager_runner_task, _manager_stop_event, mcp_manager, current_server_name

    async with _connect_lock:
        logger.info(f"Connect request for '{server_name}'")

        # If already connected to requested server, return success
        if current_server_name == server_name and mcp_manager is not None:
            return {"status": "already_connected", "server_name": server_name}

        # Stop existing runner if present
        if _manager_runner_task and _manager_stop_event:
            logger.info("Stopping existing manager runner before starting new connection...")
            _manager_stop_event.set()
            try:
                await asyncio.wait_for(_manager_runner_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Existing runner did not stop in time; cancelling task.")
                _manager_runner_task.cancel()
                try:
                    await _manager_runner_task
                except Exception:
                    pass
            finally:
                _manager_runner_task = None
                _manager_stop_event = None
                mcp_manager = None
                current_server_name = None

        # Load config
        servers = load_existing_servers()
        if server_name not in servers:
            raise HTTPException(status_code=404, detail=f"Server '{server_name}' not found in config (looked in {CONFIG_PATH})")

        server_config = servers[server_name]
        if server_config.get("disabled", False):
            raise HTTPException(status_code=400, detail=f"Server '{server_name}' is disabled in config")

        # Create Config and manager
        try:
            cfg = Config(mcp_servers={server_name: server_config})
        except Exception as e:
            logger.exception("Failed to create Config from server config")
            raise HTTPException(status_code=500, detail=f"Config validation failed: {e}")

        manager = MCPClientManager(cfg)
        stop_ev = asyncio.Event()
        task = asyncio.create_task(_manager_runner(manager, stop_ev, server_name))
        _manager_runner_task = task
        _manager_stop_event = stop_ev

        # Wait briefly for readiness
        try:
            await _wait_for_manager_ready(timeout=12.0)
        except asyncio.TimeoutError:
            logger.exception("Timeout while waiting for manager to become ready")
            # Stop runner and cleanup
            stop_ev.set()
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except Exception:
                pass
            _manager_runner_task = None
            _manager_stop_event = None
            raise HTTPException(status_code=504, detail="Timeout while connecting to server; check server config and logs")

        # Optionally verify capabilities are present (not mandatory)
        try:
            caps = await asyncio.wait_for(mcp_manager.list_formatted_capabilities(), timeout=5.0)
            if not caps or caps.strip() == "No capabilities.":
                logger.warning("Connected but manager reports no capabilities. Server may be healthy but registers no tools/resources.")
        except Exception:
            logger.exception("Failed to list capabilities immediately after connect (non-fatal)")

        logger.info(f"Successfully connected to '{server_name}'")
        return {"status": "connected", "server_name": server_name}

@app.post("/disconnect")
async def disconnect_server():
    """
    Signal the manager runner to stop and await it finishing.
    The runner performs the async-exit in the same task so AnyIO cancel-scopes are properly handled.
    """
    global _manager_runner_task, _manager_stop_event, mcp_manager, current_server_name
    if _manager_runner_task is None or _manager_stop_event is None:
        return {"status": "not_connected"}

    logger.info("Disconnect requested: stopping manager runner.")
    _manager_stop_event.set()
    try:
        await asyncio.wait_for(_manager_runner_task, timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning("Manager runner did not stop in time; cancelling.")
        _manager_runner_task.cancel()
        try:
            await _manager_runner_task
        except Exception:
            pass
    finally:
        _manager_runner_task = None
        _manager_stop_event = None
        mcp_manager = None
        current_server_name = None

    return {"status": "disconnected"}

@app.get("/status")
async def get_status():
    if mcp_manager is None:
        return {"connected": False, "server_name": None}
    try:
        await asyncio.wait_for(mcp_manager.wait_ready(), timeout=3.0)
        return {"connected": True, "server_name": current_server_name, "status": "ready"}
    except asyncio.TimeoutError:
        return {"connected": False, "server_name": current_server_name, "status": "not_ready"}

@app.post("/execute")
async def execute_tool(
    action_type: str = Form(...),
    action_name: str = Form(...),
    arguments: str = Form("{}"),
    manager: MCPClientManager = Depends(get_mcp_manager)
):
    """
    Execute a tool/resource/prompt via the manager.
    'arguments' is a JSON string representing the args dict.
    """
    try:
        args = json.loads(arguments) if arguments.strip() else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in arguments")

    try:
        result = await manager.execute_action({
            "action_type": action_type,
            "action_name": action_name,
            "arguments": args
        })
        return {"status": "success", "result": result, "action_type": action_type, "action_name": action_name}
    except Exception as e:
        logger.exception("Execution failed")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/capabilities")
async def get_capabilities():
    """Return the current server's capabilities as JSON."""
    if mcp_manager is None:
        return {"error": "No server connected"}

    try:
        caps = await asyncio.wait_for(mcp_manager.list_formatted_capabilities(), timeout=10.0)
        return {"capabilities": caps, "server_name": current_server_name}
    except asyncio.TimeoutError:
        return {"error": "Timeout getting capabilities"}
    except Exception as e:
        logger.exception("Error getting capabilities")
        return {"error": str(e)}

@app.get("/schemas")
async def get_schemas():
    """Return detailed schema information for all tools, resources, and prompts."""
    if mcp_manager is None:
        return {"error": "No server connected"}

    try:
        group = getattr(mcp_manager, "group", None)
        if group is None:
            return {"error": "Manager group not available"}

        schemas = {
            "tools": {},
            "resources": {},
            "prompts": {}
        }

        # Get tool schemas
        for name, tool in group.tools.items():
            if hasattr(tool, 'inputSchema') and tool.inputSchema:
                schemas["tools"][name] = {
                    "description": getattr(tool, 'description', ''),
                    "inputSchema": tool.inputSchema
                }

        # Get resource schemas
        for name, resource in group.resources.items():
            schemas["resources"][name] = {
                "description": getattr(resource, 'description', ''),
                "uri": getattr(resource, 'uri', '')
            }

        # Get prompt schemas
        for name, prompt in group.prompts.items():
            schemas["prompts"][name] = {
                "description": getattr(prompt, 'description', ''),
                "arguments": []  # Prompts don't have schemas in the same way
            }

        return {"schemas": schemas, "server_name": current_server_name}
    except Exception as e:
        logger.exception("Error getting schemas")
        return {"error": str(e)}
async def debug_dump():
    """
    Diagnostic endpoint: lists tools/resources/prompts registered in the manager.group.
    Useful to see why capabilities appear empty.
    """
    if mcp_manager is None:
        return {"connected": False, "info": "No manager"}

    group = getattr(mcp_manager, "group", None)
    if group is None:
        return {"connected": True, "info": "Manager exists but group is None"}

    try:
        tools = list(getattr(group, "tools", {}).keys()) if getattr(group, "tools", None) else []
        resources = list(getattr(group, "resources", {}).keys()) if getattr(group, "resources", None) else []
        prompts = list(getattr(group, "prompts", {}).keys()) if getattr(group, "prompts", None) else []
        return {"connected": True, "server": current_server_name, "tools": tools, "resources": resources, "prompts": prompts}
    except Exception as e:
        logger.exception("Debug dump failed")
        return {"error": str(e)}

# Run with `uvicorn mcp_inspector:app --reload`
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mcp_inspector:app", host="127.0.0.1", port=8000, reload=True)
