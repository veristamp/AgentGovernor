import asyncio
import json
import logging
import os
from typing import Dict, List, Any, Optional, Callable

from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv
# Official MCP imports (no fallback - fails if not available)
from mcp import ClientSession, ClientSessionGroup, types, McpError
from mcp.client.session_group import SseServerParameters, StreamableHttpParameters

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("MCPClientManager")

# Config Models (map to official params)
class StreamableHttpConfig(BaseModel):
    connection_type: str = "streamable_http"
    url: str
    headers: Dict[str, Any] = Field(default_factory=dict)
    timeout: float = 30.0
    sse_read_timeout: float = 300.0
    terminate_on_close: bool = True
    disabled: bool = False

class SseConfig(BaseModel):
    connection_type: str = "sse"
    url: str
    headers: Dict[str, Any] = Field(default_factory=dict)
    timeout: float = 5.0
    sse_read_timeout: float = 300.0
    disabled: bool = False

# Union via dispatch
def parse_server_config(data: Dict[str, Any]) -> BaseModel:
    typ = data.get("connection_type", "streamable_http")
    if typ == "sse": return SseConfig(**data)
    if typ == "streamable_http": return StreamableHttpConfig(**data)
    raise ValueError(f"Unknown type: {typ}")

class Config(BaseModel):
    mcp_servers: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    @classmethod
    def load(cls, server_file: str = "mcp_servers.json") -> "Config":
        load_dotenv()
        if not os.path.exists(server_file):
            logger.warning(f"{server_file} missing.")
            return cls()
        with open(server_file, "r") as f:
            raw = json.load(f)
        validated = {}
        for name, data in raw.items():
            try:
                cfg = parse_server_config(data)
                if not cfg.disabled:
                    validated[name] = cfg.model_dump()
            except ValidationError as e:
                logger.error(f"Invalid config for {name}: {e}")
        return cls(mcp_servers=validated)

# Naming hook (official: avoid collisions)
def default_name_hook(name: str, server_info: types.Implementation) -> str:
    return f"{server_info.name or 'server'}.{name}"

class MCPClientManager:
    """Modular MCP manager using official ClientSessionGroup. Attach to agents via async with."""
    def __init__(self, config: Config, name_hook: Optional[Callable[[str, types.Implementation], str]] = None):
        self.config = config
        self.name_hook = name_hook or default_name_hook
        self.group: Optional[ClientSessionGroup] = None
        self._ready = asyncio.Event()
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        self.group = ClientSessionGroup(component_name_hook=self.name_hook)
        await self.connect_all()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.group:
            try:
                await self.group.__aexit__(exc_type, exc_val, exc_tb)
            except RuntimeError as e:
                if "cancel scope" in str(e):
                    logger.warning(f"MCP library cleanup error (known issue): {e}")
                else:
                    raise
            finally:
                self.group = None
        await self.disconnect_all()

    async def disconnect_all(self):
        """Cleanup any remaining connections."""
        # The ClientSessionGroup handles its own cleanup via __aexit__
        logger.info("All disconnected.")

    async def connect_all(self):
        """Concurrent connect to enabled servers (from our mcp_client_manager.py)."""
        enabled = [(name, cfg) for name, cfg in self.config.mcp_servers.items()]
        if not enabled:
            logger.warning("No servers.")
            self._ready.set()
            return

        async with self._lock:
            tasks = [self._connect_server(name, cfg) for name, cfg in enabled]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success = sum(1 for r in results if isinstance(r, types.Implementation))
            logger.info(f"Connected {success}/{len(enabled)} servers.")
            self._ready.set()

    async def _connect_server(self, name: str, cfg: Dict[str, Any]) -> Optional[types.Implementation]:
        """Connect via official transport (dispatch)."""
        typ = cfg["connection_type"]
        logger.info(f"Connecting {name} ({typ})")
        try:
            if typ == "sse":
                from mcp.client.session_group import SseServerParameters
                params = SseServerParameters(
                    url=cfg["url"], 
                    headers=cfg.get("headers", {}), 
                    timeout=cfg.get("timeout", 5.0), 
                    sse_read_timeout=cfg.get("sse_read_timeout", 300.0)
                )
                session = await self.group.connect_to_server(params)
                server_info = await session.initialize()
                logger.info(f"{name} ready.")
                return server_info
            elif typ == "streamable_http":
                from mcp.client.session_group import StreamableHttpParameters
                params = StreamableHttpParameters(
                    url=cfg["url"],
                    headers=cfg.get("headers", {}),
                    timeout=cfg.get("timeout", 30.0),
                    sse_read_timeout=cfg.get("sse_read_timeout", 300.0),
                    terminate_on_close=cfg.get("terminate_on_close", True)
                )
                session = await self.group.connect_to_server(params)
                server_info = await session.initialize()
                logger.info(f"{name} ready.")
                return server_info
            else:
                raise ValueError(f"Unsupported connection type: {typ}")
        except Exception as e:
            logger.error(f"{name} connect failed: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    async def wait_ready(self):
        """Wait for all healthy (poll caps like our agent_tools.py)."""
        await self._ready.wait()

    # For LLM Prompts (from GG.py/mc3.py)
    async def list_formatted_capabilities(self) -> str:
        """Formatted str: 'Server.Tool: Desc [Args]' for LLM prompts."""
        await self.wait_ready()
        if not self.group:
            return "No capabilities."

        # Official: Aggregate via group attrs (tools/resources/prompts are dicts)
        parts = []
        for cat, items in [("Tools", self.group.tools), ("Resources", self.group.resources), ("Prompts", self.group.prompts)]:
            if items:
                parts.append(f"{cat}:")
                for name, item in items.items():
                    desc = getattr(item, 'description', '') or ''
                    args = ""
                    if cat == "Tools" and hasattr(item, 'inputSchema'):
                        schema = item.inputSchema
                        if isinstance(schema, dict) and 'properties' in schema:
                            props = [f"{k} ({v.get('type', '?')}{' req' if k in schema.get('required', []) else ''})" for k, v in schema['properties'].items()]
                            args = f" [Args: {', '.join(props)}]"
                    parts.append(f"  {name}: {desc}{args}")
        return "\n".join(parts)

    # For Agent Execution (from mc3.py/agent_tools.py)
    async def execute_action(self, action: Dict[str, Any]) -> str:
        """Execute tool/resource/prompt from JSON plan. Returns str output."""
        await self.wait_ready()
        typ = action.get("action_type")
        name = action.get("action_name")  # Namespaced via hook
        args = action.get("arguments", {})

        if typ not in ("tool", "resource", "prompt") or not self.group:
            return f"Error: Invalid '{typ}' or no group."

        try:
            if typ == "tool":
                result = await self.group.call_tool(name, args=args)
                return result.content[0].text if result.content else "No output."
            elif typ == "resource":
                result = await self.group.read_resource(name)
                content = result.content.decode('utf-8') if result.content else ""
                return content[:500] + "..." if len(content) > 500 else content
            elif typ == "prompt":
                result = await self.group.get_prompt(name, args=args)
                texts = [c.text for msg in result.messages for c in msg.content if hasattr(c, 'text')]
                return " ".join(texts) or "No content."
        except McpError as e:
            return f"Error: {e.data.message}"
        except Exception as e:
            logger.error(f"Execute failed: {e}")
            return f"Error: {str(e)}"