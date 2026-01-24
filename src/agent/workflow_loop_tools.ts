import type { AgentLoopTool, AgentLoopToolContext } from "../agent_loop/types";
import type { WorkflowRegistry } from "../workflow_registry";
import type { SkillCatalog } from "./skill_catalog";
import type {
	AgentIdentityScope,
	AgentSkillSummary,
	AgentWorkflowExample,
} from "./types";

export interface WorkflowLoopState {
	skills: AgentSkillSummary[];
	workflowExamples: AgentWorkflowExample[];
	plan: string;
	executionGraph?: unknown;
}

function toIdentity(ctx: AgentLoopToolContext): AgentIdentityScope {
	return {
		orgId: ctx.orgId,
		roles: ctx.roles ?? [],
		scopes: ctx.scopes ?? [],
	};
}

function summarizeSkills(
	skills: AgentSkillSummary[],
	limit: number = 8,
): string[] {
	return skills
		.slice(0, limit)
		.map((s) => `${s.skillRef}: ${s.description || ""}`.trim());
}

export function createWorkflowLoopTools(params: {
	catalog: SkillCatalog;
	workflows: WorkflowRegistry;
	state: WorkflowLoopState;
}): AgentLoopTool[] {
	return [
		{
			name: "skills.search",
			description:
				"Search allowed skills by natural language query and optionally add them to the current context.",
			inputSchema: {
				type: "object",
				properties: {
					query: { type: "string" },
					limit: { type: "number" },
					add_to_context: { type: "boolean" },
				},
				required: ["query"],
			},
			async execute(args: Record<string, unknown>, ctx: AgentLoopToolContext) {
				const identity = toIdentity(ctx);
				const query = String(args.query || "");
				const limit =
					typeof args.limit === "number" ? args.limit : Number(args.limit || 5);
				const add =
					typeof args.add_to_context === "boolean" ? args.add_to_context : true;
				const found = await params.catalog.search(
					query,
					identity,
					Math.min(limit || 5, 25),
				);
				const added: AgentSkillSummary[] = [];
				if (add) {
					const existing = new Set(params.state.skills.map((s) => s.skillRef));
					for (const s of found) {
						if (!existing.has(s.skillRef)) {
							params.state.skills.push(s);
							existing.add(s.skillRef);
							added.push(s);
						}
					}
				}
				return {
					query,
					results: found,
					added_count: added.length,
					context_skills: summarizeSkills(params.state.skills, 12),
				};
			},
		},
		{
			name: "skills.get",
			description:
				"Inspect a single skill and return its interfaces and examples.",
			inputSchema: {
				type: "object",
				properties: {
					skillRef: { type: "string" },
				},
				required: ["skillRef"],
			},
			async execute(args: Record<string, unknown>, ctx: AgentLoopToolContext) {
				const identity = toIdentity(ctx);
				const skillRef = String(args.skillRef || "");
				const detail = await params.catalog.inspect(skillRef, identity);
				return { skill: detail };
			},
		},
		{
			name: "workflows.search",
			description:
				"Search previously saved workflows that match the goal and are compatible with the current skill context.",
			inputSchema: {
				type: "object",
				properties: {
					query: { type: "string" },
					limit: { type: "number" },
				},
				required: ["query"],
			},
			async execute(args: Record<string, unknown>, ctx: AgentLoopToolContext) {
				const query = String(args.query || "");
				const limit =
					typeof args.limit === "number" ? args.limit : Number(args.limit || 3);
				const skillRefs = params.state.skills.map((s) => s.skillRef);
				const orgId = ctx.orgId;
				const results = await params.workflows.search(
					query,
					skillRefs,
					orgId,
					Math.min(limit || 3, 10),
				);
				const mapped = results.map((entry) => ({
					id: entry.metadata.id,
					goal: entry.metadata.goal,
					summary: entry.metadata.summary,
					skills: entry.metadata.skills,
				}));
				params.state.workflowExamples = mapped;
				return {
					query,
					results: mapped,
				};
			},
		},
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
