import type { AgentLoopTool } from "../../runtime/types";
import type { EngramService, NodePointer } from "./types";

/**
 * Create Engram MCP Tools for the Agent Loop
 *
 * These tools implement the "Switch-Brain" architecture:
 * - kb.search: Semantic search (returns pointers, not content)
 * - kb.inspect: Get node structure/metadata
 * - kb.structure: Get file hierarchy (O(1) lookup)
 * - kb.load: Load actual content (the "page fault")
 * - kb.hop: Hub-Hop to find related documents
 * - kb.concepts: Search by concept names
 * - kb.function: Load a specific function
 *
 * The key pattern: Return STRUCTURE first, load CONTENT on-demand.
 * This prevents context stuffing and enables surgical precision.
 */
export function createEngramTools(engram: EngramService): AgentLoopTool[] {
	return [
		// =====================================================================
		// SEARCH (Semantic Discovery)
		// =====================================================================
		{
			name: "kb.search",
			description:
				"Search the structural memory (Engram) for capabilities, code, and documentation. " +
				"Returns lightweight pointers - use kb.load to get actual content.",
			inputSchema: {
				type: "object",
				properties: {
					query: {
						type: "string",
						description:
							"Natural language query (e.g., 'authentication', 'file handling')",
					},
					limit: {
						type: "number",
						description: "Maximum results (default: 5)",
					},
				},
				required: ["query"],
			},
			execute: async (args: Record<string, unknown>) => {
				const result = await engram.search(
					String(args.query),
					Number(args.limit) || 5,
				);
				return {
					nodes: result.nodes.map((n) => ({
						id: n.id,
						type: n.type,
						name: n.name,
						description: n.description,
						// Include pointer for kb.load if available
						nodeId: n.nodePointer?.id,
						tokenCount: n.nodePointer?.tokenCount || 0,
					})),
					relatedConcepts: result.relatedConcepts,
					totalTokens: result.totalTokens || 0,
				};
			},
		},

		// =====================================================================
		// INSPECT (Node Metadata)
		// =====================================================================
		{
			name: "kb.inspect",
			description:
				"Inspect the structure (inputs, outputs, dependencies) of a specific node. " +
				"Returns AST-level metadata WITHOUT loading full content.",
			inputSchema: {
				type: "object",
				properties: {
					nodeId: {
						type: "string",
						description:
							"Node URI (e.g., 'tools:filesystem.read', '/path/to/file.ts')",
					},
				},
				required: ["nodeId"],
			},
			execute: async (args: Record<string, unknown>) => {
				const node = await engram.inspect(String(args.nodeId));
				if (!node) {
					return { error: `Node not found: ${args.nodeId}` };
				}
				return {
					id: node.id,
					type: node.type,
					name: node.name,
					description: node.description,
					structure: node.structure,
					relatedConcepts: node.relatedConcepts,
					// Pointer for loading content
					nodeId: node.nodePointer?.id,
					lineRange: node.nodePointer?.lineRange,
				};
			},
		},

		// =====================================================================
		// STRUCTURE (File Hierarchy - O(1) Lookup)
		// =====================================================================
		{
			name: "kb.structure",
			description:
				"Get the structural hierarchy of a file or directory WITHOUT loading content. " +
				"This is the 'page table lookup' - O(1) and zero tokens. " +
				"Use this to understand file organization before loading specific parts.",
			inputSchema: {
				type: "object",
				properties: {
					filePattern: {
						type: "string",
						description:
							"File path or pattern (e.g., 'auth.ts', 'src/components')",
					},
					maxDepth: {
						type: "number",
						description: "How deep to traverse hierarchy (default: 3)",
					},
				},
				required: ["filePattern"],
			},
			execute: async (args: Record<string, unknown>) => {
				const result = await engram.getFileStructure(
					String(args.filePattern),
					Number(args.maxDepth) || 3,
				);
				return {
					nodes: result.nodes.map(formatPointer),
					totalTokens: result.totalTokens,
					path: result.pathDescription,
					hint: "Use kb.load with nodeIds to load actual content",
				};
			},
		},

		// =====================================================================
		// LOAD (Content - The "Page Fault")
		// =====================================================================
		{
			name: "kb.load",
			description:
				"Load actual content for specific nodes. This is the expensive operation. " +
				"Use kb.structure or kb.search first to identify which nodes you need, " +
				"then load only those. This prevents context stuffing.",
			inputSchema: {
				type: "object",
				properties: {
					nodeIds: {
						type: "array",
						items: { type: "number" },
						description:
							"Array of node IDs to load (from kb.structure or kb.search)",
					},
					includeFlow: {
						type: "boolean",
						description:
							"Also load prev/next chunks for context (default: false)",
					},
				},
				required: ["nodeIds"],
			},
			execute: async (args: Record<string, unknown>) => {
				const nodeIds = args.nodeIds as number[];
				const includeFlow = Boolean(args.includeFlow);

				const contents = await engram.loadContent(nodeIds, includeFlow);

				// Format for LLM consumption
				const results: Record<string, unknown>[] = [];
				for (const [id, data] of Object.entries(contents)) {
					results.push({
						nodeId: Number(id),
						content: data.content,
						type: data.type,
						file: data.docUrl,
						lines: `${data.lineStart}-${data.lineEnd}`,
						...(includeFlow && data.prevContent
							? { prevContent: `${data.prevContent.slice(0, 200)}...` }
							: {}),
						...(includeFlow && data.nextContent
							? { nextContent: `${data.nextContent.slice(0, 200)}...` }
							: {}),
					});
				}

				return { loaded: results };
			},
		},

		// =====================================================================
		// HOP (Hub-Hop - Find Related via Concepts)
		// =====================================================================
		{
			name: "kb.hop",
			description:
				"Find related documents via shared concepts (the Hub-Hop pattern). " +
				"Given a starting node, finds other nodes that mention the same concepts. " +
				"Useful for discovering related code, docs, or examples.",
			inputSchema: {
				type: "object",
				properties: {
					sourceId: {
						type: "number",
						description: "Starting node ID",
					},
					minSharedConcepts: {
						type: "number",
						description:
							"Minimum shared concepts to consider related (default: 2)",
					},
					limit: {
						type: "number",
						description: "Maximum results (default: 10)",
					},
				},
				required: ["sourceId"],
			},
			execute: async (args: Record<string, unknown>) => {
				const results = await engram.hubHop(
					Number(args.sourceId),
					Number(args.minSharedConcepts) || 2,
					Number(args.limit) || 10,
				);

				return {
					related: results.map((r) => ({
						nodeId: r.relatedChunkId,
						file: r.relatedDocUrl,
						sharedConceptCount: r.sharedConceptCount,
						sharedConcepts: r.sharedConcepts,
					})),
					hint: "Use kb.load with nodeIds to load content",
				};
			},
		},

		// =====================================================================
		// CONCEPTS (Search by Concept Names)
		// =====================================================================
		{
			name: "kb.concepts",
			description:
				"Search for nodes by high-level concept names. " +
				"Useful when you know what concepts you're looking for " +
				"(e.g., 'authentication', 'vector search', 'rate limiting').",
			inputSchema: {
				type: "object",
				properties: {
					concepts: {
						type: "array",
						items: { type: "string" },
						description: "List of concept names to search for",
					},
					limit: {
						type: "number",
						description: "Maximum results (default: 20)",
					},
				},
				required: ["concepts"],
			},
			execute: async (args: Record<string, unknown>) => {
				const concepts = args.concepts as string[];
				const limit = Number(args.limit) || 20;

				const pointers = await engram.conceptSearch(concepts, limit);

				return {
					nodes: pointers.map(formatPointer),
					searchedConcepts: concepts,
					hint: "Use kb.load with nodeIds to load content",
				};
			},
		},

		// =====================================================================
		// FUNCTION (Surgical Function Load)
		// =====================================================================
		{
			name: "kb.function",
			description:
				"Load a specific function or class by name from a file. " +
				"This is surgical precision - loads exactly one definition, not the whole file.",
			inputSchema: {
				type: "object",
				properties: {
					filePattern: {
						type: "string",
						description: "File path or pattern",
					},
					functionName: {
						type: "string",
						description: "Name of function, class, or method",
					},
				},
				required: ["filePattern", "functionName"],
			},
			execute: async (args: Record<string, unknown>) => {
				const result = await engram.loadFunction(
					String(args.filePattern),
					String(args.functionName),
				);

				if (!result) {
					return {
						error: `Function '${args.functionName}' not found in '${args.filePattern}'`,
						hint: "Use kb.structure to explore file contents first",
					};
				}

				return {
					content: result.content,
					file: result.docUrl,
					lines: `${result.lineStart}-${result.lineEnd}`,
					type: result.type,
				};
			},
		},

		// =====================================================================
		// EXPLORE (Graph Traversal)
		// =====================================================================
		{
			name: "kb.explore",
			description:
				"Explore the graph around a node (get children, related nodes). " +
				"Useful for understanding context and relationships.",
			inputSchema: {
				type: "object",
				properties: {
					nodeId: {
						type: "string",
						description: "Node URI to explore from",
					},
					depth: {
						type: "number",
						description: "How many hops to traverse (default: 1)",
					},
				},
				required: ["nodeId"],
			},
			execute: async (args: Record<string, unknown>) => {
				const result = await engram.explore(
					String(args.nodeId),
					Number(args.depth) || 1,
				);

				return {
					nodes: result.nodes.map((n) => ({
						id: n.id,
						type: n.type,
						name: n.name,
						description: n.description,
					})),
					path: result.pathDescription,
				};
			},
		},
	];
}

/**
 * Format a NodePointer for LLM consumption
 */
function formatPointer(p: NodePointer) {
	return {
		nodeId: p.id,
		type: p.type,
		file: p.docUrl,
		section: p.sectionPath,
		lines: p.lineRange,
		tokens: p.tokenCount,
		concepts: p.conceptNames.slice(0, 5),
		children: p.childIds.length,
	};
}
