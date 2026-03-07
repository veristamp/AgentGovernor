import { readdir } from "node:fs/promises";
import { join, resolve } from "node:path";
import { eq, sql } from "drizzle-orm";
import { analyzeSkillCode } from "../../core/audit";
import { getOrgPolicyPaths } from "../../core/policy/org_config";
import { db, toTsVector } from "../db/db";
import { skills } from "../db/schema";
import type {
	GcmSignature,
	SkillExample,
	SkillFunctionSignature,
} from "./schema";

export interface SkillSummary {
	skillRef: string;
	skillId: string;
	version: string;
	description: string;
	interfaces: string[];
	bindings: Record<string, string>;
	fanoutTools: string[];
	functions?: SkillFunctionSignature[];
	examples?: SkillExample[];
	keywords?: string[];
}

// Re-export for compatibility
export interface SkillSearchResult extends SkillSummary {}

const DEFAULT_SKILLS_DIR = resolve("skills");

export class SkillRegistry {
	private skillsDir: string;

	constructor(skillsDir: string = DEFAULT_SKILLS_DIR, _dbPath?: string) {
		this.skillsDir = resolve(skillsDir);
	}

	/**
	 * Scan disk and populate Postgres
	 */
	public async ingest() {
		try {
			const entries = await readdir(this.skillsDir, { withFileTypes: true });
			let count = 0;

			for (const entry of entries) {
				if (!entry.isDirectory()) continue;
				const skillDir = join(this.skillsDir, entry.name);

				try {
					const summary = await this.readSkillFromDisk(skillDir);
					if (summary) {
						await this.upsert(summary);
						count++;
					}
				} catch (e) {
					console.error(
						`[SkillRegistry] Failed to load skill ${entry.name}:`,
						e,
					);
				}
			}

			if (count > 0) {
				console.log(`[SkillRegistry] Ingested ${count} skills.`);
			}
		} catch (_e) {
			// Directory might not exist
		}
	}

