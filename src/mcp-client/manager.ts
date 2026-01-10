/**
 * MCP Client Manager
 * 
 * The heart of Governed Code Mode - manages connections to MCP servers,
 * indexes capabilities, and routes actions through the policy gate.
 * 
 * This is GATE 2 of the double-gated security architecture.
 */

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { spawn } from 'child_process';

import { CapabilityIndex } from './indices';
import { loadConfig, defaultServerPrefix } from './config';
import type { Config, ServerConfig, Action, ExecutionContext, AuditEntry, ToolInfo, ResourceInfo, PromptInfo } from './types';

// Policy imports
import { PolicyEngine, DEFAULT_RULES, AuthSDK, getAuthSDK, type Identity, type PolicyDecision } from '../policy';
import { getAuditLogger, type AuditLogger } from '../audit';

export interface MCPClientManagerOptions {
    configPath?: string;
    enablePolicy?: boolean;
    enableAuth?: boolean;
    policyRules?: typeof DEFAULT_RULES;
}

export class MCPClientManager {
    private config: Config;
    private index: CapabilityIndex;
    private clients: Map<string, Client> = new Map();
    private ready: boolean = false;

    // Policy & Auth
    private policyEngine: PolicyEngine | null = null;
    private authSDK: AuthSDK | null = null;
    private auditLogger: AuditLogger;
    private enablePolicy: boolean;
    private enableAuth: boolean;

    constructor(options: MCPClientManagerOptions | string = {}) {
        // Handle legacy string argument
        const opts = typeof options === 'string' ? { configPath: options } : options;

        this.config = loadConfig(opts.configPath);
        this.index = new CapabilityIndex();
        this.enablePolicy = opts.enablePolicy ?? false;
        this.enableAuth = opts.enableAuth ?? false;
        this.auditLogger = getAuditLogger();

        // Initialize policy engine if enabled
        if (this.enablePolicy) {
            this.policyEngine = new PolicyEngine(opts.policyRules ?? DEFAULT_RULES);
        }

        // Initialize auth SDK if enabled
        if (this.enableAuth) {
            this.authSDK = getAuthSDK();
        }
    }

    // ============== Lifecycle ==============

    async initialize(): Promise<void> {
        console.log('[MCPClientManager] Initializing...');
        console.log(`[MCPClientManager] Policy: ${this.enablePolicy ? 'ENABLED' : 'disabled'}`);
        console.log(`[MCPClientManager] Auth: ${this.enableAuth ? 'ENABLED' : 'disabled'}`);

        const servers = Object.entries(this.config.mcpServers);
        if (servers.length === 0) {
            console.log('[MCPClientManager] No servers configured');
            this.ready = true;
            return;
        }

        const results = await Promise.allSettled(
            servers.map(([name, cfg]) => this.connectOne(name, cfg))
        );

        const connected = results.filter(r => r.status === 'fulfilled').length;
        console.log(`[MCPClientManager] Connected ${connected}/${servers.length} servers`);

        this.ready = true;
    }

    async close(): Promise<void> {
        console.log('[MCPClientManager] Closing connections...');
        for (const [name, client] of this.clients) {
            try {
                await client.close();
                console.log(`[MCPClientManager] Closed: ${name}`);
            } catch (e) {
                console.warn(`[MCPClientManager] Error closing ${name}:`, e);
            }
        }
        this.clients.clear();
        this.ready = false;
    }

    // ============== Connection ==============

