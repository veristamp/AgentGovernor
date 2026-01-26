import type { LanguageModel } from "ai";
import type { EngramService } from "../../core/engram/types";
import type { MCPClientManager } from "../../core/mcp/manager";
import type { PolicyEngine } from "../../core/policy/engine";
import type { ToolRegistry } from "../../registry/tools/registry";
import { type RuntimeContext } from "../../runtime/factory";
import type { RuntimeIdentity } from "../../runtime/middleware";
import {
  buildRuntimeContext,
  createCapabilityTools,
  createRuntimeWithTools,
  runAgentLoop,
} from "../runner";

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
You do NOT have all tools loaded. You must discover and load them on demand.

# Architecture
1. **Discovery**: Use 'capability_search' to find tools, skills, and workflows.
2. **Loading**: Use 'system.load_capability' to load a tool into your context.
3. **Execution**: Once loaded, use the tool in the NEXT step.

# Protocol
1. Analyze the User Goal.
2. SEARCH for tools/skills/workflows.
3. LOAD the tools you need using 'system.load_capability'.
5. EXECUTE the task using the loaded tools.
`;

export async function runRecursiveAgent(
  goal: string,
  config: RecursiveAgentConfig,
) {
  // 1. Create Tools
  const capabilityTools = createCapabilityTools({
    deps: { engram: config.engram, toolRegistry: config.toolRegistry },
    mcp: config.mcp,
  });

  // 2. Create Runtime
  const ctx: RuntimeContext = buildRuntimeContext({
    identity: config.identity,
    mcp: config.mcp,
    policy: config.policy,
    model: config.model,
  });

  const runtime = await createRuntimeWithTools(ctx, capabilityTools);

  // 3. Run Loop
  return await runAgentLoop(ctx, runtime, RECURSIVE_AGENT_PROMPT, goal, {
    maxIterations: 10,
    sessionId: config.identity.sessionId,
    runType: "tool",
  });
}
