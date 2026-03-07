import type { CoreMessage } from "./context";

export interface MessageImportance {
	score: number;
	reason: string;
}

export interface MemoryConfig {
	maxEpisodicMessages: number;
	importanceThreshold: number;
	compressThreshold: number;
	alwaysKeepLast: number;
}

export interface MemoryStats {
	totalMessages: number;
	episodicMessages: number;
	compressedMessages: number;
	totalTokens: number;
	avgImportance: number;
	cacheHitRate: number;
}

/**
 * Memory Manager - AI SDK v6 Aligned Memory Management
 *
 * Provides intelligent message prioritization, importance scoring,
 * and compression for long-running conversations.
 *
 * Architecture:
 * ┌─────────────────────────────────────────────────────────────┐
 * │                    MemoryManager                            │
 * │  - Importance scoring for smart eviction                  │
 * │  - Dynamic compression when context grows                  │
 * │  - Cache-aware message ordering                          │
 * │  - Analytics and monitoring                              │
 * └─────────────────────────────────────────────────────────────┘
 */
export class MemoryManager {
	private config: MemoryConfig;
	private stats: MemoryStats;
	private importanceCache: Map<string, MessageImportance> = new Map();

	constructor(config: Partial<MemoryConfig> = {}) {
		this.config = {
			maxEpisodicMessages: 50,
			importanceThreshold: 0.3,
			compressThreshold: 30,
			alwaysKeepLast: 5,
			...config,
		};

		this.stats = {
			totalMessages: 0,
			episodicMessages: 0,
			compressedMessages: 0,
			totalTokens: 0,
			avgImportance: 0,
			cacheHitRate: 0,
		};
	}

	/**
   * Calculate importance score for a message
   * 
   Higher importance = less likely to be evicted
   */
	calculateImportance(msg: CoreMessage): MessageImportance {
		const cacheKey = this.getMessageCacheKey(msg);

		// Return cached importance if available
		if (this.importanceCache.has(cacheKey)) {
			const cachedImportance = this.importanceCache.get(cacheKey);
			if (cachedImportance) {
				return cachedImportance;
			}
		}

		let score = 0.5; // Default importance
		let reason = "default";

		const content =
			typeof msg.content === "string"
				? msg.content.toLowerCase()
				: JSON.stringify(msg.content).toLowerCase();

		// High importance indicators
		if (msg.role === "system") {
			score = 1.0;
			reason = "system_prompt";
		} else if (this.hasCodeContent(content)) {
			score = Math.max(score, 0.9);
			reason = "contains_code";
		} else if (msg.role === "user" && content.includes("?")) {
			score = Math.max(score, 0.7);
			reason = "question";
		} else if (this.hasToolCalls(msg)) {
			score = Math.max(score, 0.8);
			reason = "tool_call";
		} else if (this.hasCitations(content)) {
			score = Math.max(score, 0.75);
			reason = "has_citations";
		}

		// Low importance indicators
		const acknowledgments = [
			"thanks",
			"thank you",
			"ok",
			"okay",
			"got it",
			"i see",
			"understood",
		];
		if (acknowledgments.some((ack) => content.includes(ack))) {
			if (content.length < 50) {
				score = Math.min(score, 0.2);
				reason = "acknowledgment";
			}
		}

		// Boost for recent messages (recency bias)
		// This is applied at retrieval time, not here

		const importance: MessageImportance = { score, reason };
		this.importanceCache.set(cacheKey, importance);

		return importance;
	}

	/**
   * Prepare messages for AI SDK v6 prepareStep hook
   * 
   This is the main integration point with AI SDK v6.
   * It applies intelligent pruning, importance-based filtering,
   * and compression to optimize context for each step.
   */
	prepareMessages(params: {
		messages: CoreMessage[];
		maxMessages?: number;
		keepLast?: number;
		enableCompression?: boolean;
	}): CoreMessage[] {
		const {
			messages,
			maxMessages = this.config.maxEpisodicMessages,
			keepLast = this.config.alwaysKeepLast,
			enableCompression = true,
		} = params;

		// If under limit, return as-is
		if (messages.length <= maxMessages) {
			return messages;
		}

		// Separate system message
		const systemMsg = messages.find((m) => m.role === "system");
		const nonSystem = messages.filter((m) => m.role !== "system");

		// Calculate importance for all messages
		const withImportance = nonSystem.map((msg) => ({
			msg,
			importance: this.calculateImportance(msg),
		}));

		// Sort by importance (descending), then by recency
		withImportance.sort((a, b) => {
			// Always keep last N messages
			const aIsRecent = nonSystem.indexOf(a.msg) >= nonSystem.length - keepLast;
			const bIsRecent = nonSystem.indexOf(b.msg) >= nonSystem.length - keepLast;

			if (aIsRecent && !bIsRecent) return -1;
			if (!aIsRecent && bIsRecent) return 1;

			// Otherwise, sort by importance
			if (b.importance.score !== a.importance.score) {
				return b.importance.score - a.importance.score;
			}

			// Tie-breaker: keep original order (recency)
			return nonSystem.indexOf(a.msg) - nonSystem.indexOf(b.msg);
		});

		// Select top messages
		const selected = withImportance
			.slice(0, maxMessages - (systemMsg ? 1 : 0))
			.map((item) => item.msg);

		// Add system message back
		const result = systemMsg ? [systemMsg, ...selected] : selected;
		const maybeCompressed = enableCompression
			? this.compressMessages({ messages: result, keepRecent: keepLast })
			: result;

		// Update stats
		this.stats.episodicMessages = maybeCompressed.length;
		this.stats.compressedMessages = messages.length - maybeCompressed.length;

		return maybeCompressed;
	}

