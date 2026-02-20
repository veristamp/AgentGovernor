#!/usr/bin/env bun
/**
 * OAuth 2.1 User Flow Demo - TypeScript (Bun)
 *
 * This demo application shows the complete user-facing OAuth 2.1 flow using Bun's native HTTP server.
 *
 * === THE FLOW ===
 * 1. User visits /login → Redirects to auth server
 * 2. User authenticates (email + password)
 * 3. User selects organization (if multiple orgs and org scopes requested)
 * 4. User consents to permissions
 * 5. Auth server redirects back to /callback with code
 * 6. App exchanges code for tokens
 * 7. App shows user info at /me
 *
 * === PREREQUISITES ===
 * 1. Create an OAuth app in the console:
 *    - Go to Console → OAuth Apps → Create App
 *    - Name: "Demo App TS"
 *    - Type: Web Application
 *    - Redirect URI: http://localhost:9001/callback
 *    - Scopes: openid, profile, email
 *    - Save the client_id and client_secret
 *
 * 2. Set environment variables:
 *    export OAUTH_CLIENT_ID="your-client-id"
 *    export OAUTH_CLIENT_SECRET="your-client-secret"
 *    export OAUTH_AUTH_SERVER="http://localhost:8787"
 *
 * 3. Run the demo:
 *    cd sdk/typescript
 *    bun run oauth-demo.ts
 *
 * 4. Open http://localhost:9001 in your browser
 */

import { createHash, randomBytes } from "node:crypto";

function getErrorMessage(error: unknown): string {
	return error instanceof Error ? error.message : String(error);
}

// =============================================================================
// Auto Setup (Admin Bootstrap)
// =============================================================================

async function autoSetup(): Promise<{
	clientId: string;
	clientSecret: string;
	authServer: string;
}> {
	console.log("\n⚡ Starting Auto-Setup Mode...");

	// 1. Try to run the direct DB setup script (Most Robust)
	try {
		// Run the setup script using bun
		// We assume we are running from project root or sdk/typescript/
		let scriptPath = "scripts/setup-oauth-demo.ts";

		// Check if script exists at root
		if (!(await Bun.file(scriptPath).exists())) {
			// Try relative to this file if running from root
			scriptPath = "scripts/setup-oauth-demo.ts";

			// If not found, try going up if we are in sdk/typescript CWD (unlikely with bun run path)
			if (!(await Bun.file(scriptPath).exists())) {
				// Maybe we are in sdk/typescript/
				scriptPath = "../../scripts/setup-oauth-demo.ts";
			}
		}

		// Final check
		if (!(await Bun.file(scriptPath).exists())) {
			// One last try: Absolute path based on CWD
			// If CWD is root, it is scripts/...
			throw new Error(
				`Setup script not found at ${scriptPath} (CWD: ${process.cwd()})`,
			);
		}

		console.log(`   Running bootstrap script: ${scriptPath}`);
		const proc = Bun.spawn(["bun", "run", scriptPath], {
			cwd: process.cwd(), // Inherit current working directory
			env: { ...process.env, FORCE_COLOR: "1" },
			stderr: "inherit",
		});

		const output = await new Response(proc.stdout).text();
		await proc.exited;

		if (proc.exitCode !== 0) {
			throw new Error(`Setup script failed with code ${proc.exitCode}`);
		}

		// Force flush of stdout might needed? No, await proc.exited should handle it.
		// Debug output if parsing fails
		if (!output.includes("JSON_START")) {
			console.log("DEBUG: Script Output was:", output);
		}

		// Extract JSON from output
		// The script prints log lines and then the JSON
		// We search for the JSON between markers
		const jsonMatch = output.match(/JSON_START\s*([\s\S]*?)\s*JSON_END/);
		if (!jsonMatch) {
			// Fallback to regex search
			const looseMatch = output.match(/\{"clientId":.*?\}/);
			if (looseMatch) {
				const creds = JSON.parse(looseMatch[0]);
				console.log(`   ✅ Auto-setup complete via DB direct access!`);
				return {
					clientId: creds.clientId,
					clientSecret: creds.clientSecret,
					authServer: creds.authServer,
				};
			}

			console.error("Script output:", output);
			throw new Error("Could not parse credentials from setup script output");
		}

		const creds = JSON.parse(jsonMatch[1]);
		console.log(`   ✅ Auto-setup complete via DB direct access!`);

		return {
			clientId: creds.clientId,
			clientSecret: creds.clientSecret,
			authServer: creds.authServer,
		};
	} catch (e: unknown) {
		console.warn(`   ⚠️  DB Setup failed: ${getErrorMessage(e)}`);
		console.warn(`   Falling back to API setup...`);
	}

	// Fallback: API Setup (Original Logic)
	// ... (Keep existing logic as backup, but it's likely to fail if DB setup failed)

	// For now, let's just throw if DB setup failed, as API is known broken
	throw new Error(
		"Auto-setup failed. Please run 'bun run scripts/setup-oauth-demo.ts' from root manually.",
	);
}

