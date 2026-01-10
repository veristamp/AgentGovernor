/**
 * MCP Identity SDK - Admin Client
 *
 * Client for MCP administrative tasks like minting invites,
 * managing clients, and checking status.
 *
 * Handles session management, CSRF tokens, and origin headers.
 *
 * @example
 * ```typescript
 * const admin = new MCPAdminClient({ authServer: 'https://auth.example.com' });
 *
 * // Login as admin
 * await admin.login('admin@example.com', 'password');
 *
 * // Create invite
 * const invite = await admin.createInvite({
 *   orgId: 'org_123',
 *   budget: 5,
 *   allowedScopes: ['read:data'],
 *   allowedAudiences: ['mcp://rag-service'],
 * });
 *
 * // Revoke a client
 * await admin.revokeClient('mcp_client_123');
 * ```
 */

import type { MCPAdminClientConfig } from './types';
import { MCPAuthError } from './errors';

export interface CreateInviteParams {
    orgId: string;
    budget?: number;
    ttlSeconds?: number;
    allowedScopes?: string[];
    allowedAudiences?: string[];
}

export interface InviteResult {
    token: string;
    inviteId: string;
    expiresAt: string;
}

export class MCPAdminClient {
    private authServer: string;
    private timeout: number;
    private csrfToken?: string;
    private cookies: Map<string, string> = new Map();

    constructor(config: MCPAdminClientConfig) {
        this.authServer = config.authServer.replace(/\/$/, '');
        this.timeout = config.timeout ?? 30000;
    }

    /**
     * Update cookies from response headers.
     */
    private updateCookies(response: Response): void {
        const setCookie = response.headers.get('set-cookie');
        if (setCookie) {
            // Parse Set-Cookie header (simplified)
            const cookies = setCookie.split(',').map((c) => c.trim());
            for (const cookie of cookies) {
                const [nameValue] = cookie.split(';');
                if (nameValue) {
                    const [name, value] = nameValue.split('=');
                    if (name && value) {
                        this.cookies.set(name.trim(), value.trim());
                    }
                }
            }
        }
    }

    /**
     * Get cookies as header string.
     */
    private getCookieHeader(): string {
        return Array.from(this.cookies.entries())
            .map(([k, v]) => `${k}=${v}`)
            .join('; ');
    }

    /**
     * Fetch a fresh CSRF token from the server.
     */
    async getCsrfToken(): Promise<string> {
        const response = await fetch(`${this.authServer}/api/csrf-token`, {
            headers: {
                'Origin': this.authServer,
                'Cookie': this.getCookieHeader(),
            },
            signal: AbortSignal.timeout(this.timeout),
        });

        this.updateCookies(response);

        const data = (await response.json()) as { csrfToken?: string };
        this.csrfToken = data.csrfToken;

        // Also check cookies if not in body
        if (!this.csrfToken) {
            this.csrfToken =
                this.cookies.get('csrf_token') ?? this.cookies.get('better-auth.csrf-token');
        }

        return this.csrfToken ?? '';
    }

    /**
     * Sign in as an administrator.
     *
     * @param email - Admin email
     * @param password - Admin password
     * @returns True if login successful
     */
    async login(email: string, password: string): Promise<boolean> {
        await this.getCsrfToken();

        const response = await fetch(`${this.authServer}/api/auth/sign-in/email`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': this.csrfToken ?? '',
                'Origin': this.authServer,
                'Cookie': this.getCookieHeader(),
            },
            body: JSON.stringify({ email, password }),
            signal: AbortSignal.timeout(this.timeout),
        });

        if (response.status === 200) {
            this.updateCookies(response);
            return true;
        }

        return false;
    }

    /**
     * Make an authenticated request to the admin API.
     */
    async request<T = unknown>(
        method: string,
        path: string,
        body?: unknown
    ): Promise<{ status: number; data: T }> {
        const url = path.startsWith('http') ? path : `${this.authServer}${path}`;

        const headers: Record<string, string> = {
            'Origin': this.authServer,
            'Cookie': this.getCookieHeader(),
        };

        // Add CSRF token for mutation methods
        if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method.toUpperCase())) {
            if (!this.csrfToken) {
                await this.getCsrfToken();
            }
            headers['X-CSRF-Token'] = this.csrfToken ?? '';
        }

        if (body) {
            headers['Content-Type'] = 'application/json';
        }

        const response = await fetch(url, {
            method,
            headers,
            body: body ? JSON.stringify(body) : undefined,
            signal: AbortSignal.timeout(this.timeout),
        });

        this.updateCookies(response);

        const data = await response.json().catch(() => ({}));
        return { status: response.status, data: data as T };
    }

    /**
     * Create a registration invite for agents.
     */
    async createInvite(params: CreateInviteParams): Promise<InviteResult> {
        const { status, data } = await this.request<{ data?: InviteResult; token?: string }>(
            'POST',
            '/api/admin/mcp/invites',
            {
                orgId: params.orgId,
                budget: params.budget ?? 1,
                ttlSeconds: params.ttlSeconds ?? 600,
                allowedScopes: params.allowedScopes ?? [],
                allowedAudiences: params.allowedAudiences ?? [],
            }
        );

        if (status !== 200 && status !== 201) {
            throw new MCPAuthError(`Failed to create invite: ${status}`);
        }

        // Handle both response formats
        const result = (data.data ?? data) as InviteResult;
        return result;
    }

    /**
     * Get a client by ID.
     */
    async getClient(clientId: string): Promise<Record<string, unknown> | null> {
        const { status, data } = await this.request<Record<string, unknown>>(
            'GET',
            `/api/admin/mcp/clients/${clientId}`
        );

        if (status === 200) {
            return data;
        }

        return null;
    }

    /**
     * Disable a client (temporary suspension).
     */
    async disableClient(clientId: string): Promise<boolean> {
        const { status } = await this.request(
            'POST',
            `/api/admin/mcp/clients/${clientId}/disable`
        );
        return status === 200 || status === 204;
    }

    /**
     * Enable a previously disabled client.
     */
    async enableClient(clientId: string): Promise<boolean> {
        const { status } = await this.request(
            'POST',
            `/api/admin/mcp/clients/${clientId}/enable`
        );
        return status === 200 || status === 204;
    }

    /**
     * Revoke a client (permanent termination).
     */
    async revokeClient(clientId: string): Promise<boolean> {
        const { status } = await this.request(
            'POST',
            `/api/admin/mcp/clients/${clientId}/revoke`
        );
        return status === 200 || status === 204;
    }

    /**
     * Get the session cookie string for use with other clients.
     */
    getSessionCookieString(): string {
        return this.getCookieHeader();
    }
}
