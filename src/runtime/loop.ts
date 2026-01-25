import { generateText } from "ai";
import { z } from "zod";
// Define CoreMessage compatible with AI SDK and ContextManager
// We define it locally or import from context to avoid 'ai' import issues if types are missing
import type { CoreMessage } from "./context";
import { ContextManager } from "./context";
import type { AgentRuntime, RuntimeContext } from "./factory";
import { type TraceEvent, TraceManager } from "./trace";
import type { AgentLoopRunOptions } from "./types";

export interface GovernedLoopOptions extends AgentLoopRunOptions {
	runId?: string;
	sessionId?: string;
	validateFinal?: (
		value: unknown,
	) =>
		| { ok: true; value: any }
		| { ok: false; error: string }
		| Promise<{ ok: true; value: any } | { ok: false; error: string }>;
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
}> {
	const maxSteps = options.maxIterations ?? 10;
	const traceManager = new TraceManager({
		runId: options.runId,
		sessionId: options.sessionId || ctx.identity.sessionId,
	});
	const contextManager = new ContextManager();

	console.log(`[Loop] Starting run (Session: ${traceManager.sessionId})`);

	const recentEvents = await traceManager.getRecentEvents(50);
	const messages = contextManager.compose({
		system: systemPrompt,
		initialUser: userPrompt,
		history: recentEvents,
	});

	const sdkTools: Record<string, any> = {};
	const nameMap = new Map<string, string>();
	const reverseNameMap = new Map<string, string>();

	for (const t of runtime.tools) {
		let safeName = t.name.replace(/[^a-zA-Z0-9_-]/g, "_");
		let suffix = 1;
		while (reverseNameMap.has(safeName)) {
			safeName = `${safeName}_${suffix}`;
			suffix += 1;
		}

		nameMap.set(t.name, safeName);
		reverseNameMap.set(safeName, t.name);

		sdkTools[safeName] = {
			description: t.description,
			inputSchema: z.object({}).passthrough(),
			execute: async (args: any) => {
				return await t.execute(args, {
					orgId: ctx.identity.orgId,
					roles: ctx.identity.roles,
					scopes: ctx.identity.scopes,
				});
			},
		};
	}

	let currentIteration = 0;

	try {
		// Use explicit casting to avoid TS errors with potentially stale type definitions
		// maxSteps is supported in AI SDK 4.0+
		const genOptions: any = {
			model: runtime.model,
			tools: sdkTools,
			maxSteps: maxSteps,
			messages: messages,
			onStepFinish: async ({ text, toolCalls, toolResults }: any) => {
				const iteration = currentIteration++;

				if (toolCalls) {
					for (const call of toolCalls) {
						const originalName =
							reverseNameMap.get(call.toolName) || call.toolName;
						await traceManager.emit({
							iteration,
							type: "tool_call",
							content: {
								name: originalName,
								arguments: call.args,
							},
							reasoning: text,
						});
					}
				}

				if (toolResults) {
					for (const res of toolResults) {
						const originalName =
							reverseNameMap.get(res.toolName) || res.toolName;
						await traceManager.emit({
							iteration,
							type: "tool_result",
							content: {
								name: originalName,
								result: res.result,
							},
						});
					}
				}
			},
		};

		const result = await generateText(genOptions);

		let finalValue: any = result.text;
		try {
			const text = (result.text || "").trim();
			if (text.startsWith("{") || text.startsWith("[")) {
				finalValue = JSON.parse(text);
			} else {
				const jsonMatch =
					text.match(/```json\n([\s\S]*?)\n```/) ||
					text.match(/```\n([\s\S]*?)\n```/);
				if (jsonMatch && jsonMatch[1]) {
					finalValue = JSON.parse(jsonMatch[1]);
				}
			}
		} catch (e) {
			// ignore
		}

		if (options.validateFinal) {
			const validation = await options.validateFinal(finalValue);
			if (!validation.ok) {
				const errorMsg = `Validation Failed: ${validation.error}`;
				await traceManager.emit({
					iteration: currentIteration,
					type: "error",
					content: { error: errorMsg },
				});
				throw new Error(errorMsg);
			}
			finalValue = validation.value;
		}

		await traceManager.emit({
			iteration: currentIteration,
			type: "final",
			content: { result: finalValue },
		});

		return {
			final: finalValue as TFinal,
			iterations: currentIteration + 1,
			trace: await traceManager.getRecentEvents(100),
		};
	} catch (e) {
		console.error("[Loop] Error:", e);
		await traceManager.emit({
			iteration: currentIteration,
			type: "error",
			content: { error: String(e) },
		});
		throw e;
	}
}
