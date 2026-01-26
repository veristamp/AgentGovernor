import type { LanguageModel } from "ai";
import type { MCPClientManager } from "../core/mcp/manager";
import type { PolicyEngine } from "../core/policy/engine";
import { createAgentRuntime, type RuntimeContext } from "./factory";
import { runGovernedLoop } from "./loop";
import type { RuntimeIdentity } from "./middleware";
import type { TraceEvent } from "./trace";
import { createChildIdentity, createMissionRuntime } from "./mission";
import type { AgentLoopTool } from "./types";

export interface SubAgentRunOptions {
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

export interface TaskAgentToolOptions {
  identity: RuntimeIdentity;
  mcp: MCPClientManager;
  policy: PolicyEngine;
  model: LanguageModel;
  maxIterations?: number;
  defaultTools?: string[];
}

export async function runSubAgent<TFinal = string>(
  options: SubAgentRunOptions,
): Promise<{ final: TFinal; iterations: number; trace: TraceEvent[] }> {
  const ctx: RuntimeContext = {
    identity: options.identity,
    mcp: options.mcp,
    policy: options.policy,
    model: options.model,
  };

  const runtime = await createAgentRuntime(ctx, options.allowedTools);
  return await runGovernedLoop<TFinal>(
    ctx,
    runtime,
    options.system,
    options.user,
    {
      maxIterations: options.maxIterations ?? 10,
      runId: options.runId,
      runType: options.runType || "tool",
      sessionId: options.identity.sessionId,
    },
  );
}

export function createTaskAgentTool(
  options: TaskAgentToolOptions,
): AgentLoopTool {
  return {
    name: "task.run",
    description:
      "Run a sub-agent to handle a focused sub-task. Returns the sub-agent result.",
    inputSchema: {
      type: "object",
      properties: {
        goal: { type: "string" },
        context: { type: "string" },
        system: { type: "string" },
        tools: { type: "array", items: { type: "string" } },
        maxIterations: { type: "number" },
        runType: { type: "string" },
      },
      required: ["goal"],
    },
    execute: async (args: Record<string, unknown>) => {
      const goal = String(args.goal || "").trim();
      const context = typeof args.context === "string" ? args.context : "";
      const systemText =
        typeof args.system === "string"
          ? args.system
          : "You are a focused sub-agent. Solve the task and return a concise result.";
      const toolsArg = Array.isArray(args.tools)
        ? args.tools.filter((t): t is string => typeof t === "string")
        : undefined;
      const maxIterations =
        typeof args.maxIterations === "number"
          ? args.maxIterations
          : options.maxIterations;
      const runType = typeof args.runType === "string" ? args.runType : "tool";

      const parent = createMissionRuntime(options.identity);
      const childIdentity = createChildIdentity(parent, {
        id: `sub-agent-${Date.now()}`,
        sessionId: `sess_${Date.now()}`,
      });

      const allowedTools = toolsArg?.length
        ? toolsArg
        : options.defaultTools?.length
          ? options.defaultTools
          : options.mcp.getToolNames();

      const system = `${systemText}\n\nCONTEXT:\n${context}`.trim();
      const user = `GOAL:\n${goal}`;
      const runId = `task-run-${Date.now()}`;
      const result = await runSubAgent({
        identity: childIdentity,
        mcp: options.mcp,
        policy: options.policy,
        model: options.model,
        system,
        user,
        allowedTools,
        runId,
        maxIterations: maxIterations ?? 8,
        runType: runType as SubAgentRunOptions["runType"],
      });

      return {
        goal,
        result: result.final,
        iterations: result.iterations,
      };
    },
  };
}
