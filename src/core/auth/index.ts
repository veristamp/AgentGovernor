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
 * Features:
 * - Budgeted Dynamic Client Registration (REG_JWT)
 * - Token acquisition with audience support (RFC 8707)
 * - Token introspection (RFC 7662)
 * - Protected Resource Metadata discovery (RFC 9728)
 * - Rate limit handling
 * - Public client (PKCE) support
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
 * const jwtToken = await agent.getToken(['read:data'], 'https://api.example.com');
 * ```
 *
 * @example Resource Server Token Validation
 * ```typescript
 * import { MCPResourceServer } from './auth';
 *
 * const server = new MCPResourceServer({
 *   authServer: 'https://auth.example.com',
 *   myAudience: 'https://api.example.com',
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

export {
	type CreateInviteParams,
	type InviteResult,
	MCPAdminClient,
} from "./admin-client";
// Clients
export { MCPAgentClient, type RegisterOptions } from "./agent-client";

// Errors
export {
	MCPAuthError,
	MCPConsentError,
	MCPError,
	MCPRateLimitError,
	MCPRegistrationError,
	MCPValidationError,
} from "./errors";
// Helpers
export {
	extractBearerToken,
	getAccessToken,
	registerAgent,
	validateToken,
} from "./helpers";

// JWKS and signature verification
export { JWKSManager, verifyJWT } from "./jwks";
// JWT utilities
export {
	checkJWTAudience,
	decodeJWT,
	decodeJWTHeader,
	extractClientId,
	extractScopes,
	isJWT,
	isJWTExpired,
} from "./jwt";
export {
	MCPResourceServer,
	type ValidateTokenOptions,
} from "./resource-server";
// Types
export type {
	ClientStatus,
	ClientStatusResponse,
	CredentialAccessResult,
	CredentialsListResponse,
	CredentialTokensResponse,
	// Key Cabinet types (per-agent consent)
	ExternalCredentialInfo,
	ExternalProviderConfig,
	GrantConsentRequest,
	GrantMCPServerConsentRequest,
	IntrospectionResponse,
	JWTClaims,
	// OAuth Token Propagation types
	LinkedProvider,
	LinkedProvidersResponse,
	MCPAdminClientConfig,
	MCPAgentClientConfig,
	MCPCredentials,
	MCPResourceServerConfig,
	MCPServerAuthStartResponse,
	MCPServerConsentGrantResponse,
	MCPServerDetail,
	MCPServerDiscoverResponse,
	MCPServerInfo,
	MCPServerListResponse,
	MCPServerShare,
	MCPServerSharePermission,
	MCPServerSharesResponse,
	MCPServerTokenErrorCode,
	MCPServerTokenForClientResponse,
	MCPServerTokenStatusResponse,
	MCPServerTransport,
	MCPServerVisibility,
	MCPToken,
	ProtectedResourceMetadata,
	ProviderLinkRequired,
	ProviderLinkUrlResponse,
	ProvidersListResponse,
	ProviderTokenRequest,
	ProviderTokenResponse,
	RateLimitInfo,
	RegisterMCPServerRequest,
	RegisterMCPServerResponse,
	RegistrationResponse,
	SaveApiKeyRequest,
	SaveMCPServerTokenRequest,
	ShareMCPServerRequest,
	ShareMCPServerResponse,
	TokenResponse,
	UpdateMCPServerRequest,
	UpdateMCPServerResponse,
	ValidationErrorCode,
	ValidationResult,
} from "./types";
export {
	CLIENT_CACHE_TTL,
	DEFAULT_TOKEN_TTL,
	isClientStatusStale,
	isTokenExpired,
	JWKS_CACHE_TTL,
} from "./types";
// Versioning
export {
	getSdkHeaders,
	SDK_LANGUAGE,
	SDK_LANGUAGE_HEADER,
	SDK_VERSION,
	SDK_VERSION_HEADER,
} from "./version";
