/**
 * AI SDK v6 Middleware
 *
 * Provides caching and governance middleware for the AI SDK.
 * Uses the LanguageModelV3Middleware interface from @ai-sdk/provider.
 *
 * Usage:
 * ```typescript
 * import { wrapLanguageModel } from 'ai';
 * import { cacheMiddleware, governanceMiddleware } from './middleware';
 *
 * const wrappedModel = wrapLanguageModel({
 *   model: openai('gpt-4o'),
 *   middleware: cacheMiddleware,
 * });
 * ```
 */

import { createHash } from "node:crypto";
import type {
	LanguageModelV3CallOptions,
	LanguageModelV3Middleware,
} from "@ai-sdk/provider";
import { getAuditLogger } from "../core/audit";
import type { PolicyEngine } from "../core/policy/engine";
import type { Identity } from "../core/policy/types";

export interface RuntimeIdentity extends Identity {
	sessionId: string;
	missionId: string;
}

// ============================================================================
// Caching Middleware
// ============================================================================

interface CacheEntry {
	result: unknown;
	timestamp: number;
}

interface CacheMiddlewareOptions {
	ttlMs?: number;
	maxEntries?: number;
	namespace?: string;
}

/**
 * AI SDK v6 Caching Middleware
 *
 * Implements LanguageModelV3Middleware for transparent LLM response caching.
 */
export const cacheMiddleware = (
	options: CacheMiddlewareOptions = {},
): LanguageModelV3Middleware => {
	const {
		ttlMs = 3600000,
		maxEntries = 1000,
		namespace = "llm:cache",
	} = options;
	const cache = new Map<string, CacheEntry>();

	function getCacheKey(params: LanguageModelV3CallOptions): string {
		const hash = createHash("sha256")
			.update(JSON.stringify(params))
			.digest("hex")
			.slice(0, 32);
		return `${namespace}:${hash}`;
	}

	function isExpired(timestamp: number): boolean {
		return Date.now() - timestamp > ttlMs;
	}

	return {
		specificationVersion: "v3" as const,

		wrapGenerate: async ({ doGenerate, params }) => {
			const cacheKey = getCacheKey(params);

			const cached = cache.get(cacheKey);
			if (cached && !isExpired(cached.timestamp)) {
				console.log(`[Cache] Hit ${cacheKey.slice(0, 16)}`);
				return cached.result as Awaited<ReturnType<typeof doGenerate>>;
			}

			console.log(`[Cache] Miss ${cacheKey.slice(0, 16)}`);
			const result = await doGenerate();

			// LRU eviction
			if (cache.size >= maxEntries) {
				const firstKey = cache.keys().next().value;
				if (firstKey) cache.delete(firstKey);
			}
			cache.set(cacheKey, { result, timestamp: Date.now() });

			return result;
		},

		wrapStream: async ({ doStream }) => {
			// For streaming, skip caching by default (complex to implement correctly)
			return doStream();
		},
	};
};

// ============================================================================
// Governance Middleware
// ============================================================================

interface GovernanceMiddlewareOptions {
	policy: PolicyEngine;
	identity: RuntimeIdentity;
}

/**
 * AI SDK v6 Governance Middleware
 *
 * Adds policy checking and audit logging at the middleware level.
 */
export const governanceMiddleware = (
	options: GovernanceMiddlewareOptions,
): LanguageModelV3Middleware => {
	const { policy, identity } = options;
	const auditLogger = getAuditLogger();

	return {
		specificationVersion: "v3" as const,

		wrapGenerate: async ({ doGenerate, params: _params, model }) => {
			const modelId = model?.modelId || "unknown";

			// Policy check
			const decision = await policy.check({
				identity,
				action: "llm.generate",
				resource: modelId,
			});

			if (!decision.allowed) {
				throw new Error(`Policy Violation: ${decision.reason}`);
			}

			const start = Date.now();
			const result = await doGenerate();

			// Audit log
			auditLogger.log({
				timestamp: new Date(),
				identityId: identity.id,
				missionId: identity.missionId,
				tool: "llm.generate",
				args: { model: modelId },
				result: {
					inputTokens: (result as { usage?: { promptTokens?: number } }).usage
						?.promptTokens,
					outputTokens: (result as { usage?: { completionTokens?: number } })
						.usage?.completionTokens,
				},
				latencyMs: Date.now() - start,
			});

			return result;
		},

		wrapStream: async ({ doStream, model }) => {
			const modelId = model?.modelId || "unknown";

			const decision = await policy.check({
				identity,
				action: "llm.stream",
				resource: modelId,
			});

			if (!decision.allowed) {
				throw new Error(`Policy Violation: ${decision.reason}`);
			}

			return doStream();
		},
	};
};
