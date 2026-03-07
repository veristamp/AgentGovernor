/**
 * MCP Identity SDK - Types
 *
 * TypeScript type definitions for the MCP Machine Identity fabric.
 *
 * Updated to include:
 * - Token introspection response types (RFC 7662)
 * - Protected Resource Metadata types (RFC 9728)
 * - Rate limit error handling
 * - Allowed roles support
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
	allowedRoles?: string[];
	orgId?: string;
	isPublic?: boolean;
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
 * Error codes returned by validation.
 */
export type ValidationErrorCode =
	| "missing_token"
	| "invalid_token"
	| "invalid_signature"
	| "token_expired"
	| "audience_mismatch"
	| "insufficient_scope"
	| "client_revoked"
	| "client_disabled"
	| "token_inactive"
	| "client_not_found"
	| "no_client_id"
	| "jwt_validation_error"
	| "validation_error"
	| "rate_limit_exceeded";

/**
 * Result of token validation.
 */
export interface ValidationResult {
	valid: boolean;
	clientId?: string;
	orgId?: string;
	scopes: string[];
	allowedAudiences?: string[];
	roles?: string[];
	clientType?: string;
	riskLevel?: string;
	error?: string;
	errorCode?: ValidationErrorCode;
}

/**
 * Cached client status for kill switch enforcement.
 */
export interface ClientStatus {
	clientId: string;
	status: "active" | "disabled" | "revoked";
	allowedScopes: string[];
	allowedAudiences: string[];
	allowedRoles?: string[];
	orgId?: string;
	fetchedAt: number;
}

/**
 * Check if client status cache is stale.
 */
export function isClientStatusStale(
	status: ClientStatus,
	ttl: number = CLIENT_CACHE_TTL,
): boolean {
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
	jti?: string; // JWT ID
	azp?: string; // Authorized party (client_id)
	client_id?: string; // Alternative client_id
	scope?: string | string[]; // Space-separated scopes OR array of strings
	scp?: string[]; // Array of scopes (alternative format)
	org_id?: string; // Organization ID
	client_type?: string; // Client type (machine, user, etc.)
	risk_level?: string; // Risk level (normal, elevated, high_risk)
	roles?: string[]; // Assigned roles
	linked_providers?: string[]; // OAuth providers user has linked (for token propagation)
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
	client_secret: string | null;
	client_name?: string;
	redirect_uris?: string[];
	grant_types?: string[];
	token_endpoint_auth_method?: string;
	allowed_scopes?: string[];
	allowed_audiences?: string[];
	allowed_roles?: string[];
	organization_id?: string;
	org_id?: string;
	is_public?: boolean;
	require_pkce?: boolean;
}

/**
 * Introspection endpoint response (RFC 7662).
 */
export interface IntrospectionResponse {
	active: boolean;
	sub?: string;
	client_id?: string;
	scope?: string;
	aud?: string;
	iss?: string;
	exp?: number;
	iat?: number;
	jti?: string;
	token_type?: string;
	// MCP custom claims
	org_id?: string;
	client_type?: string;
	risk_level?: string;
	roles?: string[];
	[key: string]: unknown;
}

/**
 * Client status response from admin API.
 */
export interface ClientStatusResponse {
	status: string;
	allowedScopes?: string[];
	allowedAudiences?: string[];
	allowedRoles?: string[];
	orgId?: string;
	clientType?: string;
	riskLevel?: string;
}

/**
 * Protected Resource Metadata (RFC 9728).
 */
export interface ProtectedResourceMetadata {
	resource: string;
	authorization_servers: string[];
	jwks_uri?: string;
	scopes_supported?: string[];
	bearer_methods_supported?: string[];
	introspection_endpoint?: string;
	introspection_endpoint_auth_methods_supported?: string[];
	resource_documentation?: string;
	resource_name?: string;
	resource_signing_alg_values_supported?: string[];
}

/**
 * MCP server token and consent specific error codes.
 */
export type MCPServerTokenErrorCode =
	| "consent_required"
	| "consent_scope_mismatch"
	| "invalid_consent_scopes"
	| "token_expired";

/**
 * Response when reading MCP server token status for a server owner.
 */
export interface MCPServerTokenStatusResponse {
	hasToken: boolean;
	scopes: string[];
	expiresAt?: string;
	isExpired: boolean;
}

/**
 * Response when reading MCP server token material for an MCP client with consent.
 */
export interface MCPServerTokenForClientResponse {
	accessToken: string;
	expiresAt?: string;
	scopes: string[];
}

/**
 * Request payload for saving an MCP server token.
 */
export interface SaveMCPServerTokenRequest {
	accessToken: string;
	refreshToken?: string;
	tokenType?: "oauth2" | "api_key" | "bearer";
	scopes?: string[];
	expiresInSeconds?: number;
}

/**
 * Request payload for granting MCP server consent.
 */
