import asyncio
import json
import logging
import os
from typing import Dict, List, Any, Optional, Callable

from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv
# Official MCP imports (no fallback - fails if not available)
from mcp import ClientSession, ClientSessionGroup, types, McpError, StdioServerParameters
from mcp.client.session_group import SseServerParameters, StreamableHttpParameters

# UI handling imports
import webbrowser
import tempfile
import base64

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

class StdioConfig(BaseModel):
    connection_type: str = "stdio"
    command: str
    args: List[str] = Field(default_factory=list)
    cwd: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)
    timeout: float = 5.0
    disabled: bool = False

# Union via dispatch
def parse_server_config(data: Dict[str, Any]) -> BaseModel:
    typ = data.get("connection_type", "streamable_http")
    if typ == "sse": return SseConfig(**data)
    if typ == "streamable_http": return StreamableHttpConfig(**data)
    if typ == "stdio": return StdioConfig(**data)
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
            elif typ == "stdio":
                params = StdioServerParameters(
                    command=cfg["command"],
                    args=cfg.get("args", []),
                    cwd=cfg.get("cwd"),
                    env=cfg.get("env", {})
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
        """Execute tool/resource/prompt from JSON plan. Returns str output and handles UI resources."""
        await self.wait_ready()
        typ = action.get("action_type")
        name = action.get("action_name")  # Namespaced via hook
        args = action.get("arguments", {})

        if typ not in ("tool", "resource", "prompt") or not self.group:
            return f"Error: Invalid '{typ}' or no group."

        try:
            if typ == "tool":
                result = await self.group.call_tool(name, args=args)
                outputs = []

                # Handle each content block in the result
                for content_block in result.content:
                    if hasattr(content_block, 'type'):
                        block_type = content_block.type

                        if block_type == "text":
                            # Handle TextContent
                            text_content = content_block.text
                            outputs.append(text_content)

                            # Check if this text contains UI resource information
                            if 'UI Preview:' in text_content and 'ui://' in text_content:
                                # Extract UI resource URI from text
                                lines = text_content.split('\n')
                                for line in lines:
                                    if line.startswith('UI Preview:'):
                                        ui_uri = line.replace('UI Preview:', '').strip()
                                        outputs.append(f"UI Resource: {ui_uri}")
                                        # For demo purposes, we'll show the URI but not auto-open
                                        # In a real implementation, you might parse and handle the UI resource here

                        elif block_type == "resource":
                            # Handle EmbeddedResource
                            resource = content_block.resource
                            if isinstance(resource, dict):
                                uri = resource.get('uri', '')
                                mime_type = resource.get('mimeType', '')

                                if uri.startswith('ui://'):
                                    outputs.append(f"Received UI Resource: {uri}")

                                    if 'text/html' in mime_type: # For 'rawHtml' type
                                        html_content = resource.get('text', '')
                                        if not html_content and 'blob' in resource:
                                            import base64
                                            html_content = base64.b64decode(resource['blob']).decode('utf-8')

                                        # Save to a temporary file and open in browser
                                        import tempfile
                                        import webbrowser
                                        with tempfile.NamedTemporaryFile('w', delete=False, suffix='.html', encoding='utf-8') as f:
                                            f.write(html_content)
                                            webbrowser.open(f'file://{f.name}')
                                        outputs.append("-> Opened local preview in your browser.")

                                    elif 'text/uri-list' in mime_type: # For 'externalUrl' type
                                        url = resource.get('text', '')
                                        webbrowser.open(url)
                                        outputs.append(f"-> Opened external URL in your browser: {url}")
                                else:
                                    # For other resource types, just mention the URI
                                    outputs.append(f"Resource: {uri}")
                            else:
                                outputs.append(f"Resource content: {resource}")

                        elif block_type == "image":
                            # Handle ImageContent
                            image_data = content_block.data if hasattr(content_block, 'data') else ""
                            outputs.append(f"[Image content: {len(image_data)} bytes]")

                        elif block_type == "audio":
                            # Handle AudioContent
                            audio_data = content_block.data if hasattr(content_block, 'data') else ""
                            outputs.append(f"[Audio content: {len(audio_data)} bytes]")

                return "\n".join(outputs) if outputs else "No output."

            elif typ == "resource":
                result = await self.group.read_resource(name)
                # Handle different types of resource content
                if hasattr(result, 'contents') and result.contents:
                    content_parts = []
                    for content in result.contents:
                        if hasattr(content, 'text'):
                            content_parts.append(content.text)
                        elif hasattr(content, 'blob'):
                            import base64
                            decoded = base64.b64decode(content.blob).decode('utf-8', errors='ignore')
                            content_parts.append(decoded)
                        else:
                            content_parts.append(str(content))
                    return "\n".join(content_parts)[:500] + "..." if len("\n".join(content_parts)) > 500 else "\n".join(content_parts)
                else:
                    return "No content in resource."

            elif typ == "prompt":
                result = await self.group.get_prompt(name, args=args)
                texts = []
                if hasattr(result, 'messages'):
                    for msg in result.messages:
                        if hasattr(msg, 'content'):
                            for c in msg.content:
                                if hasattr(c, 'text'):
                                    texts.append(c.text)
                return " ".join(texts) or "No content."
        except McpError as e:
            return f"Error: {e.data.message}"
        except Exception as e:
            logger.error(f"Execute failed: {e}")
            return f"Error: {str(e)}"