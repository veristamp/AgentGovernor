import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
	type Root,
	RootsListChangedNotificationSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import {
	createDirectory,
	directoryTree,
	getFileInfo,
	listDirectory,
	listDirectoryWithSizes,
	moveFile,
	readMediaFile,
	readMultipleFiles,
	readTextFile,
	searchFiles,
	writeFile,
} from "./lib/fs-ops.js";
import {
	editFileReplace,
	patchLines,
	patchSpan,
	stitchFile,
} from "./lib/patch-ops.js";
import { getValidRootDirectories } from "./roots-utils.js";
import {
	getAllowedDirectories,
	setAllowedDirectories,
} from "./state/allowed-dirs.js";

export function createAgentFilesystemServer() {
	const server = new McpServer({
		name: "agent-filesystem-server",
		version: "0.1.0",
	});

	async function updateAllowedDirectoriesFromRoots(
		requestedRoots: readonly Root[],
	) {
		const validated = await getValidRootDirectories(requestedRoots);
		if (validated.length > 0) {
			setAllowedDirectories(validated);
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

		if (getAllowedDirectories().length === 0) {
			throw new Error(
				"Server cannot operate: No allowed directories available. Provide CLI directories or use a client that supports MCP Roots.",
			);
		}
	};

	// -------------------------
	// Filesystem tools
	// -------------------------

	server.registerTool(
		"read_text_file",
		{
			title: "Read Text File",
			description:
				"Read the complete contents of a file as UTF-8 text. Use head/tail to read only part of the file. Only works within allowed directories.",
			inputSchema: {
				path: z.string(),
				head: z.number().int().positive().optional(),
				tail: z.number().int().positive().optional(),
			},
			annotations: { readOnlyHint: true },
		},
		async (args) => {
			const text = await readTextFile(args.path, {
				head: args.head,
				tail: args.tail,
			});
			return {
				content: [{ type: "text", text }],
				structuredContent: { content: text },
			};
		},
	);

	server.registerTool(
		"read_media_file",
		{
			title: "Read Media File",
			description:
				"Read an image/audio/binary file and return base64 data with MIME type. Only works within allowed directories.",
			inputSchema: { path: z.string() },
			annotations: { readOnlyHint: true },
		},
		async (args, _extra) => {
			const item = await readMediaFile(args.path);
			const contentItem =
				item.type === "image"
					? ({
							type: "image",
							data: item.data,
							mimeType: item.mimeType,
						} as const)
					: item.type === "audio"
						? ({
								type: "audio",
								data: item.data,
								mimeType: item.mimeType,
							} as const)
						: ({
								type: "text",
								text: item.data,
							} as const);
			return {
				content: [contentItem],
				structuredContent: { content: [item] },
			};
		},
	);

	server.registerTool(
		"read_multiple_files",
		{
			title: "Read Multiple Files",
			description:
				"Read the contents of multiple text files. Continues on per-file errors. Only works within allowed directories.",
			inputSchema: {
				paths: z.array(z.string()).min(1),
			},
			annotations: { readOnlyHint: true },
		},
		async (args) => {
			const text = await readMultipleFiles(args.paths);
			return {
				content: [{ type: "text", text }],
				structuredContent: { content: text },
			};
		},
	);

	server.registerTool(
		"write_file",
		{
			title: "Write File",
			description:
				"Create or overwrite a file. Supports utf-8 text or base64 content. Atomic write. Only works within allowed directories.",
			inputSchema: {
				path: z.string(),
				content: z.string(),
				encoding: z.enum(["utf-8", "base64"]).default("utf-8"),
				max_bytes: z.number().int().positive().default(2_000_000),
				overwrite: z.boolean().default(true),
			},
			annotations: {
				readOnlyHint: false,
				idempotentHint: true,
				destructiveHint: true,
			},
		},
		async (args) => {
			const res = await writeFile(args.path, args.content, {
				encoding: args.encoding,
				maxBytes: args.max_bytes,
				overwrite: args.overwrite,
			});
			const text = `Successfully wrote ${res.bytes} bytes to ${args.path}`;
			return {
				content: [{ type: "text", text }],
				structuredContent: { content: text },
			};
		},
	);

	server.registerTool(
		"create_directory",
		{
			title: "Create Directory",
			description:
				"Create a directory (recursively). Only works within allowed directories.",
			inputSchema: { path: z.string() },
			annotations: {
				readOnlyHint: false,
				idempotentHint: true,
				destructiveHint: false,
			},
		},
		async (args) => {
			await createDirectory(args.path);
			const text = `Successfully created directory ${args.path}`;
			return {
				content: [{ type: "text", text }],
				structuredContent: { content: text },
			};
		},
	);

	server.registerTool(
		"list_directory",
		{
			title: "List Directory",
			description:
				"List directory entries. Only works within allowed directories.",
			inputSchema: { path: z.string() },
			annotations: { readOnlyHint: true },
		},
		async (args) => {
			const text = await listDirectory(args.path);
			return {
				content: [{ type: "text", text }],
				structuredContent: { content: text },
			};
		},
	);

	server.registerTool(
		"list_directory_with_sizes",
		{
			title: "List Directory with Sizes",
			description:
				"List directory entries with sizes and summary. Only works within allowed directories.",
			inputSchema: {
				path: z.string(),
				sortBy: z.enum(["name", "size"]).default("name"),
			},
			annotations: { readOnlyHint: true },
		},
		async (args) => {
			const text = await listDirectoryWithSizes(args.path, {
				sortBy: args.sortBy,
			});
			return {
				content: [{ type: "text", text }],
				structuredContent: { content: text },
			};
		},
	);

	server.registerTool(
		"directory_tree",
		{
			title: "Directory Tree",
			description:
				"Recursive directory tree as JSON. Supports excludePatterns globs, max_depth, max_nodes. Only works within allowed directories.",
			inputSchema: {
				path: z.string(),
				excludePatterns: z.array(z.string()).default([]),
				max_depth: z.number().int().positive().default(5),
				max_nodes: z.number().int().positive().default(5000),
			},
			annotations: { readOnlyHint: true },
		},
		async (args) => {
			const tree = await directoryTree(args.path, {
				excludePatterns: args.excludePatterns,
				maxDepth: args.max_depth,
				maxNodes: args.max_nodes,
			});
			const text = JSON.stringify(tree, null, 2);
			return {
				content: [{ type: "text", text }],
				structuredContent: { content: text },
			};
		},
	);

	server.registerTool(
		"move_file",
		{
			title: "Move File",
			description:
				"Move/rename a file or directory. Fails if destination exists. Only works within allowed directories.",
			inputSchema: { source: z.string(), destination: z.string() },
			annotations: {
				readOnlyHint: false,
				idempotentHint: false,
				destructiveHint: false,
			},
		},
		async (args) => {
			await moveFile(args.source, args.destination);
			const text = `Successfully moved ${args.source} to ${args.destination}`;
			return {
				content: [{ type: "text", text }],
				structuredContent: { content: text },
			};
		},
	);

	server.registerTool(
		"search_files",
		{
			title: "Search Files",
			description:
				"Recursively search for paths matching a glob pattern, relative to the search root. Only works within allowed directories.",
			inputSchema: {
				path: z.string(),
				pattern: z.string(),
				excludePatterns: z.array(z.string()).default([]),
				limit: z.number().int().positive().default(5000),
			},
			annotations: { readOnlyHint: true },
		},
		async (args) => {
			const results = await searchFiles(args.path, args.pattern, {
				excludePatterns: args.excludePatterns,
				limit: args.limit,
			});
			const text = results.length > 0 ? results.join("\n") : "No matches found";
			return {
				content: [{ type: "text", text }],
				structuredContent: { content: text },
			};
		},
	);

	server.registerTool(
		"get_file_info",
		{
			title: "Get File Info",
			description:
				"Get file/directory metadata. Only works within allowed directories.",
			inputSchema: { path: z.string() },
			annotations: { readOnlyHint: true },
		},
		async (args) => {
			const info = await getFileInfo(args.path);
			const text = Object.entries(info)
				.map(([k, v]) => `${k}: ${v}`)
				.join("\n");
			return {
				content: [{ type: "text", text }],
				structuredContent: { content: text },
			};
		},
	);

	server.registerTool(
		"list_allowed_directories",
		{
			title: "List Allowed Directories",
			description: "Show current allowed directories.",
			inputSchema: {},
			annotations: { readOnlyHint: true },
		},
		async () => {
			const dirs = getAllowedDirectories();
			const text = `Allowed directories:\n${dirs.join("\n")}`;
			return {
				content: [{ type: "text", text }],
				structuredContent: { content: text },
			};
		},
	);

	// -------------------------
	// Patch / composition tools
	// -------------------------

	server.registerTool(
		"edit_file",
		{
			title: "Edit File",
			description:
				"Structured replace edits for text files. Returns a unified diff. Use dry_run=true first.",
			inputSchema: {
				path: z.string(),
				edits: z
					.array(z.object({ oldText: z.string(), newText: z.string() }))
					.min(1),
				dry_run: z.boolean().default(true),
				require_all: z.boolean().default(true),
			},
			annotations: {
				readOnlyHint: false,
				idempotentHint: false,
				destructiveHint: true,
			},
		},
		async (args) => {
			const res = await editFileReplace(args.path, args.edits, {
				dry_run: args.dry_run,
				require_all: args.require_all,
			});
			return {
				content: [{ type: "text", text: res.diff }],
				structuredContent: { content: res.diff },
			};
		},
	);

	server.registerTool(
		"patch_span",
		{
			title: "Patch Span",
			description:
				"Replace a 0-based character span [start:end] with new content. Optional sha256 guard on selected slice. Use dry_run=true first.",
			inputSchema: {
				path: z.string(),
				start: z.number().int().nonnegative(),
				end: z.number().int().nonnegative(),
				new_content: z.string(),
				expected_sha256: z.string().optional(),
				allow_drift: z.boolean().default(false),
				dry_run: z.boolean().default(true),
			},
			annotations: {
				readOnlyHint: false,
				idempotentHint: false,
				destructiveHint: true,
			},
		},
		async (args) => {
			const res = await patchSpan(
				args.path,
				{ start: args.start, end: args.end },
				args.new_content,
				{
					expected_sha256: args.expected_sha256,
					allow_drift: args.allow_drift,
				},
				{ dry_run: args.dry_run },
			);
			return {
				content: [{ type: "text", text: res.diff }],
				structuredContent: { content: res.diff },
			};
		},
	);

	server.registerTool(
		"patch_lines",
		{
			title: "Patch Lines",
			description:
				"Replace a 1-based inclusive line range with new content. Optional sha256 guard on selected slice. Use dry_run=true first.",
			inputSchema: {
				path: z.string(),
				start_line: z.number().int().positive(),
				end_line: z.number().int().positive(),
				new_content: z.string(),
				expected_sha256: z.string().optional(),
				allow_drift: z.boolean().default(false),
				dry_run: z.boolean().default(true),
			},
			annotations: {
				readOnlyHint: false,
				idempotentHint: false,
				destructiveHint: true,
			},
		},
		async (args) => {
			const res = await patchLines(
				args.path,
				{ start_line: args.start_line, end_line: args.end_line },
				args.new_content,
				{
					expected_sha256: args.expected_sha256,
					allow_drift: args.allow_drift,
				},
				{ dry_run: args.dry_run },
			);
			return {
				content: [{ type: "text", text: res.diff }],
				structuredContent: { content: res.diff },
			};
		},
	);

	server.registerTool(
		"stitch_file",
		{
			title: "Stitch File",
			description:
				"Assemble a new file from character slices of existing files. Each graft copies [start:end] from a source. Use dry_run=true first.",
			inputSchema: {
				grafts: z
					.array(
						z.object({
							source: z.string(),
							start: z.number().int().nonnegative(),
							end: z.number().int().nonnegative(),
							comment: z.string().optional(),
							glue: z.string().optional(),
						}),
					)
					.min(1),
				output_path: z.string(),
				overwrite: z.boolean().default(false),
				dry_run: z.boolean().default(true),
			},
			annotations: {
				readOnlyHint: false,
				idempotentHint: false,
				destructiveHint: true,
			},
		},
		async (args) => {
			const res = await stitchFile(args.grafts, args.output_path, {
				overwrite: args.overwrite,
				dry_run: args.dry_run,
			});
			const text = JSON.stringify({ success: true, ...res }, null, 2);
			return {
				content: [{ type: "text", text }],
				structuredContent: { content: text },
			};
		},
	);

	return server;
}