// =============================================================================
// Main Application Setup
// =============================================================================

let AUTH_SERVER = process.env.OAUTH_AUTH_SERVER || "http://localhost:8787";
let CLIENT_ID = process.env.OAUTH_CLIENT_ID || "";
let CLIENT_SECRET = process.env.OAUTH_CLIENT_SECRET || "";
const PORT = 9001;
const REDIRECT_URI =
	process.env.OAUTH_REDIRECT_URI || `http://localhost:${PORT}/callback`;

const SCOPES = [
	"openid",
	"profile",
	"email",
	"read:organization",
	"offline_access",
];

// Check if we need to run auto-setup
if (!CLIENT_ID) {
	try {
		const setup = await autoSetup();
		CLIENT_ID = setup.clientId;
		CLIENT_SECRET = setup.clientSecret;
		AUTH_SERVER = setup.authServer;

		// Export for user visibility
		console.log(`\n${"=".repeat(70)}`);
		console.log("  ⚠️  AUTO-GENERATED CREDENTIALS (Valid for this session)");
		console.log("=".repeat(70));
		console.log(`  export OAUTH_CLIENT_ID="${CLIENT_ID}"`);
		console.log(`  export OAUTH_CLIENT_SECRET="${CLIENT_SECRET}"`);
		console.log(`  export OAUTH_AUTH_SERVER="${AUTH_SERVER}"`);
		console.log("=".repeat(70));
	} catch (e: unknown) {
		console.error("\n❌ Auto-setup failed:", getErrorMessage(e));
		console.error(
			"Please set OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET manually.",
		);
		process.exit(1);
	}
}

// =============================================================================
// OAuth Client Implementation
// =============================================================================

interface OAuthTokens {
	access_token: string;
	token_type: string;
	expires_in: number;
	refresh_token?: string;
	id_token?: string;
	scope?: string;
	expires_at?: number;
}

interface OAuthUser {
	sub: string;
	email?: string;
	email_verified?: boolean;
	name?: string;
	picture?: string;
	org_id?: string;
	org_slug?: string;
	org_role?: string;
	[key: string]: unknown;
}

interface OAuthDiscovery {
	issuer: string;
	authorization_endpoint: string;
	token_endpoint: string;
	userinfo_endpoint?: string;
	end_session_endpoint?: string;
	revocation_endpoint?: string;
}

class OAuthClient {
	private discovery: OAuthDiscovery | null = null;

	constructor(
		private authServer: string,
		private clientId: string,
		private clientSecret: string | undefined,
		private redirectUri: string,
		private scopes: string[] = ["openid", "profile", "email"],
	) {
		this.authServer = authServer.replace(/\/$/, "");
	}