    private async connectOne(serverKey: string, cfg: ServerConfig): Promise<void> {
        console.log(`[MCPClientManager] Connecting to ${serverKey}...`);

        try {
            let client: Client;

            if (cfg.type === 'stdio') {
                client = await this.connectStdio(serverKey, cfg);
            } else if (cfg.type === 'streamable_http' || cfg.type === 'sse') {
                console.warn(`[MCPClientManager] ${cfg.type} not yet implemented for ${serverKey}`);
                return;
            } else {
                throw new Error(`Unknown connection type: ${cfg.type}`);
            }

            // Get capabilities
            const toolsResult = await client.listTools();
            const tools: ToolInfo[] = toolsResult.tools.map(t => ({
                name: t.name,
                description: t.description,
                inputSchema: t.inputSchema as Record<string, unknown>,
            }));

            let resources: ResourceInfo[] = [];
            let prompts: PromptInfo[] = [];

            try {
                const resourcesResult = await client.listResources();
                resources = resourcesResult.resources.map(r => ({
                    uri: r.uri,
                    name: r.name,
                    description: r.description,
                    mimeType: r.mimeType,
                }));
            } catch (e: unknown) {
                if (!this.isMethodNotFound(e)) throw e;
                console.log(`[MCPClientManager] ${serverKey}: resources not supported`);
            }

            try {
                const promptsResult = await client.listPrompts();
                prompts = promptsResult.prompts.map(p => ({
                    name: p.name,
                    description: p.description,
                    arguments: p.arguments,
                }));
            } catch (e: unknown) {
                if (!this.isMethodNotFound(e)) throw e;
                console.log(`[MCPClientManager] ${serverKey}: prompts not supported`);
            }

            // Register with index
            const prefix = defaultServerPrefix(serverKey, null);
            this.index.registerClient(prefix, client, tools, resources, prompts);
            this.clients.set(serverKey, client);

            console.log(`[MCPClientManager] ${serverKey} ready: ${tools.length} tools, ${resources.length} resources, ${prompts.length} prompts`);

        } catch (e) {
            console.error(`[MCPClientManager] Failed to connect ${serverKey}:`, e);
            throw e;
        }
    }

    private async connectStdio(serverKey: string, cfg: ServerConfig): Promise<Client> {
        if (!cfg.command) {
            throw new Error(`stdio server ${serverKey} requires 'command'`);
        }

        const transport = new StdioClientTransport({
            command: cfg.command,
            args: cfg.args,
            env: cfg.env,
            cwd: cfg.cwd,
        });

        const client = new Client({
            name: 'mcp-client-manager',
            version: '1.0.0',
        });

        await client.connect(transport);
        return client;
    }

    private isMethodNotFound(err: unknown): boolean {
        if (err && typeof err === 'object') {
            const code = (err as { code?: number }).code;
            const message = (err as { message?: string }).message || String(err);
            if (code === -32601) return true;
            if (message.toLowerCase().includes('method not found')) return true;
        }
        return false;
    }

    // ============== Capabilities ==============

    getCapabilities() {
        return this.index.getCapabilities();
    }

    getToolNames(): string[] {
        return this.index.getToolNames();
    }

    hasTool(name: string): boolean {
        return this.index.hasTool(name);
    }

    // ============== Authentication ==============

    /**
     * Validate a JWT and extract identity.
     */
    async validateToken(token: string): Promise<Identity> {
        if (!this.authSDK) {
            throw new Error('Auth is not enabled');
        }
        return this.authSDK.validateJWT(token);
    }

    /**
     * Check if an identity has been revoked.
     */
    async isRevoked(identityId: string): Promise<boolean> {
        if (!this.authSDK) {
            return false;
        }
        return this.authSDK.isRevoked(identityId);
    }

    // ============== Policy ==============

    /**
     * Check if an action is allowed for an identity.
     */
    checkPolicy(identity: Identity, action: string, resource?: string): PolicyDecision {
        if (!this.policyEngine) {
            return { allowed: true, reason: 'Policy not enabled' };
        }
        return this.policyEngine.check({ identity, action, resource });
    }

    // ============== Execution (GATE 2) ==============

