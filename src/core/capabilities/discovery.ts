import type { SkillRegistry } from "../../registry/skills/registry";
import type { ToolRegistry } from "../../registry/tools/registry";
import type { WorkflowRegistry } from "../../registry/workflows/workflow_registry";
import type { AgentLoopTool, AgentLoopToolContext } from "../../runtime/types";
import type { EngramService } from "../engram/types";
import type { MCPClientManager } from "../mcp/manager";
import { getRolePermissionsAsync, matchesPermission } from "../policy/roles";
import { CapabilityRegistry } from "./registry";

export interface CapabilitySearchOptions {
	engram?: EngramService;
	toolRegistry?: ToolRegistry;
	skillRegistry?: SkillRegistry;
	workflowRegistry?: WorkflowRegistry;
	mcp?: MCPClientManager;
	registry?: CapabilityRegistry;
}

/**
 * Create Capability Search Tool
 *
 * This is the "Switch-Brain" entry point for the Agent:
 * 1. Search Engram for relevant capabilities (Tools, Skills, Workflows)
 * 2. Apply Policy Filtering (Gate 2)
 * 3. Return lightweight pointers for dynamic loading
 *
 * The key insight: The Agent doesn't get a static list of tools.
 * It DISCOVERS capabilities on-demand via the graph.
 */
export function createCapabilitySearchTool(
	options: CapabilitySearchOptions,
): AgentLoopTool {
	return {
		name: "capability_search",
		description:
			"Search for available Tools, Skills, and Workflows via the Engram Graph. " +
			"Use this to discover what capabilities are available for a task. " +
			"Returns pointers - use system.load_tool to activate a capability.",
		inputSchema: {
			type: "object",
			properties: {
				query: {
					type: "string",
					description:
						"Natural language description of what you need (e.g., 'file operations', 'authentication')",
				},
				limit: {
					type: "number",
					description: "Max results (default: 5)",
				},
				types: {
					type: "array",
					items: { type: "string" },
					description: "Filter by type: 'tool', 'skill', 'workflow' (optional)",
				},
			},
			required: ["query"],
		},
		execute: async (
			args: Record<string, unknown>,
			ctx: AgentLoopToolContext,
		) => {
			const query = String(args.query || "");
			const limit = Number(args.limit || 5);
			const typeFilter = args.types as string[] | undefined;
			const registry =
				options.registry ||
				new CapabilityRegistry({
					engram: options.engram,
					toolRegistry: options.toolRegistry,
					skillRegistry: options.skillRegistry,
					workflowRegistry: options.workflowRegistry,
					mcp: options.mcp,
				});
			const identity = { orgId: ctx.orgId, roles: ctx.roles ?? [] };
			const result = await registry.search(query, identity, {
				limit,
				types: typeFilter,
			});
			return {
				capabilities: result.capabilities,
				totalFound: result.totalFound,
				hint: "Use system.load_capability to activate tools or inspect skills/workflows",
			};
		},
	};
}

/**
 * Create Capability Loader Tool
 *
 * Dynamically loads a capability into the agent's context.
 * This is how the Agent "acquires" new abilities during execution.
 */
export function createCapabilityLoaderTool(
	options: CapabilitySearchOptions,
): AgentLoopTool {
	return {
		name: "system.load_capability",
		description:
			"Load a capability (Tool, Skill, or Workflow) into your context. " +
			"Use this after finding a capability with 'capability_search'. " +
			"Returns the full definition including input schema.",
		inputSchema: {
			type: "object",
			properties: {
				capabilityId: {
					type: "string",
					description:
						"The capability ID (e.g., 'tools:filesystem.read_file', 'skills:auth.login')",
				},
			},
			required: ["capabilityId"],
		},
		execute: async (
			args: Record<string, unknown>,
			ctx: AgentLoopToolContext,
		) => {
			const capabilityId = String(args.capabilityId);
			const registry =
				options.registry ||
				new CapabilityRegistry({
					engram: options.engram,
					toolRegistry: options.toolRegistry,
					skillRegistry: options.skillRegistry,
					workflowRegistry: options.workflowRegistry,
					mcp: options.mcp,
				});
			const identity = { orgId: ctx.orgId, roles: ctx.roles ?? [] };
			return registry.load(capabilityId, identity);
		},
	};
}

/**
 * Create Hub-Hop Discovery Tool
 *
 * Enables the Agent to discover related capabilities via shared concepts.
 * This is the "associative memory" pattern.
 */
export function createHubHopTool(
	options: CapabilitySearchOptions,
): AgentLoopTool {
	return {
		name: "capability_discover",
		description:
			"Discover related capabilities via shared concepts. " +
			"Given a starting capability, finds others that share similar concepts. " +
			"Useful for finding alternatives or related functionality.",
		inputSchema: {
			type: "object",
			properties: {
				fromCapability: {
					type: "string",
					description: "Starting capability ID or file path",
				},
				minSharedConcepts: {
					type: "number",
					description: "Minimum shared concepts (default: 2)",
				},
				limit: {
					type: "number",
					description: "Max results (default: 5)",
				},
			},
			required: ["fromCapability"],
		},
		execute: async (
			args: Record<string, unknown>,
			ctx: AgentLoopToolContext,
		) => {
			if (!options.engram) {
				return {
					error: "Engram not available for discovery",
				};
			}

			const fromCapability = String(args.fromCapability);
			const minShared = Number(args.minSharedConcepts) || 2;
			const limit = Number(args.limit) || 5;

			// 1. Get the starting node
			const startNode = await options.engram.inspect(fromCapability);
			if (!startNode || !startNode.nodePointer) {
				return {
					error: `Capability not found: ${fromCapability}`,
					hint: "Provide a valid capability ID or file path",
				};
			}

			// 2. Hub-Hop to find related
			const related = await options.engram.hubHop(
				startNode.nodePointer.id,
				minShared,
				limit * 2, // Get more for filtering
			);

			// 3. Policy filter
			const identity = {
				orgId: ctx.orgId,
				roles: ctx.roles ?? [],
			};
			const isAdmin = identity.roles.includes("mcp:admin");
			const permissions = isAdmin
				? null
				: await getRolePermissionsAsync(identity.roles, identity.orgId);

			const filtered = related.filter((r) => {
				if (isAdmin) return true;
				if (!permissions) return false;
				return (
					matchesPermission(permissions, r.relatedDocUrl) ||
					matchesPermission(permissions, "*")
				);
			});

			return {
				startedFrom: fromCapability,
				related: filtered.slice(0, limit).map((r) => ({
					id: r.relatedDocUrl,
					nodeId: r.relatedChunkId,
					sharedConcepts: r.sharedConcepts,
					relevance: r.sharedConceptCount,
				})),
				sharedConceptsUsed: startNode.relatedConcepts?.slice(0, 5),
			};
		},
	};
}

/**
 * Bundle all capability discovery tools
 */
export function createCapabilityTools(
	options: CapabilitySearchOptions,
): AgentLoopTool[] {
	return [
		createCapabilitySearchTool(options),
		createCapabilityLoaderTool(options),
		createHubHopTool(options),
	];
}