	private async readSkillFromDisk(
		skillDir: string,
	): Promise<SkillSummary | null> {
		const manifestPath = join(skillDir, "manifest.json");
		if (!(await Bun.file(manifestPath).exists())) return null;

		const raw = await Bun.file(manifestPath).text();
		const data = JSON.parse(raw);
		const signature = await this.readSignatureFromDisk(skillDir);
		const skillId = String(signature?.skillId ?? data.skillId ?? "").trim();
		if (!skillId) return null;

		const version = String(signature?.version ?? data.version ?? 1);
		const skillRef = signature?.skillRef ?? `skills:${skillId}@${version}`;

		const ownerOrgId =
			typeof data.ownerOrgId === "string" ? data.ownerOrgId : undefined;

		const libPath = join(skillDir, "lib.py");
		if (await Bun.file(libPath).exists()) {
			try {
				const code = await Bun.file(libPath).text();
				const paths = await getOrgPolicyPaths(ownerOrgId);
				const audit = await analyzeSkillCode(code, {
					configPath: paths.skillGateConfigPath,
				});
				if (!audit.allowed) {
					console.error(
						`[SkillRegistry] Skill gate rejected ${skillId}: ${audit.errors.join("; ")}`,
					);
					return null;
				}
			} catch (e) {
				console.error(`[SkillRegistry] Skill gate failed for ${skillId}:`, e);
				return null;
			}
		}

		let description = signature?.description ?? "";
		let interfaces: string[] = [];
		const functions: SkillFunctionSignature[] | undefined =
			signature?.functions;
		const examples: SkillExample[] | undefined = signature?.examples;
		const keywords: string[] | undefined = signature?.keywords;

		if (functions?.length) {
			interfaces = this.buildInterfacesFromFunctions(functions);
		} else if (data.interfaces && Array.isArray(data.interfaces)) {
			interfaces = data.interfaces;
		} else {
			const docPath = join(skillDir, "SKILL.md");
			if (await Bun.file(docPath).exists()) {
				const docContent = await Bun.file(docPath).text();
				const firstLine = docContent.split("\n")[0];
				description =
					description || (firstLine ?? "").replace(/^#\s+/, "").trim();
				const lines = docContent.split("\n");
				for (const line of lines) {
					if (line.trim() && !line.startsWith("#")) {
						description = description || line.trim();
						break;
					}
				}
				let inInterfaceSection = false;
				for (const line of lines) {
					if (line.match(/^##\s+Interface/i)) {
						inInterfaceSection = true;
						continue;
					}
					if (inInterfaceSection) {
						if (line.startsWith("##")) break;
						const match = line.match(/[`']?([\w_]+\([^)]*\))[`']?/);
						if (match) {
							interfaces.push(match[1] as string);
						}
					}
				}
			}
		}

		const resolvedInterfaces = interfaces.length
			? interfaces
			: data.interfaces || [];
		return {
			skillRef,
			skillId,
			version,
			description: description || data.description || "",
			interfaces: resolvedInterfaces,
			bindings: data.bindings || {},
			fanoutTools: data.fanoutTools || [],
			functions,
			examples,
			keywords,
		};
	}

	private async readSignatureFromDisk(
		skillDir: string,
	): Promise<GcmSignature | null> {
		const signaturePath = join(skillDir, "signature.json");
		if (!(await Bun.file(signaturePath).exists())) return null;
		const raw = await Bun.file(signaturePath).text();
		const parsed = JSON.parse(raw);
		return parsed as GcmSignature;
	}

	private buildInterfacesFromFunctions(
		functions: SkillFunctionSignature[],
	): string[] {
		return functions.map((fn) => {
			const params = (fn.params ?? []).map((param) => param.name).join(", ");
			return `${fn.name}(${params})`;
		});
	}

	private async upsert(skill: SkillSummary) {
		const interfacesJson = skill.interfaces;
		const keywordText = skill.keywords?.join(" ") ?? "";
		const functionText = skill.functions?.map((fn) => fn.name).join(" ") ?? "";
		const searchText = `${skill.skillRef} ${skill.skillId} ${skill.description} ${interfacesJson.join(" ")} ${keywordText} ${functionText}`;

		await db
			.insert(skills)
			.values({
				skillRef: skill.skillRef,
				skillId: skill.skillId,
				version: skill.version,
				description: skill.description,
				manifest: {
					bindings: skill.bindings,
					fanoutTools: skill.fanoutTools,
				},
				interfaces: interfacesJson,
				searchVector: toTsVector(searchText),
			})
			.onConflictDoUpdate({
				target: skills.skillRef,
				set: {
					description: skill.description,
					manifest: {
						bindings: skill.bindings,
						fanoutTools: skill.fanoutTools,
					},
					interfaces: interfacesJson,
					searchVector: toTsVector(searchText),
				},
			});
	}

	public async search(
		query: string,
		limit: number = 20,
	): Promise<SkillSummary[]> {
		const sanitized = query.replace(/[^\w\s]/g, "").trim();
		if (!sanitized) return (await this.listAll()).slice(0, limit);

		const tokens = sanitized.split(/\s+/).filter((t) => t.length > 2);
		if (tokens.length === 0) return (await this.listAll()).slice(0, limit);

		const searchQuery = tokens.join(" | ");

		const results = await db
			.select()
			.from(skills)
			.where(sql`search_vector @@ to_tsquery('english', ${searchQuery})`)
			.limit(limit);

		return results.map(this.mapRow);
	}

	public async listAll(): Promise<SkillSummary[]> {
		const results = await db.select().from(skills);
		return results.map(this.mapRow);
	}

	public async inspect(skillRef: string): Promise<SkillSummary | null> {
		const results = await db
			.select()
			.from(skills)
			.where(eq(skills.skillRef, skillRef));
		if (results.length === 0 || !results[0]) return null;
		const summary = this.mapRow(results[0]);
		const signature = await this.readSignatureFromDisk(
			join(this.skillsDir, summary.skillId),
		);
		if (!signature) return summary;
		summary.description = signature.description || summary.description;
		summary.functions = signature.functions;
		summary.examples = signature.examples;
		summary.keywords = signature.keywords;
		if (signature.functions?.length) {
			summary.interfaces = this.buildInterfacesFromFunctions(
				signature.functions,
			);
		}
		return summary;
	}

	private mapRow(row: typeof skills.$inferSelect): SkillSummary {
		const manifest = row.manifest as {
			bindings: Record<string, string>;
			fanoutTools: string[];
		};
		return {
			skillRef: row.skillRef,
			skillId: row.skillId,
			version: row.version,
			description: row.description,
			interfaces: row.interfaces as string[],
			bindings: manifest.bindings,
			fanoutTools: manifest.fanoutTools,
		};
	}
}
