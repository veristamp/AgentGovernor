import { createAnthropic } from "@ai-sdk/anthropic";
import { createGoogleGenerativeAI } from "@ai-sdk/google";
import { createOpenAI } from "@ai-sdk/openai";
import { generateText, type LanguageModel } from "ai";
import type { LlmCompletionOptions, LlmMessage } from "./types";

export class LlmClient {
	private openai: ReturnType<typeof createOpenAI>;
	private anthropic: ReturnType<typeof createAnthropic>;
	private google: ReturnType<typeof createGoogleGenerativeAI>;

	constructor(
		// Legacy support, usually for OpenAI-compatible proxies
		baseUrl?: string,
		apiKey?: string,
	) {
		// Initialize providers (keys ideally come from env, but can be passed)
		this.openai = createOpenAI({
			apiKey: process.env.OPENAI_API_KEY || apiKey,
			baseURL: baseUrl, // Supports local proxies like Ollama/LMStudio if compatible
		});
		this.anthropic = createAnthropic({
			apiKey: process.env.ANTHROPIC_API_KEY,
		});
		this.google = createGoogleGenerativeAI({
			apiKey: process.env.GOOGLE_GENERATIVE_AI_API_KEY,
		});
	}

	private getModel(modelId: string): LanguageModel {
		if (modelId.startsWith("claude")) {
			return this.anthropic(modelId);
		}
		if (modelId.startsWith("gemini")) {
			return this.google(modelId);
		}
		// Default to OpenAI for "gpt-*" or unknown models (assuming proxy)
		return this.openai(modelId);
	}

	async complete(
		messages: LlmMessage[],
		options: LlmCompletionOptions,
	): Promise<string> {
		const model = this.getModel(options.model);

		// Vercel AI SDK handles the fetch/streaming/retries internally
		const { text } = await generateText({
			model,
			messages: messages.map((m) => ({
				role: m.role,
				content: m.content,
			})),
			temperature: options.temperature,
			// We can add abortSignal here if we propagate it from options
			abortSignal: options.timeoutMs
				? AbortSignal.timeout(options.timeoutMs)
				: undefined,
		});

		return text;
	}
}
