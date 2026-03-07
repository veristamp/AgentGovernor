import crypto from "node:crypto";
import {
	accessSync,
	type Dirent,
	constants as fsConstants,
	statSync,
} from "node:fs";
import { mkdir, readdir, realpath, rename, rm, stat } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
	type Root,
	RootsListChangedNotificationSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

const args = process.argv.slice(2);
const defaultDir = path.resolve(".");
let allowedDirectories: string[] = [];

const expandHome = (inputPath: string) =>
	inputPath.startsWith("~")
		? path.join(os.homedir(), inputPath.slice(1))
		: inputPath;

const normalizePath = (inputPath: string) =>
	path.resolve(expandHome(inputPath));

const isWithin = (targetPath: string, root: string) => {
	const relative = path.relative(root, targetPath);
	return (
		relative === "" ||
		(!relative.startsWith("..") && !path.isAbsolute(relative))
	);
};

const bootstrapAllowedDirectories = () => {
	if (args.length === 0) {
		allowedDirectories = [defaultDir];
		let current = defaultDir;
		for (let i = 0; i < 3; i += 1) {
			const parent = path.dirname(current);
			if (parent !== current) {
				allowedDirectories.push(parent);
				current = parent;
			} else {
				break;
			}
		}
		return;
	}

	const candidates = args.map((dir) => normalizePath(dir));
	const valid: string[] = [];
	for (const dir of candidates) {
		try {
			const info = statSync(dir);
			if (!info.isDirectory()) {
				continue;
			}
			accessSync(dir, fsConstants.R_OK);
			valid.push(dir);
		} catch {}
	}

	allowedDirectories = valid.length > 0 ? valid : [defaultDir];
};

bootstrapAllowedDirectories();

const validatePath = async (requestedPath: string) => {
	const absolute = normalizePath(requestedPath);
	if (allowedDirectories.length === 0) {
		throw new Error("No allowed directories configured");
	}

	if (!allowedDirectories.some((root) => isWithin(absolute, root))) {
		throw new Error(
			`Access denied - path outside allowed directories: ${absolute}`,
		);
	}

	// If target exists, validate resolved (symlink-safe)
	try {
		const resolved = await realpath(absolute);
		if (!allowedDirectories.some((root) => isWithin(resolved, root))) {
			throw new Error(
				`Access denied - symlink target outside allowed directories: ${resolved}`,
			);
		}
		return resolved;
	} catch (err) {
		// For new paths, verify the parent exists and is inside allowed dirs.
		const code =
			err &&
			typeof err === "object" &&
			"code" in err &&
			typeof (err as { code?: unknown }).code === "string"
				? (err as { code: string }).code
				: undefined;
		if (code === "ENOENT") {
			const parent = path.dirname(absolute);
			const resolvedParent = await realpath(parent).catch(() => {
				throw new Error(`Parent directory does not exist: ${parent}`);
			});
			if (!allowedDirectories.some((root) => isWithin(resolvedParent, root))) {
				throw new Error(
					`Access denied - parent directory outside allowed directories: ${resolvedParent}`,
				);
			}
			return absolute;
		}
		throw err;
	}
};

const normalizeLineEndings = (text: string) => text.replace(/\r\n/g, "\n");

const createUnifiedDiff = (
	original: string,
	modified: string,
	filepath: string,
) => {
	const originalLines = normalizeLineEndings(original).split("\n");
	const modifiedLines = normalizeLineEndings(modified).split("\n");
	const dp: number[][] = Array.from({ length: originalLines.length + 1 }, () =>
		new Array(modifiedLines.length + 1).fill(0),
	);

	for (let i = 1; i <= originalLines.length; i += 1) {
		for (let j = 1; j <= modifiedLines.length; j += 1) {
			const row = dp[i];
			const upRow = dp[i - 1];
			if (!row || !upRow) {
				throw new Error("Invariant failed: dp rows missing");
			}

			if (originalLines[i - 1] === modifiedLines[j - 1]) {
				row[j] = (upRow[j - 1] ?? 0) + 1;
			} else {
				row[j] = Math.max(upRow[j] ?? 0, row[j - 1] ?? 0);
			}
		}
	}

	const diffLines: string[] = [];
	let i = originalLines.length;
	let j = modifiedLines.length;
	while (i > 0 && j > 0) {
		if (originalLines[i - 1] === modifiedLines[j - 1]) {
			diffLines.push(` ${originalLines[i - 1]}`);
			i -= 1;
			j -= 1;
		} else if ((dp[i - 1]?.[j] ?? 0) >= (dp[i]?.[j - 1] ?? 0)) {
			diffLines.push(`-${originalLines[i - 1]}`);
			i -= 1;
		} else {
			diffLines.push(`+${modifiedLines[j - 1]}`);
			j -= 1;
		}
	}

	while (i > 0) {
		diffLines.push(`-${originalLines[i - 1]}`);
		i -= 1;
	}

	while (j > 0) {
		diffLines.push(`+${modifiedLines[j - 1]}`);
		j -= 1;
	}

	diffLines.reverse();
	return [`--- ${filepath}`, `+++ ${filepath}`, ...diffLines].join("\n");
};