	/**
   * Compress old messages into summaries
   * 
   When context grows too large, compress older messages
   into concise summaries to save tokens while preserving
   key information.
   */
	compressMessages(params: {
		messages: CoreMessage[];
		keepRecent: number;
	}): CoreMessage[] {
		const { messages, keepRecent } = params;

		if (messages.length <= this.config.compressThreshold) {
			return messages;
		}

		// Separate system message
		const systemMsg = messages.find((m) => m.role === "system");
		const nonSystem = messages.filter((m) => m.role !== "system");

		// Keep recent messages
		const recent = nonSystem.slice(-keepRecent);
		const toCompress = nonSystem.slice(0, -keepRecent);

		if (toCompress.length === 0) {
			return messages;
		}

		// Create summary
		const summary = this.createSummary(toCompress);

		// Build result: system + summary + recent
		const result: CoreMessage[] = [];
		if (systemMsg) result.push(systemMsg);
		result.push(summary);
		result.push(...recent);

		// Update stats
		this.stats.compressedMessages += toCompress.length;

		return result;
	}

	/**
   * Create a summary of multiple messages
   * 
   Extracts key information while reducing token count
   */
	private createSummary(messages: CoreMessage[]): CoreMessage {
		const parts: string[] = [];

		for (const msg of messages) {
			const importance = this.calculateImportance(msg);

			// Only include important messages in summary
			if (importance.score < this.config.importanceThreshold) {
				continue;
			}

			const content =
				typeof msg.content === "string"
					? msg.content
					: JSON.stringify(msg.content);

			// Extract key information
			const excerpt = this.extractKeyInfo(content, msg.role);
			parts.push(excerpt);
		}

		const summaryText = parts.join("\n");

		return {
			role: "assistant",
			content: `[SUMMARY of ${messages.length} messages]\n${summaryText}`,
		};
	}

	/**
	 * Extract key information from a message
	 */
	private extractKeyInfo(content: string, role: string): string {
		// Truncate to reasonable length
		const maxLength = 200;

		if (content.length <= maxLength) {
			return `${role.toUpperCase()}: ${content}`;
		}

		// Extract first sentence or key points
		const firstSentence = content.split(/[.!?]/)[0];
		return `${role.toUpperCase()}: ${firstSentence}...`;
	}

	/**
	 * Check if content contains code
	 */
	private hasCodeContent(content: string): boolean {
		const codePatterns = [
			"```",
			"function ",
			"class ",
			"import ",
			"const ",
			"let ",
			"var ",
			"def ",
			"async ",
			"await ",
			"=>",
			"{",
			"}",
		];

		return codePatterns.some((pattern) => content.includes(pattern));
	}

	/**
	 * Check if message has tool calls
	 */
	private hasToolCalls(msg: CoreMessage): boolean {
		if (Array.isArray(msg.content)) {
			return msg.content.some(
				(part) => part.type === "tool-call" || part.type === "tool-result",
			);
		}
		return false;
	}

	/**
	 * Check if content has citations
	 */
	private hasCitations(content: string): boolean {
		return (
			content.includes("[citation:") ||
			content.includes("source:") ||
			content.includes("ref:")
		);
	}

	/**
	 * Get cache key for a message
	 */
	private getMessageCacheKey(msg: CoreMessage): string {
		const content =
			typeof msg.content === "string"
				? msg.content
				: JSON.stringify(msg.content);
		return `${msg.role}:${content.slice(0, 100)}`;
	}

	/**
	 * Get memory statistics
	 */
	getStats(): MemoryStats {
		return { ...this.stats };
	}

	/**
	 * Reset statistics
	 */
	resetStats() {
		this.stats = {
			totalMessages: 0,
			episodicMessages: 0,
			compressedMessages: 0,
			totalTokens: 0,
			avgImportance: 0,
			cacheHitRate: 0,
		};
		this.importanceCache.clear();
	}

	/**
	 * Update cache hit rate
	 */
	updateCacheHitRate(hitRate: number) {
		this.stats.cacheHitRate = hitRate;
	}
}

/**
 * Create a default memory manager
 */
export function createMemoryManager(
	config?: Partial<MemoryConfig>,
): MemoryManager {
	return new MemoryManager(config);
}
