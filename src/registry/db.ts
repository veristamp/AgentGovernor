import { Database } from 'bun:sqlite';
import { resolve } from 'path';

export class RegistryDatabase {
    private db: Database;
    private static instance: RegistryDatabase;

    private constructor(dbPath: string) {
        this.db = new Database(dbPath);
        this.init();
    }

    public static getInstance(dbPath: string = 'registry.sqlite'): RegistryDatabase {
        if (!RegistryDatabase.instance) {
            RegistryDatabase.instance = new RegistryDatabase(dbPath);
        }
        return RegistryDatabase.instance;
    }

    private init() {
        // Shared configuration
        this.db.run('PRAGMA journal_mode = WAL;');
        this.db.run('PRAGMA synchronous = NORMAL;');

        // --- Tools Table ---
        this.db.run(`
            CREATE TABLE IF NOT EXISTS tools (
                qualified_name TEXT PRIMARY KEY,
                server_prefix TEXT,
                name TEXT,
                description TEXT,
                schema_json TEXT
            )
        `);
        this.db.run(`
            CREATE VIRTUAL TABLE IF NOT EXISTS tools_fts USING fts5(
                qualified_name,
                server_prefix,
                name,
                description,
                tokenize="porter"
            )
        `);
        this.db.run(`
            CREATE TRIGGER IF NOT EXISTS tools_ai AFTER INSERT ON tools BEGIN
                INSERT INTO tools_fts(qualified_name, server_prefix, name, description)
                VALUES (new.qualified_name, new.server_prefix, new.name, new.description);
            END;
        `);
        this.db.run(`
            CREATE TRIGGER IF NOT EXISTS tools_ad AFTER DELETE ON tools BEGIN
                DELETE FROM tools_fts WHERE qualified_name = old.qualified_name;
            END;
        `);
        // Note: SQLite FTS triggers for UPDATE are tricky, often better to DELETE+INSERT or custom update logic. 
        // For simplicity in this architecture, ingest usually does REPLACE (INSERT OR REPLACE), which triggers DELETE then INSERT.

        // --- Skills Table ---
        this.db.run(`
            CREATE TABLE IF NOT EXISTS skills (
                skill_ref TEXT PRIMARY KEY,
                skill_id TEXT,
                version TEXT,
                description TEXT,
                manifest_json TEXT,
                interfaces_json TEXT
            )
        `);
        this.db.run(`
            CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(
                skill_ref,
                skill_id,
                description,
                interfaces_text, -- serialized interfaces for searching
                tokenize="porter"
            )
        `);
        this.db.run(`
            CREATE TRIGGER IF NOT EXISTS skills_ai AFTER INSERT ON skills BEGIN
                INSERT INTO skills_fts(skill_ref, skill_id, description, interfaces_text)
                VALUES (new.skill_ref, new.skill_id, new.description, json_extract(new.interfaces_json, '$'));
            END;
        `);
        this.db.run(`
            CREATE TRIGGER IF NOT EXISTS skills_ad AFTER DELETE ON skills BEGIN
                DELETE FROM skills_fts WHERE skill_ref = old.skill_ref;
            END;
        `);

        // --- Workflows Table ---
        this.db.run(`
            CREATE TABLE IF NOT EXISTS workflows (
                workflow_id TEXT PRIMARY KEY,
                org_id TEXT,
                goal TEXT,
                summary TEXT,
                code TEXT,
                metadata_json TEXT
            )
        `);
        this.db.run(`
            CREATE VIRTUAL TABLE IF NOT EXISTS workflows_fts USING fts5(
                workflow_id,
                goal,
                summary,
                code,
                tokenize="porter"
            )
        `);
        this.db.run(`
            CREATE TRIGGER IF NOT EXISTS workflows_ai AFTER INSERT ON workflows BEGIN
                INSERT INTO workflows_fts(workflow_id, goal, summary, code)
                VALUES (new.workflow_id, new.goal, new.summary, new.code);
            END;
        `);
        this.db.run(`
            CREATE TRIGGER IF NOT EXISTS workflows_ad AFTER DELETE ON workflows BEGIN
                DELETE FROM workflows_fts WHERE workflow_id = old.workflow_id;
            END;
        `);
    }

    public getDb(): Database {
        return this.db;
    }
}
