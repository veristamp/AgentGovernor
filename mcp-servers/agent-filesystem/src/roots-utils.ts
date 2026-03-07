import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { Root } from "@modelcontextprotocol/sdk/types.js";
import { normalizePath, stripFileUri } from "./path-utils.js";

async function parseRootUri(rootUri: string): Promise<string | null> {
	try {
		const raw = stripFileUri(rootUri);
		const expanded =
			raw.startsWith("~/") || raw === "~"
				? path.join(os.homedir(), raw.slice(1))
				: raw;
		const absolute = path.resolve(expanded);
		const resolved = await fs.realpath(absolute);
		return normalizePath(resolved);
	} catch {
		return null;
	}
}

export async function getValidRootDirectories(requestedRoots: readonly Root[]) {
	const validated: string[] = [];
	for (const r of requestedRoots) {
		const resolved = await parseRootUri(r.uri);
		if (!resolved) continue;
		try {
			const st = await fs.stat(resolved);
			if (st.isDirectory()) validated.push(resolved);
		} catch {}
	}
	return validated;
}
