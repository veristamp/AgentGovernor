import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { validatePath } from "../path-validation.js";
import { minimatch } from "minimatch";

export type GrepMatch = {
	file: string;
	line: number;
	column: number;
	lineContent: string;
};

export type GrepOptions = {
	pattern: string;
	path: string;
	excludePatterns?: string[];
	fileExtensions?: string[];
	maxMatches?: number;
	contextLines?: number;
	caseSensitive?: boolean;
	useRegex?: boolean;
};

/**
 * Check if ripgrep is available
 */
export async function isRipgrepAvailable(): Promise<boolean> {
	try {
		await new Promise<void>((resolve, reject) => {
			const proc = spawn("rg", ["--version"], {
				stdio: ["ignore", "pipe", "pipe"],
			});
			proc.on("close", (code) => {
				if (code === 0) resolve();
				else reject(new Error("rg not found"));
			});
			proc.on("error", () => reject(new Error("rg not found")));
			setTimeout(() => {
				proc.kill();
				reject(new Error("rg timeout"));
			}, 2000);
		});
		return true;
	} catch {
		return false;
	}
}

/**
 * Execute ripgrep search
 */
async function searchWithRipgrep(
	rootPath: string,
	pattern: string,
	opts: GrepOptions,
): Promise<GrepMatch[]> {
	const maxMatches = opts.maxMatches ?? 1000;
	const contextLines = opts.contextLines ?? 0;
	const args = [
		"--line-number",
		"--column",
		"--no-heading",
		"--with-filename",
		"--case-insensitive", // Default to case-insensitive for agent use
		"--max-count", String(maxMatches),
	];

	if (opts.contextLines && opts.contextLines > 0) {
		args.push("--", "-B", String(opts.contextLines), "-A", String(opts.contextLines));
	}

	if (opts.caseSensitive) {
		args.push("--case-sensitive");
	}

	if (!opts.useRegex) {
		args.push("--fixed-strings");
	}

	// Add file extensions filter if specified
	if (opts.fileExtensions && opts.fileExtensions.length > 0) {
		const extPatterns = opts.fileExtensions.map((ext) => `*.${ext.replace(/^\./, "")}`);
		args.push(...extPatterns);
	}

	// Add exclude patterns
	if (opts.excludePatterns && opts.excludePatterns.length > 0) {
		for (const ex of opts.excludePatterns) {
			args.push("--glob", `!${ex}`);
		}
	}

	args.push(pattern);
	args.push(rootPath);

	return new Promise((resolve, reject) => {
		const matches: GrepMatch[] = [];
		const proc = spawn("rg", args, {
			stdio: ["ignore", "pipe", "pipe"],
		});

		let stderr = "";
		proc.stderr.on("data", (data) => {
			stderr += data.toString();
		});

		const chunks: Buffer[] = [];
		proc.stdout.on("data", (data) => {
			chunks.push(Buffer.from(data));
		});

		proc.on("close", () => {
			try {
				const output = Buffer.concat(chunks).toString("utf-8");
				for (const line of output.split("\n")) {
					if (!line.trim()) continue;
					const match = parseRipgrepLine(line);
					if (match) {
						// Check exclusions manually as well
						let relative = path.relative(rootPath, match.file);
						relative = relative.replace(/\\/g, "/");
						const excluded = opts.excludePatterns?.some((ex) =>
							minimatch(relative, ex, { dot: true }),
						);
						if (!excluded) {
							matches.push(match);
						}
					}
					if (matches.length >= maxMatches) break;
				}
				resolve(matches);
			} catch (err) {
				reject(err);
			}
		});

		proc.on("error", (err) => {
			reject(err);
		});

		// Timeout after 30 seconds
		setTimeout(() => {
			proc.kill();
			resolve(matches); // Return what we have so far
		}, 30000);
	});
}

