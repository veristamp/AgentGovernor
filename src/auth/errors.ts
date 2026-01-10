/**
 * MCP Identity SDK - Errors
 *
 * Custom error classes for MCP authentication operations.
 */

/**
 * Base error for MCP SDK operations.
 */
export class MCPError extends Error {
    code?: string;

    constructor(message: string, code?: string) {
        super(message);
        this.name = 'MCPError';
        this.code = code;
    }
}

/**
 * Registration failed.
 */
export class MCPRegistrationError extends MCPError {
    constructor(message: string, code?: string) {
        super(message, code);
        this.name = 'MCPRegistrationError';
    }
}

/**
 * Authentication/authorization failed.
 */
export class MCPAuthError extends MCPError {
    constructor(message: string, code?: string) {
        super(message, code);
        this.name = 'MCPAuthError';
    }
}

/**
 * Token validation failed.
 */
export class MCPValidationError extends MCPError {
    constructor(message: string, code?: string) {
        super(message, code);
        this.name = 'MCPValidationError';
    }
}

/**
 * Rate limit exceeded.
 */
export class MCPRateLimitError extends MCPError {
    retryAfter: number;
    remaining: number;

    constructor(message: string, retryAfter: number = 60, remaining: number = 0) {
        super(message, 'rate_limit_exceeded');
        this.name = 'MCPRateLimitError';
        this.retryAfter = retryAfter;
        this.remaining = remaining;
    }
}
