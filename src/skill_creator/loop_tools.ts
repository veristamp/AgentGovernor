import type { AgentIdentityScope } from "../agent/types";
import type { AgentLoopTool, AgentLoopToolContext } from "../agent_loop/types";
import { getRolePermissionsAsync, matchesPermission } from "../policy/roles";
import type { SkillRegistry, SkillSummary } from "../skills_registry/registry";
import type { ToolRegistry } from "../tool_registry/registry";
import type { ToolDescriptor } from "../tool_registry/types";

export interface RegistrySearchArgs {
	kind: "tool" | "skill";
	query: string;
	limit?: number;
}

export interface RegistryGetToolArgs {
	qualifiedName: string;
}

export interface RegistryGetSkillArgs {
	skillRef: string;
}

export interface UpdatePlanArgs {
	plan: string;
	execution_graph?: unknown;
}

function compactTool(
	t: ToolDescriptor,
): Pick<
	ToolDescriptor,
	"qualifiedName" | "description" | "serverPrefix" | "name"
> {
	return {
		qualifiedName: t.qualifiedName,
		description: t.description,
		serverPrefix: t.serverPrefix,
		name: t.name,
	};
}

function compactSkill(
	s: SkillSummary,
): Pick<
	SkillSummary,
	"skillRef" | "skillId" | "version" | "description" | "interfaces"
> {
	return {
		skillRef: s.skillRef,
		skillId: s.skillId,
		version: s.version,
		description: s.description,
		interfaces: s.interfaces,
	};
}

async function isToolAllowed(
	toolName: string,
	identity: AgentIdentityScope,
): Promise<boolean> {
	if (identity.roles?.includes("mcp:admin")) return true;
	const permissions = await getRolePermissionsAsync(
		identity.roles ?? [],
		identity.orgId,
	);
	if (matchesPermission(permissions, "*")) return true;
	if (matchesPermission(permissions, toolName)) return true;
	return false;
}

async function isSkillAllowed(
	skillRef: string,
	identity: AgentIdentityScope,
): Promise<boolean> {
	if (identity.roles?.includes("mcp:admin")) return true;
	const permissions = await getRolePermissionsAsync(
		identity.roles ?? [],
		identity.orgId,
	);
	if (matchesPermission(permissions, "*")) return true;
	if (matchesPermission(permissions, skillRef)) return true;
	return false;
}

function toIdentity(ctx: AgentLoopToolContext): AgentIdentityScope {
	return {
		orgId: ctx.orgId,
		roles: ctx.roles ?? [],
		scopes: ctx.scopes ?? [],
	};
}

export function createSkillCreatorLoopTools(params: {
	toolRegistry: ToolRegistry;
	skillRegistry: SkillRegistry;
	planState: { plan: string; execution_graph?: unknown };
}): AgentLoopTool[] {
	return [
		{
			name: "registry.search",
			description: "Search tools or skills by natural language query.",
			inputSchema: {
				type: "object",
				properties: {
					kind: { type: "string", enum: ["tool", "skill"] },
					query: { type: "string" },
					limit: { type: "number" },
				},
				required: ["kind", "query"],
			},
			async execute(args: Record<string, unknown>, ctx: AgentLoopToolContext) {
				const identity = toIdentity(ctx);
				const kind = String(args.kind || "") as RegistrySearchArgs["kind"];
				const query = String(args.query || "");
				const limit =
					typeof args.limit === "number" ? args.limit : Number(args.limit || 8);

				if (kind === "tool") {
					const results = await params.toolRegistry.search(
						query,
						Math.min(limit || 8, 25),
					);
					const filtered: ToolDescriptor[] = [];
					for (const tool of results) {
						if (await isToolAllowed(tool.qualifiedName, identity)) {
							filtered.push(tool);
						}
					}
					return {
						kind,
						query,
						results: filtered.map(compactTool),
					};
				}

				if (kind === "skill") {
					const results = await params.skillRegistry.search(
						query,
						Math.min(limit || 8, 25),
					);
					const filtered: SkillSummary[] = [];
					for (const skill of results) {
						if (await isSkillAllowed(skill.skillRef, identity)) {
							filtered.push(skill);
						}
					}
					return {
						kind,
						query,
						results: filtered.map(compactSkill),
					};
				}

				throw new Error(`Invalid kind: ${kind}`);
			},
		},
		{
			name: "registry.get_tool",
			description: "Fetch a full tool schema by qualifiedName.",
			inputSchema: {
				type: "object",
				properties: {
					qualifiedName: { type: "string" },
				},
				required: ["qualifiedName"],
			},
			async execute(args: Record<string, unknown>, ctx: AgentLoopToolContext) {
				const identity = toIdentity(ctx);
				const qualifiedName = String(args.qualifiedName || "");
				if (!(await isToolAllowed(qualifiedName, identity))) {
					throw new Error(`Forbidden tool: ${qualifiedName}`);
				}
				const tool = await params.toolRegistry.get(qualifiedName);
				if (!tool) return { tool: null };
				return { tool };
			},
		},
		{
			name: "registry.get_skill",
			description:
				"Fetch full skill signature (including examples) by skillRef.",
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
				if (!(await isSkillAllowed(skillRef, identity))) {
					throw new Error(`Forbidden skill: ${skillRef}`);
				}
				const skill = await params.skillRegistry.inspect(skillRef);
				if (!skill) return { skill: null };
				const rawDeps = (skill as { dependencies?: unknown }).dependencies;
				const dependencies = Array.isArray(rawDeps)
					? rawDeps.filter((d): d is string => typeof d === "string")
					: [];
				return {
					skill: {
						skillRef: skill.skillRef,
						description: skill.description,
						interfaces: skill.interfaces,
						examples: skill.examples ?? [],
						dependencies,
					},
				};
			},
		},
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