function parseRipgrepLine(line: string): GrepMatch | null {
	// Format: file:line:column:content or file:line:column
	const colonIdx1 = line.indexOf(":");
	if (colonIdx1 === -1) return null;

	const file = line.slice(0, colonIdx1);
	const rest = line.slice(colonIdx1 + 1);

	const colonIdx2 = rest.indexOf(":");
	if (colonIdx2 === -1) {
		// Just file:line - no content
		const lineNum = parseInt(rest, 10);
		if (isNaN(lineNum)) return null;
		return {
			file,
			line: lineNum,
			column: 1,
			lineContent: "",
		};
	}

	const lineNum = parseInt(rest.slice(0, colonIdx2), 10);
	if (isNaN(lineNum)) return null;

	const afterCol = rest.slice(colonIdx2 + 1);
	const colonIdx3 = afterCol.indexOf(":");
	if (colonIdx3 === -1) return null;

	const column = parseInt(afterCol.slice(0, colonIdx3), 10);
	if (isNaN(column)) return null;

	const content = afterCol.slice(colonIdx3 + 1);

	return {
		file,
		line: lineNum,
		column,
		lineContent: content,
	};
}

/**
 * Fallback: Basic content search using Node.js
 */
async function searchWithNode(
	rootPath: string,
	pattern: string,
	opts: GrepOptions,
): Promise<GrepMatch[]> {
	const maxMatches = opts.maxMatches ?? 1000;
	const matches: GrepMatch[] = [];
	const searchRegex = opts.useRegex
		? new RegExp(pattern, opts.caseSensitive ? "g" : "gi")
		: null;

	async function walk(current: string): Promise<void> {
		if (matches.length >= maxMatches) return;

		let entries: import("node:fs").Dirent[];
		try {
			entries = await fs.readdir(current, { withFileTypes: true });
		} catch {
			return;
		}

		for (const entry of entries) {
			if (matches.length >= maxMatches) break;

			const full = path.join(current, entry.name);
			let relative = path.relative(rootPath, full);
			relative = relative.replace(/\\/g, "/");

			// Check exclusions
			const excluded = opts.excludePatterns?.some((ex) =>
				minimatch(relative, ex, { dot: true }),
			);
			if (excluded) continue;

			// Check file extensions
			if (opts.fileExtensions && opts.fileExtensions.length > 0) {
				const ext = path.extname(entry.name).replace(/^\./, "");
				if (!opts.fileExtensions.includes(ext)) {
					if (entry.isFile()) continue;
				}
			}

			if (entry.isDirectory()) {
				await walk(full);
			} else if (entry.isFile()) {
				try {
					const content = await fs.readFile(full, "utf-8");
					const lines = content.split("\n");
					for (let i = 0; i < lines.length && matches.length < maxMatches; i++) {
						const line = lines[i];
						let matched = false;

						if (searchRegex) {
							searchRegex.lastIndex = 0;
							matched = searchRegex.test(line);
						} else {
							matched = opts.caseSensitive
								? line.includes(pattern)
								: line.toLowerCase().includes(pattern.toLowerCase());
						}

						if (matched) {
							matches.push({
								file: full,
								line: i + 1,
								column: line.indexOf(pattern) + 1,
								lineContent: line.trim(),
							});
						}
					}
				} catch {
					// Skip unreadable files
				}
			}
		}
	}

	await walk(rootPath);
	return matches;
}

/**
 * Main grep search function - uses ripgrep if available, falls back to Node.js
 */
export async function grepSearch(opts: GrepOptions): Promise<GrepMatch[]> {
	const rootPath = await validatePath(opts.path);

	// Check if ripgrep is available
	const hasRipgrep = await isRipgrepAvailable();

	if (hasRipgrep) {
		try {
			return await searchWithRipgrep(rootPath, opts.pattern, opts);
		} catch {
			// Fall back to Node.js if ripgrep fails
		}
	}

	// Use Node.js fallback
	return await searchWithNode(rootPath, opts.pattern, opts);
}

/**
 * Format grep results for display
 */
export function formatGrepResults(matches: GrepMatch[]): string {
	if (matches.length === 0) {
		return "No matches found";
	}

	const grouped = new Map<string, GrepMatch[]>();
	for (const match of matches) {
		if (!grouped.has(match.file)) {
			grouped.set(match.file, []);
		}
		grouped.get(match.file)!.push(match);
	}

	const lines: string[] = [];
	for (const [file, fileMatches] of grouped) {
		lines.push(`\n${file}:`);
		for (const match of fileMatches) {
			const content = match.lineContent
				? ` | ${match.lineContent}`
				: "";
			lines.push(`  ${match.line}:${match.column}${content}`);
		}
	}

	lines.push(`\nTotal: ${matches.length} matches in ${grouped.size} files`);
	return lines.join("\n");
}
