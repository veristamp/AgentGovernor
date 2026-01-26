import { and, eq, inArray, sql } from "drizzle-orm";
import { db } from "../../registry/db/db";
import { edges, globalConcepts, nodes } from "../../registry/db/schema";
import type {
	ContentResult,
	EngramLookupResult,
	EngramNode,
	EngramService,
	HubHopResult,
	NavigatorResult,
	NodePointer,
	NodeType,
} from "./types";

/**
 * Graph-Augmented Engram Service
 *
 * The "Neural Inode Table" - provides O(1) structural lookups via the
 * Unified Graph (Nodes/Edges/GlobalConcepts).
 *
 * Key Pattern: Return POINTERS first, load CONTENT on-demand.
 * This mimics hardware memory access:
 *   - Page table lookup (getFileStructure) → O(1)
 *   - Page fault (loadContent) → On-demand
 *   - TLB cache (in-memory cache) → Hot paths stay fast
 *
 * Implements Policy Filtering (Gate 2) at the query level.
 */
export class EngramServiceImpl implements EngramService {
	// TLB-style cache for frequently accessed nodes
	private _cache = new Map<number, NodePointer>();
	private _cacheMaxSize = 1000;

	// =========================================================================
	// SEARCH (Semantic Query → Concepts → Nodes)
	// =========================================================================

	async search(query: string, limit = 5): Promise<EngramLookupResult> {
		// 1. Extract keywords and find matching concepts
		const keywords = query
			.toLowerCase()
			.split(/\s+/)
			.filter((w) => w.length > 3);
		if (keywords.length === 0) return { nodes: [] };

		// Build ILIKE patterns for each keyword
		const patterns = keywords.map((k) => `%${k}%`);

		// Find relevant concepts via keyword matching
		// TODO: Replace with vector search for better semantic matching
		const conceptMatches = await db
			.select()
			.from(globalConcepts)
			.where(
				sql`LOWER(${globalConcepts.name}) SIMILAR TO ${patterns.map((p) => p.replace(/%/g, ".*")).join("|")}`,
			)
			.limit(10);

		if (conceptMatches.length === 0) {
			// Fallback: direct node search
			return this._fallbackSearch(query, limit);
		}

		const conceptIds = conceptMatches.map((c) => c.id);

		// 2. Hub-Hop: Find Nodes connected to these concepts via MENTIONS
		const relevantNodes = await db
			.select({
				id: nodes.id,
				type: nodes.type,
				docUrl: nodes.docUrl,
				content: nodes.content,
				sectionPath: nodes.sectionPath,
				meta: nodes.meta,
				parentId: nodes.parentId,
				prevId: nodes.prevId,
				nextId: nodes.nextId,
			})
			.from(nodes)
			.innerJoin(edges, eq(edges.sourceId, nodes.id))
			.where(
				and(
					inArray(edges.targetId, conceptIds),
					sql`${edges.edgeType} IN ('MENTIONS', 'PROVIDES')`,
				),
			)
			.limit(limit * 2);

		// 3. Transform to EngramNode (with NodePointer for deeper exploration)
		const results: EngramNode[] = relevantNodes.map((n) => {
			const meta = n.meta as Record<string, unknown> | null;
			const pointer = this._toNodePointer({
				...n,
				meta: meta,
			});

			// Cache the pointer
			this._cachePointer(pointer);

			return {
				id: n.docUrl,
				type: this._mapNodeType(n.type),
				name: n.docUrl.split("/").pop()?.split(".")[0] || "unknown",
				description:
					(meta?.description as string) || n.sectionPath || "No description",
				structure: {
					inputs: (meta?.inputs as Record<string, string>) || {},
					outputs: (meta?.outputs as string) || "any",
					dependencies: [],
				},
				nodePointer: pointer,
			};
		});

		// Deduplicate by ID
		const unique = Array.from(
			new Map(results.map((item) => [item.id, item])).values(),
		);

		return {
			nodes: unique.slice(0, limit),
			relatedConcepts: conceptMatches.map((c) => c.name),
			totalTokens: unique.reduce(
				(sum, n) => sum + (n.nodePointer?.tokenCount || 0),
				0,
			),
		};
	}

