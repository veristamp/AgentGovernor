import type { CoreMessage } from './context';

export interface CacheControlOptions {
  enableAnthropicCache?: boolean;
  enableVertexCache?: boolean;
  cacheSystemPrompt?: boolean;
  cacheContextChunks?: boolean;
  cacheStableMetadata?: boolean;
}

export interface CacheStats {
  cacheCreationTokens: number;
  cacheReadTokens: number;
  cacheHitRate: number;
  totalTokens: number;
  savedTokens: number;
}

/**
 * Add AI SDK v6 cache control to messages
 * 
 * This enables provider-specific prompt caching to reduce latency and costs
 * for repeated prompts across multiple LLM calls.
 * 
 * Usage:
 * ```typescript
 * const messages = addCacheControlToMessages({
 *   messages: originalMessages,
 *   options: { enableAnthropicCache: true }
 * });
 * ```
 */
export function addCacheControlToMessages(params: {
  messages: CoreMessage[];
  options?: CacheControlOptions;
}): CoreMessage[] {
  const { messages, options = {} } = params;
  const {
    enableAnthropicCache = false,
    enableVertexCache = false,
    cacheSystemPrompt = true,
    cacheContextChunks = true,
    cacheStableMetadata = true,
  } = options;

  // Skip if no caching enabled
  if (!enableAnthropicCache && !enableVertexCache) {
    return messages;
  }

  return messages.map((msg, index) => {
    // Cache system prompt (first message)
    if (msg.role === 'system' && cacheSystemPrompt && index === 0) {
      return {
        ...msg,
        providerOptions: {
          anthropic: enableAnthropicCache 
            ? { cacheControl: { type: 'ephemeral' } }
            : undefined,
        },
      };
    }

    // Cache context chunks (identified by content patterns)
    if (cacheContextChunks && shouldCacheMessage(msg)) {
      return {
        ...msg,
        providerOptions: {
          anthropic: enableAnthropicCache
            ? { cacheControl: { type: 'ephemeral' } }
            : undefined,
        },
      };
    }

    // Cache stable metadata (user profile, session context)
    if (cacheStableMetadata && isStableMetadata(msg)) {
      return {
        ...msg,
        providerOptions: {
          anthropic: enableAnthropicCache
            ? { cacheControl: { type: 'ephemeral' } }
            : undefined,
        },
      };
    }

    return msg;
  });
}

/**
 * Extract cache statistics from provider metadata
 * 
 * Returns detailed cache performance metrics from AI SDK v6 responses
 */
export function extractCacheStats(result: any): CacheStats | null {
  const anthropic = result.providerMetadata?.anthropic;
  if (!anthropic) return null;

  const cacheCreationTokens = anthropic.cacheCreationInputTokens || 0;
  const cacheReadTokens = anthropic.cacheReadInputTokens || 0;
  const totalTokens = cacheCreationTokens + cacheReadTokens;

  return {
    cacheCreationTokens,
    cacheReadTokens,
    cacheHitRate: totalTokens > 0 ? cacheReadTokens / totalTokens : 0,
    totalTokens,
    savedTokens: cacheReadTokens, // Tokens that were served from cache
  };
}

/**
 * Check if a message should be cached
 * 
 * Messages that are likely to be reused across multiple calls
 */
function shouldCacheMessage(msg: CoreMessage): boolean {
  if (msg.role === 'system') return true;
  
  if (typeof msg.content === 'string') {
    // Cache context chunks
    if (msg.content.includes('<context>') || 
        msg.content.includes('<chunk') ||
        msg.content.includes('<session_context>')) {
      return true;
    }
    
    // Cache stable metadata
    if (msg.content.includes('user:') || 
        msg.content.includes('profile:') ||
        msg.content.includes('preferences:')) {
      return true;
    }
  }
  
  return false;
}

/**
 * Check if message contains stable metadata
 * 
 * Stable metadata doesn't change during a session and is
 * a good candidate for caching
 */
function isStableMetadata(msg: CoreMessage): boolean {
  if (typeof msg.content !== 'string') return false;
  
  const stablePatterns = [
    'user_id:',
    'org_id:',
    'mission_id:',
    'session_id:',
    'role:',
    'permissions:',
    'preferences:',
  ];
  
  return stablePatterns.some(pattern => msg.content.includes(pattern));
}

/**
 * Calculate cache savings
 * 
 * Estimates cost and latency savings from cache hits
 */
export function calculateCacheSavings(stats: CacheStats): {
  costSavings: number;
  latencySavings: number;
  percentageSaved: number;
} {
  // Assume $0.15 per 1M input tokens (approximate)
  const costPerToken = 0.00000015;
  const costSavings = stats.savedTokens * costPerToken;
  
  // Assume 0.5ms per token for prefill (approximate)
  const latencyPerToken = 0.5;
  const latencySavings = stats.savedTokens * latencyPerToken;
  
  const percentageSaved = stats.totalTokens > 0 
    ? (stats.savedTokens / stats.totalTokens) * 100 
    : 0;
  
  return {
    costSavings,
    latencySavings,
    percentageSaved,
  };
}
