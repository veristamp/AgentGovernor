import type { LanguageModel } from "ai";
import type { MCPClientManager } from "../mcp-client/manager";
import type { PolicyEngine } from "../policy/engine";
import { type RuntimeIdentity, wrapGovernedModel } from "./middleware";
import type { AgentLoopTool, AgentLoopToolContext } from "./types";

export interface RuntimeContext {
	identity: RuntimeIdentity;
	mcp: MCPClientManager;
	policy: PolicyEngine;
	model: LanguageModel;
}

export interface AgentRuntime {
	model: LanguageModel;
	tools: AgentLoopTool[];
}

/**
 * Agent Runtime Factory
 *
 * Assembles the "User Space" runtime by wrapping the Kernel components (MCP, Policy)
 * into safe, governed interfaces (Tools, Model).
 */
export async function createAgentRuntime(
	ctx: RuntimeContext,
	allowedToolNames: string[],
): Promise<AgentRuntime> {
	// 1. Wrap the model with Governance Middleware
	// This ensures all LLM calls are policy-checked and cached
	const governedModel = wrapGovernedModel(ctx.model, ctx.policy, ctx.identity);

	// 2. Create the Tools (System Calls)
	// We need to resolve the tool definitions from the Kernel (MCP Manager)
	const capabilities = ctx.mcp.getCapabilities();
	const tools: AgentLoopTool[] = [];

	for (const name of allowedToolNames) {
		const toolDef = capabilities.tools.get(name);
		if (!toolDef) {
			console.warn(`[RuntimeFactory] Tool not found: ${name}`);
			continue;
		}

		tools.push({
			name: toolDef.name,
			description: toolDef.description || "",
			inputSchema: toolDef.inputSchema ?? {},
			execute: async (
				args: Record<string, unknown>,
				toolCtx: AgentLoopToolContext,
			) => {
				// The "System Call" to the Kernel
				// We inject the identity from the RuntimeContext, overriding or merging
				// with the tool context if needed.

				// Note: executeAction in MCPClientManager handles the Policy Check (Gate 2)
				return await ctx.mcp.executeAction(
					{
						actionType: "tool",
						actionName: name,
						arguments: args,
					},
					{
						// Pass Identity Context for Policy Check
						identityId: ctx.identity.id,
						orgId: ctx.identity.orgId,
						roles: ctx.identity.roles,
						scopes: ctx.identity.scopes,
						missionId: ctx.identity.sessionId, // Mapping session to mission? or separate?
						// We can pass JWT if we have one, but here we trust the internal call
					},
				);
			},
		});
	}

	return {
		model: governedModel,
		tools,
	};
}