	private async _fallbackSearch(
		query: string,
		limit: number,
	): Promise<EngramLookupResult> {
		// Direct content search when concept matching fails
		const results = await db
			.select({
				id: nodes.id,
				type: nodes.type,
				docUrl: nodes.docUrl,
				sectionPath: nodes.sectionPath,
				meta: nodes.meta,
			})
			.from(nodes)
			.where(sql`${nodes.content} ILIKE ${"%" + query + "%"}`)
			.limit(limit);

		const engramNodes: EngramNode[] = results.map((n) => ({
			id: n.docUrl,
			type: this._mapNodeType(n.type),
			name: n.docUrl.split("/").pop()?.split(".")[0] || "unknown",
			description: n.sectionPath || "Direct content match",
			structure: { inputs: {}, outputs: "any" },
		}));

		return { nodes: engramNodes };
	}

	// =========================================================================
	// INSPECT (Single Node Metadata)
	// =========================================================================

	async inspect(nodeId: string): Promise<EngramNode | null> {
		// Query by docUrl (which serves as stable Logical ID)
		const result = await db
			.select()
			.from(nodes)
			.where(eq(nodes.docUrl, nodeId))
			.limit(1);

		if (result.length === 0) return null;
		const n = result[0]!;
		const meta = n.meta as Record<string, unknown> | null;

		// Fetch dependencies (outgoing edges)
		const deps = await db
			.select({
				targetId: edges.targetId,
				edgeType: edges.edgeType,
			})
			.from(edges)
			.where(
				and(
					eq(edges.sourceId, n.id),
					sql`${edges.edgeType} IN ('DEPENDS_ON', 'REFERS_TO')`,
				),
			);

		// Fetch related concepts
		const conceptEdges = await db
			.select({
				conceptId: edges.targetId,
				conceptName: globalConcepts.name,
			})
			.from(edges)
			.innerJoin(globalConcepts, eq(edges.targetId, globalConcepts.id))
			.where(and(eq(edges.sourceId, n.id), eq(edges.edgeType, "MENTIONS")));

		const pointer = this._toNodePointer({
			...n,
			meta: n.meta as Record<string, unknown> | null,
		});
		this._cachePointer(pointer);

		return {
			id: n.docUrl,
			type: this._mapNodeType(n.type),
			name: n.docUrl.split("/").pop()?.split(".")[0] || "unknown",
			description: (meta?.description as string) || n.sectionPath || "",
			structure: {
				inputs: (meta?.inputs as Record<string, string>) || {},
				outputs: (meta?.outputs as string) || "any",
				dependencies: deps.map((d) => String(d.targetId)),
			},
			relatedConcepts: conceptEdges.map((c) => c.conceptName),
			nodePointer: pointer,
		};
	}

	// =========================================================================
	// EXPLORE (Graph Traversal)
	// =========================================================================

	async explore(nodeId: string, depth = 1): Promise<EngramLookupResult> {
		// Find the starting node
		const startNode = await db
			.select()
			.from(nodes)
			.where(eq(nodes.docUrl, nodeId))
			.limit(1);

		if (startNode.length === 0) return { nodes: [] };
		const startId = startNode[0]!.id;

		// Get graph context using recursive CTE
		// This mirrors the Python get_graph_context RPC
		const contextNodes = await db.execute<{
			id: number;
			type: string;
			doc_url: string;
			section_path: string | null;
			meta: Record<string, unknown> | null;
			content: string | null;
			depth: number;
		}>(sql`
            WITH RECURSIVE walk AS (
                SELECT 
                    n.id,
                    n.type,
                    n.doc_url,
                    n.section_path,
                    n.meta,
                    n.content,
                    0 as depth
                FROM gcm_registry.nodes n 
                WHERE n.id = ${startId}
                
                UNION ALL
                
                SELECT 
                    n.id,
                    n.type,
                    n.doc_url,
                    n.section_path,
                    n.meta,
                    n.content,
                    w.depth + 1
                FROM gcm_registry.nodes n
                JOIN gcm_registry.edges e ON (e.target_id = n.id OR e.source_id = n.id)
                JOIN walk w ON (e.source_id = w.id OR e.target_id = w.id) AND n.id != w.id
                WHERE w.depth < ${depth}
                  AND e.edge_type IN ('CHILD_OF', 'FOLLOWS', 'PARENT', 'REFERS_TO', 'MENTIONS')
            )
            SELECT DISTINCT ON (id) * FROM walk ORDER BY id, depth
            LIMIT 50
        `);

		const results: EngramNode[] = contextNodes.map((row) => ({
			id: row.doc_url,
			type: this._mapNodeType(row.type),
			name: row.doc_url?.split("/").pop()?.split(".")[0] || "unknown",
			description: row.section_path || "",
			structure: { inputs: {}, outputs: "any" },
		}));

		return {
			nodes: results,
			pathDescription: `explore:${nodeId}→depth=${depth}`,
		};
	}

