import type { LanguageModel } from "ai";
import type { MCPClientManager } from "../core/mcp/manager";
import type { PolicyEngine } from "../core/policy/engine";
import { createAgentSpawner, type AgentConfig, type SpawnOptions } from "../executor";
import type { RuntimeIdentity } from "./middleware";
import type { TraceEvent } from "./trace";
import type { AgentLoopTool } from "./types";

interface SubAgentOptions {
  identity: RuntimeIdentity;
  mcp: MCPClientManager;
  policy: PolicyEngine;
  model: LanguageModel;
  system: string;
  user: string;
  allowedTools: string[];
  runId?: string;
  maxIterations?: number;
  runType?: "workflow" | "skill" | "tool" | "research";
}

/** Validate sub-agent options for security */
function validateSubAgentOptions(opts: SubAgentOptions): void {
  if (!opts.identity?.id) throw new Error("Invalid identity: missing id");
  if (!opts.mcp) throw new Error("Invalid MCP client");
  if (!opts.policy) throw new Error("Invalid policy engine");
  if (!opts.model) throw new Error("Invalid model");
  if (opts.maxIterations && (opts.maxIterations < 1 || opts.maxIterations > 100)) {
    throw new Error("Invalid maxIterations: must be between 1 and 100");
  }
  // Sanitize system prompt length
  if (opts.system.length > 50000) throw new Error("System prompt too long (max 50k)");
  if (opts.user.length > 100000) throw new Error("User prompt too long (max 100k)");
}

/** Run a sub-agent with the new spawner - streamlined and secure */
export async function runSubAgent<TFinal = string>(
  options: SubAgentOptions
): Promise<{ final: TFinal; iterations: number; trace: TraceEvent[] }> {
  validateSubAgentOptions(options);

  const config: AgentConfig = {
    id: `sub-${Date.now()}`,
    name: "Sub Agent",
    description: "Focused task agent",
    systemPrompt: options.system,
    allowedTools: options.allowedTools,
    maxIterations: options.maxIterations ?? 10,
    runType: options.runType || "tool",
  };

  const spawner = createAgentSpawner();
  const handle = await spawner.spawn(
    config,
    { identity: options.identity, mcp: options.mcp, policy: options.policy, model: options.model },
    { runId: options.runId, sessionId: options.identity.sessionId, inheritMission: true }
  );

  const result = await handle.run(options.user);
  
  return {
    final: result.final as TFinal,
    iterations: result.iterations,
    trace: result.trace as TraceEvent[],
  };
}

/** Create a task.run tool - streamlined */
export function createTaskAgentTool(
  identity: RuntimeIdentity,
  mcp: MCPClientManager,
  policy: PolicyEngine,
  model: LanguageModel,
  maxIterations = 8,
  defaultTools?: string[]
): AgentLoopTool {
  return {
    name: "task.run",
    description: "Run a focused sub-agent to handle a sub-task",
    inputSchema: {
      type: "object",
      properties: {
        goal: { type: "string", maxLength: 5000 },
        context: { type: "string", maxLength: 10000 },
        system: { type: "string", maxLength: 10000 },
        tools: { type: "array", items: { type: "string" } },
        maxIterations: { type: "number", minimum: 1, maximum: 50 },
        runType: { type: "string", enum: ["workflow", "skill", "tool", "research"] },
      },
      required: ["goal"],
    },
    execute: async (args: Record<string, unknown>) => {
      const goal = String(args.goal || "").trim();
      if (!goal) throw new Error("Goal is required");
      if (goal.length > 5000) throw new Error("Goal too long (max 5000 chars)");

      const context = String(args.context || "").slice(0, 10000);
      const system = String(args.system || "You are a focused sub-agent. Solve the task and return a concise result.").slice(0, 10000);
      const tools = Array.isArray(args.tools) 
        ? args.tools.filter((t): t is string => typeof t === "string")
        : defaultTools ?? mcp.getToolNames();
      
      const iterations = typeof args.maxIterations === "number" 
        ? Math.min(Math.max(args.maxIterations, 1), 50)
        : maxIterations;

      const result = await runSubAgent({
        identity,
        mcp,
        policy,
        model,
        system: `${system}\n\nCONTEXT:\n${context}`.trim(),
        user: `GOAL:\n${goal}`,
        allowedTools: tools,
        runId: `task-${Date.now()}`,
        maxIterations: iterations,
        runType: (args.runType as any) || "tool",
      });

      return { goal, result: result.final, iterations: result.iterations };
    },
  };
}

/** Spawn skill creator - specialized helper */
export async function spawnSkillCreator(
  identity: RuntimeIdentity,
  mcp: MCPClientManager,
  policy: PolicyEngine,
  model: LanguageModel,
  goal: string,
  constraints?: string[]
): Promise<{ final: unknown; iterations: number; trace: TraceEvent[] }> {
  if (!goal || goal.length > 5000) throw new Error("Invalid goal");
  
  const { skillCreatorConfig } = await import("../agents/skill-creator");
  const spawner = createAgentSpawner();
  
  const handle = await spawner.spawn(
    skillCreatorConfig,
    { identity, mcp, policy, model },
    { runId: `creator-${Date.now()}`, inheritMission: true }
  );

  return handle.run({ goal, constraints: constraints ?? [], requester: { id: identity.id, roles: identity.roles ?? [] } });
}