const sha256Hex = (text: string) =>
	crypto.createHash("sha256").update(text).digest("hex");

const fileLinesToSpan = (
	content: string,
	startLine1: number,
	endLine1: number,
): { start: number; end: number } => {
	if (startLine1 < 1 || endLine1 < 1 || endLine1 < startLine1) {
		throw new Error(
			"Invalid line range: start_line/end_line are 1-based and end_line must be >= start_line",
		);
	}

	const lines = normalizeLineEndings(content).split("\n");
	if (startLine1 > lines.length || endLine1 > lines.length) {
		throw new Error(`Line range out of bounds. File has ${lines.length} lines`);
	}

	let start = 0;
	for (let i = 1; i < startLine1; i += 1) {
		start += (lines[i - 1]?.length ?? 0) + 1;
	}

	let end = start;
	for (let i = startLine1; i <= endLine1; i += 1) {
		end += lines[i - 1]?.length ?? 0;
		if (i !== lines.length) end += 1;
	}

	return { start, end };
};

const atomicWrite = async (
	filePath: string,
	data: string | Uint8Array,
): Promise<void> => {
	const dir = path.dirname(filePath);
	await mkdir(dir, { recursive: true });
	const tmp = path.join(
		dir,
		`.tmp.${path.basename(filePath)}.${crypto.randomBytes(8).toString("hex")}`,
	);
	try {
		await Bun.write(tmp, data);
		await rename(tmp, filePath);
	} finally {
		await rm(tmp, { force: true }).catch(() => {});
	}
};

const searchFilesImpl = async (
	rootPath: string,
	pattern: string,
	excludePatterns: string[] = [],
	limit: number = 5000,
) => {
	const results: string[] = [];
	const lowerPattern = pattern.toLowerCase();
	const excludeRegexes = excludePatterns
		.map((raw) => {
			try {
				return new RegExp(raw);
			} catch {
				return null;
			}
		})
		.filter((regex): regex is RegExp => Boolean(regex));

	const stack: string[] = [rootPath];
	while (stack.length > 0 && results.length < limit) {
		const current = stack.pop();
		if (!current) break;

		let entries: Dirent[];
		try {
			entries = (await readdir(current, { withFileTypes: true })) as Dirent[];
		} catch {
			continue;
		}

		for (const entry of entries) {
			const fullPath = path.join(current, entry.name);
			const relativePath = path.relative(rootPath, fullPath);
			if (excludeRegexes.some((regex) => regex.test(relativePath))) {
				continue;
			}

			if (entry.name.toLowerCase().includes(lowerPattern)) {
				results.push(fullPath);
				if (results.length >= limit) break;
			}

			if (entry.isDirectory()) {
				stack.push(fullPath);
			}
		}
	}

	return results;
};

const server = new McpServer({
	name: "secure-filesystem-server",
	version: "2.0.0",
});

async function updateAllowedDirectoriesFromRoots(
	requestedRoots: readonly Root[],
) {
	const next: string[] = [];
	for (const r of requestedRoots) {
		const raw = r.uri.startsWith("file://") ? r.uri.slice(7) : r.uri;
		const absolute = normalizePath(raw);
		try {
			const resolved = await realpath(absolute);
			const info = await stat(resolved);
			if (info.isDirectory()) next.push(resolved);
		} catch {}
	}

	if (next.length > 0) {
		allowedDirectories = next;
	}
}