export interface GrantMCPServerConsentRequest {
	mcpClientId: string;
	scopes?: string[];
	expiresInDays?: number;
}

/**
 * Response payload for granted MCP server consent.
 */
export interface MCPServerConsentGrantResponse {
	success: boolean;
	consentId: string;
	grantedScopes: string[];
	expiresAt?: string;
}

/**
 * MCP server share permission.
 */
export type MCPServerSharePermission = "use" | "manage";

/**
 * MCP server transport options.
 */
export type MCPServerTransport = "http" | "sse" | "stdio";

/**
 * MCP server visibility options.
 */
export type MCPServerVisibility = "private" | "org" | "public";

/**
 * Generic MCP server record shape.
 */
export interface MCPServerInfo {
	id: string;
	name: string;
	url: string;
	description: string | null;
	icon: string | null;
	transport: string;
	authType: string | null;
	discoveryStatus: string;
	visibility: string;
	isEnabled: boolean;
	config: Record<string, unknown> | null;
	healthStatus: string | null;
	hasToken: boolean;
	tokenScopes: string[];
	shareCount: number;
	createdAt: string;
	updatedAt: string;
}

/**
 * MCP server detail response.
 */
export interface MCPServerDetail {
	server: MCPServerInfo & {
		resource?: string;
		authorizationServers?: string[];
		scopesSupported?: string[];
		authorizationEndpoint?: string;
		tokenEndpoint?: string;
		clientId?: string;
		discoveryError?: string;
		lastDiscoveredAt?: string;
	};
	hasToken: boolean;
	tokenExpired: boolean;
	tokenScopes: string[];
}

/**
 * Request payload for MCP server registration.
 */
export interface RegisterMCPServerRequest {
	name: string;
	url?: string;
	description?: string;
	transport?: MCPServerTransport;
	visibility?: MCPServerVisibility;
	orgId?: string;
	headerTemplate?: Record<string, string>;
	config?: Record<string, unknown>;
}

/**
 * Response payload for MCP server registration.
 */
export interface RegisterMCPServerResponse {
	success: boolean;
	serverId: string;
	discoveryStatus: string;
	authType: string;
}

/**
 * Request payload for updating an MCP server.
 */
export interface UpdateMCPServerRequest {
	name?: string;
	description?: string;
	icon?: string;
	isEnabled?: boolean;
	headerTemplate?: Record<string, string>;
	clientId?: string;
	clientSecret?: string;
	config?: Record<string, unknown>;
}

/**
 * Response payload for updating an MCP server.
 */
export interface UpdateMCPServerResponse {
	success: boolean;
	server: MCPServerInfo;
}

/**
 * Response payload for listing MCP servers.
 */
export interface MCPServerListResponse {
	servers: MCPServerInfo[];
}

/**
 * Response payload for MCP server discovery.
 */
export interface MCPServerDiscoverResponse {
	success: boolean;
	authType: string;
	requiresAuth: boolean;
	status: string;
	error?: string;
}

/**
 * Response payload for starting MCP server OAuth flow.
 */
export interface MCPServerAuthStartResponse {
	authorizationUrl: string;
	state: string;
}

/**
 * Request payload for sharing an MCP server.
 */
export interface ShareMCPServerRequest {
	userId: string;
	permission?: MCPServerSharePermission;
}

/**
 * Response payload for sharing an MCP server.
 */
export interface ShareMCPServerResponse {
	success: boolean;
	shareId: string;
	sharedWithUserId: string;
}

/**
 * MCP server share record.
 */
export interface MCPServerShare {
	id: string;
	sharedWithUserId: string;
	permission: MCPServerSharePermission;
	sharedAt: string;
}

/**
 * Response payload for listing MCP server shares.
 */
export interface MCPServerSharesResponse {
	shares: MCPServerShare[];
}

/**
 * Rate limit error details.
 */
export interface RateLimitInfo {
	retryAfter: number;
	remaining?: number;
	limit?: number;
	type?: "ip" | "org" | "token_mint";
}

// =============================================================================
// OAuth Token Propagation (Third-Party Tokens)
// =============================================================================

/**
 * Information about a linked OAuth provider account.
 */
export interface LinkedProvider {
	/** Provider ID (e.g., "google", "github") */
	providerId: string;
	/** Account ID from the provider */
	accountId: string;
	/** When the access token expires (ISO string or null) */
	expiresAt: string | null;
	/** Scopes granted by this provider */
	scopes: string[];
}

/**
 * Request for external OAuth tokens.
 * Used by MCP agents to request third-party tokens for API access.
 */
export interface ProviderTokenRequest {
	/** List of provider IDs to fetch tokens for (e.g., ["github", "google"]) */
	providers: string[];
	/** Callback URL for provider linking (used if providers are not linked) */
	callbackUrl?: string;
}

/**
 * Response containing external OAuth tokens.
 */
