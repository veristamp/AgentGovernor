export * from "./registry";
export * from "./types";

import { ToolRegistry } from "./registry";

// Global singleton instance
let instance: ToolRegistry | null = null;

export function getToolRegistry(toolsDir?: string): ToolRegistry {
	if (!instance) {
		instance = new ToolRegistry({ toolsDir });
		void instance.ingest().catch((err) => {
			console.warn("[ToolRegistry] Ingest failed:", err);
		});
	}
	return instance;
}