server.server.setNotificationHandler(
	RootsListChangedNotificationSchema,
	async () => {
		try {
			const resp = await server.server.listRoots();
			if (resp && "roots" in resp) {
				await updateAllowedDirectoriesFromRoots(resp.roots);
			}
		} catch {}
	},
);

server.server.oninitialized = async () => {
	const caps = server.server.getClientCapabilities();
	if (caps?.roots) {
		try {
			const resp = await server.server.listRoots();
			if (resp && "roots" in resp) {
				await updateAllowedDirectoriesFromRoots(resp.roots);
			}
		} catch {}
	}
};

// Register tools using the non-deprecated registerTool API
server.registerTool(
	"read-file",
	{
		description:
			"Read the complete contents of a file asynchronously.\n\n" +
			"Args:\n" +
			"    path: Path to the file\n" +
			'    encoding: "utf-8" for text files (default), "base64" for binary files (xlsx, images, pdf)\n\n' +
			'For binary files like Excel, use encoding="base64" to get base64-encoded content.\n' +
			"Only works within allowed directories.",
		inputSchema: {
			path: z.string().describe("Path to the file"),
			encoding: z
				.string()
				.default("utf-8")
				.describe(
					'"utf-8" for text files (default), "base64" for binary files (xlsx, images, pdf)',
				),
		},
		annotations: { readOnlyHint: true },
	},
	async ({ path: filePath, encoding }) => {
		const validPath = await validatePath(filePath);
		const file = Bun.file(validPath);
		const exists = await file.exists();
		if (!exists) {
			throw new Error(`File not found: ${filePath}`);
		}

		if (encoding === "base64") {
			const data = await file.arrayBuffer();
			const encoded = Buffer.from(data).toString("base64");
			return { content: [{ type: "text", text: encoded }] };
		}

		const text = await file.text();
		return { content: [{ type: "text", text }] };
	},
);

server.registerTool(
	"read-multiple-files",
	{
		description:
			"Read the contents of multiple files asynchronously.\n" +
			"Returns each file's content prefixed with its path, separated by '---'.\n" +
			"Continues on individual file errors. Only works within allowed directories.",
		inputSchema: {
			paths: z.array(z.string()).describe("Paths to the files"),
		},
		annotations: { readOnlyHint: true },
	},
	async ({ paths }) => {
		const results: string[] = [];
		for (const filePath of paths) {
			try {
				const validPath = await validatePath(filePath);
				const file = Bun.file(validPath);
				const exists = await file.exists();
				if (!exists) {
					throw new Error("File not found");
				}
				const text = await file.text();
				results.push(`${filePath}:\n${text}`);
			} catch (err) {
				results.push(`${filePath}: Error - ${String(err)}`);
			}
		}
		return { content: [{ type: "text", text: results.join("\n---\n") }] };
	},
);

server.registerTool(
	"write-file",
	{
		description:
			"Create or overwrite a file with new content asynchronously.\n\n" +
			"Args:\n" +
			"    path: Path to the file\n" +
			"    content: Content to write (string or base64-encoded for binary)\n" +
			'    encoding: "utf-8" for text files (default), "base64" for binary files\n\n' +
			'For binary files, pass base64-encoded content and set encoding="base64".\n' +
			"Overwrites existing files without warning. Only works within allowed directories.",
		inputSchema: {
			path: z.string().describe("Path to the file"),
			content: z
				.string()
				.describe("Content to write (string or base64-encoded for binary)"),
			encoding: z
				.string()
				.default("utf-8")
				.describe(
					'"utf-8" for text files (default), "base64" for binary files',
				),
			max_bytes: z.number().default(2000000).describe("Maximum bytes to write"),
		},
		annotations: {
			readOnlyHint: false,
			idempotentHint: true,
			destructiveHint: true,
		},
	},
	async ({ path: filePath, content, encoding, max_bytes }) => {
		const validPath = await validatePath(filePath);

		if (encoding === "base64") {
			let binary: Buffer;
			try {
				binary = Buffer.from(content, "base64");
			} catch (err) {
				throw new Error(`Invalid base64 content: ${String(err)}`);
			}

			if (binary.length > max_bytes) {
				throw new Error(`Refusing to write >${max_bytes} bytes`);
			}

			await atomicWrite(validPath, binary);
			return {
				content: [
					{
						type: "text",
						text: `Successfully wrote ${binary.length} bytes to ${filePath}`,
					},
				],
			};
		}

		const data = new TextEncoder().encode(content);
		if (data.length > max_bytes) {
			throw new Error(`Refusing to write >${max_bytes} bytes`);
		}

		await atomicWrite(validPath, content);
		return {
			content: [{ type: "text", text: `Successfully wrote to ${filePath}` }],
		};
	},
);

