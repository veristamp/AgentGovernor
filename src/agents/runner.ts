import type { LanguageModel } from "ai";
import type { AgentRuntime, RuntimeContext } from "../runtime/factory";
import { createAgentRuntime } from "../runtime/factory";
import type { AgentLoopTool } from "../runtime/types";
import { runGovernedLoop, type GovernedLoopOptions } from "../runtime/loop";
import type { RuntimeIdentity } from "../runtime/middleware";
import { CapabilityRegistry } from "../core/capabilities/registry";
import {
  createCapabilityLoaderTool,
  createCapabilitySearchTool,
} from "../core/capabilities/discovery";
import type { MCPClientManager } from "../core/mcp/manager";
import type { PolicyEngine } from "../core/policy/engine";
import type { SkillRegistry } from "../registry/skills/registry";
import type { ToolRegistry } from "../registry/tools/registry";
import type { WorkflowRegistry } from "../registry/workflows/workflow_registry";
import type { EngramService } from "../core/engram/types";

export type AgentRuntimeDeps = {
  identity: RuntimeIdentity;
  mcp: MCPClientManager;
  policy: PolicyEngine;
  model: LanguageModel;
};

export type CapabilityDeps = {
  toolRegistry?: ToolRegistry;
  skillRegistry?: SkillRegistry;
  workflowRegistry?: WorkflowRegistry;
  engram?: EngramService;
};

export async function createRuntimeWithTools(
  ctx: RuntimeContext,
  tools: AgentLoopTool[],
): Promise<AgentRuntime> {
  const runtime = await createAgentRuntime(ctx, []);
  runtime.tools = [...runtime.tools, ...tools];
  return runtime;
}

export function createCapabilityTools(params: {
  deps: CapabilityDeps;
  mcp: MCPClientManager;
}) {
  const registry = new CapabilityRegistry({
    toolRegistry: params.deps.toolRegistry,
    skillRegistry: params.deps.skillRegistry,
    workflowRegistry: params.deps.workflowRegistry,
    engram: params.deps.engram,
    mcp: params.mcp,
  });
  return [
    createCapabilitySearchTool({ registry }),
    createCapabilityLoaderTool({ registry }),
  ];
}

export async function runAgentLoop<TFinal = string>(
  ctx: RuntimeContext,
  runtime: AgentRuntime,
  system: string,
  user: string,
  options: GovernedLoopOptions,
): Promise<{ final: TFinal; iterations: number; trace: unknown[] }> {
  return await runGovernedLoop<TFinal>(ctx, runtime, system, user, options);
}

export function buildRuntimeContext(deps: AgentRuntimeDeps): RuntimeContext {
  return {
    identity: deps.identity,
    mcp: deps.mcp,
    policy: deps.policy,
    model: deps.model,
  };
}
