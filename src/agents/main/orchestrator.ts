import { getMCPClientManager } from "../../core/mcp/manager";
import type { PolicyEngine } from "../../core/policy/engine";
import { WorkflowRegistry } from "../../registry/workflows";
import type { RuntimeIdentity } from "../../runtime/middleware";
import { createMissionRuntime } from "../../runtime/mission";
import { createTaskAgentTool } from "../../runtime/sub_agent";
import type { AgentLoopTool } from "../../runtime/types";
import {
  buildRuntimeContext,
  createRuntimeWithTools,
  runAgentLoop,
} from "../runner";
import { SkillCreatorAgent } from "../skill_creator/skill_creator_agent";
import type { LlmClient } from "./llm_client";
import { SkillCatalog } from "./skill_catalog";
import type { AgentRequest, AgentResult } from "./types";

const ORCHESTRATOR_TOOLS = {
  "workflows.search": {
    description:
      "Search for existing workflows that might match the user's goal",
  },
  "skills.search": {
    description:
      "Search for skills/capabilities if no direct workflow is found",
  },
  "skill.create": {
    description: "Create a new reusable skill (Python code) to solve a task.",
  },
  "task.run": {
    description:
      "Run a sub-agent to explore or solve a focused sub-task and return a summary",
  },
};

export class OrchestratorAgent {
  private catalog: SkillCatalog;
  private workflows: WorkflowRegistry;

  constructor(
    private options: {
      llm: LlmClient;
      policy: PolicyEngine;
      model: string;
      scoutModel?: string;
    },
  ) {
    this.catalog = new SkillCatalog(options.policy);
    this.workflows = new WorkflowRegistry();
  }

  async run(request: AgentRequest): Promise<AgentResult> {
    const { createOpenAI } = await import("@ai-sdk/openai");
    const openai = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
    const model = openai(this.options.model);
    const scoutModel = openai(this.options.scoutModel || this.options.model);
    const mcp = await getMCPClientManager();

    const baseIdentity: RuntimeIdentity = {
      ...request.identity,
      id: `orchestrator-${Date.now()}`,
      type: "agent",
      missionId: request.identity.missionId || `miss_${Date.now()}`,
      sessionId: request.identity.sessionId || `sess_${Date.now()}`,
    };
    const mission = createMissionRuntime(baseIdentity);
    const runtimeIdentity = mission.identity;
    const workflows = this.workflows;
    const catalog = this.catalog;
    const options = this.options;

    const taskTool = createTaskAgentTool({
      identity: runtimeIdentity,
      mcp,
      policy: this.options.policy,
      model: scoutModel,
      maxIterations: 8,
    });

    const tools: AgentLoopTool[] = [
      {
        name: "workflows.search",
        description: ORCHESTRATOR_TOOLS["workflows.search"].description,
        inputSchema: {
          type: "object",
          properties: {
            query: { type: "string" },
            limit: { type: "number" },
          },
          required: ["query"],
        },
        async execute(args: Record<string, unknown>) {
          const query = String(args.query || "");
          const limit =
            typeof args.limit === "number"
              ? args.limit
              : Number(args.limit || 5);
          return await workflows.search(
            query,
            [],
            request.identity.orgId,
            Math.min(limit || 5, 10),
          );
        },
      },
      {
        name: "skills.search",
        description: ORCHESTRATOR_TOOLS["skills.search"].description,
        inputSchema: {
          type: "object",
          properties: {
            query: { type: "string" },
            limit: { type: "number" },
          },
          required: ["query"],
        },
        async execute(args: Record<string, unknown>) {
          const query = String(args.query || "");
          const limit =
            typeof args.limit === "number"
              ? args.limit
              : Number(args.limit || 5);
          return await catalog.search(
            query,
            request.identity,
            Math.min(limit || 5, 10),
          );
        },
      },
      {
        name: "skill.create",
        description: ORCHESTRATOR_TOOLS["skill.create"].description,
        inputSchema: {
          type: "object",
          properties: {
            goal: { type: "string" },
          },
          required: ["goal"],
        },
        async execute(args: Record<string, unknown>) {
          const goal = String(args.goal || "");
          console.log(`[Orchestrator] Spawning Skill Creator for: ${goal}`);
          const creator = new SkillCreatorAgent(
            { llm: options.llm, policy: options.policy },
            { model: options.model },
          );
          const result = await creator.run(
            {
              goal,
              requester: {
                id: request.identity.id ?? "unknown-orchestrator",
                roles: request.identity.roles,
                orgId: request.identity.orgId,
                missionId: runtimeIdentity.missionId,
                sessionId: runtimeIdentity.sessionId,
              },
            },
            { mcp },
          );
          return {
            skillRef: result.skillRef,
            summary: result.draft.summary,
          };
        },
      },
      taskTool,
    ];

    const ctx = buildRuntimeContext({
      identity: runtimeIdentity,
      mcp,
      policy: this.options.policy,
      model,
    });
    const runtime = await createRuntimeWithTools(ctx, tools);

    const systemPrompt = `You are the Orchestrator. Your job is to route the user's request to the best execution path.

STRATEGY:
1. First, CALL 'workflows.search' to check for existing workflows.
2. IF workflows found: summarize the best match and return code or summary.
3. IF NO workflows found:
   - CALL 'skills.search'.
4. IF NO skills found:
   - CALL 'skill.create' to generate a new skill.
   - OR CALL 'task.run' if the task is exploratory.

CRITICAL: You MUST keep calling tools until you have a solution. Do not stop at an empty search result.

Return JSON with keys: code, selectedSkills (string[]), plan.`;

    const { final, iterations } = await runAgentLoop<{
      code?: string;
      selectedSkills?: string[];
      plan?: string;
      result?: string;
    }>(ctx, runtime, systemPrompt, request.goal, {
      maxIterations: 8,
      runId: `orchestrator-run-${Date.now()}`,
      sessionId: runtimeIdentity.sessionId,
      runType: "workflow",
      validateFinal: async (value) => {
        if (typeof value === "string") {
          return { ok: true, value: { code: value } };
        }
        if (value && typeof value === "object") {
          const record = value as Record<string, unknown>;
          const code =
            typeof record.code === "string"
              ? record.code
              : typeof record.result === "string"
                ? record.result
                : "";
          if (!code) return { ok: false, error: "Missing code" };
          return { ok: true, value: { ...record, code } };
        }
        return { ok: false, error: "Invalid result" };
      },
    });

    const resolved = final as {
      code?: string;
      selectedSkills?: string[];
      plan?: string;
      result?: string;
    };
    const code =
      typeof resolved.code === "string"
        ? resolved.code
        : typeof resolved.result === "string"
          ? resolved.result
          : "";
    const selectedSkills = Array.isArray(resolved.selectedSkills)
      ? resolved.selectedSkills.filter((s) => typeof s === "string")
      : [];
    const plan = typeof resolved.plan === "string" ? resolved.plan : undefined;

    return {
      code: code || "",
      selectedSkills,
      prompt: `${systemPrompt}\n\n${request.goal}`,
      repairAttempts: iterations,
      plan,
    };
  }
}