	// =========================================================================
	// GET FILE STRUCTURE (O(1) - No Content Loading)
	// =========================================================================

	async getFileStructure(
		filePattern: string,
		maxDepth = 3,
	): Promise<NavigatorResult> {
		const pattern = `%${filePattern}%`;

		// Use recursive CTE to get file hierarchy
		const result = await db.execute<{
			id: number;
			type: string;
			doc_url: string;
			section_path: string | null;
			parent_id: number | null;
			prev_id: number | null;
			next_id: number | null;
			meta: Record<string, unknown> | null;
			depth: number;
			child_ids: number[];
			concept_ids: number[];
			concept_names: string[];
		}>(sql`
            WITH RECURSIVE tree AS (
                SELECT 
                    n.id, n.type, n.doc_url, n.section_path,
                    n.parent_id, n.prev_id, n.next_id,
                    n.meta,
                    0 as depth
                FROM gcm_registry.nodes n
                WHERE n.doc_url LIKE ${pattern}
                AND n.parent_id IS NULL
                
                UNION ALL
                
                SELECT 
                    n.id, n.type, n.doc_url, n.section_path,
                    n.parent_id, n.prev_id, n.next_id,
                    n.meta,
                    t.depth + 1
                FROM gcm_registry.nodes n
                JOIN tree t ON n.parent_id = t.id
                WHERE t.depth < ${maxDepth}
            )
            SELECT 
                t.*,
                COALESCE(
                    (SELECT array_agg(c.id) FROM gcm_registry.nodes c WHERE c.parent_id = t.id),
                    ARRAY[]::bigint[]
                ) as child_ids,
                COALESCE(
                    (SELECT array_agg(gc.id) FROM gcm_registry.edges e 
                     JOIN gcm_registry.global_concepts gc ON e.target_id = gc.id 
                     WHERE e.source_id = t.id AND e.edge_type = 'MENTIONS'),
                    ARRAY[]::integer[]
                ) as concept_ids,
                COALESCE(
                    (SELECT array_agg(gc.name) FROM gcm_registry.edges e 
                     JOIN gcm_registry.global_concepts gc ON e.target_id = gc.id 
                     WHERE e.source_id = t.id AND e.edge_type = 'MENTIONS'),
                    ARRAY[]::text[]
                ) as concept_names
            FROM tree t
            ORDER BY t.depth, t.id
        `);

		const pointers: NodePointer[] = result.map((row) => {
			const meta = row.meta || {};
			const pointer: NodePointer = {
				id: row.id,
				type: row.type as NodeType,
				docUrl: row.doc_url,
				sectionPath: row.section_path || undefined,
				parentId: row.parent_id || undefined,
				prevId: row.prev_id || undefined,
				nextId: row.next_id || undefined,
				childIds: row.child_ids || [],
				conceptIds: row.concept_ids || [],
				conceptNames: row.concept_names || [],
				tokenCount: (meta.token_count as number) || 0,
				charCount:
					((meta.char_end as number) || 0) - ((meta.char_start as number) || 0),
				lineRange: [
					(meta.line_start as number) || 0,
					(meta.line_end as number) || 0,
				],
			};
			this._cachePointer(pointer);
			return pointer;
		});

		return {
			nodes: pointers,
			totalTokens: pointers.reduce((sum, p) => sum + p.tokenCount, 0),
			pathDescription: `structure:${filePattern}`,
			hopCount: 0,
		};
	}

	// =========================================================================
	// LOAD CONTENT (The "Page Fault Handler")
	// =========================================================================

