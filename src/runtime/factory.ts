import type { LanguageModelV3 } from "@ai-sdk/provider";
import { type LanguageModel, wrapLanguageModel } from "ai";
import type { MCPClientManager } from "../core/mcp/manager";
import type { PolicyEngine } from "../core/policy/engine";
import {
	cacheMiddleware,
	governanceMiddleware,
	type RuntimeIdentity,
} from "./middleware";
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

export interface RuntimeOptions {
	/** Enable LLM response caching */
	enableCache?: boolean;
	/** Cache TTL in milliseconds */
	cacheTtlMs?: number;
}

/**
 * Agent Runtime Factory
 *
 * Creates runtime with AI SDK v6 middleware pattern using wrapLanguageModel.
 */
export async function createAgentRuntime(
	ctx: RuntimeContext,
	allowedToolNames: string[],
	options: RuntimeOptions = {},
): Promise<AgentRuntime> {
	// Cast model to LanguageModelV3 for middleware compatibility
	const v3Model = ctx.model as unknown as LanguageModelV3;

	// Apply governance middleware
	let wrappedModel = wrapLanguageModel({
		model: v3Model,
		middleware: governanceMiddleware({
			policy: ctx.policy,
			identity: ctx.identity,
		}),
	});

	// Apply caching middleware if enabled
	if (options.enableCache) {
		wrappedModel = wrapLanguageModel({
			model: wrappedModel,
			middleware: cacheMiddleware({ ttlMs: options.cacheTtlMs }),
		});
	}

	// 3. Create the Tools (System Calls)
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
				_toolCtx: AgentLoopToolContext,
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
						missionId: ctx.identity.missionId,
						sessionId: ctx.identity.sessionId,
						// We can pass JWT if we have one, but here we trust the internal call
					},
				);
			},
		});
	}

	return {
		model: wrappedModel,
		tools,
	};
}
