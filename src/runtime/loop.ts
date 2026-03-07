import { generateText, stepCountIs, type ToolSet } from "ai";
import { z } from "zod";
import { AnalyticsManager } from "./analytics";
import { calculateCacheSavings } from "./cache-control";
import { ContextManager } from "./context";
import type { AgentRuntime, RuntimeContext } from "./factory";
import { SessionManager } from "./session_manager";
import { type TraceEvent, TraceManager } from "./trace";
import type { AgentLoopTool } from "./types";

export interface GovernedLoopOptions {
	maxIterations?: number;
	toolCallTimeoutMs?: number;
	runId?: string;
	sessionId?: string;
	runType?: "workflow" | "skill" | "tool" | "research";
	compaction?: {
		maxMessages?: number;
		keepLast?: number;
	};
	enableCache?: boolean;
	enableAnalytics?: boolean;
	validateFinal?: (
		value: unknown,
	) => Promise<{ ok: true; value: unknown } | { ok: false; error: string }>;
}

/** Shared ContextManager instance for AI SDK v6 prepareStep hooks */
const contextManager = new ContextManager(
	128000, // maxTokens
	4000, // reserveTokens
	{
		maxEpisodicMessages: 50,
		importanceThreshold: 0.3,
		compressThreshold: 30,
		alwaysKeepLast: 5,
	},
	{
		enableAnthropicCache: false, // Disabled by default, enable per-session
	},
);

/** Shared AnalyticsManager instance */
const analyticsManager = new AnalyticsManager();

/** Convert tools to AI SDK format with automatic execution through Gate 2 */
function convertToolsToToolSet(
	tools: AgentLoopTool[],
	ctx: RuntimeContext,
): ToolSet {
	const toolSet: ToolSet = {};

	for (const t of tools) {
		const safeName = t.name.replace(/[^a-zA-Z0-9_-]/g, "_");
		toolSet[safeName] = {
			description: t.description,
			parameters: z.object({}).passthrough(),
			execute: async (args: Record<string, unknown>) =>
				t.execute(args, {
					orgId: ctx.identity.orgId,
					roles: ctx.identity.roles,
					scopes: ctx.identity.scopes,
					missionId: ctx.identity.missionId,
					sessionId: ctx.identity.sessionId,
				}),
		};
	}

	return toolSet;
}

/** Sanitize user prompt to prevent injection attacks */
function sanitizePrompt(prompt: string): string {
	// Remove potential system prompt injection attempts
	return prompt
		.replace(/<\/?system>/gi, "")
		.replace(/<\/?instruction>/gi, "")
		.slice(0, 100000); // Max 100k chars
}

/** Validate system prompt for security */
function validateSystemPrompt(prompt: string): void {
	if (prompt.length > 50000) {
		throw new Error("System prompt exceeds maximum length of 50000 characters");
	}
	// Check for potentially dangerous content
	const dangerous = ["ignore previous", "disregard all", "system override"];
	if (dangerous.some((d) => prompt.toLowerCase().includes(d))) {
		throw new Error("System prompt contains potentially dangerous content");
	}
}