    async executeAction(action: Action, context?: ExecutionContext): Promise<unknown> {
        if (!this.ready) {
            throw new Error('MCPClientManager not initialized');
        }

        const startTime = Date.now();
        const { actionType, actionName, arguments: args = {} } = action;

        // ========== GATE 2: Policy Enforcement ==========

        // 1. Validate identity if JWT provided
        let identity: Identity | undefined;
        if (context?.jwt && this.authSDK) {
            try {
                identity = await this.authSDK.validateJWT(context.jwt);

                // Update context with identity info
                context.identityId = identity.id;
                context.scopes = identity.scopes;

            } catch (e) {
                this.logAudit({
                    timestamp: new Date(),
                    tool: actionName,
                    args: args as Record<string, unknown>,
                    error: `Auth failed: ${e}`,
                    latencyMs: Date.now() - startTime,
                });
                throw e;
            }
        }

        // 2. Check policy if enabled
        if (this.policyEngine && identity) {
            const decision = this.policyEngine.check({
                identity,
                action: actionName,
            });

            if (!decision.allowed) {
                this.logAudit({
                    timestamp: new Date(),
                    identityId: identity.id,
                    tool: actionName,
                    args: args as Record<string, unknown>,
                    error: `Policy denied: ${decision.reason}`,
                    latencyMs: Date.now() - startTime,
                });
                throw new Error(`Forbidden: ${decision.reason}`);
            }
        }

        // 3. Check kill switch
        if (identity && this.authSDK) {
            const revoked = await this.authSDK.isRevoked(identity.id);
            if (revoked) {
                this.logAudit({
                    timestamp: new Date(),
                    identityId: identity.id,
                    tool: actionName,
                    args: args as Record<string, unknown>,
                    error: 'Identity revoked (kill switch)',
                    latencyMs: Date.now() - startTime,
                });
                throw new Error('Identity has been revoked');
            }
        }

        // ========== Execute Action ==========

        // Resolve client
        const client = this.index.resolveClient(actionName);
        if (!client) {
            throw new Error(`No client found for: ${actionName}`);
        }

        const baseName = this.index.getBaseName(actionName);

        try {
            let result: unknown;

            if (actionType === 'tool') {
                const callResult = await client.callTool({ name: baseName, arguments: args });
                result = this.formatToolResult(callResult);

            } else if (actionType === 'resource') {
                const resourceResult = await client.readResource({ uri: baseName });
                result = resourceResult.contents;

            } else if (actionType === 'prompt') {
                const promptResult = await client.getPrompt({ name: baseName, arguments: args as Record<string, string> });
                result = promptResult.messages;

            } else {
                throw new Error(`Unknown action type: ${actionType}`);
            }

            // Audit log success
            this.logAudit({
                timestamp: new Date(),
                missionId: context?.missionId,
                identityId: context?.identityId,
                tool: actionName,
                args: args as Record<string, unknown>,
                result,
                latencyMs: Date.now() - startTime,
            });

            return result;

        } catch (e) {
            // Audit log error
            this.logAudit({
                timestamp: new Date(),
                missionId: context?.missionId,
                identityId: context?.identityId,
                tool: actionName,
                args: args as Record<string, unknown>,
                error: String(e),
                latencyMs: Date.now() - startTime,
            });

            throw e;
        }
    }

    private formatToolResult(result: unknown): unknown {
        if (result && typeof result === 'object' && 'content' in result) {
            const content = (result as { content: unknown[] }).content;
            if (Array.isArray(content)) {
                const texts = content
                    .filter((c: unknown) => c && typeof c === 'object' && 'text' in c)
                    .map((c: unknown) => (c as { text: string }).text);
                return texts.join('\n');
            }
        }
        return result;
    }

    // ============== Audit ==============

    private logAudit(entry: AuditEntry): void {
        this.auditLogger.log(entry);
    }

    getAuditLog(): AuditEntry[] {
        return this.auditLogger.getEntries();
    }

    clearAuditLog(): void {
        this.auditLogger.clear();
    }

    getAuditStats() {
        return this.auditLogger.getStats();
    }
}

// Export singleton factory
let instance: MCPClientManager | null = null;

export async function getMCPClientManager(options?: MCPClientManagerOptions | string): Promise<MCPClientManager> {
    if (!instance) {
        instance = new MCPClientManager(options ?? {});
        await instance.initialize();
    }
    return instance;
}

export async function closeMCPClientManager(): Promise<void> {
    if (instance) {
        await instance.close();
        instance = null;
    }
}
