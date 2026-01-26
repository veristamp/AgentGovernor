import {
	getRolePermissionsAsync,
	matchesPermission,
} from "../../core/policy/roles";
import type { AgentLoopTool, AgentLoopToolContext } from "../../runtime/types";
import type { EngramServiceImpl } from "../engram/service";
import type { EngramNode, NodePointer } from "../engram/types";

export interface CapabilitySearchOptions {
	engram: EngramServiceImpl;
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

			// 1. Search via Engram (Graph)
			const result = await options.engram.search(query, limit * 2);

			// 2. Apply Policy Filtering (Gate 2)
			const identity = {
				orgId: ctx.orgId,
				roles: ctx.roles ?? [],
			};

			const allowedNodes: EngramNode[] = [];

			// Optimization: If admin, skip granular checks
			const isAdmin = identity.roles.includes("mcp:admin");

			if (isAdmin) {
				allowedNodes.push(...result.nodes);
			} else {
				const permissions = await getRolePermissionsAsync(
					identity.roles,
					identity.orgId,
				);

				for (const node of result.nodes) {
					// Normalize ID for policy check
					// Policy expects "skills:auth.login" or "tools:fs.read"
					if (
						matchesPermission(permissions, node.id) ||
						matchesPermission(permissions, "*")
					) {
						allowedNodes.push(node);
					}
				}
			}

			// 3. Apply type filter if specified
			let filteredNodes = allowedNodes;
			if (typeFilter && typeFilter.length > 0) {
				filteredNodes = allowedNodes.filter((n) => typeFilter.includes(n.type));
			}

			// 4. Format for LLM consumption
			return {
				capabilities: filteredNodes.slice(0, limit).map((n) => ({
					id: n.id,
					type: n.type,
					name: n.name,
					description: n.description,
					// Include structure hints
					inputs: n.structure?.inputs ? Object.keys(n.structure.inputs) : [],
					// Include pointer for kb.load
					nodeId: n.nodePointer?.id,
					tokenCount: n.nodePointer?.tokenCount || 0,
				})),
				relatedConcepts: result.relatedConcepts,
				totalFound: allowedNodes.length,
				hint: "Use system.load_tool to activate a capability, or kb.inspect for more details",
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

			// 1. Get full node details
			const node = await options.engram.inspect(capabilityId);

			if (!node) {
				return {
					error: `Capability not found: ${capabilityId}`,
					hint: "Use capability_search to find available capabilities",
				};
			}

			// 2. Policy check
			const identity = {
				orgId: ctx.orgId,
				roles: ctx.roles ?? [],
			};

			const isAdmin = identity.roles.includes("mcp:admin");
			if (!isAdmin) {
				const permissions = await getRolePermissionsAsync(
					identity.roles,
					identity.orgId,
				);
				if (
					!matchesPermission(permissions, capabilityId) &&
					!matchesPermission(permissions, "*")
				) {
					return {
						error: `Access denied to capability: ${capabilityId}`,
						requiredPermission: capabilityId,
					};
				}
			}

			// 3. Return full capability definition
			return {
				loaded: true,
				capability: {
					id: node.id,
					type: node.type,
					name: node.name,
					description: node.description,
					structure: node.structure,
					relatedConcepts: node.relatedConcepts,
				},
				// Signal to the loop that this capability should be available
				_system_signal: "capability_loaded",
				capabilityId: capabilityId,
			};
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
				return (
					matchesPermission(permissions!, r.relatedDocUrl) ||
					matchesPermission(permissions!, "*")
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
