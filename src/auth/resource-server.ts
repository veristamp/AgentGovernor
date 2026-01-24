/**
 * MCP Identity SDK - Resource Server
 *
 * Helper for MCP resource servers to validate incoming tokens.
 *
 * Supports two validation modes:
 * - JWT validation (stateless, ~0.1ms, no auth server call)
 * - Introspection validation (~35ms, calls auth server)
 *
 * @example
 * ```typescript
 * const server = new MCPResourceServer({
 *   authServer: 'https://auth.example.com',
 *   myAudience: 'mcp://rag-service',
 * });
 *
 * const result = await server.validateToken(token, {
 *   requiredScopes: ['read:data'],
 *   useJwt: true,
 * });
 *
 * if (result.valid) {
 *   console.log(`Client: ${result.clientId}`);
 * }
 * ```
 */

import type {
    MCPResourceServerConfig,
    ValidationResult,
    ClientStatus,
    IntrospectionResponse,
    ClientStatusResponse,
} from './types';
import { CLIENT_CACHE_TTL, isClientStatusStale } from './types';
import {
    decodeJWT,
    isJWT,
    isJWTExpired,
    checkJWTAudience,
    extractClientId,
    extractScopes,
} from './jwt';
import { JWKSManager, verifyJWT } from './jwks';

export interface ValidateTokenOptions {
    requiredScopes?: string[];
    useJwt?: boolean;
    requireActiveCheck?: boolean;
    /** If true, verify JWT signature using JWKS (adds ~1-2ms first call, then cached) */
    verifySignature?: boolean;
}

function normalizeRoles(roles?: string[] | string | null): string[] {
    if (!roles) {
        return [];
    }
    if (Array.isArray(roles)) {
        return roles.filter(Boolean);
    }
    if (typeof roles === 'string') {
        return roles.split(' ').filter(Boolean);
    }
    return [];
}

export class MCPResourceServer {
    private authServer: string;
    private myAudience: string;
    private clientId?: string;
    private clientSecret?: string;
    private adminApiKey?: string;
    private adminSessionCookie?: string;
    private cacheTtl: number;
    private clientCache: Map<string, ClientStatus> = new Map();
    private jwksManager: JWKSManager;

    constructor(config: MCPResourceServerConfig) {
        this.authServer = config.authServer.replace(/\/$/, '');
        this.myAudience = config.myAudience;
        this.clientId = config.clientId;
        this.clientSecret = config.clientSecret;
        this.adminApiKey = config.adminApiKey;
        this.adminSessionCookie = config.adminSessionCookie;
        this.cacheTtl = config.cacheTtl ?? CLIENT_CACHE_TTL;
        this.jwksManager = new JWKSManager(this.authServer);
    }

    /**
     * Validate an incoming access token.
     *
     * @param token - The Bearer token from Authorization header
     * @param options - Validation options
     * @returns ValidationResult indicating if token is valid
     */
    async validateToken(
        token: string,
        options: ValidateTokenOptions = {}
    ): Promise<ValidationResult> {
        const { requiredScopes, useJwt = true, requireActiveCheck = false, verifySignature = false } = options;

        if (!token) {
            return {
                valid: false,
                scopes: [],
                error: 'Missing token',
                errorCode: 'missing_token',
            };
        }

        try {
            const isJwtToken = isJWT(token);

            if (useJwt && isJwtToken) {
                // Fast path: JWT validation locally
                return await this.validateJwtToken(token, requiredScopes, requireActiveCheck, verifySignature);
            } else {
                // Slow path: Introspection
                return await this.validateViaIntrospect(token, requiredScopes);
            }
        } catch (e) {
            return {
                valid: false,
                scopes: [],
                error: e instanceof Error ? e.message : String(e),
                errorCode: 'validation_error',
            };
        }
    }

    /**
     * Validate a JWT access token locally.
     * This is the fast path - no HTTP calls unless requireActiveCheck=true.
     */
    private async validateJwtToken(
        token: string,
        requiredScopes?: string[],
        requireActiveCheck: boolean = false,
        verifySignature: boolean = false
    ): Promise<ValidationResult> {
        let claims;

        // Optionally verify signature using JWKS
        if (verifySignature) {
            const verifyResult = await verifyJWT(token, this.jwksManager);
            if (!verifyResult.verified) {
                return {
                    valid: false,
                    scopes: [],
                    error: verifyResult.error,
                    errorCode: 'invalid_signature',
                };
            }
            claims = verifyResult.claims;
        } else {
            // Just decode without verification (for trusted internal use)
            claims = decodeJWT(token);
            if (!claims) {
                return {
                    valid: false,
                    scopes: [],
                    error: 'Invalid JWT format',
                    errorCode: 'invalid_token',
                };
            }
        }

        // Check expiration
        if (isJWTExpired(claims)) {
            return {
                valid: false,
                scopes: [],
                error: 'Token has expired',
                errorCode: 'token_expired',
            };
        }

        // Check audience
        if (!checkJWTAudience(claims, this.myAudience)) {
            return {
                valid: false,
                scopes: [],
                error: `Token audience '${claims.aud}' does not match '${this.myAudience}'`,
                errorCode: 'audience_mismatch',
            };
        }

        const clientId = extractClientId(claims);
        const tokenScopes = extractScopes(claims);
        const roles = normalizeRoles(claims.roles as string[] | string | null | undefined);
        const clientType = typeof claims.client_type === 'string' ? claims.client_type : undefined;
        const riskLevel = typeof claims.risk_level === 'string' ? claims.risk_level : undefined;

        // Check required scopes
        if (requiredScopes && requiredScopes.length > 0) {
            const missing = requiredScopes.filter((s) => !tokenScopes.includes(s));
            if (missing.length > 0) {
                return {
                    valid: false,
                    clientId,
                    scopes: tokenScopes,
                    error: `Missing required scopes: ${missing.join(', ')}`,
                    errorCode: 'insufficient_scope',
                };
            }
        }

        // Optional: Check client is still active (kill switch)
        if (requireActiveCheck && clientId) {
            const clientStatus = await this.getClientStatus(clientId);
            if (clientStatus && clientStatus.status !== 'active') {
                return {
                    valid: false,
                    clientId,
                    scopes: tokenScopes,
                    error: `Client is ${clientStatus.status}`,
                    errorCode: `client_${clientStatus.status}`,
                };
            }
        }

        // JWT is valid
        return {
            valid: true,
            clientId,
            orgId: claims.org_id as string | undefined,
            scopes: tokenScopes,
            roles,
            clientType,
            riskLevel,
        };
    }