server.registerTool(
	"edit-file",
	{
		description:
			"Make line-based edits to a text file with flexible matching.\n" +
			"Returns a git-style diff and a UI preview.",
		inputSchema: {
			path: z.string().describe("Path to the file"),
			edits: z
				.array(
					z.object({
						oldText: z.string().describe("Text to replace"),
						newText: z.string().describe("New text"),
					}),
				)
				.describe("List of edit operations"),
			dry_run: z
				.boolean()
				.default(true)
				.describe("Whether to perform a dry run"),
		},
		annotations: {
			readOnlyHint: false,
			idempotentHint: false,
			destructiveHint: true,
		},
	},
	async ({ path: filePath, edits, dry_run }) => {
		const validPath = await validatePath(filePath);
		const file = Bun.file(validPath);
		const exists = await file.exists();
		if (!exists) {
			throw new Error(`File not found: ${filePath}`);
		}

		const original = normalizeLineEndings(await file.text());
		let modified = original;
		let applied = 0;

		for (const edit of edits) {
			if (modified.includes(edit.oldText)) {
				modified = modified.replace(edit.oldText, edit.newText);
				applied += 1;
				continue;
			}

			const oldLines = edit.oldText.split("\n").map((line) => line.trim());
			const lines = modified.split("\n");
			for (let idx = 0; idx <= lines.length - oldLines.length; idx += 1) {
				const slice = lines
					.slice(idx, idx + oldLines.length)
					.map((line) => line.trim());
				const matches = slice.every((line, i) => line === oldLines[i]);
				if (matches) {
					const replacement = edit.newText.split("\n");
					lines.splice(idx, oldLines.length, ...replacement);
					modified = lines.join("\n");
					applied += 1;
					break;
				}
			}
		}

		if (applied === 0) {
			throw new Error("No edits applied (no matches found).");
		}

		const diff = createUnifiedDiff(original, modified, validPath);
		if (!dry_run) await atomicWrite(validPath, modified);

		return { content: [{ type: "text", text: diff }] };
	},
);

server.registerTool(
	"patch-lines",
	{
		description:
			"LLM-friendly surgical patch: replace a 1-based inclusive line range with new content. " +
			"Returns a unified diff. Use dry_run=true first.",
		inputSchema: {
			path: z.string().describe("Path to the file"),
			start_line: z.number().describe("1-based start line (inclusive)"),
			end_line: z.number().describe("1-based end line (inclusive)"),
			new_content: z.string().describe("Replacement content"),
			expected_sha256: z
				.string()
				.optional()
				.describe("Optional sha256 guard of the selected slice"),
			allow_drift: z
				.boolean()
				.default(false)
				.describe("If true, proceed even if expected_sha256 mismatches"),
			dry_run: z.boolean().default(true),
		},
		annotations: {
			readOnlyHint: false,
			idempotentHint: false,
			destructiveHint: true,
		},
	},
	async ({
		path: filePath,
		start_line,
		end_line,
		new_content,
		expected_sha256,
		allow_drift,
		dry_run,
	}) => {
		const validPath = await validatePath(filePath);
		const file = Bun.file(validPath);
		if (!(await file.exists())) throw new Error(`File not found: ${filePath}`);

		const original = normalizeLineEndings(await file.text());
		const span = fileLinesToSpan(original, start_line, end_line);
		const currentSlice = original.slice(span.start, span.end);
		if (expected_sha256) {
			const got = sha256Hex(currentSlice);
			if (got !== expected_sha256.toLowerCase()) {
				if (!allow_drift)
					throw new Error("Content drift detected for selected line range");
			}
		}

		const modified =
			original.slice(0, span.start) + new_content + original.slice(span.end);
		const diff = createUnifiedDiff(original, modified, validPath);
		if (!dry_run) await atomicWrite(validPath, modified);
		return { content: [{ type: "text", text: diff }] };
	},
);

