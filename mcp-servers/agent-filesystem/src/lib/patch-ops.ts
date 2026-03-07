import fs from "node:fs/promises";
import path from "node:path";
import { validatePath } from "../path-validation.js";
import { createUnifiedDiff } from "./diff.js";
import { sha256Hex } from "./hashes.js";
import { fileLinesToSpan, normalizeLineEndings } from "./text.js";

export type PatchGuard = {
	expected_sha256?: string;
	allow_drift?: boolean;
};

export async function patchSpan(
	requestedPath: string,
	span: { start: number; end: number },
	newContent: string,
	guard: PatchGuard = {},
	opts: { dry_run?: boolean } = {},
) {
	const dryRun = opts.dry_run ?? true;
	const allowDrift = guard.allow_drift ?? false;
	const validPath = await validatePath(requestedPath);
	const file = Bun.file(validPath);
	if (!(await file.exists()))
		throw new Error(`File not found: ${requestedPath}`);
	const original = normalizeLineEndings(await file.text());
	if (
		span.start < 0 ||
		span.end < 0 ||
		span.start > span.end ||
		span.end > original.length
	) {
		throw new Error(
			`Invalid offsets: start=${span.start}, end=${span.end}, len=${original.length}`,
		);
	}

	const currentSlice = original.slice(span.start, span.end);
	if (guard.expected_sha256) {
		const got = sha256Hex(currentSlice);
		if (got !== guard.expected_sha256.toLowerCase() && !allowDrift) {
			throw new Error("Content drift detected for selected span");
		}
	}

	const modified =
		original.slice(0, span.start) + newContent + original.slice(span.end);
	const diff = createUnifiedDiff(original, modified, validPath);

	if (!dryRun) {
		await atomicWriteText(validPath, modified);
	}

	return { diff };
}

export async function patchLines(
	requestedPath: string,
	lines: { start_line: number; end_line: number },
	newContent: string,
	guard: PatchGuard = {},
	opts: { dry_run?: boolean } = {},
) {
	const dryRun = opts.dry_run ?? true;
	const allowDrift = guard.allow_drift ?? false;
	const validPath = await validatePath(requestedPath);
	const file = Bun.file(validPath);
	if (!(await file.exists()))
		throw new Error(`File not found: ${requestedPath}`);
	const original = normalizeLineEndings(await file.text());
	const span = fileLinesToSpan(original, lines.start_line, lines.end_line);
	const currentSlice = original.slice(span.start, span.end);
	if (guard.expected_sha256) {
		const got = sha256Hex(currentSlice);
		if (got !== guard.expected_sha256.toLowerCase() && !allowDrift) {
			throw new Error("Content drift detected for selected line range");
		}
	}

	const modified =
		original.slice(0, span.start) + newContent + original.slice(span.end);
	const diff = createUnifiedDiff(original, modified, validPath);
	if (!dryRun) {
		await atomicWriteText(validPath, modified);
	}
	return { diff };
}

export type ReplaceEdit = { oldText: string; newText: string };

export async function editFileReplace(
	requestedPath: string,
	edits: ReplaceEdit[],
	opts: { dry_run?: boolean; require_all?: boolean } = {},
) {
	const dryRun = opts.dry_run ?? true;
	const requireAll = opts.require_all ?? true;
	const validPath = await validatePath(requestedPath);
	const file = Bun.file(validPath);
	if (!(await file.exists()))
		throw new Error(`File not found: ${requestedPath}`);
	const original = normalizeLineEndings(await file.text());

	let modified = original;
	let applied = 0;
	const failures: string[] = [];

	for (const e of edits) {
		const oldText = normalizeLineEndings(e.oldText);
		const newText = normalizeLineEndings(e.newText);

		if (modified.includes(oldText)) {
			modified = modified.replace(oldText, newText);
			applied += 1;
			continue;
		}

		// Fallback: block match ignoring whitespace.
		const oldLines = oldText.split("\n").map((l) => l.trim());
		const lines = modified.split("\n");
		let matched = false;
		for (let i = 0; i <= lines.length - oldLines.length; i += 1) {
			const slice = lines.slice(i, i + oldLines.length).map((l) => l.trim());
			if (slice.every((l, j) => l === oldLines[j])) {
				const replacement = newText.split("\n");
				lines.splice(i, oldLines.length, ...replacement);
				modified = lines.join("\n");
				matched = true;
				applied += 1;
				break;
			}
		}
		if (!matched) failures.push(e.oldText);
	}

	if (applied === 0) {
		throw new Error("No edits applied (no matches found). ");
	}
	if (requireAll && failures.length > 0) {
		throw new Error(
			`Some edits did not apply (require_all=true). Missing: ${failures.length}`,
		);
	}

	const diff = createUnifiedDiff(original, modified, validPath);
	if (!dryRun) await atomicWriteText(validPath, modified);
	return { diff, applied, missing: failures.length };
}

export type StitchGraft = {
	source: string;
	start: number;
	end: number;
	comment?: string;
	glue?: string;
};

export async function stitchFile(
	grafts: StitchGraft[],
	requestedOutputPath: string,
	opts: { overwrite?: boolean; dry_run?: boolean } = {},
) {
	const overwrite = opts.overwrite ?? false;
	const dryRun = opts.dry_run ?? true;

	const outPath = await validatePath(requestedOutputPath, {
		allowCreate: true,
	});
	const exists = await fs
		.stat(outPath)
		.then(() => true)
		.catch(() => false);
	if (exists && !overwrite)
		throw new Error(`Output exists: ${requestedOutputPath}`);

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
		if (g.comment) parts.push(formatComment(requestedOutputPath, g.comment));
		parts.push(src.slice(g.start, g.end));
		if (g.glue) parts.push(g.glue);
	}

	const assembled = parts.join("\n");
	if (!dryRun) {
		await fs.mkdir(path.dirname(outPath), { recursive: true });
		await atomicWriteText(outPath, assembled);
	}
	return {
		output_path: outPath,
		grafts: grafts.length,
		bytes: Buffer.byteLength(assembled, "utf-8"),
		dry_run: dryRun,
	};
}

function formatComment(outputPath: string, comment: string) {
	const ext = path.extname(outputPath).toLowerCase();
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
}

async function atomicWriteText(filePath: string, content: string) {
	const dir = path.dirname(filePath);
	const randomBytes = new Uint8Array(8);
	crypto.getRandomValues(randomBytes);
	const hexRandom = Array.from(randomBytes)
		.map((b) => b.toString(16).padStart(2, "0"))
		.join("");
	const tmp = path.join(dir, `.tmp.${path.basename(filePath)}.${hexRandom}`);
	await fs.mkdir(dir, { recursive: true });
	try {
		await Bun.write(tmp, content);
		await fs.rename(tmp, filePath);
	} finally {
		await fs.unlink(tmp).catch(() => {});
	}
}
