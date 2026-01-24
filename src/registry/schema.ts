import { pgTable, text, jsonb, index, customType, pgSchema } from 'drizzle-orm/pg-core';
import { sql } from 'drizzle-orm';

export const gcmSchema = pgSchema('gcm_registry');

const tsvector = customType<{ data: string }>({
    dataType() {
        return 'tsvector';
    },
});

// Tools Table
export const tools = gcmSchema.table('tools', {
    qualifiedName: text('qualified_name').primaryKey(),
    serverPrefix: text('server_prefix').notNull(),
    name: text('name').notNull(),
    description: text('description').notNull(),
    schema: jsonb('schema_json').notNull(),
    searchVector: tsvector('search_vector'),
}, (table) => ({
    searchIndex: index('tools_search_idx').using('gin', table.searchVector),
}));

// Skills Table
export const skills = gcmSchema.table('skills', {
    skillRef: text('skill_ref').primaryKey(),
    skillId: text('skill_id').notNull(),
    version: text('version').notNull(),
    description: text('description').notNull(),
    manifest: jsonb('manifest_json').notNull(), // { bindings, fanoutTools }
    interfaces: jsonb('interfaces_json').notNull(), // string[]
    searchVector: tsvector('search_vector'),
}, (table) => ({
    searchIndex: index('skills_search_idx').using('gin', table.searchVector),
}));

// Workflows Table
export const workflows = gcmSchema.table('workflows', {
    workflowId: text('workflow_id').primaryKey(),
    orgId: text('org_id').notNull(),
    goal: text('goal').notNull(),
    summary: text('summary'),
    code: text('code').notNull(),
    metadata: jsonb('metadata_json').notNull(),
    searchVector: tsvector('search_vector'),
}, (table) => ({
    searchIndex: index('workflows_search_idx').using('gin', table.searchVector),
}));