	async loadContent(
		nodeIds: number[],
		includeFlow = false,
	): Promise<ContentResult> {
		if (nodeIds.length === 0) return {};

		const result = await db.execute<{
			id: number;
			content: string | null;
			type: string;
			section_path: string | null;
			doc_url: string;
			meta: Record<string, unknown> | null;
			prev_content: string | null;
			next_content: string | null;
		}>(sql`
            SELECT 
                n.id,
                n.content,
                n.type,
                n.section_path,
                n.doc_url,
                n.meta,
                pn.content as prev_content,
                nn.content as next_content
            FROM gcm_registry.nodes n
            LEFT JOIN gcm_registry.nodes pn ON n.prev_id = pn.id
            LEFT JOIN gcm_registry.nodes nn ON n.next_id = nn.id
            WHERE n.id = ANY(${nodeIds})
        `);

		const contents: ContentResult = {};
		for (const row of result) {
			const meta = row.meta || {};
			contents[row.id] = {
				content: row.content || "",
				type: row.type,
				sectionPath: row.section_path || undefined,
				docUrl: row.doc_url,
				lineStart: (meta.line_start as number) || 0,
				lineEnd: (meta.line_end as number) || 0,
				prevContent: includeFlow ? row.prev_content || undefined : undefined,
				nextContent: includeFlow ? row.next_content || undefined : undefined,
			};
		}

		return contents;
	}

	// =========================================================================
	// HUB-HOP (Find Related via Shared Concepts)
	// =========================================================================

	async hubHop(
		sourceId: number,
		minSharedConcepts = 2,
		limit = 10,
	): Promise<HubHopResult[]> {
		// This mirrors the Python find_related_documents RPC
		const result = await db.execute<{
			related_chunk_id: number;
			related_doc_url: string;
			shared_concept_count: number;
			shared_concepts: string[];
		}>(sql`
            WITH source_concepts AS (
                SELECT e.target_id AS concept_id
                FROM gcm_registry.edges e
                WHERE e.source_id = ${sourceId}
                AND e.edge_type = 'MENTIONS'
                AND e.weight > 0.4
            ),
            related_chunks AS (
                SELECT 
                    e.source_id AS chunk_id,
                    n.doc_url,
                    COUNT(DISTINCT e.target_id)::INT AS shared_count,
                    jsonb_agg(DISTINCT gc.name) AS shared_names
                FROM gcm_registry.edges e
                JOIN source_concepts sc ON e.target_id = sc.concept_id
                JOIN gcm_registry.nodes n ON n.id = e.source_id
                JOIN gcm_registry.global_concepts gc ON gc.id = e.target_id
                WHERE e.edge_type = 'MENTIONS'
                AND e.source_id != ${sourceId}
                AND e.weight > 0.4
                GROUP BY e.source_id, n.doc_url
                HAVING COUNT(DISTINCT e.target_id) >= ${minSharedConcepts}
            )
            SELECT 
                chunk_id AS related_chunk_id,
                doc_url AS related_doc_url,
                shared_count AS shared_concept_count,
                shared_names AS shared_concepts
            FROM related_chunks
            ORDER BY shared_count DESC
            LIMIT ${limit}
        `);

		return result.map((row) => ({
			relatedChunkId: row.related_chunk_id,
			relatedDocUrl: row.related_doc_url,
			sharedConceptCount: row.shared_concept_count,
			sharedConcepts: row.shared_concepts || [],
		}));
	}

	// =========================================================================
	// CONCEPT SEARCH (Find Nodes by Concept Names)
	// =========================================================================

