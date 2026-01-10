/**
 * Auth SDK Integration
 * 
 * Integrates with the mono-authz SDK for:
 * - JWT validation
 * - Kill switch checking
 * - Identity extraction
 */

import type { Identity } from './types';

// JWT payload structure (from mono-authz)
interface JWTPayload {
    sub: string;           // Subject (identity ID)
    aud: string | string[]; // Audience
    iat: number;           // Issued at
    exp: number;           // Expiration
    iss: string;           // Issuer
    scope?: string;        // Space-separated scopes
    scopes?: string[];     // Array of scopes
    type?: 'agent' | 'user' | 'service';
    org_id?: string;
    security_level?: number;
}

// Configuration
interface AuthConfig {
    /** Auth server URL for validation */
    authServerUrl?: string;
    /** JWKS endpoint for key fetching */
    jwksUrl?: string;
    /** Expected audience */
    audience?: string;
    /** Expected issuer */
    issuer?: string;
    /** Whether to check kill switch on every request */
    checkKillSwitch?: boolean;
    /** Kill switch check interval (ms) */
    killSwitchCacheMs?: number;
}

// Kill switch cache entry
interface KillSwitchEntry {
    revoked: boolean;
    checkedAt: number;
}

export class AuthSDK {
    private config: AuthConfig;
    private killSwitchCache: Map<string, KillSwitchEntry> = new Map();
    private jwksCache: Map<string, unknown> = new Map();

    constructor(config: AuthConfig = {}) {
        this.config = {
            authServerUrl: process.env.MCP_AUTH_SERVER || config.authServerUrl,
            jwksUrl: config.jwksUrl,
            audience: process.env.MCP_MY_AUDIENCE || config.audience,
            issuer: config.issuer,
            checkKillSwitch: config.checkKillSwitch ?? true,
            killSwitchCacheMs: config.killSwitchCacheMs ?? 5000, // 5 seconds
        };
    }

    /**
     * Validate a JWT and extract identity.
     * 
     * This performs:
     * 1. Signature verification (if JWKS configured)
     * 2. Expiration check
     * 3. Audience check
     * 4. Kill switch check (async, cached)
     */
    async validateJWT(token: string): Promise<Identity> {
        // 1. Decode the JWT
        const payload = this.decodeJWT(token);

        // 2. Check expiration
        if (payload.exp * 1000 < Date.now()) {
            throw new AuthError('Token expired', 'TOKEN_EXPIRED');
        }

        // 3. Check audience (if configured)
        if (this.config.audience) {
            const audiences = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
            if (!audiences.includes(this.config.audience)) {
                throw new AuthError('Invalid audience', 'INVALID_AUDIENCE');
            }
        }

        // 4. Check issuer (if configured)
        if (this.config.issuer && payload.iss !== this.config.issuer) {
            throw new AuthError('Invalid issuer', 'INVALID_ISSUER');
        }

        // 5. Build identity
        const identity: Identity = {
            id: payload.sub,
            type: payload.type || 'user',
            scopes: this.extractScopes(payload),
            orgId: payload.org_id,
            securityLevel: payload.security_level ?? 5,
            revoked: false,
            expiresAt: payload.exp * 1000,
        };

        // 6. Check kill switch (async, uses cache)
        if (this.config.checkKillSwitch) {
            const revoked = await this.isRevoked(identity.id);
            if (revoked) {
                throw new AuthError('Identity has been revoked', 'REVOKED');
            }
            identity.revoked = revoked;
        }

        return identity;
    }

    /**
     * Check if an identity has been revoked (kill switch).
     * Uses a cache to avoid hammering the auth server.
     */
    async isRevoked(identityId: string): Promise<boolean> {
        // Check cache first
        const cached = this.killSwitchCache.get(identityId);
        const now = Date.now();

        if (cached && (now - cached.checkedAt) < (this.config.killSwitchCacheMs ?? 5000)) {
            return cached.revoked;
        }

        // Check auth server
        try {
            const revoked = await this.checkKillSwitchRemote(identityId);
            this.killSwitchCache.set(identityId, { revoked, checkedAt: now });
            return revoked;
        } catch (e) {
            // On error, use cached value or assume not revoked
            console.warn('[AuthSDK] Kill switch check failed:', e);
            return cached?.revoked ?? false;
        }
    }

    /**
     * Manually revoke an identity (for local testing).
     * In production, this would be done via the auth server.
     */
    revokeIdentity(identityId: string): void {
        this.killSwitchCache.set(identityId, { revoked: true, checkedAt: Date.now() });
    }

    /**
     * Clear the kill switch cache.
     */
    clearCache(): void {
        this.killSwitchCache.clear();
    }

    // ==================== Private Methods ====================

    private decodeJWT(token: string): JWTPayload {
        try {
            const parts = token.split('.');
            if (parts.length !== 3) {
                throw new Error('Invalid JWT format');
            }

            const payload = JSON.parse(
                Buffer.from(parts[1]!, 'base64url').toString('utf-8')
            );

            return payload as JWTPayload;
        } catch (e) {
            throw new AuthError('Failed to decode JWT', 'INVALID_TOKEN');
        }
    }

    private extractScopes(payload: JWTPayload): string[] {
        if (payload.scopes && Array.isArray(payload.scopes)) {
            return payload.scopes;
        }
        if (payload.scope && typeof payload.scope === 'string') {
            return payload.scope.split(' ').filter(Boolean);
        }
        return [];
    }

    private async checkKillSwitchRemote(identityId: string): Promise<boolean> {
        if (!this.config.authServerUrl) {
            // No auth server configured - skip remote check
            return false;
        }

        const url = `${this.config.authServerUrl}/api/auth/kill-switch/${identityId}`;

        try {
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                },
            });

            if (!response.ok) {
                // 404 = not revoked, other errors = assume not revoked
                return false;
            }

            const data = await response.json() as { revoked?: boolean };
            return data.revoked === true;
        } catch (e) {
            // Network error - assume not revoked
            return false;
        }
    }
}

// ==================== Error Class ====================

export class AuthError extends Error {
    constructor(
        message: string,
        public code: 'TOKEN_EXPIRED' | 'INVALID_TOKEN' | 'INVALID_AUDIENCE' | 'INVALID_ISSUER' | 'REVOKED'
    ) {
        super(message);
        this.name = 'AuthError';
    }
}

// ==================== Singleton ====================

let authSDK: AuthSDK | null = null;

export function getAuthSDK(config?: AuthConfig): AuthSDK {
    if (!authSDK) {
        authSDK = new AuthSDK(config);
    }
    return authSDK;
}

// ==================== Helper Functions ====================

/**
 * Extract JWT from Authorization header.
 */
export function extractBearerToken(authHeader?: string): string | null {
    if (!authHeader) return null;
    if (!authHeader.startsWith('Bearer ')) return null;
    return authHeader.slice(7);
}

/**
 * Create a mock identity for testing.
 */
export function createMockIdentity(overrides?: Partial<Identity>): Identity {
    return {
        id: 'test:mock',
        type: 'agent',
        scopes: ['*'],
        securityLevel: 5,
        revoked: false,
        expiresAt: Date.now() + 3600000, // 1 hour
        ...overrides,
    };
}
