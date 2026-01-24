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
	MCPAgentClientConfig,
	MCPCredentials,
	MCPToken,
	ProtectedResourceMetadata,
	RegistrationResponse,
	TokenResponse,
} from "./types";
import { isTokenExpired } from "./types";

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

		// RFC 8707: Pass audience as 'resource' parameter to get JWT with aud claim
		if (audience) {
			formData.set("resource", audience);
		}

		const response = await fetch(`${this.authServer}/api/auth/oauth2/token`, {
			method: "POST",
			headers: {
				"Content-Type": "application/x-www-form-urlencoded",
				Origin: this.authServer,
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
}
