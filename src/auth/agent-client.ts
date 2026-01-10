/**
 * MCP Identity SDK - Agent Client
 *
 * Client for MCP agents to register and obtain tokens.
 *
 * @example
 * ```typescript
 * const agent = new MCPAgentClient({
 *   authServer: 'https://auth.example.com',
 *   regJwt: 'eyJ...',
 * });
 *
 * // Register once
 * const creds = await agent.register('my-agent');
 *
 * // Get tokens as needed
 * const token = await agent.getToken(['read:data']);
 * ```
 */

import type {
    MCPAgentClientConfig,
    MCPCredentials,
    MCPToken,
    TokenResponse,
    RegistrationResponse,
} from './types';
import { MCPRegistrationError, MCPAuthError, MCPRateLimitError } from './errors';
import { isTokenExpired } from './types';

export class MCPAgentClient {
    private authServer: string;
    private regJwt?: string;
    private clientId?: string;
    private clientSecret?: string;
    private timeout: number;
    private currentToken?: MCPToken;
    private credentials?: MCPCredentials;

    constructor(config: MCPAgentClientConfig) {
        this.authServer = config.authServer.replace(/\/$/, '');
        this.regJwt = config.regJwt;
        this.clientId = config.clientId;
        this.clientSecret = config.clientSecret;
        this.timeout = config.timeout ?? 30000;
    }

    /**
     * Register a new MCP machine client.
     *
     * @param clientName - Human-readable name for this agent
     * @param metadata - Optional metadata to attach
     * @returns MCPCredentials with clientId and clientSecret
     */
    async register(
        clientName: string,
        metadata?: Record<string, unknown>
    ): Promise<MCPCredentials> {
        if (!this.regJwt) {
            throw new MCPRegistrationError('Registration requires a REG_JWT invite token');
        }

        const body: Record<string, unknown> = { client_name: clientName };
        if (metadata) {
            body.metadata = metadata;
        }

        const response = await fetch(`${this.authServer}/api/mcp/register`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.regJwt}`,
                'Content-Type': 'application/json',
                'Origin': this.authServer,
            },
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(this.timeout),
        });

        if (response.status === 201) {
            const data = (await response.json()) as RegistrationResponse;

            this.credentials = {
                clientId: data.client_id,
                clientSecret: data.client_secret,
                allowedScopes: data.allowed_scopes ?? [],
                allowedAudiences: data.allowed_audiences ?? [],
                orgId: data.org_id,
            };

            this.clientId = this.credentials.clientId;
            this.clientSecret = this.credentials.clientSecret;

            return this.credentials;
        }

        const errorData = await response.json().catch(() => ({})) as Record<string, string>;
        throw new MCPRegistrationError(
            errorData.error_description ?? `Registration failed: ${response.status}`,
            errorData.error
        );
    }

    /**
     * Get an access token, refreshing if necessary.
     *
     * When an audience is specified, the auth server issues a JWT access token
     * with the 'aud' claim set, enabling stateless validation via JWKS.
     * Without audience, an opaque token is issued (requires introspection).
     *
     * @param scopes - Scopes to request (must be within allowed set)
     * @param audience - Target audience/resource (RFC 8707). If provided, a JWT is issued.
     * @param forceRefresh - Force a new token even if current is valid
     * @returns MCPToken (JWT if audience specified, opaque otherwise)
     */
    async getToken(
        scopes?: string[],
        audience?: string,
        forceRefresh: boolean = false
    ): Promise<MCPToken> {
        if (!this.clientId || !this.clientSecret) {
            throw new MCPAuthError('Client credentials not set. Call register() first.');
        }

        // Return cached token if still valid
        if (!forceRefresh && this.currentToken && !isTokenExpired(this.currentToken)) {
            return this.currentToken;
        }

        // Build form data
        const formData = new URLSearchParams();
        formData.set('grant_type', 'client_credentials');
        formData.set('client_id', this.clientId);
        formData.set('client_secret', this.clientSecret);

        if (scopes && scopes.length > 0) {
            formData.set('scope', scopes.join(' '));
        }

        // RFC 8707: Pass audience as 'resource' parameter to get JWT with aud claim
        if (audience) {
            formData.set('resource', audience);
        }

        const response = await fetch(`${this.authServer}/api/auth/oauth2/token`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': this.authServer,
            },
            body: formData,
            signal: AbortSignal.timeout(this.timeout),
        });

        if (response.status === 200) {
            const data = (await response.json()) as TokenResponse;

            this.currentToken = {
                accessToken: data.access_token,
                tokenType: data.token_type ?? 'Bearer',
                expiresIn: data.expires_in ?? 3600,
                scope: data.scope ?? '',
                expiresAt: Date.now() / 1000 + (data.expires_in ?? 3600),
            };

            return this.currentToken;
        }

        const errorData = await response.json().catch(() => ({})) as Record<string, unknown>;

        // Handle rate limiting (429 Too Many Requests)
        if (response.status === 429) {
            const retryAfter = (errorData.retryAfter as number) ?? 60;
            throw new MCPRateLimitError(
                (errorData.error_description as string) ?? 'Rate limit exceeded',
                retryAfter
            );
        }

        throw new MCPAuthError(
            (errorData.error_description as string) ?? `Token request failed: ${response.status}`,
            errorData.error as string
        );
    }

    /**
     * Get the current credentials (after registration).
     */
    getCredentials(): MCPCredentials | undefined {
        return this.credentials;
    }

    /**
     * Get client ID (if set or after registration).
     */
    getClientId(): string | undefined {
        return this.clientId;
    }
}
