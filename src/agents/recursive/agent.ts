import type { LanguageModel } from "ai";
import { createToolLoader } from "../../core/capabilities/loader";
import { createEngramTools } from "../../core/engram/mcp";
import type { EngramService } from "../../core/engram/types";
import type { MCPClientManager } from "../../core/mcp/manager";
import type { PolicyEngine } from "../../core/policy/engine";
import type { ToolRegistry } from "../../registry/tools/registry";
import { createAgentRuntime, type RuntimeContext } from "../../runtime/factory";
import { runGovernedLoop } from "../../runtime/loop";
import type { RuntimeIdentity } from "../../runtime/middleware";

export interface RecursiveAgentConfig {
	identity: RuntimeIdentity;
	mcp: MCPClientManager;
	policy: PolicyEngine;
	model: LanguageModel;
	engram: EngramService;
	toolRegistry: ToolRegistry;
}

export const RECURSIVE_AGENT_PROMPT = `
You are a Recursive Agent (RLM).
You do NOT have all tools loaded. You must find them in the Engram.

# Architecture
1. **Engram**: Your structural memory. Use 'kb.search' to find capabilities.
2. **Recursion**: If you find a complex tool/skill, you can inspect it with 'kb.inspect'.
3. **Execution**: Once you know the tool name, use 'system.load_tool' to load it. Then you can use it in the NEXT step.

# Protocol
1. Analyze the User Goal.
2. SEARCH Engram for tools/skills.
3. INSPECT promising nodes.
4. LOAD the tools you need using 'system.load_tool'.
5. EXECUTE the task using the loaded tools.
`;

export async function runRecursiveAgent(
	goal: string,
	config: RecursiveAgentConfig,
) {
	// 1. Create Tools
	// The agent gets standard tools + Engram tools + Loader
	const engramTools = createEngramTools(config.engram);
	const loaderTool = createToolLoader(config.toolRegistry);

	// 2. Create Runtime
	const ctx: RuntimeContext = {
		identity: config.identity,
		mcp: config.mcp,
		policy: config.policy,
		model: config.model,
	};

	const runtime = await createAgentRuntime(ctx, []);
	runtime.tools.push(...engramTools, loaderTool);

	// 3. Run Loop
	return await runGovernedLoop(ctx, runtime, RECURSIVE_AGENT_PROMPT, goal, {
		maxIterations: 10,
		sessionId: config.identity.sessionId,
	});
}
