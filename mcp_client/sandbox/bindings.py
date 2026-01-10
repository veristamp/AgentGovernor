"""
Binding Proxies for Zero-Trust Chassis.

This module creates "fake" binding objects that trap all I/O calls
and route them through the MCPClientManager for policy enforcement
and audit logging.

The LLM-generated code calls these bindings (e.g., `filesystem.list_directory()`),
but the actual execution is trapped and routed through the host.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable, Dict

log = logging.getLogger("sandbox.bindings")


class BindingProxy:
    """
    Proxy object that traps method calls and routes them to MCPClientManager.
    
    When LLM code calls `binding.method(**kwargs)`, this proxy:
    1. Captures the qualified name (e.g., "filesystem.list_directory")
    2. Captures all arguments
    3. Routes the call through the trap function (which calls MCPClientManager)
    4. Returns the result back to the sandbox
    
    This is the "I/O Trap" from the Governed Code Mode architecture.
    """
    
    def __init__(self, server_name: str, trap_fn: Callable[[str, Dict[str, Any]], Awaitable[Any]]):
        """
        Initialize a binding proxy for a specific MCP server.
        
        Args:
            server_name: The server prefix (e.g., "filesystem", "memory")
            trap_fn: Async function that routes calls to MCPClientManager
        """
        self._server = server_name
        self._trap = trap_fn
        log.debug(f"Created BindingProxy for server: {server_name}")
    
    def __getattr__(self, method_name: str):
        """
        Intercept attribute access to create trapped method calls.
        
        When code accesses `binding.method`, we return an async function
        that will trap the call when invoked.
        """
        qualified_name = f"{self._server}.{method_name}"
        
        async def trapped_call(**kwargs) -> Any:
            """
            The actual trapped call that routes to MCPClientManager.
            """
            log.info(f"TRAP: {qualified_name}({list(kwargs.keys())})")
            try:
                result = await self._trap(qualified_name, kwargs)
                log.debug(f"TRAP RESULT: {qualified_name} -> {type(result).__name__}")
                return result
            except Exception as e:
                log.error(f"TRAP ERROR: {qualified_name} raised {type(e).__name__}: {e}")
                raise
        
        return trapped_call
    
    def __repr__(self) -> str:
        return f"<BindingProxy:{self._server}>"


def create_bindings(
    server_names: list[str],
    trap_fn: Callable[[str, Dict[str, Any]], Awaitable[Any]]
) -> Dict[str, BindingProxy]:
    """
    Create binding proxies for a list of MCP servers.
    
    Args:
        server_names: List of server prefixes (e.g., ["filesystem", "memory"])
        trap_fn: Async function that routes calls to MCPClientManager
    
    Returns:
        Dict mapping server names to BindingProxy objects
    
    Example:
        bindings = create_bindings(["filesystem", "memory"], trap_fn)
        # Now in sandbox: await filesystem.list_directory(path=".")
    """
    log.info(f"Creating bindings for servers: {server_names}")
    bindings = {}
    for name in server_names:
        bindings[name] = BindingProxy(name, trap_fn)
    return bindings