	async discover(): Promise<OAuthDiscovery> {
		if (this.discovery) return this.discovery;

		try {
			const res = await fetch(
				`${this.authServer}/.well-known/openid-configuration`,
			);
			if (!res.ok) throw new Error("Discovery failed");
			const data = (await res.json()) as Partial<OAuthDiscovery>;

			this.discovery = {
				issuer: data.issuer || this.authServer,
				authorization_endpoint:
					data.authorization_endpoint ||
					`${this.authServer}/api/auth/authorize`,
				token_endpoint:
					data.token_endpoint || `${this.authServer}/api/auth/oauth2/token`,
				userinfo_endpoint:
					data.userinfo_endpoint || `${this.authServer}/api/auth/userinfo`,
				end_session_endpoint: data.end_session_endpoint,
				revocation_endpoint: data.revocation_endpoint,
			};
		} catch (e) {
			console.warn("Discovery failed, using defaults", e);
			this.discovery = {
				issuer: this.authServer,
				authorization_endpoint: `${this.authServer}/api/auth/authorize`,
				token_endpoint: `${this.authServer}/api/auth/oauth2/token`,
				userinfo_endpoint: `${this.authServer}/api/auth/userinfo`,
			};
		}
		return this.discovery;
	}

	generatePkcePair(): { code_verifier: string; code_challenge: string } {
		const code_verifier = randomBytes(32).toString("base64url");
		const hash = createHash("sha256").update(code_verifier).digest("base64url");
		// Ensure standard base64url format (no padding)
		const code_challenge = hash.replace(/=/g, "");
		return { code_verifier, code_challenge };
	}

	generateState(): string {
		return randomBytes(24).toString("hex");
	}

	async getAuthorizationUrl(state?: string, scopes?: string[]) {
		const discovery = await this.discover();
		const { code_verifier, code_challenge } = this.generatePkcePair();
		const finalState = state || this.generateState();

		const params = new URLSearchParams({
			client_id: this.clientId,
			redirect_uri: this.redirectUri,
			response_type: "code",
			scope: (scopes || this.scopes).join(" "),
			state: finalState,
			code_challenge: code_challenge,
			code_challenge_method: "S256",
			prompt: "consent",
		});

		return {
			url: `${discovery.authorization_endpoint}?${params.toString()}`,
			state: finalState,
			code_verifier,
		};
	}

	async exchangeCode(code: string, codeVerifier: string): Promise<OAuthTokens> {
		const discovery = await this.discover();

		const body: Record<string, string> = {
			grant_type: "authorization_code",
			code,
			redirect_uri: this.redirectUri,
			// client_id is usually not needed in body for Basic Auth, but safe to include
			code_verifier: codeVerifier,
		};

		const headers: Record<string, string> = {
			"Content-Type": "application/x-www-form-urlencoded",
		};

		// Use Basic Auth for client secret
		if (this.clientId && this.clientSecret) {
			const credentials = btoa(`${this.clientId}:${this.clientSecret}`);
			headers.Authorization = `Basic ${credentials}`;
		} else {
			body.client_id = this.clientId;
		}

		const res = await fetch(discovery.token_endpoint, {
			method: "POST",
			headers,
			body: new URLSearchParams(body),
		});

		if (!res.ok) {
			const text = await res.text();
			throw new Error(`Token exchange failed: ${res.status} ${text}`);
		}

		const data = (await res.json()) as OAuthTokens;
		return {
			...data,
			expires_at: Date.now() + data.expires_in * 1000,
		};
	}

	async refreshTokens(refreshToken: string): Promise<OAuthTokens> {
		const discovery = await this.discover();

		const body: Record<string, string> = {
			grant_type: "refresh_token",
			refresh_token: refreshToken,
		};

		const headers: Record<string, string> = {
			"Content-Type": "application/x-www-form-urlencoded",
		};

		// Use Basic Auth for client secret
		if (this.clientId && this.clientSecret) {
			const credentials = btoa(`${this.clientId}:${this.clientSecret}`);
			headers.Authorization = `Basic ${credentials}`;
		} else {
			body.client_id = this.clientId;
		}

		const res = await fetch(discovery.token_endpoint, {
			method: "POST",
			headers,
			body: new URLSearchParams(body),
		});

		if (!res.ok) {
			const text = await res.text();
			throw new Error(`Token refresh failed: ${res.status} ${text}`);
		}

		const data = (await res.json()) as OAuthTokens;
		return {
			...data,
			expires_at: Date.now() + data.expires_in * 1000,
			refresh_token: data.refresh_token || refreshToken, // Keep old if not rotated
		};
	}

