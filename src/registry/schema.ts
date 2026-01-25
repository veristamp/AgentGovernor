import { customType, index, jsonb, pgSchema, text } from "drizzle-orm/pg-core";

export const gcmSchema = pgSchema("gcm_registry");

const tsvector = customType<{ data: string }>({
	dataType() {
		return "tsvector";
	},
});

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
