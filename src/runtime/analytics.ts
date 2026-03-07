import type { CacheStats } from "./cache-control";
import type { MemoryStats } from "./memory-manager";

export interface SessionAnalytics {
	sessionId: string;
	startTime: number;
	endTime?: number;
	totalSteps: number;
	totalTokens: number;
	cacheStats: CacheStats | null;
	memoryStats: MemoryStats;
	compressionEvents: CompressionEvent[];
}

export interface CompressionEvent {
	timestamp: number;
	originalMessages: number;
	compressedMessages: number;
	tokensSaved: number;
	compressionRatio: number;
}

export interface PerformanceMetrics {
	avgLatency: number;
	p50Latency: number;
	p95Latency: number;
	p99Latency: number;
	totalRequests: number;
	errorRate: number;
}

/**
 * Analytics Manager - Track and analyze memory/cache performance
 *
 * Provides comprehensive monitoring for:
 * - Cache hit rates and savings
 * - Memory compression efficiency
 * - Token usage patterns
 * - Performance metrics
 */
export class AnalyticsManager {
	private sessions: Map<string, SessionAnalytics> = new Map();
	private latencies: number[] = [];
	private errors: number = 0;
	private totalRequests: number = 0;

	/**
	 * Start tracking a session
	 */
	startSession(sessionId: string): SessionAnalytics {
		const analytics: SessionAnalytics = {
			sessionId,
			startTime: Date.now(),
			totalSteps: 0,
			totalTokens: 0,
			cacheStats: null,
			memoryStats: {
				totalMessages: 0,
				episodicMessages: 0,
				compressedMessages: 0,
				totalTokens: 0,
				avgImportance: 0,
				cacheHitRate: 0,
			},
			compressionEvents: [],
		};

		this.sessions.set(sessionId, analytics);
		return analytics;
	}

	/**
	 * End tracking a session
	 */
	endSession(sessionId: string): SessionAnalytics | null {
		const session = this.sessions.get(sessionId);
		if (!session) return null;

		session.endTime = Date.now();
		return session;
	}

	/**
	 * Record a step in the session
	 */
	recordStep(sessionId: string, tokens: number, latency: number) {
		const session = this.sessions.get(sessionId);
		if (!session) return;

		session.totalSteps++;
		session.totalTokens += tokens;
		this.latencies.push(latency);
		this.totalRequests++;
	}

	/**
	 * Record cache statistics
	 */
	recordCacheStats(sessionId: string, stats: CacheStats) {
		const session = this.sessions.get(sessionId);
		if (!session) return;

		session.cacheStats = stats;
		session.memoryStats.cacheHitRate = stats.cacheHitRate;
	}

	/**
	 * Record memory statistics
	 */
	recordMemoryStats(sessionId: string, stats: MemoryStats) {
		const session = this.sessions.get(sessionId);
		if (!session) return;

		session.memoryStats = { ...stats };
	}

	/**
	 * Record a compression event
	 */
	recordCompression(
		sessionId: string,
		originalMessages: number,
		compressedMessages: number,
		tokensSaved: number,
	) {
		const session = this.sessions.get(sessionId);
		if (!session) return;

		const compressionRatio =
			originalMessages > 0
				? (originalMessages - compressedMessages) / originalMessages
				: 0;

		session.compressionEvents.push({
			timestamp: Date.now(),
			originalMessages,
			compressedMessages,
			tokensSaved,
			compressionRatio,
		});
	}

	/**
	 * Record an error
	 */
	recordError() {
		this.errors++;
	}

	/**
	 * Get session analytics
	 */
	getSessionAnalytics(sessionId: string): SessionAnalytics | null {
		return this.sessions.get(sessionId) || null;
	}

	/**
	 * Get performance metrics
	 */
	getPerformanceMetrics(): PerformanceMetrics {
		if (this.latencies.length === 0) {
			return {
				avgLatency: 0,
				p50Latency: 0,
				p95Latency: 0,
				p99Latency: 0,
				totalRequests: this.totalRequests,
				errorRate: 0,
			};
		}

		const sorted = [...this.latencies].sort((a, b) => a - b);
		const sum = sorted.reduce((a, b) => a + b, 0);

		return {
			avgLatency: sum / sorted.length,
			p50Latency: sorted[Math.floor(sorted.length * 0.5)] ?? 0,
			p95Latency: sorted[Math.floor(sorted.length * 0.95)] ?? 0,
			p99Latency: sorted[Math.floor(sorted.length * 0.99)] ?? 0,
			totalRequests: this.totalRequests,
			errorRate: this.totalRequests > 0 ? this.errors / this.totalRequests : 0,
		};
	}

