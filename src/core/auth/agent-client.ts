/**
 * MCP Identity SDK - Agent Client
 *
 * Client for MCP agents to register and obtain tokens.
 *
 * Features:
 * - Registration with REG_JWT invite tokens
 * - Token acquisition with audience support (RFC 8707)
 * - Automatic token refresh
 * - Rate limit handling
 * - Public client (PKCE) support
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

import {
	MCPAuthError,
	MCPRateLimitError,
	MCPRegistrationError,
} from "./errors";
import type {
	IntrospectionResponse,
	LinkedProvidersResponse,
	MCPAgentClientConfig,
	MCPCredentials,
	MCPToken,
	ProtectedResourceMetadata,
	ProviderLinkRequired,
	ProviderLinkUrlResponse,
	// OAuth Token Propagation types
	ProviderTokenRequest,
	ProviderTokenResponse,
	RegistrationResponse,
	TokenResponse,
} from "./types";
import { isTokenExpired } from "./types";
import { getSdkHeaders } from "./version";

/**
 * Registration options for public clients.
 */
export interface RegisterOptions {
	/** Whether to register as a public client (PKCE required, no secret) */
	isPublic?: boolean;
	/** Optional metadata to attach */
	metadata?: Record<string, unknown>;
	/** Redirect URIs (for public clients with auth code flow) */
	redirectUris?: string[];
}

export class MCPAgentClient {
	private authServer: string;
	private regJwt?: string;
	private clientId?: string;
	private clientSecret?: string | null;
	private timeout: number;
	private currentToken?: MCPToken;
	private credentials?: MCPCredentials;

	constructor(config: MCPAgentClientConfig) {
		this.authServer = config.authServer.replace(/\/$/, "");
		this.regJwt = config.regJwt;
		this.clientId = config.clientId;
		this.clientSecret = config.clientSecret;
		this.timeout = config.timeout ?? 30000;
	}

