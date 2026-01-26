import {
	bigint,
	customType,
	doublePrecision,
	index,
	integer,
	jsonb,
	pgSchema,
	text,
	timestamp,
} from "drizzle-orm/pg-core";

export const gcmSchema = pgSchema("gcm_registry");

const tsvector = customType<{ data: string }>({
	dataType() {
		return "tsvector";
	},
});

// =============================================================================
// UNIFIED GRAPH SCHEMA (Mirroring Python kb.db.schema)
// =============================================================================

// The Hard Graph (Skeleton)
export const nodes = gcmSchema.table(
	"nodes",
	{
		id: bigint("id", { mode: "number" }).primaryKey(), // Stable ID (Qdrant compatible)
		docId: integer("doc_id"), // FK to documents.id
		docUrl: text("doc_url").notNull(),
		type: text("type").notNull(), // CHUNK, SECTION, CODE, TABLE, TOOL, SKILL, WORKFLOW
		content: text("content"),
		parentId: bigint("parent_id", { mode: "number" }),
		prevId: bigint("prev_id", { mode: "number" }),
		nextId: bigint("next_id", { mode: "number" }),
		pageIdx: integer("page_idx"),
		sectionPath: text("section_path"),
		meta: jsonb("meta"), // language, lines, etc.
		createdAt: timestamp("created_at").defaultNow().notNull(),
	},
	(table) => ({
		docTypeIdx: index("idx_nodes_doc_type").on(table.docUrl, table.type),
		sectionPathIdx: index("idx_nodes_section_path_trgm").using(
			"gin",
			table.sectionPath,
		), // Requires pg_trgm
	}),
);

// Global Concepts (Hubs)
export const globalConcepts = gcmSchema.table("global_concepts", {
	id: integer("id").primaryKey(),
	name: text("name").unique().notNull(),
	docCount: integer("doc_count").default(0),
	createdAt: timestamp("created_at").defaultNow().notNull(),
});

// Edges (Nerves)
export const edges = gcmSchema.table(
	"edges",
	{
		id: bigint("id", { mode: "number" }).primaryKey(),
		sourceId: bigint("source_id", { mode: "number" }).notNull(),
		targetId: bigint("target_id", { mode: "number" }).notNull(), // Concept ID or Node ID
		edgeType: text("edge_type").notNull(), // MENTIONS, REFERS_TO, FOLLOWS, CHILD_OF, PROVIDES, DEPENDS_ON
		weight: doublePrecision("weight").default(1.0),
	},
	(table) => ({
		sourceIdx: index("idx_edges_source").on(table.sourceId),
		targetTypeIdx: index("idx_edges_target_type").on(
			table.targetId,
			table.edgeType,
		),
		uniqueLinkIdx: index("idx_edges_unique_link").on(
			table.sourceId,
			table.targetId,
			table.edgeType,
		), // Should be unique constraint ideally
	}),
);

// Documents Registry
export const documents = gcmSchema.table("documents", {
	id: integer("id").primaryKey(),
	filePath: text("file_path").unique().notNull(),
	fileType: text("file_type"),
	checksum: text("checksum"),
	totalChunks: integer("total_chunks").default(0),
	lastProcessedAt: timestamp("last_processed_at"),
	lastHarvestedAt: timestamp("last_harvested_at"),
	createdAt: timestamp("created_at").defaultNow().notNull(),
	syncStatus: text("sync_status").default("stale"),
});

// =============================================================================
// LEGACY REGISTRY TABLES (To be deprecated or mapped to Nodes)
// =============================================================================

// Tools Table
export const tools = gcmSchema.table(
	"tools",
	{
		qualifiedName: text("qualified_name").primaryKey(),
		serverPrefix: text("server_prefix").notNull(),
		name: text("name").notNull(),
		description: text("description").notNull(),
		schema: jsonb("schema_json").notNull(),
		searchVector: tsvector("search_vector"),
	},
	(table) => ({
		searchIndex: index("tools_search_idx").using("gin", table.searchVector),
	}),
);

