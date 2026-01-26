import type { ToolRegistry } from "../../registry/tools/registry";
import type { AgentLoopTool, AgentLoopToolContext } from "../../runtime/types";
import { getMCPClientManager } from "../mcp/manager";

export function createToolLoader(toolRegistry: ToolRegistry): AgentLoopTool {
	return {
		name: "system.load_tool",
		description:
			"Load a tool dynamically into your context. Use this after finding a tool with 'capability_search'.",
		inputSchema: {
			type: "object",
			properties: {
				toolName: {
					type: "string",
					description:
						"The qualified name of the tool (e.g., 'tools:filesystem.read_file' or 'filesystem.read_file')",
				},
			},
			required: ["toolName"],
		},
		execute: async (
			args: Record<string, unknown>,
			_ctx: AgentLoopToolContext,
		) => {
			const rawName = String(args.toolName);
			// Strip prefixes if present
			const name = rawName.replace(/^tools:/, "").replace(/^skills:/, ""); // strict loading of tools for now

			const mcp = await getMCPClientManager();
			const tools = mcp.getCapabilities().tools;

			// Check if tool exists in MCP manager (which connects to everything)
			// In our current architecture, MCPManager has ALL tools connected at startup.
			// The "Dynamic Loading" is purely about exposing it to the LLM.

			// If the tool is NOT in the current runtime's exposed list, we need to signal the loop to add it.
			// We return a special signal or rely on the loop to observe side effects?

			// Since `execute` returns a value to the LLM, we can return "Tool Loaded".
			// But the *Loop* needs to know to update the `tools` definition for the next API call.

			// We can return a special object that the Loop detects?
			// Or we can pass a callback to `createToolLoader`?

			return {
				_system_signal: "load_tool",
				toolName: name,
			};
		},
	};
}
