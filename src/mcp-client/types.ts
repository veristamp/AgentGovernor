/**
 * MCP Client Types
 * Type definitions for the MCPClientManager
 */

export interface ServerConfig {
    /** Connection type: stdio, streamable_http, or sse */
    type: 'stdio' | 'streamable_http' | 'sse';

    // stdio options
    command?: string;
    args?: string[];
    cwd?: string;
    env?: Record<string, string>;

    // HTTP options
    url?: string;
    headers?: Record<string, string>;
    timeout?: number;
    sseReadTimeout?: number;
}

export interface Config {
    mcpServers: Record<string, ServerConfig>;
}

export interface ToolInfo {
    name: string;
    description?: string;
    inputSchema?: Record<string, unknown>;
}

export interface ResourceInfo {
    uri: string;
    name?: string;
    description?: string;
    mimeType?: string;
}

export interface PromptInfo {
    name: string;
    description?: string;
    arguments?: Array<{
        name: string;
        description?: string;
        required?: boolean;
    }>;
}

export interface Capabilities {
    tools: Map<string, ToolInfo>;
    resources: Map<string, ResourceInfo>;
    prompts: Map<string, PromptInfo>;
}

export interface Action {
    actionType: 'tool' | 'resource' | 'prompt';
    actionName: string;
    arguments?: Record<string, unknown>;
}

export interface ExecutionContext {
    /** JWT token for identity */
    jwt?: string;
    /** Identity ID extracted from JWT */
    identityId?: string;
    /** Scopes from JWT */
    scopes?: string[];
    /** Mission ID for audit trail */
    missionId?: string;
}

export interface AuditEntry {
    timestamp: Date;
    missionId?: string;
    identityId?: string;
    tool: string;
    args: Record<string, unknown>;
    result?: unknown;
    error?: string;
    latencyMs: number;
}
