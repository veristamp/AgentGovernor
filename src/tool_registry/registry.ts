import { readdirSync, readFileSync, statSync } from 'fs';
import { join, resolve } from 'path';
import { RegistryDatabase } from '../registry/db';
import type { ToolDescriptor, ToolRegistryOptions } from './types';

export class ToolRegistry {
    private db;
    private toolsDir: string;

    constructor(options: ToolRegistryOptions = {}) {
        // Use shared DB instance (persisted or memory)
        this.db = RegistryDatabase.getInstance(options.dbPath).getDb();
        this.toolsDir = resolve(options.toolsDir || 'tools');
    }

    public ingest() {
        const walk = (dir: string) => {
            if (!require('fs').existsSync(dir)) {
                return;
            }
            const files = readdirSync(dir);
            for (const file of files) {
                const path = join(dir, file);
                const stat = statSync(path);
                if (stat.isDirectory()) {
                    walk(path);
                } else if (file.endsWith('.json')) {
                    try {
                        const content = readFileSync(path, 'utf-8');
                        const data = JSON.parse(content);
                        if (data.qualifiedName && data.description) {
                            this.upsert(data);
                        }
                    } catch (e) {
                        console.error(`Failed to ingest ${path}:`, e);
                    }
                }
            }
        };

        // Check if empty, then ingest
        const countResult = this.db.query('SELECT count(*) as count FROM tools').get() as { count: number };
        if (countResult.count === 0) {
             walk(this.toolsDir);
             const finalCount = this.db.query('SELECT count(*) as c FROM tools').get() as {c: number};
             console.log(`[ToolRegistry] Ingested ${finalCount.c} tools.`);
        }
    }

    private upsert(tool: any) {
        const insert = this.db.prepare(`
            INSERT OR REPLACE INTO tools (qualified_name, server_prefix, name, description, schema_json)
            VALUES ($qualifiedName, $serverPrefix, $name, $description, $schema)
        `);

        insert.run({
            $qualifiedName: tool.qualifiedName,
            $serverPrefix: tool.serverPrefix,
            $name: tool.name,
            $description: tool.description,
            $schema: JSON.stringify(tool.schema || {})
        });
    }

    public search(query: string, limit: number = 10): ToolDescriptor[] {
        const sanitized = query.replace(/[^\w\s]/g, ' ').trim();
        if (!sanitized) return [];

        // Split into tokens and join with OR for broader matching
        const tokens = sanitized.split(/\s+/).filter(t => t.length > 2); // Ignore short words
        if (tokens.length === 0) return [];
        
        const ftsQueryString = tokens.map(t => `"${t}"*`).join(' OR ');

        const ftsQuery = this.db.prepare(`
            SELECT qualified_name 
            FROM tools_fts 
            WHERE tools_fts MATCH $query 
            ORDER BY rank 
            LIMIT $limit
        `);

        const results = ftsQuery.all({ 
            $query: ftsQueryString, 
            $limit: limit 
        }) as { qualified_name: string }[];

        if (results.length === 0) return [];

        const placeholders = results.map(() => '?').join(',');
        const finalQuery = this.db.prepare(`
            SELECT * FROM tools WHERE qualified_name IN (${placeholders})
        `);

        const rows = finalQuery.all(...results.map(r => r.qualified_name)) as any[];

        return rows.map(this.mapRow);
    }

    public getAll(): ToolDescriptor[] {
        const query = this.db.query('SELECT * FROM tools');
        const rows = query.all() as any[];
        return rows.map(this.mapRow);
    }
    
    public get(qualifiedName: string): ToolDescriptor | null {
        const query = this.db.prepare('SELECT * FROM tools WHERE qualified_name = ?');
        const row = query.get(qualifiedName) as any;
        if (!row) return null;
        return this.mapRow(row);
    }

    private mapRow(row: any): ToolDescriptor {
        return {
            qualifiedName: row.qualified_name,
            serverPrefix: row.server_prefix,
            name: row.name,
            description: row.description,
            schema: JSON.parse(row.schema_json)
        };
    }
}
