import type { ToolRegistry } from "../../registry/tools/registry";
import type { AgentLoopTool, AgentLoopToolContext } from "../../runtime/types";
import { CapabilityRegistry } from "./registry";

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
        capabilityId: {
          type: "string",
          description:
            "Capability ID from capability_search (optional, used to resolve tool name)",
        },
      },
      required: [],
    },
    execute: async (
      args: Record<string, unknown>,
      ctx: AgentLoopToolContext,
    ) => {
      const rawName =
        typeof args.toolName === "string" ? args.toolName : undefined;
      const rawId =
        typeof args.capabilityId === "string" ? args.capabilityId : undefined;
      const capabilityId = rawName || rawId || "";
      const registry = new CapabilityRegistry({ toolRegistry });
      const identity = { orgId: ctx.orgId, roles: ctx.roles ?? [] };
      return registry.load(capabilityId, identity);
    },
  };
}
