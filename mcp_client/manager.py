from __future__ import annotations

import asyncio
import json
import logging
import traceback
from typing import Any, Dict, Optional, Callable, Tuple, List

from mcp import ClientSessionGroup, McpError
from mcp.client.session_group import (
    StdioServerParameters,
    StreamableHttpParameters,
    SseServerParameters,
)

from mcp_client.config import Config, parse_server_config
from mcp_client.naming import default_server_prefix
from mcp_client.indices import CapabilityIndex
from mcp_client.utils import format_capabilities
from mcp_client.exceptions import ExecutionError

logger = logging.getLogger("MCPClientManager")


def _is_method_not_found(err: BaseException) -> bool:
    """
    Detect "method not found" across MCP SDKs/servers.
    - JSON-RPC code -32601
    - string codes like "MethodNotFound"/"methodNotFound"
    - message fallback containing the phrase
    """
    try:
        # mcp.shared.exceptions.McpError often carries .code and .message/data
        code = getattr(err, "code", None)
        if isinstance(code, int) and code == -32601:
            return True
        if isinstance(code, str) and code.lower() in {"methodnotfound", "method_not_found", "methodnotfounderror"}:
            return True
        msg = getattr(err, "message", None) or str(err)
        if isinstance(msg, str) and "method not found" in msg.lower():
            return True
    except Exception:
        pass
    return False


