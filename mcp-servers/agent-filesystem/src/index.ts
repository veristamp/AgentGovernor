#!/usr/bin/env bun

import fs from "node:fs/promises";
import path from "node:path";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { expandHome, normalizePath } from "./path-utils.js";
import { createAgentFilesystemServer } from "./server.js";
import { setAllowedDirectories } from "./state/allowed-dirs.js";

const args = process.argv.slice(2);

async function resolveAllowedDirectories(cliDirs: string[]) {
	const resolved = await Promise.all(
		cliDirs.map(async (dir) => {
			const expanded = expandHome(dir);
			const absolute = path.resolve(expanded);
			try {
				const real = await fs.realpath(absolute);
				return normalizePath(real);
			} catch {
				return normalizePath(absolute);
			}
		}),
	);

	// Validate directories exist and are directories.
	await Promise.all(
		resolved.map(async (dir) => {
			const st = await fs.stat(dir);
			if (!st.isDirectory()) throw new Error(`${dir} is not a directory`);
		}),
	);

	return resolved;
}

async function main() {
	if (args.length > 0) {
		const dirs = await resolveAllowedDirectories(args);
		setAllowedDirectories(dirs);
	} else {
		// Start with no allowed directories; prefer MCP Roots.
		setAllowedDirectories([]);
	}

	const server = createAgentFilesystemServer();
	const transport = new StdioServerTransport();
	await server.connect(transport);

	if (args.length === 0) {
		console.error(
			"agent-filesystem-server started without CLI directories; waiting for MCP Roots to configure allowed directories",
		);
	}
}

main().catch((err) => {
	console.error(err instanceof Error ? err.message : String(err));
	process.exit(1);
});
