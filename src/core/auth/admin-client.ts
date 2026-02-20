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
 *   allowedAudiences: ['https://api.example.com'],
 * });
 *
 * // Revoke a client
 * await admin.revokeClient('mcp_client_123');
 * ```
 */

import { MCPAuthError, MCPConsentError } from "./errors";
import type {
	GrantMCPServerConsentRequest,
	MCPAdminClientConfig,
	MCPServerAuthStartResponse,
	MCPServerConsentGrantResponse,
	MCPServerDetail,
	MCPServerDiscoverResponse,
	MCPServerInfo,
	MCPServerListResponse,
	MCPServerShare,
	MCPServerSharesResponse,
	MCPServerTokenForClientResponse,
	MCPServerTokenStatusResponse,
	RegisterMCPServerRequest,
	RegisterMCPServerResponse,
	SaveMCPServerTokenRequest,
	ShareMCPServerRequest,
	ShareMCPServerResponse,
	UpdateMCPServerRequest,
	UpdateMCPServerResponse,
} from "./types";
import { getSdkHeaders } from "./version";

export interface CreateInviteParams {
	orgId: string;
	budget?: number;
	ttlSeconds?: number;
	allowedScopes?: string[];
	allowedAudiences?: string[];
	allowedRoles?: string[];
}

export interface InviteResult {
	token: string;
	inviteId: string;
	expiresAt: string;
}

type MCPApiErrorPayload = {
	error?: string;
	message?: string;
	error_description?: string;
	consentUrl?: string;
	invalidScopes?: string[];
};

export class MCPAdminClient {
	private authServer: string;
	private timeout: number;
	private csrfToken?: string;
	private cookies: Map<string, string> = new Map();

	constructor(config: MCPAdminClientConfig) {
		this.authServer = config.authServer.replace(/\/$/, "");
		this.timeout = config.timeout ?? 30000;
	}

	/**
	 * Update cookies from response headers.
	 */
	private updateCookies(response: Response): void {
		const setCookie = response.headers.get("set-cookie");
		if (setCookie) {
			// Parse Set-Cookie header (simplified)
			const cookies = setCookie.split(",").map((c) => c.trim());
			for (const cookie of cookies) {
				const [nameValue] = cookie.split(";");
				if (nameValue) {
					const [name, value] = nameValue.split("=");
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
			.join("; ");
	}

	/**
	 * Fetch a fresh CSRF token from the server.
	 */
	async getCsrfToken(): Promise<string> {
		const response = await fetch(`${this.authServer}/api/csrf-token`, {
			headers: {
				Origin: this.authServer,
				Cookie: this.getCookieHeader(),
				...getSdkHeaders(),
			},
			signal: AbortSignal.timeout(this.timeout),
		});

		this.updateCookies(response);

		const data = (await response.json()) as { csrfToken?: string };
		this.csrfToken = data.csrfToken;

		// Also check cookies if not in body
		if (!this.csrfToken) {
			this.csrfToken =
				this.cookies.get("csrf_token") ??
				this.cookies.get("better-auth.csrf-token");
		}

		return this.csrfToken ?? "";
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
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				"X-CSRF-Token": this.csrfToken ?? "",
				Origin: this.authServer,
				Cookie: this.getCookieHeader(),
				...getSdkHeaders(),
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
		body?: unknown,
	): Promise<{ status: number; data: T }> {
		const url = path.startsWith("http") ? path : `${this.authServer}${path}`;

		const headers: Record<string, string> = {
			Origin: this.authServer,
			Cookie: this.getCookieHeader(),
			...getSdkHeaders(),
		};

		// Add CSRF token for mutation methods
		if (["POST", "PUT", "PATCH", "DELETE"].includes(method.toUpperCase())) {
			if (!this.csrfToken) {
				await this.getCsrfToken();
			}
			headers["X-CSRF-Token"] = this.csrfToken ?? "";
		}

		if (body) {
			headers["Content-Type"] = "application/json";
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

	private extractErrorMessage(
		payload: MCPApiErrorPayload,
		fallback: string,
	): string {
		return (
			payload.message ?? payload.error_description ?? payload.error ?? fallback
		);
	}

	private throwMcpServerError(
		status: number,
		payload: MCPApiErrorPayload,
		fallback: string,
	): never {
		const code = payload.error;
		if (
			code === "consent_required" ||
			code === "consent_scope_mismatch" ||
			code === "invalid_consent_scopes"
		) {
			throw new MCPConsentError(
				this.extractErrorMessage(payload, fallback),
				code,
				{
					consentUrl: payload.consentUrl,
					invalidScopes: payload.invalidScopes,
				},
			);
		}

		throw new MCPAuthError(
			this.extractErrorMessage(payload, fallback),
			code ?? String(status),
		);
	}

	/**
	 * Create a registration invite for agents.
	 */
	async createInvite(params: CreateInviteParams): Promise<InviteResult> {
		const { status, data } = await this.request<{
			data?: InviteResult;
			token?: string;
		}>("POST", "/api/admin/mcp/invites", {
			orgId: params.orgId,
			budget: params.budget ?? 1,
			ttlSeconds: params.ttlSeconds ?? 600,
			allowedScopes: params.allowedScopes ?? [],
			allowedAudiences: params.allowedAudiences ?? [],
			allowedRoles: params.allowedRoles ?? [],
		});

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
			"GET",
			`/api/admin/mcp/clients/${clientId}`,
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
			"POST",
			`/api/admin/mcp/clients/${clientId}/disable`,
		);
		return status === 200 || status === 204;
	}

	/**
	 * Enable a previously disabled client.
	 */
	async enableClient(clientId: string): Promise<boolean> {
		const { status } = await this.request(
			"POST",
			`/api/admin/mcp/clients/${clientId}/enable`,
		);
		return status === 200 || status === 204;
	}

	/**
	 * Revoke a client (permanent termination).
	 */
	async revokeClient(clientId: string): Promise<boolean> {
		const { status } = await this.request(
			"POST",
			`/api/admin/mcp/clients/${clientId}/revoke`,
		);
		return status === 200 || status === 204;
	}

	/**
	 * Save a token for an MCP server.
	 */
	async saveMcpServerToken(
		serverId: string,
		payload: SaveMCPServerTokenRequest,
	): Promise<{
		success: boolean;
		tokenId: string;
		scopes: string[];
		expiresAt?: string;
	}> {
		const { status, data } = await this.request<{
			success?: boolean;
			tokenId?: string;
			scopes?: string[];
			expiresAt?: string;
			error?: string;
			message?: string;
		}>("POST", `/api/mcp/servers/${serverId}/token`, payload);

		if (status !== 200) {
			this.throwMcpServerError(
				status,
				data,
				`Failed to save MCP server token: ${status}`,
			);
		}

		return {
			success: data.success ?? true,
			tokenId: data.tokenId ?? "",
			scopes: data.scopes ?? [],
			expiresAt: data.expiresAt,
		};
	}

	/**
	 * Delete a saved token for an MCP server.
	 */
	async deleteMcpServerToken(serverId: string): Promise<boolean> {
		const { status, data } = await this.request<MCPApiErrorPayload>(
			"DELETE",
			`/api/mcp/servers/${serverId}/token`,
		);

		if (status !== 200) {
			this.throwMcpServerError(
				status,
				data,
				`Failed to delete MCP server token: ${status}`,
			);
		}

		return true;
	}

	/**
	 * Get token status (owner mode) or token material (agent mode with consent).
	 */
	async getMcpServerToken(
		serverId: string,
		mcpClientId?: string,
	): Promise<MCPServerTokenStatusResponse | MCPServerTokenForClientResponse> {
		const headers: Record<string, string> = {
			Origin: this.authServer,
			Cookie: this.getCookieHeader(),
			...getSdkHeaders(),
		};
		if (mcpClientId) {
			headers["X-MCP-Client-Id"] = mcpClientId;
		}

		const response = await fetch(
			`${this.authServer}/api/mcp/servers/${serverId}/token`,
			{
				method: "GET",
				headers,
				signal: AbortSignal.timeout(this.timeout),
			},
		);
		this.updateCookies(response);

		const data = (await response
			.json()
			.catch(() => ({}))) as MCPApiErrorPayload &
			Partial<MCPServerTokenStatusResponse & MCPServerTokenForClientResponse>;

		if (response.status !== 200) {
			this.throwMcpServerError(
				response.status,
				data,
				`Failed to fetch MCP server token: ${response.status}`,
			);
		}

		if (typeof data.accessToken === "string") {
			return {
				accessToken: data.accessToken,
				expiresAt: data.expiresAt,
				scopes: data.scopes ?? [],
			};
		}

		return {
			hasToken: data.hasToken ?? false,
			scopes: data.scopes ?? [],
			expiresAt: data.expiresAt,
			isExpired: data.isExpired ?? false,
		};
	}

	/**
	 * Grant MCP client consent to use a server token.
	 */
	async grantMcpServerConsent(
		serverId: string,
		payload: GrantMCPServerConsentRequest,
	): Promise<MCPServerConsentGrantResponse> {
		const { status, data } = await this.request<
			Partial<MCPServerConsentGrantResponse> & MCPApiErrorPayload
		>("POST", `/api/mcp/servers/${serverId}/consent`, payload);

		if (status !== 200) {
			this.throwMcpServerError(
				status,
				data,
				`Failed to grant MCP server consent: ${status}`,
			);
		}

		return {
			success: data.success ?? true,
			consentId: data.consentId ?? "",
			grantedScopes: data.grantedScopes ?? [],
			expiresAt: data.expiresAt,
		};
	}

	/**
	 * Revoke MCP client consent for a server token.
	 */
	async revokeMcpServerConsent(
		serverId: string,
		mcpClientId: string,
	): Promise<boolean> {
		const { status, data } = await this.request<MCPApiErrorPayload>(
			"DELETE",
			`/api/mcp/servers/${serverId}/consent/${mcpClientId}`,
		);

		if (status !== 200) {
			this.throwMcpServerError(
				status,
				data,
				`Failed to revoke MCP server consent: ${status}`,
			);
		}

		return true;
	}

	/**
	 * List MCP servers accessible to the current user.
	 */
	async listMcpServers(): Promise<MCPServerInfo[]> {
		const { status, data } = await this.request<
			MCPServerListResponse & MCPApiErrorPayload
		>("GET", "/api/mcp/servers");

		if (status !== 200) {
			this.throwMcpServerError(
				status,
				data,
				`Failed to list MCP servers: ${status}`,
			);
		}

		return data.servers ?? [];
	}

	/**
	 * Get details for a single MCP server.
	 */
	async getMcpServer(serverId: string): Promise<MCPServerDetail> {
		const { status, data } = await this.request<
			MCPServerDetail & MCPApiErrorPayload
		>("GET", `/api/mcp/servers/${serverId}`);

		if (status !== 200) {
			this.throwMcpServerError(
				status,
				data,
				`Failed to fetch MCP server: ${status}`,
			);
		}

		return data as MCPServerDetail;
	}

	/**
	 * Register a new MCP server.
	 */
	async registerMcpServer(
		payload: RegisterMCPServerRequest,
	): Promise<RegisterMCPServerResponse> {
		const { status, data } = await this.request<
			RegisterMCPServerResponse & MCPApiErrorPayload
		>("POST", "/api/mcp/servers", payload);

		if (status !== 201) {
			this.throwMcpServerError(
				status,
				data,
				`Failed to register MCP server: ${status}`,
			);
		}

		return data as RegisterMCPServerResponse;
	}

	/**
	 * Update an existing MCP server.
	 */
	async updateMcpServer(
		serverId: string,
		payload: UpdateMCPServerRequest,
	): Promise<UpdateMCPServerResponse> {
		const { status, data } = await this.request<
			UpdateMCPServerResponse & MCPApiErrorPayload
		>("PATCH", `/api/mcp/servers/${serverId}`, payload);

		if (status !== 200) {
			this.throwMcpServerError(
				status,
				data,
				`Failed to update MCP server: ${status}`,
			);
		}

		return data as UpdateMCPServerResponse;
	}

	/**
	 * Delete an MCP server.
	 */
	async deleteMcpServer(serverId: string): Promise<boolean> {
		const { status, data } = await this.request<MCPApiErrorPayload>(
			"DELETE",
			`/api/mcp/servers/${serverId}`,
		);

		if (status !== 200) {
			this.throwMcpServerError(
				status,
				data,
				`Failed to delete MCP server: ${status}`,
			);
		}

		return true;
	}

	/**
	 * Re-run discovery for an MCP server.
	 */
	async discoverMcpServer(
		serverId: string,
	): Promise<MCPServerDiscoverResponse> {
		const { status, data } = await this.request<
			MCPServerDiscoverResponse & MCPApiErrorPayload
		>("POST", `/api/mcp/servers/${serverId}/discover`);

		if (status !== 200) {
			this.throwMcpServerError(
				status,
				data,
				`Failed to discover MCP server auth: ${status}`,
			);
		}

		return data as MCPServerDiscoverResponse;
	}

	/**
	 * Start OAuth authorization flow for an MCP server.
	 */
	async startMcpServerAuth(
		serverId: string,
	): Promise<MCPServerAuthStartResponse> {
		const { status, data } = await this.request<
			MCPServerAuthStartResponse & MCPApiErrorPayload
		>("POST", `/api/mcp/servers/${serverId}/auth`);

		if (status !== 200) {
			this.throwMcpServerError(
				status,
				data,
				`Failed to start MCP server OAuth flow: ${status}`,
			);
		}

		return data as MCPServerAuthStartResponse;
	}

	/**
	 * Share an MCP server with another user.
	 */
	async shareMcpServer(
		serverId: string,
		payload: ShareMCPServerRequest,
	): Promise<ShareMCPServerResponse> {
		const { status, data } = await this.request<
			ShareMCPServerResponse & MCPApiErrorPayload
		>("POST", `/api/mcp/servers/${serverId}/share`, payload);

		if (status !== 201) {
			this.throwMcpServerError(
				status,
				data,
				`Failed to share MCP server: ${status}`,
			);
		}

		return data as ShareMCPServerResponse;
	}

	/**
	 * Revoke an MCP server share.
	 */
	async revokeMcpServerShare(
		serverId: string,
		userId: string,
	): Promise<boolean> {
		const { status, data } = await this.request<MCPApiErrorPayload>(
			"DELETE",
			`/api/mcp/servers/${serverId}/share/${userId}`,
		);

		if (status !== 200) {
			this.throwMcpServerError(
				status,
				data,
				`Failed to revoke MCP server share: ${status}`,
			);
		}

		return true;
	}

	/**
	 * List shares for an MCP server.
	 */
	async getMcpServerShares(serverId: string): Promise<MCPServerShare[]> {
		const { status, data } = await this.request<
			MCPServerSharesResponse & MCPApiErrorPayload
		>("GET", `/api/mcp/servers/${serverId}/shares`);

		if (status !== 200) {
			this.throwMcpServerError(
				status,
				data,
				`Failed to fetch MCP server shares: ${status}`,
			);
		}

		return data.shares ?? [];
	}

	/**
	 * Get the session cookie string for use with other clients.
	 */
	getSessionCookieString(): string {
		return this.getCookieHeader();
	}
}
