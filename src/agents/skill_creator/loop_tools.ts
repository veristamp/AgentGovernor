import type { AgentLoopTool } from "../../runtime/types";

export function createSkillCreatorLoopTools(params: {
  planState: { plan: string; execution_graph?: unknown };
}): AgentLoopTool[] {
  return [
    {
      name: "update_plan",
      description:
        "Persist the current plan/execution graph state (for iterative refinement).",
      inputSchema: {
        type: "object",
        properties: {
          plan: { type: "string" },
          execution_graph: { type: "object" },
        },
        required: ["plan"],
      },
      async execute(args: Record<string, unknown>) {
        const plan = String(args.plan || "").trim();
        if (!plan) throw new Error("plan is required");
        params.planState.plan = plan;
        if (args.execution_graph) {
          params.planState.execution_graph = args.execution_graph;
        }
        return { ok: true };
      },
    },
  ];
}
