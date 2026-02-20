import fs from "node:fs/promises";
import path from "node:path";
import { minimatch } from "minimatch";
import { validatePath } from "../path-validation.js";
import { formatSize } from "./format.js";
import { normalizeLineEndings } from "./text.js";

function randomHex(bytes: number): string {
	const buf = new Uint8Array(bytes);
	crypto.getRandomValues(buf);
	return Array.from(buf)
		.map((b) => b.toString(16).padStart(2, "0"))
		.join("");
}

export async function readTextFile(
	requestedPath: string,
	opts: { head?: number; tail?: number } = {},
) {
	if (opts.head && opts.tail) {
		throw new Error("Cannot specify both head and tail simultaneously");
	}
	const validPath = await validatePath(requestedPath);
	if (opts.tail) return await tailFile(validPath, opts.tail);
	if (opts.head) return await headFile(validPath, opts.head);
	const file = Bun.file(validPath);
	if (!(await file.exists()))
		throw new Error(`File not found: ${requestedPath}`);
	return await file.text();
}

export async function readMediaFile(requestedPath: string) {
	const validPath = await validatePath(requestedPath);
	const extension = path.extname(validPath).toLowerCase();
	const mimeTypes: Record<string, string> = {
		".png": "image/png",
		".jpg": "image/jpeg",
		".jpeg": "image/jpeg",
		".gif": "image/gif",
		".webp": "image/webp",
		".bmp": "image/bmp",
		".svg": "image/svg+xml",
		".mp3": "audio/mpeg",
		".wav": "audio/wav",
		".ogg": "audio/ogg",
		".flac": "audio/flac",
	};
	const mimeType = mimeTypes[extension] || "application/octet-stream";
	const file = Bun.file(validPath);
	if (!(await file.exists()))
		throw new Error(`File not found: ${requestedPath}`);
	const data = Buffer.from(await file.arrayBuffer()).toString("base64");
	const type = mimeType.startsWith("image/")
		? "image"
		: mimeType.startsWith("audio/")
			? "audio"
			: "blob";
	return { type, data, mimeType } as const;
}

export async function readMultipleFiles(requestedPaths: string[]) {
	const results = await Promise.all(
		requestedPaths.map(async (p) => {
			try {
				const validPath = await validatePath(p);
				const file = Bun.file(validPath);
				if (!(await file.exists())) throw new Error("File not found");
				const content = await file.text();
				return `${p}:\n${content}`;
			} catch (err) {
				return `${p}: Error - ${err instanceof Error ? err.message : String(err)}`;
			}
		}),
	);
	return results.join("\n---\n");
}

export async function writeFile(
	requestedPath: string,
	content: string,
	opts: {
		encoding?: "utf-8" | "base64";
		maxBytes?: number;
		overwrite?: boolean;
		createParents?: boolean;
	} = {},
) {
	const encoding = opts.encoding ?? "utf-8";
	const maxBytes = opts.maxBytes ?? 2_000_000;
	const overwrite = opts.overwrite ?? true;
	const createParents = opts.createParents ?? true;

	const validPath = await validatePath(requestedPath, { allowCreate: true });
	if (createParents)
		await fs.mkdir(path.dirname(validPath), { recursive: true });

	let bytes: Buffer;
	if (encoding === "base64") {
		bytes = Buffer.from(content, "base64");
	} else {
		bytes = Buffer.from(content, "utf-8");
	}

	if (bytes.length > maxBytes) {
		throw new Error(`Refusing to write >${maxBytes} bytes`);
	}

	// Create-only path: fail if file exists.
	if (!overwrite) {
		await fs.writeFile(validPath, bytes, { flag: "wx" });
		return { bytes: bytes.length, path: requestedPath };
	}

	const tmpPath = `${validPath}.${randomHex(16)}.tmp`;
	try {
		await Bun.write(tmpPath, bytes);
		await fs.rename(tmpPath, validPath);
	} finally {
		await fs.unlink(tmpPath).catch(() => {});
	}

	return { bytes: bytes.length, path: requestedPath };
}