	/**
	 * Get cache performance summary
	 */
	getCacheSummary(): {
		totalSessions: number;
		avgCacheHitRate: number;
		totalCacheReadTokens: number;
		totalCacheCreationTokens: number;
		totalSavedTokens: number;
	} {
		let totalCacheHitRate = 0;
		let totalCacheReadTokens = 0;
		let totalCacheCreationTokens = 0;
		let sessionsWithCache = 0;

		for (const session of this.sessions.values()) {
			if (session.cacheStats) {
				totalCacheHitRate += session.cacheStats.cacheHitRate;
				totalCacheReadTokens += session.cacheStats.cacheReadTokens;
				totalCacheCreationTokens += session.cacheStats.cacheCreationTokens;
				sessionsWithCache++;
			}
		}

		const avgCacheHitRate =
			sessionsWithCache > 0 ? totalCacheHitRate / sessionsWithCache : 0;

		const totalSavedTokens = totalCacheReadTokens;

		return {
			totalSessions: this.sessions.size,
			avgCacheHitRate,
			totalCacheReadTokens,
			totalCacheCreationTokens,
			totalSavedTokens,
		};
	}

	/**
	 * Get compression summary
	 */
	getCompressionSummary(): {
		totalCompressionEvents: number;
		avgCompressionRatio: number;
		totalMessagesCompressed: number;
		totalTokensSaved: number;
	} {
		let totalCompressionRatio = 0;
		let totalMessagesCompressed = 0;
		let totalTokensSaved = 0;
		let eventCount = 0;

		for (const session of this.sessions.values()) {
			for (const event of session.compressionEvents) {
				totalCompressionRatio += event.compressionRatio;
				totalMessagesCompressed +=
					event.originalMessages - event.compressedMessages;
				totalTokensSaved += event.tokensSaved;
				eventCount++;
			}
		}

		const avgCompressionRatio =
			eventCount > 0 ? totalCompressionRatio / eventCount : 0;

		return {
			totalCompressionEvents: eventCount,
			avgCompressionRatio,
			totalMessagesCompressed,
			totalTokensSaved,
		};
	}

	/**
	 * Generate a comprehensive report
	 */
	generateReport(): string {
		const perf = this.getPerformanceMetrics();
		const cache = this.getCacheSummary();
		const compression = this.getCompressionSummary();

		const lines = [
			"=== Memory & Cache Performance Report ===",
			"",
			"Performance Metrics:",
			`  Total Requests: ${perf.totalRequests}`,
			`  Average Latency: ${perf.avgLatency.toFixed(2)}ms`,
			`  P50 Latency: ${perf.p50Latency.toFixed(2)}ms`,
			`  P95 Latency: ${perf.p95Latency.toFixed(2)}ms`,
			`  P99 Latency: ${perf.p99Latency.toFixed(2)}ms`,
			`  Error Rate: ${(perf.errorRate * 100).toFixed(2)}%`,
			"",
			"Cache Performance:",
			`  Total Sessions: ${cache.totalSessions}`,
			`  Average Cache Hit Rate: ${(cache.avgCacheHitRate * 100).toFixed(1)}%`,
			`  Total Cache Read Tokens: ${cache.totalCacheReadTokens.toLocaleString()}`,
			`  Total Cache Creation Tokens: ${cache.totalCacheCreationTokens.toLocaleString()}`,
			`  Total Saved Tokens: ${cache.totalSavedTokens.toLocaleString()}`,
			"",
			"Compression Performance:",
			`  Total Compression Events: ${compression.totalCompressionEvents}`,
			`  Average Compression Ratio: ${(compression.avgCompressionRatio * 100).toFixed(1)}%`,
			`  Total Messages Compressed: ${compression.totalMessagesCompressed}`,
			`  Total Tokens Saved: ${compression.totalTokensSaved.toLocaleString()}`,
			"",
		];

		return lines.join("\n");
	}

	/**
	 * Clear all analytics data
	 */
	clear() {
		this.sessions.clear();
		this.latencies = [];
		this.errors = 0;
		this.totalRequests = 0;
	}
}

/**
 * Create a default analytics manager
 */
export function createAnalyticsManager(): AnalyticsManager {
	return new AnalyticsManager();
}
