from __future__ import annotations
import asyncio, logging, traceback
from typing import Any, Dict, Optional, Callable
import json
import urllib
from mcp import ClientSessionGroup, McpError
from mcp.client.session_group import (
    StdioServerParameters,
    StreamableHttpParameters,
    SseServerParameters,
)

from .config import Config, parse_server_config
from .naming import default_server_prefix
from .indices import CapabilityIndex
from .utils import format_capabilities
from .exceptions import ExecutionError
logger = logging.getLogger("MCPClientManager")

class MCPClientManager:
    """
    Thin MCP client manager.
    - Connects multiple servers (stdio/streamable_http/sse)
    - Indexes capabilities with deterministic prefixes
    - Routes actions (tool/resource/prompt) to the correct session
    """
    def __init__(
        self,
        config: Config,
        server_prefix_hook: Optional[Callable[[str, Any], str]] = None,
    ) -> None:
        self.config = config
        self._prefix_hook = server_prefix_hook or default_server_prefix
        self._group: Optional[ClientSessionGroup] = None
        self._ready = asyncio.Event()
        self._lock = asyncio.Lock()
        self._index = CapabilityIndex()

    def _handle_ui_resource(self, ui_data: Dict[str, Any]) -> str:
        """Enhanced handler for UIResource - uses secure iframe for HTML rendering."""
        uri = ui_data.get("uri", "unknown")
        mime_type = ui_data.get("mimeType", "")
        print(f"[DEBUG] Handling UI resource for URI: {uri}")
        if mime_type == "text/html" and "text" in ui_data:
            html_content = ui_data["text"]
            # Use iframe for security (similar to mcp-ui)
            return f'<iframe srcdoc="{html_content}" sandbox="allow-scripts" width="100%" height="400" style="border:1px solid #ccc;"></iframe>'
        elif mime_type == "text/uri-list" and "text" in ui_data:
            url = ui_data["text"]
            # Use iframe for external URLs
            return f'<iframe src="{url}" width="100%" height="400" style="border:1px solid #ccc;"></iframe>'
        return f"[UI Resource] Unsupported. URI: {uri}, MIME: {mime_type}"
        # Note: For full interactivity (e.g., handling actions from iframe), integrate with a frontend like React using @mcp-ui/client

    async def __aenter__(self) -> "MCPClientManager":
        self._group = ClientSessionGroup()
        await self._connect_all()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if self._group:
                await self._group.__aexit__(exc_type, exc, tb)
        except RuntimeError as e:
            if "cancel scope" in str(e):
                logger.warning(f"MCP cleanup warning: {e}")
            else:
                raise
        finally:
            self._group = None
        self._ready.clear()

    async def wait_ready(self) -> None:
        await self._ready.wait()

    # ---------- Connections ----------

    async def _connect_all(self) -> None:
        servers = list(self.config.mcp_servers.items())
        if not servers:
            logger.info("No MCP servers configured.")
            self._ready.set()
            return

        async with self._lock:
            tasks = [self._connect_one(name, cfg) for name, cfg in servers]
            await asyncio.gather(*tasks)
            logger.info(f"Connected {len(self._index.prefix_to_session)}/{len(servers)} servers.")
            self._ready.set()

    async def _connect_one(self, server_key: str, raw_cfg: Dict[str, Any]) -> None:
        cfg = parse_server_config(raw_cfg)
        assert self._group is not None
        try:
            if cfg.connection_type == "stdio":
                params = StdioServerParameters(
                    command=cfg.command,
                    args=cfg.args,
                    cwd=cfg.cwd,
                    env=cfg.env,
                )
            elif cfg.connection_type == "streamable_http":
                params = StreamableHttpParameters(
                    url=cfg.url,
                    headers=cfg.headers,
                    timeout=cfg.timeout,
                    sse_read_timeout=cfg.sse_read_timeout,
                    terminate_on_close=cfg.terminate_on_close,
                )
            elif cfg.connection_type == "sse":
                params = SseServerParameters(
                    url=cfg.url,
                    headers=cfg.headers,
                    timeout=cfg.timeout,
                    sse_read_timeout=cfg.sse_read_timeout,
                )
            else:
                raise ValueError(f"Unsupported connection_type: {cfg.connection_type}")

            session = await self._group.connect_to_server(params)
            server_info = await session.initialize()
            prefix = self._prefix_hook(server_key, server_info)
            # list capabilities
            tools = await session.list_tools()
            resources = await session.list_resources()
            prompts = await session.list_prompts()
            # index
            self._index.register_session(prefix, session, tools.tools, resources.resources, prompts.prompts)
            logger.info(f"{server_key} ready as prefix '{prefix}'.")
        except Exception as e:
            logger.error(f"{server_key} connect failed: {e}")
            logger.error("Traceback: " + traceback.format_exc())

    # ---------- Capabilities ----------

    def get_capabilities(self) -> Dict[str, Dict[str, Any]]:
        t, r, p = self._index.all()
        return {"tools": dict(t), "resources": dict(r), "prompts": dict(p)}

    async def list_formatted_capabilities(self) -> str:
        await self.wait_ready()
        t, r, p = self._index.all()
        return format_capabilities(t, r, p)

    # ---------- Execution ----------

    async def execute_action(self, action: Dict[str, Any]) -> str:
        """
        action = {
          "action_type": "tool" | "resource" | "prompt",
          "action_name": "<qualified-or-bare-capability-name>",
          "arguments": {...}
        }
        """
        await self.wait_ready()
        kind = action.get("action_type")
        name = action.get("action_name")
        args = action.get("arguments", {}) or {}

        if kind not in ("tool", "resource", "prompt") or not name:
            raise ExecutionError("Invalid action payload")

        session = self._index.resolve_session(name)
        if session is None:
            raise ExecutionError(f"No active session for capability '{name}'")

        # Our capabilities are stored as "prefix.cap". Servers register "cap" only.
        base = name.split(".", 1)[-1]

        try:
            if kind == "tool":
                result = await session.call_tool(base, arguments=args)
                parts: list[str] = []
                content = result if isinstance(result, list) else (getattr(result, "content", None) or [])
                for block in content:
                    print(f"[DEBUG] Processing block: {block}")
                    print(f"[DEBUG] Processing block with type: {block.get('type') if hasattr(block, 'get') else getattr(block, 'type', None)}")
                    # Check if this is a UIResource
                    block_type = (block.get("type") if hasattr(block, "get") else getattr(block, "type", None))
                    if block_type == "resource":
                        # Handle UIResource
                        ui_data = (block.get("resource") if hasattr(block, "get") else getattr(block, "resource", None))
                        if ui_data:
                            parts.append(self._handle_ui_resource(ui_data))
                            continue
                    # common case: TextContent(text=...)
                    txt = (block.get("text") if hasattr(block, "get") else getattr(block, "text", None))
                    if txt:
                        # Check if this text contains a UI resource
                        if '"mimeType"' in txt:
                            try:
                                parsed = json.loads(txt)
                                if parsed.get("resource", {}).get("mimeType") == "text/html":
                                    resource_data = parsed["resource"]
                                    parts.append(self._handle_ui_resource(resource_data))
                                    continue
                            except json.JSONDecodeError:
                                pass
                        parts.append(txt)
                        continue
                    # rare: dict-like or other
                    try:
                        s = str(block)
                        if s and s != "None":
                            parts.append(s)
                    except Exception:
                        pass
                out = "\n".join(parts).strip()
                return {"output": out or "No output.", "blocks": content}
            if kind == "resource":
                # Resolve resource meta from our index, then ALWAYS read by URI
                resources = self.get_capabilities().get("resources", {})
                meta = resources.get(name) or resources.get(base)
                if not meta:
                    return f"Resource '{name}' not found."
                uri = getattr(meta, "uri", None) or getattr(meta, "name", None)
                if not uri:
                    return f"Resource '{name}' has no readable URI."

                res = await session.read_resource(uri)
                # normalize result to text
                if hasattr(res, "text") and res.text is not None:
                    content = res.text
                elif hasattr(res, "content") and isinstance(res.content, (bytes, bytearray)):
                    content = res.content.decode("utf-8", errors="replace")
                else:
                    content = str(res)
                content = content or ""
                return content if len(content) <= 2000 else (content[:2000] + " ...[truncated]")
            if kind == "prompt":
                # render the prompt with arguments (not just list)
                prompt = await session.get_prompt(base, arguments=args)
                texts = []
                for msg in getattr(prompt, "messages", []) or []:
                    for c in getattr(msg, "content", []) or []:
                        if hasattr(c, "text") and c.text:
                            texts.append(c.text)
                return "\n".join(texts) if texts else "No content."
        except McpError as e:
            # expose code/message if available
            code = getattr(e, "code", "unknown")
            data = getattr(e, "data", None)
            msg = getattr(getattr(e, "data", None), "message", None) or getattr(e, "message", str(e))
            return f"Error ({code}): {msg}" + (f" | data={data}" if data else "")
        except Exception as e:
            return f"Error: {str(e)}"