export async function createDirectory(requestedPath: string) {
	const validPath = await validatePath(requestedPath, { allowCreate: true });
	await fs.mkdir(validPath, { recursive: true });
	return { path: requestedPath };
}

export async function listDirectory(requestedPath: string) {
	const validPath = await validatePath(requestedPath);
	const entries = await fs.readdir(validPath, { withFileTypes: true });
	return entries
		.map((e) => `${e.isDirectory() ? "[DIR]" : "[FILE]"} ${e.name}`)
		.join("\n");
}

export async function listDirectoryWithSizes(
	requestedPath: string,
	opts: { sortBy?: "name" | "size" } = {},
) {
	const sortBy = opts.sortBy ?? "name";
	const validPath = await validatePath(requestedPath);
	const entries = await fs.readdir(validPath, { withFileTypes: true });

	const detailed = await Promise.all(
		entries.map(async (e) => {
			const p = path.join(validPath, e.name);
			try {
				const st = await fs.stat(p);
				return {
					name: e.name,
					isDirectory: e.isDirectory(),
					size: st.size,
				};
			} catch {
				return { name: e.name, isDirectory: e.isDirectory(), size: 0 };
			}
		}),
	);

	const sorted = [...detailed].sort((a, b) => {
		if (sortBy === "size") return b.size - a.size;
		return a.name.localeCompare(b.name);
	});

	const totalFiles = detailed.filter((e) => !e.isDirectory).length;
	const totalDirs = detailed.filter((e) => e.isDirectory).length;
	const totalSize = detailed.reduce(
		(sum, e) => sum + (e.isDirectory ? 0 : e.size),
		0,
	);

	const formatted = sorted.map(
		(e) =>
			`${e.isDirectory ? "[DIR]" : "[FILE]"} ${e.name.padEnd(30)} ${
				e.isDirectory ? "" : formatSize(e.size).padStart(10)
			}`,
	);

	return [
		...formatted,
		"",
		`Total: ${totalFiles} files, ${totalDirs} directories`,
		`Combined size: ${formatSize(totalSize)}`,
	].join("\n");
}

export async function getFileInfo(requestedPath: string) {
	const validPath = await validatePath(requestedPath);
	const st = await fs.stat(validPath);
	return {
		size: st.size,
		created: st.birthtimeMs,
		modified: st.mtimeMs,
		accessed: st.atimeMs,
		isDirectory: st.isDirectory(),
		isFile: st.isFile(),
		permissions: st.mode.toString(8).slice(-3),
	};
}

export async function moveFile(
	requestedSource: string,
	requestedDestination: string,
) {
	const source = await validatePath(requestedSource);
	const dest = await validatePath(requestedDestination, { allowCreate: true });
	const exists = await fs
		.stat(dest)
		.then(() => true)
		.catch(() => false);
	if (exists) {
		throw new Error(`Destination already exists: ${requestedDestination}`);
	}
	await fs.rename(source, dest);
	return { source: requestedSource, destination: requestedDestination };
}

export async function searchFiles(
	requestedRoot: string,
	pattern: string,
	opts: { excludePatterns?: string[]; limit?: number } = {},
) {
	const excludePatterns = opts.excludePatterns ?? [];
	const limit = opts.limit ?? 5000;

	const rootPath = await validatePath(requestedRoot);
	const results: string[] = [];

	async function walk(current: string) {
		if (results.length >= limit) return;
		const entries = await fs.readdir(current, { withFileTypes: true });
		for (const entry of entries) {
			if (results.length >= limit) break;
			const full = path.join(current, entry.name);
			let relative = path.relative(rootPath, full);
			relative = relative.replace(/\\/g, "/");

			const excluded = excludePatterns.some((ex) =>
				minimatch(relative, ex, { dot: true }),
			);
			if (excluded) continue;

			if (minimatch(relative, pattern, { dot: true })) {
				results.push(full);
				if (results.length >= limit) break;
			}

			if (entry.isDirectory()) {
				await walk(full);
			}
		}
	}

	await walk(rootPath);
	return results;
}

