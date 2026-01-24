import type { LlmCompletionOptions, LlmMessage } from "./types";

export class LlmClient {
	constructor(
		private baseUrl: string,
		private apiKey: string,
	) {}

	async complete(
		messages: LlmMessage[],
		options: LlmCompletionOptions,
	): Promise<string> {
		const payload = {
			model: options.model,
			temperature: options.temperature ?? 0.2,
			max_tokens: options.maxTokens ?? 2048,
			stream: false,
			messages,
		};

		const headers: Record<string, string> = {
			"Content-Type": "application/json",
		};

		if (this.apiKey) {
			headers.Authorization = `Bearer ${this.apiKey}`;
		}

		const response = await fetch(`${this.baseUrl}/chat/completions`, {
			method: "POST",
			headers,
			body: JSON.stringify(payload),
			signal: options.timeoutMs
				? AbortSignal.timeout(options.timeoutMs)
				: undefined,
		});

		if (!response.ok) {
			const body = await response.text();
			throw new Error(`LLM request failed: ${response.status} ${body}`);
		}

		const data = (await response.json()) as {
			choices?: Array<{ message?: { content?: string } }>;
			error?: { message?: string };
		};

		if (data.error?.message) {
			throw new Error(`LLM error: ${data.error.message}`);
		}

		const content = data.choices?.[0]?.message?.content?.trim();
		if (!content) {
			throw new Error("LLM response missing content");
		}

		return content;
	}
}