server.registerTool(
	"patch-span",
	{
		description:
			"Advanced surgical patch: replace a 0-based character span [start:end] with new content. " +
			"Optionally guard with expected_sha256 of the current slice.",
		inputSchema: {
			path: z.string().describe("Path to the file"),
			start: z.number().describe("0-based char offset (inclusive)"),
			end: z.number().describe("0-based char offset (exclusive)"),
			new_content: z.string().describe("Replacement content"),
			expected_sha256: z
				.string()
				.optional()
				.describe("Optional sha256 guard of the selected slice"),
			allow_drift: z
				.boolean()
				.default(false)
				.describe("If true, proceed even if expected_sha256 mismatches"),
			dry_run: z.boolean().default(true),
		},
		annotations: {
			readOnlyHint: false,
			idempotentHint: false,
			destructiveHint: true,
		},
	},
	async ({
		path: filePath,
		start,
		end,
		new_content,
		expected_sha256,
		allow_drift,
		dry_run,
	}) => {
		const validPath = await validatePath(filePath);
		const file = Bun.file(validPath);
		if (!(await file.exists())) throw new Error(`File not found: ${filePath}`);

		const original = normalizeLineEndings(await file.text());
		if (start < 0 || end < 0 || start > end || end > original.length) {
			throw new Error(
				`Invalid offsets: start=${start}, end=${end}, len=${original.length}`,
			);
		}
		const currentSlice = original.slice(start, end);
		if (expected_sha256) {
			const got = sha256Hex(currentSlice);
			if (got !== expected_sha256.toLowerCase()) {
				if (!allow_drift)
					throw new Error("Content drift detected for selected span");
			}
		}
		const modified =
			original.slice(0, start) + new_content + original.slice(end);
		const diff = createUnifiedDiff(original, modified, validPath);
		if (!dry_run) await atomicWrite(validPath, modified);
		return { content: [{ type: "text", text: diff }] };
	},
);

server.registerTool(
	"stitch-file",
	{
		description:
			"Frankenstein stitcher: assemble a new file from byte slices of existing files. " +
			"Each graft copies [start:end] from a source file, with optional glue/comment.",
		inputSchema: {
			grafts: z.array(
				z.object({
					source: z.string().describe("Source file path"),
					start: z.number().describe("0-based char offset (inclusive)"),
					end: z.number().describe("0-based char offset (exclusive)"),
					comment: z
						.string()
						.optional()
						.describe("Optional comment inserted before this graft"),
					glue: z
						.string()
						.optional()
						.describe("Optional text appended after this graft"),
				}),
			),
			output_path: z.string().describe("Where to write the stitched file"),
			overwrite: z.boolean().default(false),
			dry_run: z.boolean().default(true),
		},
		annotations: {
			readOnlyHint: false,
			idempotentHint: false,
			destructiveHint: true,
		},
	},
	async ({ grafts, output_path, overwrite, dry_run }) => {
		const outPath = await validatePath(output_path);
		if (!overwrite && (await Bun.file(outPath).exists())) {
			throw new Error(`Output exists: ${output_path}`);
		}

		const formatComment = (filePath: string, comment: string) => {
			const ext = path.extname(filePath).toLowerCase();
			if (
				[
					".js",
					".ts",
					".tsx",
					".jsx",
					".go",
					".rs",
					".c",
					".cpp",
					".java",
				].includes(ext)
			) {
				return `// ${comment}`;
			}
			if ([".html", ".xml"].includes(ext)) return `<!-- ${comment} -->`;
			if ([".css", ".scss"].includes(ext)) return `/* ${comment} */`;
			return `# ${comment}`;
		};

		const parts: string[] = [];
		for (const g of grafts) {
			const srcPath = await validatePath(g.source);
			const srcFile = Bun.file(srcPath);
			if (!(await srcFile.exists()))
				throw new Error(`Source not found: ${g.source}`);
			const src = normalizeLineEndings(await srcFile.text());
			if (g.start < 0 || g.end < 0 || g.start > g.end || g.end > src.length) {
				throw new Error(
					`Invalid graft offsets for ${g.source}: start=${g.start}, end=${g.end}, len=${src.length}`,
				);
			}
			if (g.comment) parts.push(formatComment(output_path, g.comment));
			parts.push(src.slice(g.start, g.end));
			if (g.glue) parts.push(g.glue);
		}

		const assembled = parts.join("\n");
		if (!dry_run) await atomicWrite(outPath, assembled);
		return {
			content: [
				{
					type: "text",
					text: JSON.stringify(
						{
							success: true,
							output_path: outPath,
							grafts: grafts.length,
							bytes: assembled.length,
							dry_run,
						},
						null,
						2,
					),
				},
			],
		};
	},
);