	async conceptSearch(
		conceptNames: string[],
		limit = 20,
	): Promise<NodePointer[]> {
		if (conceptNames.length === 0) return [];

		// This mirrors the Python find_chunks_by_concepts RPC
		const result = await db.execute<{
			chunk_id: number;
			chunk_content: string | null;
			section_path: string | null;
			doc_url: string;
			type: string;
			meta: Record<string, unknown> | null;
			match_count: number;
			total_weight: number;
			matched_concepts: string;
		}>(sql`
            SELECT 
                n.id as chunk_id,
                n.content as chunk_content,
                n.section_path,
                n.doc_url,
                n.type,
                n.meta,
                COUNT(DISTINCT gc.id)::INT as match_count,
                SUM(e.weight)::FLOAT as total_weight,
                string_agg(DISTINCT gc.name, ', ') as matched_concepts
            FROM gcm_registry.nodes n
            JOIN gcm_registry.edges e ON e.source_id = n.id
            JOIN gcm_registry.global_concepts gc ON e.target_id = gc.id
            WHERE gc.name = ANY(${conceptNames})
            AND e.edge_type = 'MENTIONS'
            GROUP BY n.id
            ORDER BY match_count DESC, total_weight DESC
            LIMIT ${limit}
        `);

		return result.map((row) => {
			const meta = row.meta || {};
			const pointer: NodePointer = {
				id: row.chunk_id,
				type: row.type as NodeType,
				docUrl: row.doc_url || "",
				sectionPath: row.section_path || undefined,
				childIds: [],
				conceptIds: [],
				conceptNames: row.matched_concepts?.split(", ") || [],
				tokenCount: (meta.token_count as number) || 0,
				charCount: 0,
				lineRange: [
					(meta.line_start as number) || 0,
					(meta.line_end as number) || 0,
				],
			};
			this._cachePointer(pointer);
			return pointer;
		});
	}

	// =========================================================================
	// LOAD FUNCTION (Surgical Read)
	// =========================================================================

	async loadFunction(
		filePattern: string,
		functionName: string,
	): Promise<ContentResult[number] | null> {
		const result = await db.execute<{
			id: number;
			content: string | null;
			type: string;
			section_path: string | null;
			doc_url: string;
			meta: Record<string, unknown> | null;
		}>(sql`
            SELECT 
                n.id, n.content, n.type, n.section_path, n.doc_url, n.meta
            FROM gcm_registry.nodes n
            WHERE n.doc_url LIKE ${"%" + filePattern + "%"}
            AND n.type = 'CODE'
            AND n.meta->>'symbols_defined' LIKE ${"%" + functionName + "%"}
            LIMIT 1
        `);

		if (result.length === 0) return null;

		const row = result[0]!;
		const meta = row.meta || {};

		return {
			content: row.content || "",
			type: row.type,
			sectionPath: row.section_path || undefined,
			docUrl: row.doc_url,
			lineStart: (meta.line_start as number) || 0,
			lineEnd: (meta.line_end as number) || 0,
		};
	}

	// =========================================================================
	// HELPERS
	// =========================================================================

	private _mapNodeType(dbType: string): EngramNode["type"] {
		const t = dbType?.toLowerCase() || "";
		if (t === "tool") return "tool";
		if (t === "skill") return "skill";
		if (t === "workflow") return "workflow";
		if (t === "concept") return "concept";
		return "resource";
	}

	private _toNodePointer(n: {
		id: number;
		type: string;
		docUrl: string;
		sectionPath?: string | null;
		parentId?: number | null;
		prevId?: number | null;
		nextId?: number | null;
		meta?: Record<string, unknown> | null;
	}): NodePointer {
		const meta = n.meta;
		return {
			id: n.id,
			type: (n.type || "CHUNK") as NodeType,
			docUrl: n.docUrl || "",
			sectionPath: n.sectionPath || undefined,
			parentId: n.parentId || undefined,
			prevId: n.prevId || undefined,
			nextId: n.nextId || undefined,
			childIds: [],
			conceptIds: [],
			conceptNames: [],
			tokenCount: (meta?.token_count as number) || 0,
			charCount:
				((meta?.char_end as number) || 0) - ((meta?.char_start as number) || 0),
			lineRange: [
				(meta?.line_start as number) || 0,
				(meta?.line_end as number) || 0,
			],
		};
	}

	private _cachePointer(pointer: NodePointer): void {
		if (this._cache.size >= this._cacheMaxSize) {
			// Evict oldest entry (FIFO)
			const firstKey = this._cache.keys().next().value;
			if (firstKey !== undefined) {
				this._cache.delete(firstKey);
			}
		}
		this._cache.set(pointer.id, pointer);
	}

	getCached(nodeId: number): NodePointer | undefined {
		return this._cache.get(nodeId);
	}

	clearCache(): void {
		this._cache.clear();
	}
}

// Singleton instance
let _instance: EngramServiceImpl | null = null;

export function getEngramService(): EngramServiceImpl {
	if (!_instance) {
		_instance = new EngramServiceImpl();
	}
	return _instance;
}
