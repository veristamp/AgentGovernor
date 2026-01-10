/**
 * MCP Identity SDK - TypeScript
 *
 * A lightweight SDK for MCP agents and resource servers to interact with
 * the Mono Authz identity fabric.
 *
 * Two authentication patterns in one package:
 *
 * | SDK | Use Case | Grant Type |
 * |-----|----------|------------|
 * | **MCPAgentClient** | AI agents, backend services | `client_credentials` |
 * | **MCPResourceServer** | Token validation | JWT or introspection |
 *
 * @example Agent Registration & Token Acquisition
 * ```typescript
 * import { MCPAgentClient } from './auth';
 *
 * const agent = new MCPAgentClient({
 *   authServer: 'https://auth.example.com',
 *   regJwt: 'eyJ...',  // Registration invite token
 * });
 *
 * // Register once (save credentials!)
 * const creds = await agent.register('my-rag-agent');
 * console.log(creds.clientId, creds.clientSecret);
 *
 * // Get opaque token (no audience)
 * const token = await agent.getToken(['read:data']);
 *
 * // Get JWT token with audience (RFC 8707)
 * const jwtToken = await agent.getToken(['read:data'], 'mcp://rag-service');
 * ```
 *
 * @example Resource Server Token Validation
 * ```typescript
 * import { MCPResourceServer } from './auth';
 *
 * const server = new MCPResourceServer({
 *   authServer: 'https://auth.example.com',
 *   myAudience: 'mcp://rag-service',
 * });
 *
 * // Fast path: JWT validation (stateless, ~0.1ms)
 * const result = await server.validateToken(token, {
 *   requiredScopes: ['read:data'],
 *   useJwt: true,
 * });
 *
 * // With kill switch check (adds ~35ms for active check)
 * const resultWithCheck = await server.validateToken(token, {
 *   requiredScopes: ['admin:delete'],
 *   requireActiveCheck: true,
 * });
 *
 * if (result.valid) {
 *   console.log(`Client: ${result.clientId}, Scopes: ${result.scopes}`);
 * }
 * ```
 *
 * @module
 */

// Types
export type {
    MCPCredentials,
    MCPToken,
    ValidationResult,
    ClientStatus,
    JWTClaims,
    MCPAgentClientConfig,
    MCPResourceServerConfig,
    MCPAdminClientConfig,
    TokenResponse,
    RegistrationResponse,
    IntrospectionResponse,
    ClientStatusResponse,
} from './types';

export {
    DEFAULT_TOKEN_TTL,
    CLIENT_CACHE_TTL,
    JWKS_CACHE_TTL,
    isTokenExpired,
    isClientStatusStale,
} from './types';

// Errors
export {
    MCPError,
    MCPRegistrationError,
    MCPAuthError,
    MCPValidationError,
    MCPRateLimitError,
} from './errors';

// JWT utilities
export {
    decodeJWT,
    isJWT,
    decodeJWTHeader,
    isJWTExpired,
    checkJWTAudience,
    extractClientId,
    extractScopes,
} from './jwt';

// Clients
export { MCPAgentClient } from './agent-client';
export { MCPResourceServer, type ValidateTokenOptions } from './resource-server';
export { MCPAdminClient, type CreateInviteParams, type InviteResult } from './admin-client';

// Helpers
export {
    registerAgent,
    getAccessToken,
    validateToken,
    extractBearerToken,
} from './helpers';
