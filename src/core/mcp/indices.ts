/**
 * Capability Index
 * Indexes tools, resources, and prompts with prefixed names
 */

import type { PromptInfo, ResourceInfo, ToolInfo } from "./types";

// Minimal client surface required by MCPClientManager.executeAction.
export interface MCPClient {
	callTool: (args: {
		name: string;
		arguments?: Record<string, unknown>;
		_meta?: {
			[x: string]: unknown;
			progressToken?: string | number;
			"io.modelcontextprotocol/related-task"?: { taskId: string };
		};
		task?: { ttl?: number };
	}) => Promise<unknown>;
	readResource: (args: { uri: string }) => Promise<{ contents: unknown }>;
	getPrompt: (args: {
		name: string;
		arguments?: Record<string, string>;
	}) => Promise<{ messages: unknown }>;
}

export class CapabilityIndex {
	private prefixToClient: Map<string, MCPClient> = new Map();
	private tools: Map<string, ToolInfo> = new Map();
	private resources: Map<string, ResourceInfo> = new Map();
	private prompts: Map<string, PromptInfo> = new Map();

	registerClient(
		prefix: string,
		client: MCPClient,
		tools: ToolInfo[],
		resources: ResourceInfo[],
		prompts: PromptInfo[],
	): void {
		this.prefixToClient.set(prefix, client);

		for (const tool of tools) {
			const qualifiedName = `${prefix}.${tool.name}`;
			this.tools.set(qualifiedName, { ...tool, name: qualifiedName });
		}

		for (const resource of resources) {
			const qualifiedName = `${prefix}.${resource.name || resource.uri}`;
			this.resources.set(qualifiedName, { ...resource });
		}

		for (const prompt of prompts) {
			const qualifiedName = `${prefix}.${prompt.name}`;
			this.prompts.set(qualifiedName, { ...prompt, name: qualifiedName });
		}
	}

	resolveClient(qualifiedName: string): MCPClient | undefined {
		// Extract prefix from qualified name (e.g., "filesystem.read" -> "filesystem")
		const prefix = qualifiedName.split(".")[0] ?? "";
		return this.prefixToClient.get(prefix);
	}

	getBaseName(qualifiedName: string): string {
		// "filesystem.read" -> "read"
		return qualifiedName.split(".").slice(1).join(".");
	}

	getAllTools(): Map<string, ToolInfo> {
		return new Map(this.tools);
	}

	getAllResources(): Map<string, ResourceInfo> {
		return new Map(this.resources);
	}

	getAllPrompts(): Map<string, PromptInfo> {
		return new Map(this.prompts);
	}

	getCapabilities() {
		return {
			tools: this.getAllTools(),
			resources: this.getAllResources(),
			prompts: this.getAllPrompts(),
		};
	}

	/** Get list of all tool names for manifest checking */
	getToolNames(): string[] {
		return Array.from(this.tools.keys());
	}

	/** Check if a tool exists */
	hasTool(qualifiedName: string): boolean {
		return this.tools.has(qualifiedName);
	}

	/** Get tool metadata by qualified name */
	getTool(qualifiedName: string): ToolInfo | undefined {
		return this.tools.get(qualifiedName);
	}

	/** Simple substring search across qualified tool names and descriptions */
	searchTools(query: string, limit: number = 50): ToolInfo[] {
		const q = query.trim().toLowerCase();
		if (!q) return [];

		const results: ToolInfo[] = [];
		for (const tool of this.tools.values()) {
			const name = tool.name.toLowerCase();
			const desc = (tool.description ?? "").toLowerCase();
			if (name.includes(q) || desc.includes(q)) {
				results.push(tool);
				if (results.length >= limit) break;
			}
		}
		return results;
	}
}