export async function runGovernedLoop<TFinal = string>(
	ctx: RuntimeContext,
	runtime: AgentRuntime,
	systemPrompt: string,
	userPrompt: string,
	options: GovernedLoopOptions = {},
): Promise<{
	final: TFinal;
	iterations: number;
	trace: TraceEvent[];
	cacheStats?: unknown;
	performanceMetrics?: unknown;
}> {
	// Security: Validate inputs
	validateSystemPrompt(systemPrompt);
	const sanitizedUserPrompt = sanitizePrompt(userPrompt);

	const maxIterations = Math.min(options.maxIterations ?? 10, 50); // Hard cap at 50
	const sessionId = options.sessionId || ctx.identity.sessionId;
	const enableCache = options.enableCache ?? false;
	const enableAnalytics = options.enableAnalytics ?? false;

	// Start analytics if enabled
	let sessionAnalytics = null;
	if (enableAnalytics) {
		sessionAnalytics = analyticsManager.startSession(sessionId);
	}

	const session = await SessionManager.start({
		sessionId,
		missionId: ctx.identity.missionId,
		runId: options.runId,
		runType: options.runType,
		policyContext: {
			orgId: ctx.identity.orgId || "",
			roles: ctx.identity.roles,
			permissions: ctx.identity.scopes,
		},
	});

	const traceManager = new TraceManager({
		runId: session.runId,
		sessionId: session.sessionId,
	});

	console.log(
		`[Loop] Starting ${options.runType || "run"} (session: ${traceManager.sessionId})`,
	);
	console.log(
		`[Loop] Cache: ${enableCache ? "enabled" : "disabled"}, Analytics: ${enableAnalytics ? "enabled" : "disabled"}`,
	);
	await session.ensureSystem(systemPrompt);
	await session.addUser(sanitizedUserPrompt);

	const tools = convertToolsToToolSet(runtime.tools, ctx);

	try {
		const startTime = Date.now();
		const result = await generateText({
			model: runtime.model,
			system: systemPrompt,
			prompt: sanitizedUserPrompt,
			tools,
			stopWhen: stepCountIs(maxIterations),

			onStepFinish: async (stepResult) => {
				const step = stepResult as {
					stepNumber?: number;
					toolCalls?: Array<{
						toolName?: string;
						args?: unknown;
						input?: unknown;
						toolCallId?: string;
					}>;
					toolResults?: Array<{
						toolName?: string;
						result?: unknown;
						value?: unknown;
						toolCallId?: string;
					}>;
					finishReason?: unknown;
					usage?: unknown;
				};
				const stepIndex = step.stepNumber || 0;
				const stepLatency = Date.now() - startTime;

				// Record analytics
				if (enableAnalytics && sessionAnalytics) {
					analyticsManager.recordStep(
						sessionAnalytics.sessionId,
						stepResult.usage?.totalTokens || 0,
						stepLatency,
					);
				}

				const toolCalls = step.toolCalls || [];
				for (const call of toolCalls) {
					await traceManager.emit({
						iteration: stepIndex,
						type: "tool_call",
						content: {
							name: call.toolName || "unknown_tool",
							arguments: call.args || call.input,
							toolCallId: call.toolCallId,
						},
					});
				}

				const toolResults = step.toolResults || [];
				for (const tr of toolResults) {
					await traceManager.emit({
						iteration: stepIndex,
						type: "tool_result",
						content: {
							name: tr.toolName || "unknown_tool",
							result: tr.result ?? tr.value ?? tr,
							toolCallId: tr.toolCallId,
						},
					});
				}

				await traceManager.emit({
					iteration: stepIndex,
					type: "event",
					content: {
						event: "step_complete",
						finishReason: step.finishReason,
						usage: step.usage,
					},
				});
			},

			prepareStep: contextManager.prepareStep({
				...options.compaction,
				enableCompression: true,
			}),

			abortSignal: options.toolCallTimeoutMs
				? AbortSignal.timeout(options.toolCallTimeoutMs)
				: undefined,
		});

		let finalValue: unknown = result.text;

		// Parse JSON if present
		const parsed = (() => {
			const clean = (result.text || "").trim();
			try {
				if (clean.startsWith("{") || clean.startsWith("["))
					return JSON.parse(clean);
				const match = clean.match(/```(?:json)?\n([\s\S]*?)\n```/);
				if (match?.[1]) return JSON.parse(match[1]);
			} catch {}
			return undefined;
		})();
		if (parsed !== undefined) finalValue = parsed;

		// Validate final result
		if (options.validateFinal) {
			const validated = await options.validateFinal(finalValue);
			if (!validated.ok) {
				await traceManager.emit({
					iteration: result.steps.length,
					type: "error",
					content: { error: validated.error },
				});
				await session.finish("failed");
				if (enableAnalytics) analyticsManager.recordError();
				throw new Error(`Validation failed: ${validated.error}`);
			}
			finalValue = validated.value;
		}

		await traceManager.emit({
			iteration: result.steps.length,
			type: "final",
			content: { result: finalValue },
		});
		await session.finish("completed");

		// Extract cache statistics
		const cacheStats = contextManager.extractCacheStats(result);
		if (cacheStats) {
			console.log(
				`[Cache] Hit rate: ${(cacheStats.cacheHitRate * 100).toFixed(1)}%`,
			);
			console.log(
				`[Cache] Created: ${cacheStats.cacheCreationTokens}, Read: ${cacheStats.cacheReadTokens}`,
			);

			const savings = calculateCacheSavings(cacheStats);
			console.log(
				`[Cache] Cost savings: $${savings.costSavings.toFixed(4)}, Latency savings: ${savings.latencySavings.toFixed(0)}ms`,
			);

			// Record cache stats in analytics
			if (enableAnalytics && sessionAnalytics) {
				analyticsManager.recordCacheStats(
					sessionAnalytics.sessionId,
					cacheStats,
				);
			}
		}

		// End analytics session
		let performanceMetrics = null;
		if (enableAnalytics && sessionAnalytics) {
			analyticsManager.endSession(sessionAnalytics.sessionId);
			performanceMetrics = analyticsManager.getPerformanceMetrics();

			console.log(
				`[Analytics] Avg latency: ${performanceMetrics.avgLatency.toFixed(2)}ms`,
			);
			console.log(
				`[Analytics] P95 latency: ${performanceMetrics.p95Latency.toFixed(2)}ms`,
			);
			console.log(
				`[Analytics] Error rate: ${(performanceMetrics.errorRate * 100).toFixed(2)}%`,
			);
		}

		console.log(`[Loop] Completed ${result.steps.length} steps`);
		return {
			final: finalValue as TFinal,
			iterations: result.steps.length,
			trace: await traceManager.getRecentEvents(100),
			cacheStats,
			performanceMetrics,
		};
	} catch (error) {
		await traceManager.emit({
			iteration: 0,
			type: "error",
			content: { error: String(error) },
		});
		await session.finish("failed");
		if (enableAnalytics) analyticsManager.recordError();
		throw error;
	}
}

/**
 * Get analytics manager instance
 */
export function getAnalyticsManager(): AnalyticsManager {
	return analyticsManager;
}

/**
 * Get context manager instance
 */
export function getContextManager(): ContextManager {
	return contextManager;
}
