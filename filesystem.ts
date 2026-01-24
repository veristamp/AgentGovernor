import {
	accessSync,
	type Dirent,
	constants as fsConstants,
	statSync,
} from "node:fs";
import { mkdir, readdir, realpath, rename, stat } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
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

	const parent = path.dirname(absolute);
	const realParent = await realpath(parent).catch(() => parent);
	const realPath = path.join(realParent, path.basename(absolute));
	if (!allowedDirectories.some((root) => isWithin(realPath, root))) {
		throw new Error(
			"Access denied - symlink target outside allowed directories",
		);
	}

	return realPath;
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
			if (originalLines[i - 1] === modifiedLines[j - 1]) {
				dp[i]![j] = dp[i - 1]![j - 1]! + 1;
			} else {
				dp[i]![j] = Math.max(dp[i - 1]![j]!, dp[i]![j - 1]!);
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
		} else if (dp[i - 1]![j]! >= dp[i]![j - 1]!) {
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

			await Bun.write(validPath, binary);
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

		await Bun.write(validPath, content);
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
		if (!dry_run) {
			await Bun.write(validPath, modified);
		}

		return { content: [{ type: "text", text: diff }] };
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
	{ description: "Returns the list of directories this server can access." },
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