	async getUserInfo(accessToken: string): Promise<OAuthUser> {
		const discovery = await this.discover();
		if (!discovery.userinfo_endpoint)
			throw new Error("Userinfo endpoint not defined");

		const res = await fetch(discovery.userinfo_endpoint, {
			headers: { Authorization: `Bearer ${accessToken}` },
		});

		if (!res.ok) throw new Error(`Userinfo failed: ${res.status}`);
		return (await res.json()) as OAuthUser;
	}

	async getLogoutUrl(
		idToken?: string,
		postLogoutRedirect?: string,
	): Promise<string> {
		const discovery = await this.discover();
		// Default to /api/auth/sign-out if not in discovery
		// Better Auth uses /api/auth/sign-out for session logout, but OIDC spec uses /end-session
		// Check if end_session_endpoint is actually valid or just constructed
		const endpoint =
			discovery.end_session_endpoint || `${this.authServer}/api/auth/sign-out`;

		// If endpoint is /api/auth/oauth2/logout (Better Auth default OIDC?), it might be 404 if not enabled
		// But /api/auth/sign-out is the standard session logout endpoint

		const params = new URLSearchParams();

		// For /api/auth/sign-out, we just redirect.
		// For OIDC end-session, we pass id_token_hint etc.

		if (endpoint.includes("sign-out")) {
			// Simple session logout
			if (postLogoutRedirect) params.set("callbackURL", postLogoutRedirect);
			return `${endpoint}?${params.toString()}`;
		}

		// OIDC style
		params.set("client_id", this.clientId);
		if (idToken) params.set("id_token_hint", idToken);
		if (postLogoutRedirect)
			params.set("post_logout_redirect_uri", postLogoutRedirect);

		return `${endpoint}?${params.toString()}`;
	}
}

// =============================================================================
// Session Management (Simple In-Memory)
// =============================================================================

type SessionData = {
	oauth_state?: string;
	code_verifier?: string;
	tokens?: OAuthTokens;
	[key: string]: unknown;
};

const sessions = new Map<string, SessionData>();

function getSession(req: Request): SessionData {
	const cookieHeader = req.headers.get("Cookie");
	if (!cookieHeader) return {};

	const cookies = Object.fromEntries(
		cookieHeader.split("; ").map((c) => c.split("=")),
	) as Record<string, string>;
	const sessionId = cookies.oauth_demo_session;

	if (sessionId && sessions.has(sessionId)) {
		return sessions.get(sessionId);
	}
	return {};
}

function saveSession(
	sessionId: string | null,
	data: Partial<SessionData>,
): string {
	const id = sessionId || randomBytes(16).toString("hex");
	const existing = sessions.get(id) || {};
	sessions.set(id, { ...existing, ...data });
	return id;
}

function clearSession(req: Request) {
	const cookieHeader = req.headers.get("Cookie");
	if (!cookieHeader) return;
	const cookies = Object.fromEntries(
		cookieHeader.split("; ").map((c) => c.split("=")),
	) as Record<string, string>;
	const sessionId = cookies.oauth_demo_session;
	if (sessionId) sessions.delete(sessionId);
}

// =============================================================================
// HTML Templates
// =============================================================================

