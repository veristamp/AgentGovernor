import type { WorkflowRegistry } from "../../registry/workflows";
import type { AgentLoopTool } from "../../runtime/types";
import type { AgentSkillSummary, AgentWorkflowExample } from "./types";

export interface WorkflowLoopState {
  skills: AgentSkillSummary[];
  workflowExamples: AgentWorkflowExample[];
  plan: string;
  executionGraph?: unknown;
}

export function createWorkflowLoopTools(params: {
  state: WorkflowLoopState;
}): AgentLoopTool[] {
  return [
    {
      name: "update_plan",
      description:
        "Update the current workflow plan and optional execution graph (for UI-driven workflow builder later).",
      inputSchema: {
        type: "object",
        properties: {
          plan: { type: "string" },
          execution_graph: { type: "object" },
        },
        required: ["plan"],
      },
      async execute(args: Record<string, unknown>) {
        params.state.plan = String(args.plan || "").trim();
        if (args.execution_graph) {
          params.state.executionGraph = args.execution_graph;
        }
        return { ok: true };
      },
    },
  ];
}
