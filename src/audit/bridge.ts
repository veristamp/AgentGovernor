/**
 * Auditor Bridge
 *
 * TypeScript bridge to the Python static auditor.
 * Calls the Python analyzer and parses the result.
 */

import { spawn } from "node:child_process";
import { dirname, resolve as resolvePath } from "node:path";
import { fileURLToPath } from "node:url";
import type { Manifest } from "../policy/types";

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Analyze Python code using the static auditor.
 *
 * @param code Python workflow code
 * @returns Manifest of what the code will do
 */
export async function analyzeCode(code: string): Promise<Manifest> {
	const analyzerPath = resolvePath(__dirname, "../../auditor/analyzer.py");

	return new Promise((resolve, reject) => {
		const child = spawn("uv", ["run", analyzerPath, "--json"], {
			stdio: ["pipe", "pipe", "pipe"],
		});

		let stdout = "";
		let stderr = "";

		child.stdout.on("data", (data) => {
			stdout += data.toString();
		});

		child.stderr.on("data", (data) => {
			stderr += data.toString();
		});

		// Send code to stdin
		child.stdin.write(code);
		child.stdin.end();

		child.on("error", (err) => {
			reject(new Error(`Failed to run analyzer: ${err.message}`));
		});

		child.on("close", (_exitCode) => {
			try {
				const result = JSON.parse(stdout) as {
					manifest: {
						tools: string[];
						skills: string[];
						tool_calls: Array<{
							tool: string;
							line: number;
							col: number;
							static_args: Record<string, unknown>;
							dynamic_args: string[];
						}>;
						has_loops: boolean;
						has_conditionals: boolean;
						max_depth: number;
						errors: string[];
						warnings: string[];
					};
					violations: string[];
					allowed: boolean;
				};

				// Convert snake_case to camelCase
				const manifest: Manifest = {
					tools: result.manifest.tools,
					skills: result.manifest.skills,
					toolCalls: result.manifest.tool_calls.map((tc) => ({
						tool: tc.tool,
						line: tc.line,
						col: tc.col,
						staticArgs: tc.static_args,
						dynamicArgs: tc.dynamic_args,
					})),
					hasLoops: result.manifest.has_loops,
					hasConditionals: result.manifest.has_conditionals,
					maxDepth: result.manifest.max_depth,
					errors: result.manifest.errors,
					warnings: result.manifest.warnings,
				};

				resolve(manifest);
			} catch (_e) {
				reject(
					new Error(`Failed to parse analyzer output: ${stdout}\n${stderr}`),
				);
			}
		});
	});
}

export interface SkillAuditResult {
	errors: string[];
	warnings: string[];
	allowed: boolean;
}

export async function analyzeSkillCode(
	code: string,
	options?: { configPath?: string },
): Promise<SkillAuditResult> {
	const analyzerPath = resolvePath(
		__dirname,
		"../../auditor/skill_analyzer.py",
	);

	const args = [analyzerPath];
	if (options?.configPath) {
		args.push("--config", options.configPath);
	}

	return new Promise((resolve, reject) => {
		const child = spawn("uv", ["run", ...args], {
			stdio: ["pipe", "pipe", "pipe"],
		});

		let stdout = "";
		let stderr = "";

		child.stdout.on("data", (data) => {
			stdout += data.toString();
		});

		child.stderr.on("data", (data) => {
			stderr += data.toString();
		});

		child.stdin.write(code);
		child.stdin.end();

		child.on("error", (err) => {
			reject(new Error(`Failed to run skill analyzer: ${err.message}`));
		});

		child.on("close", () => {
			try {
				const result = JSON.parse(stdout) as SkillAuditResult;
				resolve(result);
			} catch (_e) {
				reject(
					new Error(
						`Failed to parse skill analyzer output: ${stdout}\n${stderr}`,
					),
				);
			}
		});
	});
}

/**
 * Quick check if code has any parse errors.
 */
export async function validateSyntax(
	code: string,
): Promise<{ valid: boolean; errors: string[] }> {
	const manifest = await analyzeCode(code);

	const syntaxErrors = manifest.errors.filter((e) =>
		e.includes("Syntax error"),
	);

	return {
		valid: syntaxErrors.length === 0,
		errors: syntaxErrors,
	};
}