export async function directoryTree(
	requestedRoot: string,
	opts: {
		excludePatterns?: string[];
		maxDepth?: number;
		maxNodes?: number;
	} = {},
) {
	const excludePatterns = opts.excludePatterns ?? [];
	const maxDepth = opts.maxDepth ?? 5;
	const maxNodes = opts.maxNodes ?? 5000;

	const rootPath = await validatePath(requestedRoot);
	let seen = 0;

	type TreeEntry = {
		name: string;
		type: "file" | "directory";
		children?: TreeEntry[];
	};

	async function build(current: string, depth: number): Promise<TreeEntry[]> {
		if (depth > maxDepth || seen > maxNodes) {
			return [{ name: "...truncated...", type: "file" }];
		}

		let entries: Array<import("node:fs").Dirent>;
		try {
			entries = await fs.readdir(current, { withFileTypes: true });
		} catch (err) {
			return [
				{
					name: `[error] ${err instanceof Error ? err.message : String(err)}`,
					type: "file",
				},
			];
		}

		const out: TreeEntry[] = [];
		for (const entry of entries) {
			const full = path.join(current, entry.name);
			let relative = path.relative(rootPath, full);
			relative = relative.replace(/\\/g, "/");
			const excluded = excludePatterns.some((ex) =>
				minimatch(relative, ex, { dot: true }),
			);
			if (excluded) continue;

			if (entry.isDirectory()) {
				out.push({
					name: entry.name,
					type: "directory",
					children: await build(full, depth + 1),
				});
			} else {
				out.push({ name: entry.name, type: "file" });
			}
			seen += 1;
			if (seen > maxNodes) break;
		}
		return out;
	}

	return await build(rootPath, 0);
}

async function tailFile(filePath: string, numLines: number) {
	const CHUNK_SIZE = 1024;
	const st = await fs.stat(filePath);
	if (st.size === 0) return "";

	const fh = await fs.open(filePath, "r");
	try {
		const lines: string[] = [];
		let position = st.size;
		const chunk = Buffer.alloc(CHUNK_SIZE);
		let linesFound = 0;
		let remaining = "";

		while (position > 0 && linesFound < numLines) {
			const size = Math.min(CHUNK_SIZE, position);
			position -= size;
			const { bytesRead } = await fh.read(chunk, 0, size, position);
			if (!bytesRead) break;
			const readData = chunk.slice(0, bytesRead).toString("utf-8");
			const text = readData + remaining;
			const parts = normalizeLineEndings(text).split("\n");

			if (position > 0) {
				remaining = parts[0] ?? "";
				parts.shift();
			}

			for (let i = parts.length - 1; i >= 0 && linesFound < numLines; i--) {
				lines.unshift(parts[i] ?? "");
				linesFound += 1;
			}
		}

		return lines.join("\n");
	} finally {
		await fh.close();
	}
}

async function headFile(filePath: string, numLines: number) {
	const fh = await fs.open(filePath, "r");
	try {
		const lines: string[] = [];
		let buffer = "";
		let offset = 0;
		const chunk = Buffer.alloc(1024);
		while (lines.length < numLines) {
			const res = await fh.read(chunk, 0, chunk.length, offset);
			if (res.bytesRead === 0) break;
			offset += res.bytesRead;
			buffer += chunk.slice(0, res.bytesRead).toString("utf-8");
			const lastNl = buffer.lastIndexOf("\n");
			if (lastNl !== -1) {
				const complete = buffer.slice(0, lastNl).split("\n");
				buffer = buffer.slice(lastNl + 1);
				for (const line of complete) {
					lines.push(line);
					if (lines.length >= numLines) break;
				}
			}
		}
		if (buffer.length > 0 && lines.length < numLines) lines.push(buffer);
		return lines.join("\n");
	} finally {
		await fh.close();
	}
}