    /**
     * Validate token via auth server introspection.
     * This is the slow path - requires HTTP call to auth server.
     */
    private async validateViaIntrospect(
        token: string,
        requiredScopes?: string[]
    ): Promise<ValidationResult> {
        // Step 1: Call introspect endpoint
        const introspectResult = await this.introspectToken(token);

        if (!introspectResult.active) {
            return {
                valid: false,
                scopes: [],
                error: 'Token is inactive or expired',
                errorCode: 'token_inactive',
            };
        }

        const clientId = introspectResult.client_id;
        if (!clientId) {
            return {
                valid: false,
                scopes: [],
                error: 'Token has no client_id',
                errorCode: 'no_client_id',
            };
        }

        // Step 2: Get client status (cached)
        const clientStatus = await this.getClientStatus(clientId);
        if (!clientStatus) {
            return {
                valid: false,
                clientId,
                scopes: [],
                error: 'Client not found',
                errorCode: 'client_not_found',
            };
        }

        // Step 3: Check kill switches
        if (clientStatus.status !== 'active') {
            return {
                valid: false,
                clientId,
                scopes: [],
                error: `Client is ${clientStatus.status}`,
                errorCode: `client_${clientStatus.status}`,
            };
        }

        // Step 4: Validate audience
        if (!clientStatus.allowedAudiences.includes(this.myAudience)) {
            return {
                valid: false,
                clientId,
                scopes: [],
                allowedAudiences: clientStatus.allowedAudiences,
                error: 'Token not valid for this audience',
                errorCode: 'audience_mismatch',
            };
        }

        // Step 5: Validate scopes
        const tokenScopes = (introspectResult.scope ?? '').split(' ').filter(Boolean);
        const roles = normalizeRoles(introspectResult.roles ?? clientStatus.allowedRoles ?? []);
        const clientType = introspectResult.client_type ?? clientStatus.clientType;
        const riskLevel = introspectResult.risk_level ?? clientStatus.riskLevel;
        if (requiredScopes && requiredScopes.length > 0) {
            const missing = requiredScopes.filter((s) => !tokenScopes.includes(s));
            if (missing.length > 0) {
                return {
                    valid: false,
                    clientId,
                    scopes: tokenScopes,
                    error: `Missing required scopes: ${missing.join(', ')}`,
                    errorCode: 'insufficient_scope',
                };
            }
        }

        // All checks passed
        return {
            valid: true,
            clientId,
            orgId: clientStatus.orgId,
            scopes: tokenScopes,
            allowedAudiences: clientStatus.allowedAudiences,
            roles,
            clientType,
            riskLevel,
        };
    }

    /**
     * Call the auth server's introspection endpoint.
     */
    private async introspectToken(token: string): Promise<IntrospectionResponse> {
        const formData = new URLSearchParams();
        formData.set('token', token);

        if (this.clientId && this.clientSecret) {
            formData.set('client_id', this.clientId);
            formData.set('client_secret', this.clientSecret);
        }

        const response = await fetch(`${this.authServer}/api/auth/oauth2/introspect`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': this.authServer,
            },
            body: formData,
        });

        if (response.status === 200) {
            return (await response.json()) as IntrospectionResponse;
        }

        return { active: false };
    }

    /**
     * Get client status, using cache if available.
     */
    private async getClientStatus(clientId: string): Promise<ClientStatus | null> {
        // Check cache
        const cached = this.clientCache.get(clientId);
        if (cached && !isClientStatusStale(cached, this.cacheTtl)) {
            return cached;
        }

        // Fetch from admin API
        const headers: Record<string, string> = {
            'Origin': this.authServer,
        };

        if (this.adminApiKey) {
            headers['x-api-key'] = this.adminApiKey;
        }
        if (this.adminSessionCookie) {
            headers['Cookie'] = this.adminSessionCookie;
        }

        try {
            const response = await fetch(
                `${this.authServer}/api/admin/mcp/clients/${clientId}`,
                { headers }
            );

            if (response.status === 200) {
                const data = (await response.json()) as ClientStatusResponse;

                const status: ClientStatus = {
                    clientId,
                    status: data.status as 'active' | 'disabled' | 'revoked',
                    allowedScopes: data.allowedScopes ?? [],
                    allowedAudiences: data.allowedAudiences ?? [],
                    allowedRoles: data.allowedRoles ?? [],
                    orgId: data.orgId,
                    clientType: data.clientType,
                    riskLevel: data.riskLevel,
                    fetchedAt: Date.now() / 1000,
                };

                this.clientCache.set(clientId, status);
                return status;
            }
        } catch {
            // Ignore errors, return null
        }

        return null;
    }

    /**
     * Clear the client status cache.
     */
    clearCache(): void {
        this.clientCache.clear();
        this.jwksManager.clearCache();
    }
}