class MCPClientManager:
    """
    Thin MCP client manager.
    - Connects multiple servers (stdio / streamable_http / sse)
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

    # ---------- UI Resource handling ----------

    def _handle_ui_resource(self, ui):
        uri = ui.get("uri","unknown")
        mt  = ui.get("mimeType","")
        if mt == "text/html" and "text" in ui:
            html = (ui["text"]
                    .replace("&","&amp;")
                    .replace("<","&lt;")
                    .replace('"',"&quot;"))
            return (
            '<iframe srcdoc="{h}" sandbox="allow-scripts" '
            'referrerpolicy="no-referrer" title="UIResource {u}" '
            'style="border:1px solid #ccc;width:100%;height:420px"></iframe>'
            ).format(h=html,u=uri)
        if mt == "text/uri-list" and "text" in ui:
            url = ui["text"].splitlines()[0].strip()
            return (
            '<iframe src="{url}" sandbox="" referrerpolicy="no-referrer" '
            'title="UIResource {u}" style="border:1px solid #ccc;'
            'width:100%;height:420px"></iframe>'
            ).format(url=url,u=uri)
        return f"[UI Resource] Unsupported. URI: {uri}, MIME: {mt}"


    # ---------- Async CM lifecycle ----------

    async def __aenter__(self) -> "MCPClientManager":
        # Ensure ClientSessionGroup runs with its context manager
        self._group = await ClientSessionGroup().__aenter__()
        await self._connect_all()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if self._group:
                await self._group.__aexit__(exc_type, exc, tb)
        except RuntimeError as e:
            # Trio cancel-scope mismatch can surface on some platforms; demote to warning.
            if "cancel scope" in str(e).lower():
                logger.debug("MCP cleanup note: %s", e)
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
            logger.info(
                "Connected %d/%d servers.",
                len(self._index.prefix_to_session),
                len(servers),
            )
            self._ready.set()

    async def _connect_one(self, server_key: str, raw_cfg: Dict[str, Any]) -> None:
        """
        Connect to a single server and index its capabilities. Non-fatal on optional
        feature endpoints that return MethodNotFound (e.g., prompts/resources).
        """
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
                sse_params_dict = {
                    "url": cfg.url,
                    "headers": cfg.headers
                }
                # Only add timeouts if they are explicitly set
                if cfg.timeout is not None:
                    sse_params_dict["timeout"] = cfg.timeout
                if cfg.sse_read_timeout is not None:
                    sse_params_dict["sse_read_timeout"] = cfg.sse_read_timeout
                
                # Pass the dynamically built dict
                params = SseServerParameters(**sse_params_dict)
            else:
                raise ValueError(f"Unsupported connection_type: {cfg.connection_type}")

            session = await self._group.connect_to_server(params)
            server_info = await session.initialize()
            logger.info("%s server: impl=%s version=%s",
                        server_key,
                        getattr(server_info, "implementation", None),
                        getattr(server_info, "version", None))
            prefix = self._prefix_hook(server_key, server_info)

            # list_tools() is mandatory per MCP expectations
            tools = await session.list_tools()

            try:
                resources = await session.list_resources()
                resources_list = resources.resources
            except McpError as e:
                if _is_method_not_found(e):
                    logger.warning("Could not fetch resources from %s: Method not found", server_key)
                    resources_list = []
                else:
                    raise

            try:
                prompts = await session.list_prompts()
                prompts_list = prompts.prompts
            except McpError as e:
                if _is_method_not_found(e):
                    logger.warning("Could not fetch prompts from %s: Method not found", server_key)
                    prompts_list = []
                else:
                    raise

            self._index.register_session(
                prefix,
                session,
                tools.tools,
                resources_list,
                prompts_list,
            )
            logger.info("%s ready as prefix '%s'.", server_key, prefix)

        except Exception as e:
            logger.error("%s connect failed: %s", server_key, e)
            logger.error("Traceback: %s", traceback.format_exc())

    # ---------- Capabilities ----------

    def get_capabilities(self) -> Dict[str, Dict[str, Any]]:
        """
        Return raw capability maps:
          { "tools": {...}, "resources": {...}, "prompts": {...} }
        """
        t, r, p = self._index.all()
        return {"tools": dict(t), "resources": dict(r), "prompts": dict(p)}

    async def list_formatted_capabilities(self) -> str:
        """
        Pretty-printed, human readable capability catalog.
        """
        await self.wait_ready()
        t, r, p = self._index.all()
        return format_capabilities(t, r, p)

    # ---------- Execution ----------

    async def execute_action(self, action: Dict[str, Any]) -> Any:
        """
        Execute a tool/resource/prompt by (optionally qualified) name.

        Expected action shape:
        {
          "action_type": "tool" | "resource" | "prompt",
          "action_name": "<qualified-or-bare-capability-name>",
          "arguments": {...}
        }

        Returns:
          - tool: {"output": str, "blocks": list}
          - resource: str (content)
          - prompt: str (rendered text)
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

        # Stored as "prefix.cap"; server expects bare "cap"
        base = name.split(".", 1)[-1]

        try:
            if kind == "tool":
                # Call the tool once
                call = session.call_tool(base, arguments=args)
                result = await asyncio.wait_for(call, timeout=args.get("_timeout", 60))
                
                # Result is a CallToolResult with .content (list of content blocks)
                content = getattr(result, "content", []) or []
                if not content:
                    # Fallback: maybe result is already the content list
                    content = result if isinstance(result, list) else []

                parts: List[str] = []
                structured_output_found = False

                try:
                    for block in content:
                        bget = block.get if hasattr(block, "get") else lambda k, d=None: getattr(block, k, d)
                        struct_content = bget("structuredContent")
                        if isinstance(struct_content, dict):
                            if "result" in struct_content:
                                parts.append(str(struct_content["result"]))
                                structured_output_found = True
                                break
                            parts.append(json.dumps(struct_content))
                            structured_output_found = True
                            break
                except Exception:
                    structured_output_found = False

                if not structured_output_found:
                    for block in content:
                        bget = block.get if hasattr(block, "get") else lambda k, d=None: getattr(block, k, d)
                        btype = bget("type")

                        if btype == "resource":
                            ui_data = bget("resource")
                            if ui_data:
                                parts.append(self._handle_ui_resource(ui_data))
                            continue

                        txt = bget("text")
                        if isinstance(txt, str) and txt:
                            if '"mimeType"' in txt:
                                try:
                                    parsed = json.loads(txt)
                                    res = parsed.get("resource") if isinstance(parsed, dict) else None
                                    if res and res.get("mimeType") == "text/html":
                                        parts.append(self._handle_ui_resource(res))
                                        continue
                                except json.JSONDecodeError:
                                    pass
                            parts.append(txt)
                            continue

                        try:
                            s = str(block)
                            if s and s != "None":
                                parts.append(s)
                        except Exception:
                            pass

                out = "\n".join(parts).strip()
                return out or "No output."

            if kind == "resource":
                # Resolve meta and ALWAYS read by URI
                resources = self.get_capabilities().get("resources", {})
                meta = resources.get(name) or resources.get(base)
                if not meta:
                    return f"Resource '{name}' not found."

                uri = getattr(meta, "uri", None) or getattr(meta, "name", None)
                if not uri:
                    return f"Resource '{name}' has no readable URI."

                res = await session.read_resource(uri)
                if hasattr(res, "text") and res.text is not None:
                    content = res.text
                elif hasattr(res, "content") and isinstance(res.content, (bytes, bytearray)):
                    content = res.content.decode("utf-8", errors="replace")
                else:
                    content = str(res) if res is not None else ""

                return content if len(content) <= 2000 else (content[:2000] + " ...[truncated]")

            if kind == "prompt":
                prompt = await session.get_prompt(base, arguments=args)
                texts: List[str] = []
                for msg in getattr(prompt, "messages", []) or []:
                    for c in getattr(msg, "content", []) or []:
                        t = getattr(c, "text", None)
                        if t:
                            texts.append(t)
                return "\n".join(texts) if texts else "No content."

        except McpError as e:
            code = getattr(e, "code", "unknown")
            data = getattr(e, "data", None)
            msg = getattr(getattr(e, "data", None), "message", None) or getattr(e, "message", str(e))
            return f"Error ({code}): {msg}" + (f" | data={data}" if data else "")
        except Exception as e:
            return f"Error: {str(e)}"
