import {
	addCacheControlToMessages,
	type CacheControlOptions,
	extractCacheStats,
} from "./cache-control";
import { type MemoryConfig, MemoryManager } from "./memory-manager";
import type { TraceEvent } from "./trace";

// Compatible with Vercel AI SDK Core message format
export type CoreMessage =
	| { role: "system"; content: string }
	| { role: "user"; content: string | Array<unknown> }
	| { role: "assistant"; content: string | Array<unknown> }
	| { role: "tool"; content: Array<unknown> };

/**
 * AI SDK v6 Context Manager
 *
 * Provides message composition utilities that align with AI SDK v6 patterns.
 * Use prepareStep() in generateText() for per-step context management.
 *
 * This class provides utilities for:
 * - compose(): Create initial message list from system + user + history
 * - prepareStep(): AI SDK v6 hook for context pruning
 * - estimateTokens(): Token estimation for context budgeting
 *
 * Enhanced with:
 * - MemoryManager for intelligent message prioritization
 * - Cache control for provider-specific prompt caching
 * - Analytics integration for performance monitoring
 */
export class ContextManager {
	private maxTokens: number;
	private reserveTokens: number;
	private memoryManager: MemoryManager;
	private enableCache: boolean;

	constructor(
		maxTokens = 128000,
		reserveTokens = 4000,
		memoryConfig?: Partial<MemoryConfig>,
		cacheOptions?: CacheControlOptions,
	) {
		this.maxTokens = maxTokens;
		this.reserveTokens = reserveTokens;
		this.memoryManager = new MemoryManager(memoryConfig);
		this.enableCache = cacheOptions?.enableAnthropicCache || false;
	}

	/**
	 * AI SDK v6 prepareStep hook implementation
	 *
	 * Use this in generateText() options:
	 * ```typescript
	 * const result = await generateText({
	 *   model,
	 *   tools,
	 *   prepareStep: ctxManager.prepareStep({ maxMessages: 50, keepLast: 20 }),
	 * });
	 * ```
	 *
	 * Enhanced with:
	 * - MemoryManager for intelligent message selection
	 * - Cache control for provider-specific caching
	 */
	public prepareStep(
		options: {
			maxMessages?: number;
			keepLast?: number;
			enableCompression?: boolean;
		} = {},
	) {
		const maxMessages = options.maxMessages ?? 120;
		const keepLast = options.keepLast ?? 40;
		const enableCompression = options.enableCompression ?? true;

		return async ({
			messages,
		}: {
			stepNumber: number;
			messages: CoreMessage[];
		}): Promise<{ messages: CoreMessage[] }> => {
			// Apply memory management for intelligent pruning
			let prunedMessages = this.memoryManager.prepareMessages({
				messages,
				maxMessages,
				keepLast,
				enableCompression,
			});

			// Apply cache control if enabled
			if (this.enableCache) {
				prunedMessages = addCacheControlToMessages({
					messages: prunedMessages,
					options: { enableAnthropicCache: true },
				});
			}

			return { messages: prunedMessages };
		};
	}

	public compose(params: {
		system: string;
		initialUser?: string;
		history: TraceEvent[];
	}): CoreMessage[] {
		const messages: CoreMessage[] = [];
		let currentTokens = 0;
		const budget = this.maxTokens - this.reserveTokens;

		// 1. System Prompt (Priority #1)
		const sysMsg: CoreMessage = { role: "system", content: params.system };
		messages.push(sysMsg);
		currentTokens += this.estimateTokens(params.system);

		// 2. Initial User Message (Priority #2)
		if (params.initialUser) {
			const tokens = this.estimateTokens(params.initialUser);
			let content = params.initialUser;

			if (currentTokens + tokens > budget) {
				// Truncate if massively huge
				content = `${content.slice(0, (budget - currentTokens) * 4)}... (truncated)`;
			}

			messages.push({ role: "user", content });
			currentTokens += this.estimateTokens(content);
		}

		// 3. History / Trace Events (Priority #3, Newest First)
		const contextMessages: CoreMessage[] = [];
		const reversedHistory = [...params.history].reverse();

		for (const event of reversedHistory) {
			const msg = this.traceToMessage(event);
			if (!msg) continue;

			const contentStr =
				typeof msg.content === "string"
					? msg.content
					: JSON.stringify(msg.content);

			const tokens = this.estimateTokens(contentStr);

			if (currentTokens + tokens <= budget) {
				contextMessages.unshift(msg);
				currentTokens += tokens;
			} else if (currentTokens + 100 <= budget) {
				const summary = this.summarizeEvent(event);
				const sumContentStr =
					typeof summary.content === "string"
						? summary.content
						: JSON.stringify(summary.content);
				const sumTokens = this.estimateTokens(sumContentStr);

				if (currentTokens + sumTokens <= budget) {
					contextMessages.unshift(summary);
					currentTokens += sumTokens;
				} else {
					break;
				}
			} else {
				break;
			}
		}

		return [...messages, ...contextMessages];
	}

	// Simple heuristic: 4 chars ~= 1 token
	private estimateTokens(text: string): number {
		return Math.ceil(text.length / 4);
	}

	private traceToMessage(event: TraceEvent): CoreMessage | null {
		const toolCallId =
			typeof event.content.toolCallId === "string"
				? event.content.toolCallId
				: `call_${event.iteration}`;
		switch (event.type) {
			case "plan":
				return {
					role: "assistant",
					content: `THOUGHT: ${event.content.plan || event.reasoning}`,
				};
			case "tool_call":
				return {
					role: "assistant",
					content: [
						{
							type: "tool-call",
							toolCallId,
							toolName: event.content.name,
							args: event.content.arguments,
						},
					],
				};
			case "tool_result":
				return {
					role: "tool",
					content: [
						{
							type: "tool-result",
							toolCallId,
							toolName: event.content.name,
							result: event.content.result,
						},
					],
				};
			case "error":
				return {
					role: "user",
					content: `ERROR: ${event.content.error}`,
				};
			case "final":
				return {
					role: "assistant",
					content: JSON.stringify(event.content.result),
				};
			default:
				return null;
		}
	}

	private summarizeEvent(event: TraceEvent): CoreMessage {
		if (event.type === "tool_result") {
			const toolCallId =
				typeof event.content.toolCallId === "string"
					? event.content.toolCallId
					: `call_${event.iteration}`;
			return {
				role: "tool",
				content: [
					{
						type: "tool-result",
						toolCallId,
						toolName: event.content.name,
						result: "(Output truncated to save memory)",
					},
				],
			};
		}
		const msg = this.traceToMessage(event);
		return msg || { role: "assistant", content: "..." };
	}

	/**
	 * Get memory manager instance
	 */
	getMemoryManager(): MemoryManager {
		return this.memoryManager;
	}

	/**
	 * Extract cache statistics from AI SDK result
	 */
	extractCacheStats(result: unknown) {
		return extractCacheStats(result);
	}
}
