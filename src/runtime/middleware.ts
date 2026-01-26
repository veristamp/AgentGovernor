import type { LanguageModel } from "ai";
import { getAuditLogger } from "../core/audit";
import type { PolicyEngine } from "../core/policy/engine";
import type { Identity } from "../core/policy/types";

// Extend Identity to include runtime session info
export interface RuntimeIdentity extends Identity {
	sessionId?: string;
	missionId?: string; // Links to high-level mission
}

/**
 * Governed Model Wrapper
 *
 * Wraps a Vercel AI SDK LanguageModel to enforce policy, inject caching
 * strategies transparently, and log audits.
 */
export function wrapGovernedModel(
	model: LanguageModel,
	policy: PolicyEngine,
	identity: RuntimeIdentity,
): LanguageModel {
	// Cast to any to access internal methods/properties generic way
	const v1Model = model as any;
	const auditLogger = getAuditLogger();

	return {
		...v1Model, // Preserve all properties

		doGenerate: async (options: any) => {
			const start = Date.now();
			const newOptions = await applyGovernance(
				options,
				v1Model.modelId,
				policy,
				identity,
			);

			try {
				const result = await v1Model.doGenerate(newOptions);

				// Audit Log (Success)
				auditLogger.log({
					timestamp: new Date(),
					identityId: identity.id,
					missionId: identity.missionId,
					tool: "llm.generate",
					args: {
						model: v1Model.modelId,
						inputTokens: result.usage.promptTokens,
					},
					result: {
						outputTokens: result.usage.completionTokens,
					},
					latencyMs: Date.now() - start,
				});

				if (process.env.DEBUG_GOVERNANCE) {
					console.log(
						`[Governance] Generated: ${result.usage.promptTokens} -> ${result.usage.completionTokens}`,
					);
				}
				return result;
			} catch (e) {
				// Audit Log (Failure)
				auditLogger.log({
					timestamp: new Date(),
					identityId: identity.id,
					missionId: identity.missionId,
					tool: "llm.generate",
					args: { model: v1Model.modelId },
					error: String(e),
					latencyMs: Date.now() - start,
				});
				throw e;
			}
		},

		doStream: async (options: any) => {
			const start = Date.now();
			const newOptions = await applyGovernance(
				options,
				v1Model.modelId,
				policy,
				identity,
			);

			// Note: Streaming audit logging is harder because we don't know the full usage yet.
			// We log the *start* of the stream here.
			// The runtime loop should handle logging the full trace content.

			auditLogger.log({
				timestamp: new Date(),
				identityId: identity.id,
				missionId: identity.missionId,
				tool: "llm.stream",
				args: { model: v1Model.modelId },
				latencyMs: Date.now() - start,
			});

			return v1Model.doStream(newOptions);
		},
	} as unknown as LanguageModel;
}

/**
 * Core Governance Logic
 * - Checks Policy
 * - Injects Cache Headers
 */
async function applyGovernance(
	options: any,
	modelId: string,
	policy: PolicyEngine,
	identity: RuntimeIdentity,
): Promise<any> {
	// 1. Policy Check
	const decision = await policy.check({
		identity,
		action: "llm.generate",
		resource: modelId,
	});

	if (!decision.allowed) {
		if (process.env.DEBUG_GOVERNANCE) {
			console.warn(`[Governance] Policy Warning: ${decision.reason}`);
		}
		// In strict mode, uncomment:
		// throw new Error(`Policy Violation: ${decision.reason}`);
	}

	// 2. Cache Injection
	const providerMetadata = options.providerMetadata || {};
	const newOptions = { ...options, providerMetadata: { ...providerMetadata } };

	// A. OpenAI Affinity
	if (identity.sessionId) {
		newOptions.providerMetadata.openai = {
			...newOptions.providerMetadata.openai,
			promptCacheKey: identity.sessionId.slice(0, 16),
			promptCacheRetention: "24h",
		};
	}

	// B. Gemini Named Cache
	if (identity.sessionId) {
		newOptions.providerMetadata.google = {
			...newOptions.providerMetadata.google,
			cachedContent: `session-${identity.sessionId.slice(0, 16)}`,
		};
	}

	// C. Anthropic Explicit Caching
	// Only apply if the model is likely Anthropic
	const isAnthropic =
		modelId.toLowerCase().includes("claude") ||
		modelId.toLowerCase().includes("anthropic");

	if (isAnthropic && options.prompt && Array.isArray(options.prompt)) {
		let cacheMarksUsed = 0;
		const MAX_MARKS = 2;

		newOptions.prompt = options.prompt.map((msg: any, i: number) => {
			// System Prompt
			if (msg.role === "system" && cacheMarksUsed < MAX_MARKS) {
				cacheMarksUsed++;
				if (typeof msg.content === "string") {
					return {
						...msg,
						content: [
							{
								type: "text",
								text: msg.content,
								providerOptions: {
									anthropic: { cacheControl: { type: "ephemeral" } },
								},
							},
						],
					};
				}
				if (Array.isArray(msg.content)) {
					return {
						...msg,
						content: msg.content.map((part: any) => ({
							...part,
							providerOptions: {
								...part.providerOptions,
								anthropic: { cacheControl: { type: "ephemeral" } },
							},
						})),
					};
				}
			}

			// First User Message
			if (msg.role === "user" && i <= 2 && cacheMarksUsed < MAX_MARKS) {
				const contentStr =
					typeof msg.content === "string"
						? msg.content
						: msg.content
								.map((c: any) => (c.type === "text" ? c.text : ""))
								.join("");

				if (contentStr.length > 500) {
					cacheMarksUsed++;
					if (typeof msg.content === "string") {
						return {
							...msg,
							content: [
								{
									type: "text",
									text: msg.content,
									providerOptions: {
										anthropic: { cacheControl: { type: "ephemeral" } },
									},
								},
							],
						};
					}
					if (Array.isArray(msg.content)) {
						const newContent = [...msg.content];
						const lastTextIdx = newContent.findLastIndex(
							(p: any) => p.type === "text",
						);
						if (lastTextIdx !== -1) {
							newContent[lastTextIdx] = {
								...newContent[lastTextIdx],
								providerOptions: {
									...newContent[lastTextIdx].providerOptions,
									anthropic: { cacheControl: { type: "ephemeral" } },
								},
							};
						}
						return { ...msg, content: newContent };
					}
				}
			}
			return msg;
		});
	}

	return newOptions;
}