	/**
	 * Register a new MCP machine client.
	 *
	 * @param clientName - Human-readable name for this agent
	 * @param options - Registration options (metadata, isPublic, etc.)
	 * @returns MCPCredentials with clientId and clientSecret
	 */
	async register(
		clientName: string,
		options?: RegisterOptions | Record<string, unknown>,
	): Promise<MCPCredentials> {
		if (!this.regJwt) {
			throw new MCPRegistrationError(
				"Registration requires a REG_JWT invite token",
			);
		}

		// Handle both old and new API
		const opts: RegisterOptions =
			options && "isPublic" in options
				? (options as RegisterOptions)
				: { metadata: options as Record<string, unknown> };

		const body: Record<string, unknown> = {
			client_name: clientName,
			is_public: opts.isPublic ?? false,
		};

		if (opts.metadata) {
			body.metadata = opts.metadata;
		}

		if (opts.redirectUris) {
			body.redirect_uris = opts.redirectUris;
		}

		const response = await fetch(`${this.authServer}/api/mcp/register`, {
			method: "POST",
			headers: {
				Authorization: `Bearer ${this.regJwt}`,
				"Content-Type": "application/json",
				Origin: this.authServer,
				...getSdkHeaders(),
			},
			body: JSON.stringify(body),
			signal: AbortSignal.timeout(this.timeout),
		});

		if (response.status === 201) {
			const data = (await response.json()) as RegistrationResponse;

			this.credentials = {
				clientId: data.client_id,
				clientSecret: data.client_secret ?? "",
				allowedScopes: data.allowed_scopes ?? [],
				allowedAudiences: data.allowed_audiences ?? [],
				allowedRoles: data.allowed_roles ?? [],
				orgId: data.organization_id ?? data.org_id,
				isPublic: data.is_public,
			};

			this.clientId = this.credentials.clientId;
			this.clientSecret = this.credentials.clientSecret;

			return this.credentials;
		}

		// Handle rate limiting
		if (response.status === 429) {
			const errorData = (await response.json().catch(() => ({}))) as Record<
				string,
				unknown
			>;
			const retryAfter = (errorData.retry_after as number) ?? 60;
			throw new MCPRateLimitError(
				(errorData.error_description as string) ??
					"Registration rate limit exceeded",
				retryAfter,
			);
		}

		const errorData = (await response.json().catch(() => ({}))) as Record<
			string,
			string
		>;
		throw new MCPRegistrationError(
			errorData.error_description ?? `Registration failed: ${response.status}`,
			errorData.error,
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
		forceRefresh: boolean = false,
	): Promise<MCPToken> {
		if (!this.clientId || !this.clientSecret) {
			throw new MCPAuthError(
				"Client credentials not set. Call register() first.",
			);
		}

		// Return cached token if still valid
		if (
			!forceRefresh &&
			this.currentToken &&
			!isTokenExpired(this.currentToken)
		) {
			return this.currentToken;
		}

		// Build form data
		const formData = new URLSearchParams();
		formData.set("grant_type", "client_credentials");
		formData.set("client_id", this.clientId);
		formData.set("client_secret", this.clientSecret);

		if (scopes && scopes.length > 0) {
			formData.set("scope", scopes.join(" "));
		}

		// Pass audience explicitly so backend can mint audience-bound JWTs.
		if (audience) {
			formData.set("audience", audience);
		}

		const response = await fetch(`${this.authServer}/api/auth/oauth2/token`, {
			method: "POST",
			headers: {
				"Content-Type": "application/x-www-form-urlencoded",
				Origin: this.authServer,
				...getSdkHeaders(),
			},
			body: formData,
			signal: AbortSignal.timeout(this.timeout),
		});

		if (response.status === 200) {
			const data = (await response.json()) as TokenResponse;

			this.currentToken = {
				accessToken: data.access_token,
				tokenType: data.token_type ?? "Bearer",
				expiresIn: data.expires_in ?? 3600,
				scope: data.scope ?? "",
				expiresAt: Date.now() / 1000 + (data.expires_in ?? 3600),
			};

			return this.currentToken;
		}

		const errorData = (await response.json().catch(() => ({}))) as Record<
			string,
			unknown
		>;

		// Handle rate limiting (429 Too Many Requests)
		if (response.status === 429) {
			const retryAfter =
				(errorData.retry_after as number) ??
				(errorData.retryAfter as number) ??
				60;
			throw new MCPRateLimitError(
				(errorData.error_description as string) ?? "Rate limit exceeded",
				retryAfter,
			);
		}

		throw new MCPAuthError(
			(errorData.error_description as string) ??
				`Token request failed: ${response.status}`,
			errorData.error as string,
		);
	}

	/**
	 * Introspect a token using RFC 7662 endpoint.
	 * Uses Better Auth's built-in introspection at /api/auth/oauth2/introspect.
	 *
	 * @param token - The token to introspect
	 * @returns Introspection result
	 */
	async introspectToken(token: string): Promise<{
		active: boolean;
		clientId?: string;
		scope?: string;
		exp?: number;
		orgId?: string;
		roles?: string[];
	}> {
		if (!this.clientId || !this.clientSecret) {
			throw new MCPAuthError("Client credentials required for introspection");
		}

		const response = await fetch(
			`${this.authServer}/api/auth/oauth2/introspect`,
			{
				method: "POST",
				headers: {
					"Content-Type": "application/x-www-form-urlencoded",
					...getSdkHeaders(),
				},
				body: new URLSearchParams({
					token,
					client_id: this.clientId,
					client_secret: this.clientSecret,
				}),
				signal: AbortSignal.timeout(this.timeout),
			},
		);

		// Handle non-JSON responses gracefully
		const text = await response.text();
		let data: IntrospectionResponse;
		try {
			data = JSON.parse(text) as IntrospectionResponse;
		} catch {
			// If parsing fails, return inactive (common for error responses)
			return { active: false };
		}

		return {
			active: data.active,
			clientId: data.client_id ?? data.sub,
			scope: data.scope,
			exp: data.exp,
			orgId: data.org_id,
			roles: data.roles,
		};
	}

	/**
	 * Discover protected resource metadata (RFC 9728).
	 *
	 * @param resourceUri - The resource URI (defaults to auth server)
	 * @returns Protected resource metadata
	 */
	async discoverResourceMetadata(resourceUri?: string): Promise<{
		resource: string;
		authorizationServers: string[];
		scopesSupported?: string[];
		introspectionEndpoint?: string;
	}> {
		const baseUrl = resourceUri ?? this.authServer;
		const response = await fetch(
			`${baseUrl}/.well-known/oauth-protected-resource`,
			{
				headers: {
					...getSdkHeaders(),
				},
				signal: AbortSignal.timeout(this.timeout),
			},
		);

		if (!response.ok) {
			throw new MCPAuthError(
				`Failed to discover resource metadata: ${response.status}`,
			);
		}

		const data = (await response.json()) as ProtectedResourceMetadata;

		return {
			resource: data.resource,
			authorizationServers: data.authorization_servers,
			scopesSupported: data.scopes_supported,
			introspectionEndpoint: data.introspection_endpoint,
		};
	}

	/**
	 * Rotate the client secret.
	 * This immediately invalidates the old secret.
	 */
	async rotateSecret(): Promise<{ clientSecret: string; rotatedAt: string }> {
		if (!this.clientId || !this.clientSecret) {
			throw new MCPAuthError(
				"Client credentials not set. Call register() first.",
			);
		}

		const response = await fetch(
			`${this.authServer}/api/auth/oauth2/client/rotate-secret`,
			{
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					Origin: this.authServer,
					...getSdkHeaders(),
				},
				body: JSON.stringify({
					client_id: this.clientId,
					client_secret: this.clientSecret,
				}),
				signal: AbortSignal.timeout(this.timeout),
			},
		);

		if (response.status === 200) {
			const data = (await response.json()) as {
				client_secret: string;
				rotated_at: string;
			};
			this.clientSecret = data.client_secret;
			if (this.credentials) {
				this.credentials.clientSecret = data.client_secret;
			}
			return {
				clientSecret: data.client_secret,
				rotatedAt: data.rotated_at,
			};
		}

		const errorData = (await response.json().catch(() => ({}))) as Record<
			string,
			string
		>;
		throw new MCPAuthError(
			errorData.error_description ??
				`Secret rotation failed: ${response.status}`,
			errorData.error,
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

	/**
	 * Check if this is a public client (no secret, PKCE required).
	 */
	isPublicClient(): boolean {
		return this.credentials?.isPublic ?? false;
	}

	/**
	 * Get the allowed roles for this client.
	 */
	getAllowedRoles(): string[] {
		return this.credentials?.allowedRoles ?? [];
	}

	// =========================================================================
	// OAuth Token Propagation (Third-Party Tokens)
	// =========================================================================

	/**
	 * Get third-party OAuth tokens for external services.
	 *
	 * This enables MCP agents to access external services (GitHub, Google, etc.)
	 * using the user's linked OAuth credentials.
	 *
	 * @param accessToken - The MCP access token (must be acting on behalf of a user)
	 * @param providers - List of provider IDs to request tokens for
	 * @param callbackUrl - Optional callback URL for linking (if providers are missing)
	 * @returns ProviderTokenResponse with tokens and env vars for sandbox injection
	 * @throws MCPAuthError if the request fails or if required providers are missing
	 *
	 * @example
	 * ```typescript
	 * const tokenResult = await agent.getProviderTokens(userToken, ['github', 'google']);
	 * if (tokenResult.missingProviders.length > 0) {
	 *   // Prompt user to link missing providers
	 *   console.log('Please link:', tokenResult.authorizationUrls);
	 * } else {
	 *   // Use tokens
	 *   process.env.GITHUB_TOKEN = tokenResult.env.GITHUB_TOKEN;
	 * }
	 * ```
	 */
	async getProviderTokens(
		accessToken: string,
		providers: string[],
		callbackUrl?: string,
	): Promise<ProviderTokenResponse | ProviderLinkRequired> {
		const body: ProviderTokenRequest = {
			providers,
			callbackUrl,
		};

		const response = await fetch(`${this.authServer}/api/mcp/tokens`, {
			method: "POST",
			headers: {
				Authorization: `Bearer ${accessToken}`,
				"Content-Type": "application/json",
				...getSdkHeaders(),
			},
			body: JSON.stringify(body),
			signal: AbortSignal.timeout(this.timeout),
		});

		if (response.status === 200) {
			return (await response.json()) as ProviderTokenResponse;
		}

		if (response.status === 403) {
			const data = (await response.json()) as ProviderLinkRequired;
			if (data.error === "provider_link_required") {
				return data;
			}
		}

		if (response.status === 401) {
			throw new MCPAuthError("Authentication required for token propagation");
		}

		const errorData = (await response.json().catch(() => ({}))) as Record<
			string,
			string
		>;
		throw new MCPAuthError(
			errorData.error_description ??
				`Failed to get provider tokens: ${response.status}`,
			errorData.error,
		);
	}

	/**
	 * List all linked OAuth providers for a user.
	 *
	 * @param accessToken - The MCP access token (must be acting on behalf of a user)
	 * @returns List of linked provider accounts
	 *
	 * @example
	 * ```typescript
	 * const linked = await agent.getLinkedProviders(userToken);
	 * console.log('User has linked:', linked.providers.map(p => p.providerId));
	 * ```
	 */
	async getLinkedProviders(
		accessToken: string,
	): Promise<LinkedProvidersResponse> {
		const response = await fetch(
			`${this.authServer}/api/mcp/tokens/providers`,
			{
				method: "GET",
				headers: {
					Authorization: `Bearer ${accessToken}`,
					...getSdkHeaders(),
				},
				signal: AbortSignal.timeout(this.timeout),
			},
		);

		if (response.status === 200) {
			return (await response.json()) as LinkedProvidersResponse;
		}

		if (response.status === 401) {
			throw new MCPAuthError(
				"Authentication required to list linked providers",
			);
		}

		const errorData = (await response.json().catch(() => ({}))) as Record<
			string,
			string
		>;
		throw new MCPAuthError(
			errorData.error_description ??
				`Failed to list providers: ${response.status}`,
			errorData.error,
		);
	}

	/**
	 * Get the OAuth authorization URL for linking a provider.
	 *
	 * This URL should be presented to the user to initiate the OAuth
	 * consent flow for linking their external account.
	 *
	 * @param providerId - Provider to link (e.g., "github", "google")
	 * @param callbackUrl - Where to redirect after successful linking
	 * @returns The authorization URL
	 *
	 * @example
	 * ```typescript
	 * const linkInfo = await agent.getProviderLinkUrl('github', '/settings/accounts');
	 * console.log('Redirect user to:', linkInfo.authorizationUrl);
	 * ```
	 */
	async getProviderLinkUrl(
		providerId: string,
		callbackUrl?: string,
	): Promise<ProviderLinkUrlResponse> {
		const params = new URLSearchParams();
		if (callbackUrl) {
			params.set("callbackUrl", callbackUrl);
		}

		const url =
			`${this.authServer}/api/mcp/tokens/link/${providerId}` +
			(params.toString() ? `?${params.toString()}` : "");

		const response = await fetch(url, {
			method: "GET",
			headers: {
				...getSdkHeaders(),
			},
			signal: AbortSignal.timeout(this.timeout),
		});

		if (response.status === 200) {
			return (await response.json()) as ProviderLinkUrlResponse;
		}

		const errorData = (await response.json().catch(() => ({}))) as Record<
			string,
			string
		>;
		throw new MCPAuthError(
			errorData.error_description ??
				`Failed to get link URL: ${response.status}`,
			errorData.error,
		);
	}

	/**
	 * Check if a ProviderTokenResponse indicates that provider linking is required.
	 *
	 * @param response - The response from getProviderTokens()
	 * @returns True if the response is a ProviderLinkRequired error
	 */
	isProviderLinkRequired(
		response: ProviderTokenResponse | ProviderLinkRequired,
	): response is ProviderLinkRequired {
		return "error" in response && response.error === "provider_link_required";
	}

	// =========================================================================
	// Key Cabinet Methods (External Credential Management)
	// =========================================================================

	/**
	 * Get credential tokens for external services (Key Cabinet).
	 *
	 * This is the enhanced version that supports per-agent consent.
	 * Use this instead of getProviderTokens() for the new consent-aware flow.
	 *
	 * @param accessToken - The MCP access token (must be acting on behalf of a user)
	 * @param providers - List of provider IDs to fetch tokens for
	 * @returns Credential tokens or consent/missing provider info
	 *
	 * @example
	 * ```typescript
	 * const result = await agent.getCredentialTokens(userToken, ['github', 'linear']);
	 * if (result.success) {
	 *   // Inject tokens into agent environment
	 *   Object.assign(process.env, result.env);
	 * } else if (result.needsConsent.length > 0) {
	 *   // Redirect user to grant consent
	 *   console.log('User needs to grant consent:', result.authorizationUrls);
	 * }
	 * ```
	 */
	async getCredentialTokens(
		accessToken: string,
		providers: string[],
	): Promise<{
		success: boolean;
		env: Record<string, string>;
		needsConsent: string[];
		missingProviders: string[];
		authorizationUrls?: Record<string, string>;
	}> {
		const response = await fetch(
			`${this.authServer}/api/mcp/credentials/tokens`,
			{
				method: "POST",
				headers: {
					...getSdkHeaders(),
					Authorization: `Bearer ${accessToken}`,
					"Content-Type": "application/json",
				},
				body: JSON.stringify({ providers, mcpClientId: this.clientId }),
				signal: AbortSignal.timeout(this.timeout),
			},
		);

		if (response.status === 200) {
			return (await response.json()) as {
				success: boolean;
				env: Record<string, string>;
				needsConsent: string[];
				missingProviders: string[];
				authorizationUrls?: Record<string, string>;
			};
		}

		const errorData = (await response.json().catch(() => ({}))) as Record<
			string,
			string
		>;
		throw new MCPAuthError(
			errorData.error ?? `Failed to get credential tokens: ${response.status}`,
			"credential_error",
		);
	}

	/**
	 * Check if credential access is available for a specific provider.
	 * Used by Gate 2 for pre-flight checks.
	 *
	 * @param accessToken - The MCP access token
	 * @param userId - The user ID to check
	 * @param providerId - The provider to check
	 * @param callbackUrl - Callback URL for linking/consent flows
	 * @returns Access status with URLs for linking/consent if needed
	 */
	async checkCredentialAccess(
		accessToken: string,
		userId: string,
		providerId: string,
		callbackUrl: string,
	): Promise<{
		hasConsent: boolean;
		hasCredential: boolean;
		linkUrl?: string;
		consentUrl?: string;
		availableScopes?: string[];
	}> {
		const response = await fetch(
			`${this.authServer}/api/mcp/credentials/check`,
			{
				method: "POST",
				headers: {
					...getSdkHeaders(),
					Authorization: `Bearer ${accessToken}`,
					"Content-Type": "application/json",
				},
				body: JSON.stringify({
					userId,
					providerId,
					mcpClientId: this.clientId,
					callbackUrl,
				}),
				signal: AbortSignal.timeout(this.timeout),
			},
		);

		if (response.status === 200) {
			return (await response.json()) as {
				hasConsent: boolean;
				hasCredential: boolean;
				linkUrl?: string;
				consentUrl?: string;
				availableScopes?: string[];
			};
		}

		const errorData = (await response.json().catch(() => ({}))) as Record<
			string,
			string
		>;
		throw new MCPAuthError(
			errorData.error ??
				`Failed to check credential access: ${response.status}`,
			"credential_error",
		);
	}

	/**
	 * List available external provider configurations.
	 *
	 * @returns List of supported external providers
	 */
	async getAvailableProviders(): Promise<{
		providers: Array<{
			id: string;
			name: string;
			icon: string | null;
			type: string;
			defaultScopes: string[];
			envVarName: string;
			isEnabled: boolean;
		}>;
	}> {
		const response = await fetch(
			`${this.authServer}/api/mcp/credentials/providers`,
			{
				method: "GET",
				headers: getSdkHeaders(),
				signal: AbortSignal.timeout(this.timeout),
			},
		);

		if (response.status === 200) {
			return (await response.json()) as {
				providers: Array<{
					id: string;
					name: string;
					icon: string | null;
					type: string;
					defaultScopes: string[];
					envVarName: string;
					isEnabled: boolean;
				}>;
			};
		}

		const errorData = (await response.json().catch(() => ({}))) as Record<
			string,
			string
		>;
		throw new MCPAuthError(
			errorData.error ?? `Failed to get providers: ${response.status}`,
			"provider_error",
		);
	}
}
