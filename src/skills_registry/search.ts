import { readdir } from "node:fs/promises";
import { join, resolve } from "path";
import type { SkillSearchResult, SkillSummary } from "./registry";
import { SkillRegistry } from "./registry";
import type { GcmRegistrySearchResult, GcmSignature } from "./schema";

const DEFAULT_SKILLS_DIR = resolve("skills");

export class GcmRegistrySearch {
	private signatures: GcmSignature[] = [];
	public legacyRegistry: SkillRegistry;

	constructor(private skillsDir: string = DEFAULT_SKILLS_DIR) {
		this.legacyRegistry = new SkillRegistry(skillsDir);
	}

	/**
	 * Loads signatures. If signature.json is missing, it auto-compiles from legacy skill data.
	 */
	async load(): Promise<void> {
		const resolved = resolve(this.skillsDir);
		// Ensure legacy registry is loaded for fallback/migration
		await this.legacyRegistry.ingest();

		try {
			const entries = await readdir(resolved, { withFileTypes: true });
			this.signatures = [];

			for (const entry of entries) {
				if (!entry.isDirectory()) continue;
				const skillDir = join(resolved, entry.name);
				const sigPath = join(skillDir, "signature.json");

				if (await Bun.file(sigPath).exists()) {
					try {
						const sig = await Bun.file(sigPath).json();
						this.signatures.push(sig);
					} catch (e) {
						console.error(`Failed to load signature for ${entry.name}:`, e);
					}
				} else {
					const legacySkill =
						(await this.legacyRegistry.inspect(`skills:${entry.name}@1`)) ||
						(await this.legacyRegistry.listAll()).find(
							(s) => s.skillId === entry.name,
						);
					if (legacySkill) {
						const skillRef =
							legacySkill.skillRef ||
							`skills:${legacySkill.skillId}@${legacySkill.version}`;
						this.signatures.push({
							skillRef,
							skillId: legacySkill.skillId,
							version: String(legacySkill.version),
							description: legacySkill.description.slice(0, 200),
							keywords: legacySkill.skillId.split("-"),
							functions: legacySkill.interfaces.map((signature) => ({
								name: signature.split("(")[0]?.trim() || signature,
								params: [],
							})),
							examples: [],
							dependencies: [],
							fanoutTools: legacySkill.fanoutTools,
						});
					}
				}
			}
		} catch (e) {
			// Directory might not exist
		}
	}

	/**
	 * The Core Search Function (Regex/BM25 style) - Modern Agent Path
	 * Mimics tool_search_tool_regex behavior
	 */
	search(query: string, limit: number = 5): GcmRegistrySearchResult {
		const q = query.toLowerCase();
		let matches: GcmSignature[] = [];

		try {
			// Regex Mode
			const regex = new RegExp(q, "i");
			matches = this.signatures.filter(
				(sig) =>
					regex.test(sig.skillRef) ||
					regex.test(sig.skillId) ||
					regex.test(sig.description) ||
					sig.keywords.some((k) => regex.test(k)) ||
					sig.functions.some(
						(fn) =>
							regex.test(fn.name) || (fn.summary && regex.test(fn.summary)),
					),
			);
		} catch (e) {
			// Fallback to simple inclusion if regex fails
			matches = this.signatures.filter(
				(sig) =>
					sig.skillRef.toLowerCase().includes(q) ||
					sig.skillId.toLowerCase().includes(q) ||
					sig.description.toLowerCase().includes(q),
			);
		}

		// Rank by relevance
		matches.sort((a, b) => {
			if (a.skillRef.includes(q) && !b.skillRef.includes(q)) return -1;
			if (b.skillRef.includes(q) && !a.skillRef.includes(q)) return 1;
			return 0;
		});

		const selected = matches.slice(0, limit);

		return {
			type: "tool_search_result",
			tool_references: selected.map((sig) => ({
				type: "tool_reference",
				tool_name: sig.skillRef,
				signature: sig,
			})),
		};
	}

	async listAll(): Promise<SkillSummary[]> {
		return await this.legacyRegistry.listAll();
	}
}
