import type { LlmClient } from "../agent/llm_client";
import { parseJsonObject } from "./json";
import type {
	AgentLoopMessage,
	AgentLoopModelResponse,
	AgentLoopRunOptions,
	AgentLoopTool,
	AgentLoopToolContext,
} from "./types";

export class AgentLoopError extends Error {
	constructor(
		message: string,
		public details?: unknown,
	) {
		super(message);
	}
}

function formatToolCatalog(tools: AgentLoopTool[]): string {
	const lines: string[] = [];
	lines.push("AVAILABLE LOOP TOOLS:");
	for (const tool of tools) {
		lines.push(`- name: ${tool.name}`);
		lines.push(`  description: ${tool.description}`);
		lines.push(`  input_schema: ${JSON.stringify(tool.inputSchema)}`);
	}
	return lines.join("\n");
}

function formatToolResult(name: string, result: unknown): string {
	return `TOOL_RESULT\nname: ${name}\nresult: ${JSON.stringify(result, null, 2)}`;
}

function extractPythonCode(text: string): string | null {
	const fenceMatch = text.match(/```python\s*([\s\S]*?)```/i);
	if (fenceMatch?.[1]) return fenceMatch[1].trim();
	if (text.includes("async def main")) return text.trim();
	return null;
}

function coerceToModelResponse(value: unknown): AgentLoopModelResponse | null {
	if (!value) return null;

	if (typeof value === "string") {
		const python = extractPythonCode(value);
		if (python) {
			return {
				type: "final",
				result: { code: python },
			} as AgentLoopModelResponse;
		}
		return null;
	}

	if (typeof value !== "object") return null;
	const obj = value as Record<string, unknown>;

	if (obj.type === "tool_call" && typeof obj.name === "string") {
		return {
			type: "tool_call",
			name: obj.name,
			arguments:
				typeof obj.arguments === "object" && obj.arguments ? obj.arguments : {},
		} as AgentLoopModelResponse;
	}
	if (obj.type === "final" && "result" in obj) {
		return { type: "final", result: obj.result } as AgentLoopModelResponse;
	}
	if (typeof obj.type === "string" && "result" in obj) {
		// Some models emit different type tags; treat as final if result is present.
		return { type: "final", result: obj.result } as AgentLoopModelResponse;
	}

	const resultObj =
		typeof obj.result === "object" && obj.result
			? (obj.result as Record<string, unknown>)
			: null;
	const code =
		typeof obj.code === "string"
			? obj.code
			: resultObj && typeof resultObj.code === "string"
				? resultObj.code
				: null;
	if (code && typeof code === "string" && code.trim()) {
		return {
			type: "final",
			result: { code: code.trim() },
		} as AgentLoopModelResponse;
	}

	if (typeof obj.name === "string") {
		return {
			type: "tool_call",
			name: obj.name,
			arguments:
				typeof obj.arguments === "object" && obj.arguments ? obj.arguments : {},
		} as AgentLoopModelResponse;
	}

	return null;
}

export async function runAgentLoop<TFinal>(params: {
	llm: LlmClient;
	model: string;
	system: string;
	user: string;
	tools: AgentLoopTool[];
	toolContext: AgentLoopToolContext;
	options?: AgentLoopRunOptions;
	validateFinal?: (
		value: unknown,
	) =>
		| { ok: true; value: TFinal }
		| { ok: false; error: string }
		| Promise<{ ok: true; value: TFinal } | { ok: false; error: string }>;
}): Promise<{
	final: TFinal;
	transcript: AgentLoopMessage[];
	iterations: number;
}> {
	const maxIterations = params.options?.maxIterations ?? 10;

	const toolByName = new Map(params.tools.map((t) => [t.name, t]));
	const toolCatalogText = formatToolCatalog(params.tools);

	const system = `${params.system}\n\n${toolCatalogText}\n\nOUTPUT PROTOCOL:\n- To call a tool, output JSON: {"type":"tool_call","name":"<tool>","arguments":{...}}\n- To finish, output JSON: {"type":"final","result":{...}}\nReturn JSON only.`;

	const messages: AgentLoopMessage[] = [
		{ role: "system", content: system },
		{ role: "user", content: params.user },
	];
	let lastRaw: string | undefined;

	for (let i = 0; i < maxIterations; i += 1) {
		const raw = await params.llm.complete(
			messages.map((m) => ({ role: m.role, content: m.content })),
			{
				model: params.model,
				temperature: 0,
				maxTokens: 2048,
			},
		);
		lastRaw = raw;

		let parsed: AgentLoopModelResponse;
		try {
			const candidate = parseJsonObject<unknown>(raw);
			const coerced = coerceToModelResponse(candidate);
			if (!coerced) {
				throw new Error("Unrecognized JSON shape");
			}
			parsed = coerced;
		} catch (_e) {
			const python = extractPythonCode(raw);
			if (python) {
				parsed = {
					type: "final",
					result: { code: python },
				} as AgentLoopModelResponse;
			} else {
				const searchMatch = raw.match(/SEARCH\("([^"]+)"\)/);
				if (searchMatch?.[1]) {
					parsed = {
						type: "tool_call",
						name: "skills.search",
						arguments: { query: searchMatch[1], add_to_context: true },
					} as AgentLoopModelResponse;
				} else {
					messages.push({
						role: "user",
						content: `INVALID_JSON_OUTPUT\n${raw}\n\nFix and return a valid JSON object matching the OUTPUT PROTOCOL.`,
					});
					continue;
				}
			}
		}

		if (parsed.type === "tool_call") {
			const tool = toolByName.get(parsed.name);
			if (!tool) {
				messages.push({
					role: "user",
					content: `UNKNOWN_TOOL\nRequested: ${parsed.name}\nAvailable: ${[...toolByName.keys()].join(", ")}`,
				});
				continue;
			}

			const args =
				parsed.arguments && typeof parsed.arguments === "object"
					? parsed.arguments
					: {};
			let result: unknown;
			try {
				result = await tool.execute(
					args as Record<string, unknown>,
					params.toolContext,
				);
			} catch (e) {
				messages.push({
					role: "user",
					content: `TOOL_ERROR\nname: ${tool.name}\nerror: ${String(e)}`,
				});
				continue;
			}

			messages.push({
				role: "user",
				content: formatToolResult(tool.name, result),
			});
			continue;
		}

		if (parsed.type === "final") {
			const finalValue = parsed.result;
			if (params.validateFinal) {
				const validated = await params.validateFinal(finalValue);
				if (!validated.ok) {
					messages.push({
						role: "user",
						content: `FINAL_VALIDATION_ERROR\n${validated.error}\nReturn a corrected final JSON object.`,
					});
					continue;
				}
				return {
					final: validated.value,
					transcript: messages,
					iterations: i + 1,
				};
			}

			return {
				final: finalValue as TFinal,
				transcript: messages,
				iterations: i + 1,
			};
		}

		messages.push({
			role: "user",
			content: `INVALID_RESPONSE\nExpected type=tool_call|final but got: ${raw}`,
		});
	}

	throw new AgentLoopError("Max iterations exceeded", {
		maxIterations,
		lastRaw: lastRaw ? lastRaw.slice(0, 4000) : undefined,
	});
}
