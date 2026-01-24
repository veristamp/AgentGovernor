/**
 * Config Loader
 * Loads MCP server configuration from JSON file
 *
 * Supports your existing mcp_servers.json format:
 * {
 *   "ServerName": {
 *     "connection_type": "stdio",
 *     "command": "python",
 *     "args": ["-u", "server.py"],
 *     "cwd": ".",
 *     "timeout": 5.0,
 *     "disabled": false
 *   }
 * }
 */

import { resolve as resolvePath } from "path";
import type { Config, ServerConfig } from "./types";

export async function loadConfig(
	configPath: string = "mcp_servers.json",
): Promise<Config> {
	if (!(await Bun.file(configPath).exists())) {
		console.warn(`Config file not found: ${configPath}, using empty config`);
		return { mcpServers: {} };
	}

	const data = await Bun.file(configPath).json();

	// Support both flat format and nested format
	const mcpServers: Record<string, ServerConfig> = {};

	for (const [name, cfg] of Object.entries(data.mcpServers || data)) {
		const rawCfg = cfg as Record<string, unknown>;

		// Skip disabled servers
		if (rawCfg.disabled === true) {
			console.log(`[Config] Skipping disabled server: ${name}`);
			continue;
		}

		mcpServers[name] = parseServerConfig(rawCfg, configPath);
	}

	return { mcpServers };
}

function parseServerConfig(
	raw: Record<string, unknown>,
	configPath: string,
): ServerConfig {
	// Detect connection type - support both "type" and "connection_type"
	const connectionType = (raw.connection_type || raw.type || "stdio") as string;

	let type: "stdio" | "streamable_http" | "sse" = "stdio";
	if (raw.url) {
		type = connectionType === "sse" ? "sse" : "streamable_http";
	} else if (connectionType === "sse") {
		type = "sse";
	} else if (
		connectionType === "streamable_http" ||
		connectionType === "http"
	) {
		type = "streamable_http";
	} else {
		type = "stdio";
	}

	// Resolve cwd relative to config file
	let cwd = raw.cwd as string | undefined;
	if (cwd === "." || !cwd) {
		// Use directory of config file
		cwd = resolvePath(configPath, "..");
	}

	return {
		type,
		command: raw.command as string | undefined,
		args: raw.args as string[] | undefined,
		cwd,
		env: raw.env as Record<string, string> | undefined,
		url: raw.url as string | undefined,
		headers: raw.headers as Record<string, string> | undefined,
		timeout: raw.timeout as number | undefined,
		sseReadTimeout: (raw.sse_read_timeout || raw.sseReadTimeout) as
			| number
			| undefined,
	};
}

export function defaultServerPrefix(
	serverKey: string,
	_serverInfo: unknown,
): string {
	// Normalize the prefix: lowercase, replace spaces with hyphens
	return serverKey.toLowerCase().replace(/\s+/g, "-");
}

/**
 * Get list of enabled server names from config
 */
export async function getEnabledServers(
	configPath: string = "mcp_servers.json",
): Promise<string[]> {
	const config = await loadConfig(configPath);
	return Object.keys(config.mcpServers);
}
