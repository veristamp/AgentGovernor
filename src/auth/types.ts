/**
 * MCP Identity SDK - Types
 *
 * TypeScript type definitions for the MCP Machine Identity fabric.
 */

// =============================================================================
// Configuration
// =============================================================================

export const DEFAULT_TOKEN_TTL = 600; // 10 minutes
export const CLIENT_CACHE_TTL = 60; // Cache client status for 60 seconds
export const JWKS_CACHE_TTL = 3600; // Cache JWKS for 1 hour

// =============================================================================
// Credentials & Tokens
// =============================================================================

/**
 * Credentials returned after successful agent registration.
 */
export interface MCPCredentials {
    clientId: string;
    clientSecret: string;
    allowedScopes: string[];
    allowedAudiences: string[];
    orgId?: string;
}

/**
 * Access token with metadata.
 */
export interface MCPToken {
    accessToken: string;
    tokenType: string;
    expiresIn: number;
    scope: string;
    expiresAt: number;
}

/**
 * Check if token is expired (with 30s buffer).
 */
export function isTokenExpired(token: MCPToken): boolean {
    return Date.now() / 1000 >= token.expiresAt - 30;
}

// =============================================================================
// Validation
// =============================================================================

/**
 * Result of token validation.
 */
export interface ValidationResult {
    valid: boolean;
    clientId?: string;
    orgId?: string;
    scopes: string[];
    allowedAudiences?: string[];
    error?: string;
    errorCode?: string;
}

/**
 * Error codes returned by validation.
 */
export type ValidationErrorCode =
    | 'missing_token'
    | 'invalid_token'
    | 'token_expired'
    | 'audience_mismatch'
    | 'insufficient_scope'
    | 'client_revoked'
    | 'client_disabled'
    | 'token_inactive'
    | 'client_not_found'
    | 'no_client_id'
    | 'jwt_validation_error'
    | 'validation_error';

/**
 * Cached client status for kill switch enforcement.
 */
export interface ClientStatus {
    clientId: string;
    status: 'active' | 'disabled' | 'revoked';
    allowedScopes: string[];
    allowedAudiences: string[];
    orgId?: string;
    fetchedAt: number;
}

/**
 * Check if client status cache is stale.
 */
export function isClientStatusStale(status: ClientStatus, ttl: number = CLIENT_CACHE_TTL): boolean {
    return Date.now() / 1000 - status.fetchedAt > ttl;
}

// =============================================================================
// JWT Claims
// =============================================================================

/**
 * JWT payload claims.
 */
export interface JWTClaims {
    iss?: string; // Issuer
    sub?: string; // Subject
    aud?: string | string[]; // Audience
    exp?: number; // Expiration
    iat?: number; // Issued at
    azp?: string; // Authorized party (client_id)
    client_id?: string; // Alternative client_id
    scope?: string; // Space-separated scopes
    org_id?: string; // Organization ID
    [key: string]: unknown;
}

// =============================================================================
// Configuration Options
// =============================================================================

/**
 * Configuration for MCPAgentClient.
 */
export interface MCPAgentClientConfig {
    authServer: string;
    regJwt?: string;
    clientId?: string;
    clientSecret?: string;
    timeout?: number;
}

/**
 * Configuration for MCPResourceServer.
 */
export interface MCPResourceServerConfig {
    authServer: string;
    myAudience: string;
    clientId?: string;
    clientSecret?: string;
    adminApiKey?: string;
    adminSessionCookie?: string;
    cacheTtl?: number;
}

/**
 * Configuration for MCPAdminClient.
 */
export interface MCPAdminClientConfig {
    authServer: string;
    timeout?: number;
}

// =============================================================================
// API Responses
// =============================================================================

/**
 * Token endpoint response.
 */
export interface TokenResponse {
    access_token: string;
    token_type?: string;
    expires_in?: number;
    scope?: string;
    refresh_token?: string;
}

/**
 * Registration endpoint response.
 */
export interface RegistrationResponse {
    client_id: string;
    client_secret: string;
    allowed_scopes?: string[];
    allowed_audiences?: string[];
    org_id?: string;
}

/**
 * Introspection endpoint response.
 */
export interface IntrospectionResponse {
    active: boolean;
    client_id?: string;
    scope?: string;
    [key: string]: unknown;
}

/**
 * Client status response from admin API.
 */
export interface ClientStatusResponse {
    status: string;
    allowedScopes?: string[];
    allowedAudiences?: string[];
    orgId?: string;
}
