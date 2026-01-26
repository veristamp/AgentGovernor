/**
 * Engram Types - Graph-Augmented Memory Types for GCM
 *
 * The Engram is the "Neural Inode Table" - it provides O(1) structural lookups
 * instead of O(n) context scanning. The Agent (RLM) navigates the graph
 * programmatically, loading content on-demand.
 *
 * Key Insight: Return POINTERS (IDs), not CONTENT. The Agent decides
 * when to "dereference" and load actual content.
 */

// =============================================================================
// NODE POINTER (The "Inode")
// =============================================================================

export interface NodePointer {
	id: number; // Stable ID (Qdrant compatible)
	type: NodeType; // CHUNK, CODE, SECTION, TOOL, SKILL, etc.
	docUrl: string; // File path or resource URI
	sectionPath?: string; // Hierarchical path: "Auth > Tokens > Refresh"

	// Connectivity (the "links" in the inode)
	parentId?: number;
	prevId?: number;
	nextId?: number;
	childIds: number[];

	// Concept links (the "soft graph" connections)
	conceptIds: number[];
	conceptNames: string[];

	// Size hints (for budget planning)
	tokenCount: number;
	charCount: number;
	lineRange: [number, number]; // [start, end]
}

export type NodeType =
	| "CHUNK"
	| "CODE"
	| "SECTION"
	| "TABLE"
	| "DOC"
	| "TOOL"
	| "SKILL"
	| "WORKFLOW"
	| "CONCEPT";

// =============================================================================
// ENGRAM NODE (Rich node for LLM consumption)
// =============================================================================

export interface EngramNode {
	id: string; // URI: "tools:filesystem.read", "skills:auth.login"
	type: "tool" | "skill" | "workflow" | "resource" | "concept";
	name: string;
	description: string;

	// AST / Structural Metadata
	structure?: {
		inputs: Record<string, string>; // name -> type
		outputs: string; // return type
		dependencies?: string[]; // other node IDs
		children?: string[]; // for hierarchical nodes
	};

	// Graph context (from Hub-Hop)
	relatedConcepts?: string[];

	// Pointer for deeper exploration
	nodePointer?: NodePointer;
}

// =============================================================================
// NAVIGATION RESULTS
// =============================================================================

export interface EngramLookupResult {
	nodes: EngramNode[];
	relatedConcepts?: string[];
	totalTokens?: number;
	pathDescription?: string;
}

export interface NavigatorResult {
	nodes: NodePointer[];
	totalTokens: number;
	pathDescription: string;
	sharedConcepts?: string[];
	hopCount: number;
}

export interface ContentResult {
	[nodeId: number]: {
		content: string;
		type: string;
		sectionPath?: string;
		docUrl: string;
		lineStart: number;
		lineEnd: number;
		prevContent?: string;
		nextContent?: string;
	};
}

// =============================================================================
// HUB-HOP RESULT (Related documents via shared concepts)
// =============================================================================

export interface HubHopResult {
	relatedChunkId: number;
	relatedDocUrl: string;
	sharedConceptCount: number;
	sharedConcepts: string[];
}

// =============================================================================
// CONCEPT SEARCH
// =============================================================================

export interface ConceptMatch {
	chunkId: number;
	chunkContent: string;
	sectionPath?: string;
	docUrl: string;
	matchCount: number;
	totalWeight: number;
	matchedConcepts: string;
	meta?: Record<string, unknown>;
}

// =============================================================================
// ENGRAM SERVICE INTERFACE
// =============================================================================

export interface EngramService {
	/**
	 * Semantic search to find relevant nodes (The "Hop")
	 * Returns NodePointers, not full content
	 */
	search(query: string, limit?: number): Promise<EngramLookupResult>;

	/**
	 * Precise lookup of a node's structure (The "Inode Read")
	 * Returns minimal AST/Metadata, NOT full code
	 */
	inspect(nodeId: string): Promise<EngramNode | null>;

	/**
	 * Get children/related nodes (Graph Traversal)
	 */
	explore(nodeId: string, depth?: number): Promise<EngramLookupResult>;

	/**
	 * Get file structure without loading content (O(1) lookup)
	 */
	getFileStructure(
		filePattern: string,
		maxDepth?: number,
	): Promise<NavigatorResult>;

	/**
	 * Load actual content for specific nodes (expensive - use sparingly)
	 */
	loadContent(nodeIds: number[], includeFlow?: boolean): Promise<ContentResult>;

	/**
	 * Find related documents via shared concepts (Hub-Hop pattern)
	 */
	hubHop(
		sourceId: number,
		minSharedConcepts?: number,
		limit?: number,
	): Promise<HubHopResult[]>;

	/**
	 * Find nodes by concept names
	 */
	conceptSearch(conceptNames: string[], limit?: number): Promise<NodePointer[]>;

	/**
	 * Load a specific function by name (surgical read)
	 */
	loadFunction(
		filePattern: string,
		functionName: string,
	): Promise<ContentResult[number] | null>;
}

// =============================================================================
// POLICY GATE TYPES
// =============================================================================

export type AccessDecision = "allow" | "deny" | "audit";

export interface AccessRequest {
	resourceUri: string; // e.g., "tools:fs.read", "nodes:12345"
	action: "read" | "write" | "execute" | "traverse";
	requesterId: string; // Agent/Session ID
	requesterRoles: string[]; // ["mcp:admin", "user:read"]
	orgId?: string;
	missionId?: string;
	context?: Record<string, unknown>;
}

export interface AccessResult {
	decision: AccessDecision;
	resourceUri: string;
	reason: string;
	matchedRule?: string;
	auditId?: string;
}

export interface PolicyRule {
	id: string;
	pattern: string; // Glob pattern: "tools:*", "skills:auth.*"
	actions: string[]; // ["read", "execute"] or ["*"]
	roles: string[]; // Required roles: ["mcp:admin"] or ["*"]
	decision: AccessDecision;
	priority: number; // Higher = checked first
}