function renderPage(title: string, content: string, user?: OAuthUser) {
	const nav = user
		? `
      <div style="display: flex; align-items: center; gap: 1rem;">
          <span>👤 ${user.name || user.email}</span>
          <a href="/me" class="btn">My Profile</a>
          <a href="/refresh" class="btn btn-secondary">Refresh Token</a>
          <a href="/logout" class="btn btn-danger">Logout</a>
      </div>
      `
		: '<a href="/login" class="btn">Login with OAuth</a>';

	return new Response(
		`
    <!DOCTYPE html>
    <html>
    <head>
        <title>${title} - OAuth Demo</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                margin: 0;
                padding: 2rem;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
            }
            .card {
                background: white;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.2);
                padding: 2rem;
                margin-bottom: 1rem;
            }
            .header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 2rem;
                padding-bottom: 1rem;
                border-bottom: 1px solid #eee;
            }
            .logo {
                font-size: 1.5rem;
                font-weight: bold;
                background: linear-gradient(135deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            h1 { color: #333; margin-top: 0; }
            pre {
                background: #f4f4f4;
                padding: 1rem;
                border-radius: 8px;
                overflow-x: auto;
                font-size: 0.85rem;
            }
            .btn {
                display: inline-block;
                padding: 0.75rem 1.5rem;
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 500;
                transition: transform 0.2s, box-shadow 0.2s;
            }
            .btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
            }
            .btn-secondary {
                background: #f4f4f4;
                color: #333;
            }
            .btn-danger {
                background: #dc3545;
            }
            .info-grid {
                display: grid;
                grid-template-columns: 150px 1fr;
                gap: 0.5rem 1rem;
            }
            .info-grid dt { font-weight: 600; color: #666; }
            .info-grid dd { margin: 0; word-break: break-all; }
            .badge {
                display: inline-block;
                padding: 0.25rem 0.5rem;
                background: #e0e7ff;
                color: #3730a3;
                border-radius: 4px;
                font-size: 0.75rem;
                font-weight: 600;
            }
            .success { color: #059669; }
            .flow-diagram {
                background: #f8fafc;
                border-radius: 8px;
                padding: 1.5rem;
                margin: 1rem 0;
            }
            .flow-step {
                display: flex;
                align-items: flex-start;
                gap: 1rem;
                margin-bottom: 1rem;
            }
            .flow-number {
                width: 28px;
                height: 28px;
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                font-size: 0.85rem;
                flex-shrink: 0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <div class="header">
                    <div class="logo">🔐 OAuth 2.1 Demo (TS)</div>
                    ${nav}
                </div>
                <h1>${title}</h1>
                ${content}
            </div>
        </div>
    </body>
    </html>
  `,
		{
			headers: { "Content-Type": "text/html" },
		},
	);
}

// =============================================================================
// Application Logic
// =============================================================================

const oauth = new OAuthClient(
	AUTH_SERVER,
	CLIENT_ID,
	CLIENT_SECRET,
	REDIRECT_URI,
	SCOPES,
);

console.log(`\n${"=".repeat(70)}`);
console.log("  🚀 OAuth Demo App Running (TypeScript)");
console.log("=".repeat(70));
console.log(`  Auth Server: ${AUTH_SERVER}`);
console.log(`  Client ID:   ${CLIENT_ID}`);
console.log(`  Redirect:    ${REDIRECT_URI}`);
console.log(`  Scopes:      ${SCOPES.join(", ")}`);
console.log("=".repeat(70));
console.log(`\n  Open http://localhost:${PORT} in your browser\n`);

