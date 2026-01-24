/**
 * Audit Logger
 *
 * Structured audit logging for all MCP operations.
 */

import type { AuditEntry } from "../mcp-client/types";

export interface AuditLoggerOptions {
	/** Console logging */
	console?: boolean;
	/** File path for JSON logs */
	filePath?: string;
	/** Maximum entries to keep in memory */
	maxMemoryEntries?: number;
}

export class AuditLogger {
	private entries: AuditEntry[] = [];
	private options: AuditLoggerOptions;

	constructor(options: AuditLoggerOptions = {}) {
		this.options = {
			console: options.console ?? true,
			filePath: options.filePath,
			maxMemoryEntries: options.maxMemoryEntries ?? 10000,
		};
	}

	/**
	 * Log an audit entry.
	 */
	log(entry: AuditEntry): void {
		// Add to memory
		this.entries.push(entry);

		// Trim if over limit
		if (this.entries.length > (this.options.maxMemoryEntries ?? 10000)) {
			this.entries = this.entries.slice(-1000);
		}

		// Console log
		if (this.options.console) {
			const status = entry.error ? "ERROR" : "OK";
			const identity = entry.identityId ?? "anonymous";
			console.log(
				`[AUDIT] ${entry.timestamp.toISOString()} ${identity} ${entry.tool} ${status} ${entry.latencyMs}ms`,
			);
		}

		// File log (async, fire-and-forget)
		if (this.options.filePath) {
			this.writeToFile(entry);
		}
	}

	/**
	 * Get all entries.
	 */
	getEntries(): AuditEntry[] {
		return [...this.entries];
	}

	/**
	 * Get entries for a specific identity.
	 */
	getEntriesForIdentity(identityId: string): AuditEntry[] {
		return this.entries.filter((e) => e.identityId === identityId);
	}

	/**
	 * Get entries for a specific mission.
	 */
	getEntriesForMission(missionId: string): AuditEntry[] {
		return this.entries.filter((e) => e.missionId === missionId);
	}

	/**
	 * Get entries for a specific tool.
	 */
	getEntriesForTool(tool: string): AuditEntry[] {
		return this.entries.filter((e) => e.tool === tool);
	}

	/**
	 * Get error entries.
	 */
	getErrors(): AuditEntry[] {
		return this.entries.filter((e) => e.error);
	}

	/**
	 * Get statistics.
	 */
	getStats(): {
		total: number;
		errors: number;
		avgLatency: number;
		byTool: Record<string, number>;
	} {
		const total = this.entries.length;
		const errors = this.entries.filter((e) => e.error).length;
		const avgLatency =
			total > 0
				? this.entries.reduce((sum, e) => sum + e.latencyMs, 0) / total
				: 0;

		const byTool: Record<string, number> = {};
		for (const entry of this.entries) {
			byTool[entry.tool] = (byTool[entry.tool] ?? 0) + 1;
		}

		return { total, errors, avgLatency, byTool };
	}

	/**
	 * Clear all entries.
	 */
	clear(): void {
		this.entries = [];
	}

	/**
	 * Export entries as JSON.
	 */
	toJSON(): string {
		return JSON.stringify(this.entries, null, 2);
	}

	// ==================== Private Methods ====================

	private async writeToFile(entry: AuditEntry): Promise<void> {
		if (!this.options.filePath) return;

		try {
			const line =
				JSON.stringify({
					...entry,
					timestamp: entry.timestamp.toISOString(),
				}) + "\n";

			const { appendFile } = await import("fs/promises");
			await appendFile(this.options.filePath, line);
		} catch (e) {
			console.error("[AuditLogger] Failed to write to file:", e);
		}
	}
}

// ==================== Singleton ====================

let auditLogger: AuditLogger | null = null;

export function getAuditLogger(options?: AuditLoggerOptions): AuditLogger {
	if (!auditLogger) {
		auditLogger = new AuditLogger(options);
	}
	return auditLogger;
}
