/**
 * JSON-RPC Protocol Handler
 * Handles JSON-RPC 2.0 messages for sandbox communication
 */

export interface JsonRpcRequest {
    jsonrpc: '2.0';
    method: string;
    params?: Record<string, unknown>;
    id: number | string;
}

export interface JsonRpcResponse {
    jsonrpc: '2.0';
    result?: unknown;
    error?: JsonRpcError;
    id: number | string | null;
}

export interface JsonRpcError {
    code: number;
    message: string;
    data?: unknown;
}

// Standard JSON-RPC error codes
export const ErrorCodes = {
    PARSE_ERROR: -32700,
    INVALID_REQUEST: -32600,
    METHOD_NOT_FOUND: -32601,
    INVALID_PARAMS: -32602,
    INTERNAL_ERROR: -32603,
    // Custom codes
    UNAUTHORIZED: -32000,
    FORBIDDEN: -32001,
    REVOKED: -32002,
    POLICY_DENIED: -32003,
} as const;

export function parseRequest(line: string): JsonRpcRequest {
    const data = JSON.parse(line);

    if (data.jsonrpc !== '2.0') {
        throw new Error('Invalid JSON-RPC version');
    }

    if (typeof data.method !== 'string') {
        throw new Error('Method must be a string');
    }

    return {
        jsonrpc: '2.0',
        method: data.method,
        params: data.params || {},
        id: data.id,
    };
}

export function createResponse(id: number | string | null, result: unknown): JsonRpcResponse {
    return {
        jsonrpc: '2.0',
        result,
        id,
    };
}

export function createError(
    id: number | string | null,
    code: number,
    message: string,
    data?: unknown
): JsonRpcResponse {
    return {
        jsonrpc: '2.0',
        error: { code, message, data },
        id,
    };
}

export function serializeResponse(response: JsonRpcResponse): string {
    return JSON.stringify(response) + '\n';
}