// Skills Table
export const skills = gcmSchema.table(
	"skills",
	{
		skillRef: text("skill_ref").primaryKey(),
		skillId: text("skill_id").notNull(),
		version: text("version").notNull(),
		description: text("description").notNull(),
		manifest: jsonb("manifest_json").notNull(), // { bindings, fanoutTools }
		interfaces: jsonb("interfaces_json").notNull(), // string[]
		searchVector: tsvector("search_vector"),
	},
	(table) => ({
		searchIndex: index("skills_search_idx").using("gin", table.searchVector),
	}),
);

// Workflows Table
export const workflows = gcmSchema.table(
	"workflows",
	{
		workflowId: text("workflow_id").primaryKey(),
		orgId: text("org_id").notNull(),
		goal: text("goal").notNull(),
		summary: text("summary"),
		code: text("code").notNull(),
		metadata: jsonb("metadata_json").notNull(),
		searchVector: tsvector("search_vector"),
	},
	(table) => ({
		searchIndex: index("workflows_search_idx").using("gin", table.searchVector),
	}),
);

// Missions Table
export const missions = gcmSchema.table("missions", {
	id: text("id").primaryKey(), // UUID
	name: text("name").notNull(),
	description: text("description"),
	ownerId: text("owner_id").notNull(),
	orgId: text("org_id").notNull(),
	status: text("status").notNull().default("active"), // active, archived
	createdAt: text("created_at").notNull(), // ISO string
	updatedAt: text("updated_at").notNull(), // ISO string
});

// Sessions Table (Chat/Authoring Context)
export const sessions = gcmSchema.table("sessions", {
	id: text("id").primaryKey(), // UUID
	missionId: text("mission_id").references(() => missions.id),
	title: text("title"),
	// Persisted loop state: plan, selected_skills, draft_code, etc.
	state: jsonb("state_json").default({}),
	createdAt: text("created_at").notNull(),
	lastActiveAt: text("last_active_at").notNull(),
});

// Artifacts Table (Versioned Content)
export const artifacts = gcmSchema.table("artifacts", {
	id: text("id").primaryKey(), // UUID
	type: text("type").notNull(), // workflow_draft, workflow_version, skill_draft
	content: jsonb("content_json").notNull(),
	parentId: text("parent_id"), // For version history
	sessionId: text("session_id").references(() => sessions.id),
	createdAt: text("created_at").notNull(),
});

// Runs Table (Execution Instances)
export const runs = gcmSchema.table("runs", {
	id: text("id").primaryKey(), // UUID
	sessionId: text("session_id").references(() => sessions.id),
	missionId: text("mission_id").references(() => missions.id),
	type: text("type").notNull(), // workflow, skill, tool, research
	status: text("status").notNull(), // pending, running, completed, failed
	// Snapshot of authz/policy used for this run
	policyContext: jsonb("policy_context_json").notNull(),
	createdAt: text("created_at").notNull(),
	endedAt: text("ended_at"),
});

// Trace Events Table (Granular Audit Log)
export const traceEvents = gcmSchema.table(
	"trace_events",
	{
		id: text("id").primaryKey(), // UUID
		runId: text("run_id").references(() => runs.id),
		sessionId: text("session_id").references(() => sessions.id),
		iteration: text("iteration").notNull(), // Stored as text (int) or number if using postgres.js properly, adhering to text for safety in this schema setup if needed, but int is better. Let's use integer if available or text. Drizzle 'integer' exists.
		// using text for simplicity/consistency with other IDs, but typically iteration is int.
		// Drizzle `integer` maps to DB integer.
		type: text("type").notNull(), // plan, tool_call, tool_result, error, final
		content: jsonb("content_json").notNull(), // redacted args/result
		reasoning: text("reasoning"), // The "why"
		tokenCount: text("token_count"), // int as text
		createdAt: text("created_at").notNull(),
	},
	(table) => ({
		runIdx: index("trace_run_idx").on(table.runId),
		sessionIdx: index("trace_session_idx").on(table.sessionId),
	}),
);