server.registerTool(
	"create-directory",
	{
		description:
			"Create a new directory or ensure it exists.\n" +
			"Creates nested directories if needed. Only works within allowed directories.",
		inputSchema: {
			path: z.string().describe("Path to the directory"),
		},
		annotations: {
			readOnlyHint: false,
			idempotentHint: true,
			destructiveHint: false,
		},
	},
	async ({ path: filePath }) => {
		const validPath = await validatePath(filePath);
		await mkdir(validPath, { recursive: true });
		return {
			content: [
				{ type: "text", text: `Successfully created directory ${filePath}` },
			],
		};
	},
);

server.registerTool(
	"list-directory",
	{
		description:
			"Get a detailed listing of directory contents.\n" +
			"Prefixes entries with [DIR] or [FILE]. Only works within allowed directories.",
		inputSchema: {
			path: z.string().describe("Path to the directory"),
		},
		annotations: { readOnlyHint: true },
	},
	async ({ path: filePath }) => {
		const validPath = await validatePath(filePath);
		const entries = (await readdir(validPath, {
			withFileTypes: true,
		})) as Dirent[];
		const lines = entries.map((entry) =>
			entry.isDirectory() ? `[DIR] ${entry.name}` : `[FILE] ${entry.name}`,
		);
		return { content: [{ type: "text", text: lines.join("\n") }] };
	},
);

server.registerTool(
	"view-directory-ui",
	{
		description:
			"Renders an interactive UI to display the contents of a directory.",
		inputSchema: {
			path: z.string().describe("Path to the directory"),
		},
	},
	async ({ path: filePath }) => {
		const validPath = await validatePath(filePath);
		const entries = (await readdir(validPath, {
			withFileTypes: true,
		})) as Dirent[];
		const lines = entries.map((entry) =>
			entry.isDirectory() ? `[DIR] ${entry.name}` : `[FILE] ${entry.name}`,
		);
		return { content: [{ type: "text", text: lines.join("\n") }] };
	},
);

server.registerTool(
	"directory-tree",
	{
		description:
			"Get a recursive tree view of files and directories as JSON.\n" +
			"Includes 'name' and 'type', with 'children' for directories. Only works within allowed directories.",
		inputSchema: {
			path: z.string().describe("Path to the directory"),
			max_depth: z.number().default(5).describe("Maximum depth of the tree"),
			max_nodes: z
				.number()
				.default(5000)
				.describe("Maximum number of nodes in the tree"),
		},
		annotations: { readOnlyHint: true },
	},
	async ({ path: filePath, max_depth, max_nodes }) => {
		const validPath = await validatePath(filePath);
		let seen = 0;

		const buildTree = async (
			currentPath: string,
			depth: number,
		): Promise<unknown[]> => {
			if (depth > max_depth || seen > max_nodes) {
				return [{ name: "...truncated...", type: "note" }];
			}

			let entries: Dirent[];
			try {
				entries = (await readdir(currentPath, {
					withFileTypes: true,
				})) as Dirent[];
			} catch (err) {
				return [{ name: `[error] ${String(err)}`, type: "note" }];
			}

			const tree: Array<{ name: string; type: string; children?: unknown[] }> =
				[];
			for (const entry of entries) {
				const entryPath = path.join(currentPath, entry.name);
				if (entry.isDirectory()) {
					const children = await buildTree(entryPath, depth + 1);
					tree.push({ name: entry.name, type: "directory", children });
				} else {
					tree.push({ name: entry.name, type: "file" });
				}
				seen += 1;
				if (seen > max_nodes) break;
			}

			return tree;
		};

		const tree = await buildTree(validPath, 0);
		return { content: [{ type: "text", text: JSON.stringify(tree, null, 2) }] };
	},
);

