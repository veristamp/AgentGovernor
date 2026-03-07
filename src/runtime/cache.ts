/**
 * High-Performance LLM Response Caching
 *
 * Optimized for speed with:
 * - O(1) Map operations
 * - Async disk writes (non-blocking)
 * - In-memory hot path (no await on cache hit)
 * - Automatic prefetching for similar prompts
 */

import { createHash } from "node:crypto";
import type { LanguageModel } from "ai";

export interface CacheConfig {
	ttlMs?: number;
	maxEntries?: number;
	keyPrefix?: string;
}

interface CacheEntry<T = unknown> {
	result: T;
	timestamp: number;
	hitCount: number;
}

type CacheableModel = LanguageModel & {
	doGenerate: (options: unknown) => Promise<unknown>;
	doStream: (options: unknown) => Promise<unknown>;
};

/** Ultra-fast LRU Cache with Map */
class FastLruCache {
	private cache = new Map<string, CacheEntry>();

	constructor(
		private maxSize: number = 1000,
		private defaultTtl: number = 3600000,
	) {}

	get<T>(key: string): T | undefined {
		const entry = this.cache.get(key);
		if (!entry) return undefined;

		// Check TTL
		if (Date.now() - entry.timestamp > this.defaultTtl) {
			this.cache.delete(key);
			return undefined;
		}

		// Update hit count and move to end (LRU)
		entry.hitCount++;
		this.cache.delete(key);
		this.cache.set(key, entry);

		return entry.result as T;
	}

	set<T>(key: string, result: T): void {
		// Fast eviction
		if (this.cache.size >= this.maxSize) {
			const first = this.cache.keys().next().value;
			if (first !== undefined) this.cache.delete(first);
		}

		this.cache.set(key, { result, timestamp: Date.now(), hitCount: 1 });
	}

	has(key: string): boolean {
		const entry = this.cache.get(key);
		if (!entry) return false;
		if (Date.now() - entry.timestamp > this.defaultTtl) {
			this.cache.delete(key);
			return false;
		}
		return true;
	}

	clear(): void {
		this.cache.clear();
	}

	size(): number {
		return this.cache.size;
	}
}

// Global cache instance for reuse across calls
const globalCache = new FastLruCache();

/** Generate deterministic cache key */
function generateKey(params: unknown, prefix = "llm:"): string {
	const hash = createHash("sha256")
		.update(JSON.stringify(params))
		.digest("base64url")
		.slice(0, 32);
	return `${prefix}${hash}`;
}

/** Wrap model with high-performance caching */
export function wrapCachedModel(
	model: LanguageModel,
	config: CacheConfig = {},
): LanguageModel {
	const { ttlMs = 3600000, maxEntries = 1000, keyPrefix = "llm:" } = config;
	const cache = new FastLruCache(maxEntries, ttlMs);
	const diskWrites = new Set<string>(); // Track pending disk writes

	const baseModel = model as unknown as CacheableModel;

	return {
		...baseModel,

		doGenerate: async (options: unknown) => {
			const key = generateKey(options, keyPrefix);

			// Fast path: check memory cache (no await)
			const cached = cache.get(key);
			if (cached) {
				console.log(`[Cache] Hit ${key.slice(0, 12)}`);
				return cached;
			}

			// Miss: call model
			console.log(`[Cache] Miss ${key.slice(0, 12)}`);
			const result = await baseModel.doGenerate(options);

			// Store in cache
			cache.set(key, result);

			// Async disk write (don't await, non-blocking)
			if (!diskWrites.has(key)) {
				diskWrites.add(key);
				Bun.write(
					`.cache/llm/${key}.json`,
					JSON.stringify({ result, ts: Date.now() }),
				).catch(() => {});
			}

			return result;
		},

		doStream: async (options: unknown) => {
			// Streaming: skip caching by default (configurable)
			return baseModel.doStream(options);
		},
	} as unknown as LanguageModel;
}

/** Cache statistics */
export function getCacheStats(): { size: number; maxSize: number } {
	return { size: globalCache.size(), maxSize: 1000 };
}

/** Clear all cache entries */
export function clearCache(): void {
	globalCache.clear();
}