export interface ProviderTokenResponse {
	/** Map of providerId -> accessToken (only successful retrievals) */
	tokens: Record<string, string>;
	/** Providers where token retrieval failed (need re-auth) */
	failedProviders: string[];
	/** Providers that were requested but user hasn't linked */
	missingProviders: string[];
	/** Environment variables ready for sandbox injection (e.g., GITHUB_TOKEN) */
	env: Record<string, string>;
	/** Authorization URLs for missing providers (if any) */
	authorizationUrls?: Record<string, string>;
}

/**
 * Error returned when required providers are missing.
 */
export interface ProviderLinkRequired {
	/** Error type */
	error: "provider_link_required";
	/** List of providers that must be linked */
	requiredProviders: string[];
	/** URLs to initiate OAuth linking for each provider */
	authorizationUrls: Record<string, string>;
	/** Human-readable message */
	message: string;
}

/**
 * Response from listing linked providers.
 */
export interface LinkedProvidersResponse {
	/** User ID */
	userId: string;
	/** List of linked provider accounts */
	providers: LinkedProvider[];
}

/**
 * Response from the link URL endpoint.
 */
export interface ProviderLinkUrlResponse {
	/** Provider ID */
	providerId: string;
	/** OAuth authorization URL to redirect user to */
	authorizationUrl: string;
	/** Human-readable message */
	message: string;
}

// =============================================================================
// Key Cabinet Types (External Credential Management)
// =============================================================================

/**
 * Information about a user's external credential in the Key Cabinet.
 * Separate from SSO login - these are explicitly linked for agent access.
 */
export interface ExternalCredentialInfo {
	/** Unique credential ID */
	id: string;
	/** External service ID (github, slack, linear, etc.) */
	providerId: string;
	/** Human-readable name ("Work GitHub", "Personal Slack") */
	displayName: string | null;
	/** Token type: oauth2, api_key, pat, custom */
	tokenType: string;
	/** Granted scopes */
	scopes: string[];
	/** Token expiration (ISO string, null if no expiry) */
	expiresAt: string | null;
	/** Last accessed by an agent (ISO string) */
	lastUsedAt: string | null;
	/** When linked (ISO string) */
	createdAt: string;
	/** Number of agents with consent to use this credential */
	consentCount: number;
}

/**
 * Response from listing user's external credentials.
 */
export interface CredentialsListResponse {
	/** List of linked credentials */
	credentials: ExternalCredentialInfo[];
}

/**
 * Request to save an API key credential.
 */
export interface SaveApiKeyRequest {
	/** Provider ID (e.g., "linear", "notion") */
	providerId: string;
	/** The API key to save (will be encrypted) */
	apiKey: string;
	/** Human-readable name for this credential */
	displayName?: string;
}

/**
 * Request to grant an agent access to a credential.
 */
export interface GrantConsentRequest {
	/** MCP client ID to grant access to */
	mcpClientId: string;
	/** Specific scopes to grant (subset of credential scopes, or all if omitted) */
	scopes?: string[];
	/** Consent expiration in days (no expiry if omitted) */
	expiresInDays?: number;
}

/**
 * Result of checking credential access for an agent.
 */
export interface CredentialAccessResult {
	/** Whether the agent has consent to use this credential */
	hasConsent: boolean;
	/** Whether the user has this credential linked at all */
	hasCredential: boolean;
	/** URL to link the provider (if not linked) */
	linkUrl?: string;
	/** URL to grant consent (if linked but no consent) */
	consentUrl?: string;
	/** Available scopes if credential exists */
	availableScopes?: string[];
}

/**
 * Response from getting credential tokens for an agent.
 * Enhanced version with consent tracking.
 */
export interface CredentialTokensResponse {
	/** Whether all requested tokens were retrieved successfully */
	success: boolean;
	/** Environment variables ready for injection (e.g., GITHUB_TOKEN: "abc123") */
	env: Record<string, string>;
	/** Providers that need consent from the user for this specific agent */
	needsConsent: string[];
	/** Providers that the user hasn't linked at all */
	missingProviders: string[];
	/** URLs for linking/consenting to missing providers */
	authorizationUrls?: Record<string, string>;
}

/**
 * External provider configuration.
 * Describes an available external service that can be linked.
 */
export interface ExternalProviderConfig {
	/** Provider ID (github, slack, linear, etc.) */
	id: string;
	/** Display name */
	name: string;
	/** Icon URL or identifier */
	icon: string | null;
	/** Credential type: oauth2, api_key, pat, custom */
	type: string;
	/** Default scopes to request */
	defaultScopes: string[];
	/** Environment variable name for injection (GITHUB_TOKEN) */
	envVarName: string;
	/** Whether this provider is enabled */
	isEnabled: boolean;
	/** Who configured this: system, admin, user */
	configuredBy: string;
}

/**
 * Response from listing available providers.
 */
export interface ProvidersListResponse {
	/** List of available provider configurations */
	providers: ExternalProviderConfig[];
}