server.registerTool(
	"move-file",
	{
		description:
			"Move or rename files and directories.\n" +
			"Fails if destination exists. Only works within allowed directories.",
		inputSchema: {
			source: z.string().describe("Source path"),
			destination: z.string().describe("Destination path"),
		},
		annotations: {
			readOnlyHint: false,
			idempotentHint: false,
			destructiveHint: false,
		},
	},
	async ({ source, destination }) => {
		const validSource = await validatePath(source);
		const validDestination = await validatePath(destination);
		const destinationExists = await Bun.file(validDestination).exists();
		if (destinationExists) {
			throw new Error(`Destination already exists: ${destination}`);
		}
		await rename(validSource, validDestination);
		return {
			content: [
				{
					type: "text",
					text: `Successfully moved ${source} to ${destination}`,
				},
			],
		};
	},
);

server.registerTool(
	"search-files",
	{
		description:
			"Recursively search for files matching a pattern.\n" +
			"Case-insensitive, returns full paths. Only works within allowed directories.",
		inputSchema: {
			path: z.string().describe("Path to search in"),
			pattern: z.string().describe("Search pattern"),
			exclude_patterns: z
				.array(z.string())
				.optional()
				.default([])
				.describe("Patterns to exclude"),
		},
		annotations: { readOnlyHint: true },
	},
	async ({ path: filePath, pattern, exclude_patterns }) => {
		const validPath = await validatePath(filePath);
		const results = await searchFilesImpl(validPath, pattern, exclude_patterns);
		const output = results.length > 0 ? results.join("\n") : "No matches found";
		return { content: [{ type: "text", text: output }] };
	},
);

server.registerTool(
	"get-file-info",
	{
		description:
			"Retrieve detailed metadata about a file or directory.\n" +
			"Includes size, timestamps, and permissions. Only works within allowed directories.",
		inputSchema: {
			path: z.string().describe("Path to the file"),
		},
		annotations: { readOnlyHint: true },
	},
	async ({ path: filePath }) => {
		const validPath = await validatePath(filePath);
		const info = await stat(validPath);
		const permissions = info.mode.toString(8).slice(-3);
		const output = [
			`size: ${info.size}`,
			`created: ${info.birthtimeMs}`,
			`modified: ${info.mtimeMs}`,
			`accessed: ${info.atimeMs}`,
			`isDirectory: ${info.isDirectory()}`,
			`isFile: ${info.isFile()}`,
			`permissions: ${permissions}`,
		].join("\n");
		return { content: [{ type: "text", text: output }] };
	},
);

server.registerTool(
	"list-allowed-directories",
	{
		description: "Returns the list of directories this server can access.",
		annotations: { readOnlyHint: true },
	},
	async () => {
		const output = `Allowed directories:\n${allowedDirectories.join("\n")}`;
		return { content: [{ type: "text", text: output }] };
	},
);

server.registerTool(
	"set-allowed-directories",
	{
		description: "Update the list of allowed directories at runtime.",
		inputSchema: {
			directories: z.array(z.string()).describe("List of directories"),
		},
		annotations: {
			readOnlyHint: false,
			idempotentHint: true,
			destructiveHint: false,
		},
	},
	async ({ directories }) => {
		const newDirs: string[] = [];
		for (const dir of directories) {
			const normalized = normalizePath(dir);
			try {
				const stats = await stat(normalized);
				if (!stats.isDirectory()) {
					continue;
				}
				accessSync(normalized, fsConstants.R_OK);
				newDirs.push(normalized);
			} catch {}
		}
		allowedDirectories = newDirs;
		const output = `Updated allowed directories to: ${allowedDirectories.join(", ")}`;
		return { content: [{ type: "text", text: output }] };
	},
);

const transport = new StdioServerTransport();
await server.connect(transport);
