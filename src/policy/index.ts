/**
 * Policy Module - Barrel Export
 */

export { PolicyEngine, DEFAULT_RULES } from './engine';
export * from './types';

// Re-export from auth module for backwards compatibility
export { MCPResourceServer as AuthSDK } from '../auth';
export { MCPAuthError as AuthError } from '../auth';
export { extractBearerToken } from '../auth';