Bun.serve({
	port: PORT,
	async fetch(req) {
		const url = new URL(req.url);
		const session = getSession(req);
		let sessionId =
			req.headers
				.get("Cookie")
				?.split("; ")
				.find((c) => c.startsWith("oauth_demo_session="))
				?.split("=")[1] || null;

		// -----------------------------------------------------------
		// GET /
		// -----------------------------------------------------------
		if (url.pathname === "/") {
			let user: OAuthUser | undefined;
			if (session.tokens) {
				try {
					user = await oauth.getUserInfo(session.tokens.access_token);
				} catch {
					// Token likely expired
				}
			}

			if (user) {
				const content = `
                <p class="success">✅ You are logged in!</p>
                <div class="info-grid">
                    <dt>Name</dt><dd>${user.name}</dd>
                    <dt>Email</dt><dd>${user.email}</dd>
                    <dt>User ID</dt><dd><code>${user.sub}</code></dd>
                </div>
                <p style="margin-top: 2rem;">
                    <a href="/me" class="btn">View Full Profile</a>
                </p>
                `;
				return renderPage("Welcome", content, user);
			} else {
				const content = `
                <p>This demo shows the complete OAuth 2.1 Authorization Code flow with PKCE using Bun/TypeScript.</p>
                
                <div class="flow-diagram">
                    <div class="flow-step">
                        <div class="flow-number">1</div>
                        <div>
                            <strong>Click "Login with OAuth"</strong><br>
                            <small>You'll be redirected to the authorization server</small>
                        </div>
                    </div>
                    <div class="flow-step">
                        <div class="flow-number">2</div>
                        <div>
                            <strong>Authenticate</strong><br>
                            <small>Sign in with your email and password</small>
                        </div>
                    </div>
                    <div class="flow-step">
                        <div class="flow-number">3</div>
                        <div>
                            <strong>Consent & Select Organization</strong><br>
                            <small>Review permissions and choose organization context</small>
                        </div>
                    </div>
                    <div class="flow-step">
                        <div class="flow-number">4</div>
                        <div>
                            <strong>Callback</strong><br>
                            <small>You're redirected back here with tokens</small>
                        </div>
                    </div>
                </div>
                
                <p style="text-align: center; margin-top: 2rem;">
                    <a href="/login" class="btn" style="font-size: 1.1rem; padding: 1rem 2rem;">
                        🚀 Start OAuth Flow
                    </a>
                </p>
                `;
				return renderPage("Welcome", content);
			}
		}

		// -----------------------------------------------------------
		// GET /login
		// -----------------------------------------------------------
		if (url.pathname === "/login") {
			const {
				url: authUrl,
				state,
				code_verifier,
			} = await oauth.getAuthorizationUrl();

			sessionId = saveSession(sessionId, {
				oauth_state: state,
				code_verifier: code_verifier,
			});

			console.log(`\n📤 Redirecting to authorization endpoint...`);
			console.log(`   State: ${state}`);
			console.log(`   URL: ${authUrl.substring(0, 100)}...`);

			return new Response(null, {
				status: 302,
				headers: {
					Location: authUrl,
					"Set-Cookie": `oauth_demo_session=${sessionId}; Path=/; HttpOnly; SameSite=Lax`,
				},
			});
		}

		// -----------------------------------------------------------
		// GET /callback
		// -----------------------------------------------------------
		if (url.pathname === "/callback") {
			const code = url.searchParams.get("code");
			const state = url.searchParams.get("state");
			const error = url.searchParams.get("error");
			const errorDescription = url.searchParams.get("error_description");

			if (error) {
				const content = `
                <p style="color: #dc3545;">❌ Authorization failed</p>
                <div class="info-grid">
                    <dt>Error</dt><dd>${error}</dd>
                    <dt>Description</dt><dd>${errorDescription || "N/A"}</dd>
                </div>
                <p><a href="/" class="btn">Try Again</a></p>
                `;
				return renderPage("Authorization Error", content);
			}

			if (!code || !state) {
				return new Response("Missing code or state", { status: 400 });
			}

			const storedState = session.oauth_state;
			const codeVerifier = session.code_verifier;

			if (state !== storedState) {
				return new Response("Invalid state parameter", { status: 400 });
			}

			console.log(`\n📥 Received callback!`);
			console.log(`   Code: ${code.substring(0, 20)}...`);
			console.log(`   State: ${state}`);

			try {
				const tokens = await oauth.exchangeCode(code, codeVerifier);

				console.log(`\n✅ Tokens received!`);
				console.log(
					`   Access Token: ${tokens.access_token.substring(0, 30)}...`,
				);

				sessionId = saveSession(sessionId, {
					tokens: tokens,
					oauth_state: undefined, // Clear state
					code_verifier: undefined, // Clear verifier
				});

				return new Response(null, {
					status: 302,
					headers: {
						Location: "/me",
						"Set-Cookie": `oauth_demo_session=${sessionId}; Path=/; HttpOnly; SameSite=Lax`,
					},
				});
			} catch (e: unknown) {
				const content = `
                <p style="color: #dc3545;">❌ Token exchange failed</p>
                <pre>${getErrorMessage(e)}</pre>
                <p><a href="/" class="btn">Try Again</a></p>
                `;
				return renderPage("Token Error", content);
			}
		}

		// -----------------------------------------------------------
		// GET /me
		// -----------------------------------------------------------
		if (url.pathname === "/me") {
			const tokens = session.tokens as OAuthTokens | undefined;
			if (!tokens)
				return new Response(null, {
					status: 302,
					headers: { Location: "/login" },
				});

			try {
				const user = await oauth.getUserInfo(tokens.access_token);

				const { sub, name, email, email_verified, picture, ...extra } = user;

				const content = `
                <div class="info-grid">
                    <dt>User ID (sub)</dt><dd><code>${sub}</code></dd>
                    <dt>Name</dt><dd>${name || "N/A"}</dd>
                    <dt>Email</dt><dd>${email || "N/A"}</dd>
                    <dt>Email Verified</dt><dd>${email_verified ? "✅ Yes" : "❌ No"}</dd>
                    <dt>Picture</dt><dd>${picture ? `<img src="${picture}" width="50" style="border-radius: 50%">` : "N/A"}</dd>
                </div>

                <h3 style="margin-top: 2rem;">🎫 Token Info</h3>
                <div class="info-grid">
                    <dt>Access Token</dt><dd><code style="font-size: 0.7rem;">${tokens.access_token.substring(0, 50)}...</code></dd>
                    <dt>Refresh Token</dt><dd><code style="font-size: 0.7rem;">${tokens.refresh_token ? `${tokens.refresh_token.substring(0, 50)}...` : "None"}</code></dd>
                    <dt>ID Token</dt><dd>${tokens.id_token ? "Present ✅" : "None"}</dd>
                    <dt>Expires In</dt><dd>${Math.floor(((tokens.expires_at || 0) - Date.now()) / 1000)}s</dd>
                </div>

                <h3 style="margin-top: 2rem;">📦 Additional Claims</h3>
                <pre>${JSON.stringify(extra, null, 2)}</pre>
                `;

				return renderPage("My Profile", content, user);
			} catch {
				if (tokens.refresh_token) {
					return new Response(null, {
						status: 302,
						headers: { Location: "/refresh" },
					});
				}
				return new Response(null, {
					status: 302,
					headers: { Location: "/login" },
				});
			}
		}

		// -----------------------------------------------------------
		// GET /refresh
		// -----------------------------------------------------------
		if (url.pathname === "/refresh") {
			const tokens = session.tokens as OAuthTokens | undefined;
			if (!tokens || !tokens.refresh_token) {
				return new Response(null, {
					status: 302,
					headers: { Location: "/login" },
				});
			}

			try {
				const newTokens = await oauth.refreshTokens(tokens.refresh_token);

				sessionId = saveSession(sessionId, {
					tokens: {
						...newTokens,
						// Ensure we keep refresh token if not returned (some servers don't rotate)
						refresh_token: newTokens.refresh_token || tokens.refresh_token,
					},
				});

				const content = `
                <p class="success">✅ Token refreshed successfully!</p>
                <p><a href="/me" class="btn">View Profile</a></p>
                `;
				return renderPage("Token Refreshed", content);
			} catch (e: unknown) {
				const content = `
                <p style="color: #dc3545;">❌ Token refresh failed: ${getErrorMessage(e)}</p>
                <p><a href="/login" class="btn">Login Again</a></p>
                `;
				return renderPage("Refresh Error", content);
			}
		}

		// -----------------------------------------------------------
		// GET /logout
		// -----------------------------------------------------------
		if (url.pathname === "/logout") {
			const tokens = session.tokens as OAuthTokens | undefined;

			// Try to revoke if we have a refresh token (best effort)
			// Note: We don't implement revoke in this simple demo script but typically you would.

			const idToken = tokens?.id_token;
			clearSession(req);

			const logoutUrl = await oauth.getLogoutUrl(
				idToken,
				`http://localhost:${PORT}`,
			);

			// Clear the cookie in browser
			return new Response(null, {
				status: 302,
				headers: {
					Location: logoutUrl,
					"Set-Cookie": "oauth_demo_session=; Path=/; HttpOnly; Max-Age=0",
				},
			});
		}

		return new Response("Not Found", { status: 404 });
	},
});
