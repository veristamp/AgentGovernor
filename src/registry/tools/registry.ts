import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { eq, sql } from "drizzle-orm";
import { db, toTsVector } from "../db/db";
import { tools } from "../db/schema";
import type { ToolDescriptor, ToolRegistryOptions } from "./types";

function isToolDescriptor(value: unknown): value is ToolDescriptor {
	if (!value || typeof value !== "object") return false;
	const v = value as Record<string, unknown>;
	return (
		typeof v.qualifiedName === "string" &&
		typeof v.serverPrefix === "string" &&
		typeof v.name === "string" &&
		typeof v.description === "string"
	);
}

export class ToolRegistry {
	private toolsDir: string;

	constructor(options: ToolRegistryOptions = {}) {
		this.toolsDir = resolve(options.toolsDir || "tools");
	}

	public async ingest() {
		// console.log(`[ToolRegistry] Ingesting tools from: ${this.toolsDir}`);
		const walk = async (dir: string) => {
			if (!require("node:fs").existsSync(dir)) return;

			const files = readdirSync(dir);
			for (const file of files) {
				const path = join(dir, file);
				const stat = statSync(path);
				if (stat.isDirectory()) {
					await walk(path);
				} else if (file.endsWith(".json")) {
					try {
						const content = readFileSync(path, "utf-8");
						const data = JSON.parse(content) as unknown;
						if (isToolDescriptor(data)) {
							await this.upsert(data);
						}
					} catch (e) {
						console.error(`Failed to ingest ${path}:`, e);
					}
				}
			}
		};

		// Check if empty, then ingest
		const result = await db
			.select({ count: sql<number>`count(*)` })
			.from(tools);
		const count = Number(result[0]?.count || 0);

		if (count === 0) {
			await walk(this.toolsDir);
			const final = await db
				.select({ count: sql<number>`count(*)` })
				.from(tools);
			console.log(`[ToolRegistry] Ingested ${final[0]?.count} tools.`);
		}
	}

	private async upsert(tool: ToolDescriptor) {
		await db
			.insert(tools)
			.values({
				qualifiedName: tool.qualifiedName,
				serverPrefix: tool.serverPrefix,
				name: tool.name,
				description: tool.description,
				schema: tool.schema || {},
				searchVector: toTsVector(
					`${tool.qualifiedName} ${tool.name} ${tool.description}`,
				),
			})
			.onConflictDoUpdate({
				target: tools.qualifiedName,
				set: {
					serverPrefix: tool.serverPrefix,
					name: tool.name,
					description: tool.description,
					schema: tool.schema || {},
					searchVector: toTsVector(
						`${tool.qualifiedName} ${tool.name} ${tool.description}`,
					),
				},
			});
	}

	public async search(
		query: string,
		limit: number = 10,
	): Promise<ToolDescriptor[]> {
		const sanitized = query.replace(/[^\w\s]/g, " ").trim();
		if (!sanitized) return [];

		const tokens = sanitized.split(/\s+/).filter((t) => t.length > 2);
		if (tokens.length === 0) return [];

		// Use plainto_tsquery or simple string matching for 'OR' logic
		const searchQuery = tokens.join(" | ");

		const results = await db
			.select()
			.from(tools)
			.where(sql`search_vector @@ to_tsquery('english', ${searchQuery})`)
			.limit(limit);

		return results.map(this.mapRow);
	}

	public async getAll(): Promise<ToolDescriptor[]> {
		const results = await db.select().from(tools);
		return results.map(this.mapRow);
	}

	public async get(qualifiedName: string): Promise<ToolDescriptor | null> {
		const results = await db
			.select()
			.from(tools)
			.where(eq(tools.qualifiedName, qualifiedName));
		if (results.length === 0 || !results[0]) return null;
		return this.mapRow(results[0]);
	}

	private mapRow(row: typeof tools.$inferSelect): ToolDescriptor {
		return {
			qualifiedName: row.qualifiedName,
			serverPrefix: row.serverPrefix,
			name: row.name,
			description: row.description,
			schema: row.schema as unknown,
		};
	}
}
