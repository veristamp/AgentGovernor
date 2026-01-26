#!/usr/bin/env bun
/**
 * OAuth 2.1 / OIDC User Flow Demo (Minimal) - Bun
 *
 * Endpoints:
 * - GET  /         Home (login button / logged-in view)
 * - GET  /login    Start auth code + PKCE flow (redirect to auth server)
 * - GET  /callback OAuth callback (exchange code -> tokens)
 * - GET  /me       Fetch and display userinfo
 * - GET  /refresh  Refresh access token (requires offline_access)
 * - GET  /logout   Clear local session (optionally redirect to end_session)
 *
 * Prereqs (env):
 * - OAUTH_AUTH_SERVER       (default: http://localhost:8787)
 * - OAUTH_CLIENT_ID
 * - OAUTH_CLIENT_SECRET     (optional for public clients)
 * - OAUTH_REDIRECT_URI      (default: http://localhost:9000/callback)
 * - OAUTH_SCOPES            (default: "openid profile email offline_access")
 *
 * Run:
 *   bun run examples/oauth_user_flow_demo.ts
 */

import { decodeJWT, MCPAdminClient, MCPAgentClient } from "../src/core/auth";

type OIDCDiscovery = {
	issuer?: string;
	authorization_endpoint?: string;
	token_endpoint?: string;
	userinfo_endpoint?: string;
	end_session_endpoint?: string;
};

type TokenResponse = {
	access_token: string;
	token_type?: string;
	expires_in?: number;
	refresh_token?: string;
	id_token?: string;
	scope?: string;
};

type SessionData = {
	state?: string;
	codeVerifier?: string;
	tokens?: {
		accessToken: string;
		expiresAt: number;
		refreshToken?: string;
		idToken?: string;
	};
};

const AUTH_SERVER = (
	process.env.OAUTH_AUTH_SERVER ?? "http://localhost:8787"
).replace(/\/$/, "");
let CLIENT_ID = process.env.OAUTH_CLIENT_ID ?? "";
let CLIENT_SECRET = process.env.OAUTH_CLIENT_SECRET ?? "";
const REDIRECT_URI =
	process.env.OAUTH_REDIRECT_URI ?? "http://localhost:9000/callback";
const APP_ORIGIN = new URL(REDIRECT_URI).origin;
const SCOPES = (
	process.env.OAUTH_SCOPES ?? "openid profile email offline_access"
)
	.split(/\s+/)
	.filter(Boolean);

const PORT = Number(process.env.OAUTH_DEMO_PORT ?? "9000");
const COOKIE_NAME = "oauth_demo_sid";

const SUPER_ADMIN_EMAIL = process.env.SUPER_ADMIN_EMAIL ?? "";
const SUPER_ADMIN_PASSWORD = process.env.SUPER_ADMIN_PASSWORD ?? "";
const DEMO_AUDIENCE =
	process.env.OAUTH_DEMO_AUDIENCE ?? "mcp://oauth-user-flow-demo";

const sessions = new Map<string, SessionData>();

function htmlPage(title: string, body: string): Response {
	const html = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${escapeHtml(title)}</title>
    <style>
      body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 2rem; line-height: 1.4; }
      a { color: #0b57d0; }
      code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
      pre { padding: 12px; background: #f6f8fa; border-radius: 8px; overflow-x: auto; }
      .row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
      .btn { display: inline-block; padding: 10px 14px; border-radius: 8px; background: #111; color: #fff; text-decoration: none; }
      .btn.secondary { background: #f1f3f4; color: #111; }
      .btn.danger { background: #b42318; }
      .muted { color: #666; }
      .card { max-width: 920px; padding: 16px 18px; border: 1px solid #e5e7eb; border-radius: 12px; }
      dt { font-weight: 600; }
      dd { margin: 0 0 10px 0; word-break: break-word; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1 style="margin-top:0">${escapeHtml(title)}</h1>
      ${body}
    </div>
  </body>
</html>`;

	return new Response(html, {
		headers: {
			"content-type": "text/html; charset=utf-8",
		},
	});
}

function escapeHtml(s: string): string {
	return s
		.replaceAll("&", "&amp;")
		.replaceAll("<", "&lt;")
		.replaceAll(">", "&gt;")
		.replaceAll('"', "&quot;")
		.replaceAll("'", "&#39;");
}

function base64UrlEncode(bytes: Uint8Array): string {
	return Buffer.from(bytes)
		.toString("base64")
		.replace(/\+/g, "-")
		.replace(/\//g, "_")
		.replace(/=+$/g, "");
}

function randomId(bytes: number = 32): string {
	const b = new Uint8Array(bytes);
	crypto.getRandomValues(b);
	return base64UrlEncode(b);
}

async function sha256Base64Url(input: string): Promise<string> {
	const data = new TextEncoder().encode(input);
	const digest = await crypto.subtle.digest("SHA-256", data);
	return base64UrlEncode(new Uint8Array(digest));
}

function parseCookies(req: Request): Record<string, string> {
	const header = req.headers.get("cookie");
	if (!header) {
		return {};
	}

	const out: Record<string, string> = {};
	for (const part of header.split(";")) {
		const idx = part.indexOf("=");
		if (idx === -1) {
			continue;
		}
		const name = part.slice(0, idx).trim();
		const value = part.slice(idx + 1).trim();
		if (name) {
			out[name] = value;
		}
	}
	return out;
}

function getOrCreateSession(req: Request): {
	sid: string;
	session: SessionData;
} {
	const cookies = parseCookies(req);
	const sid = cookies[COOKIE_NAME];
	const existingSession = sid ? sessions.get(sid) : undefined;
	if (sid && existingSession) {
		return { sid, session: existingSession };
	}

	const newSid = randomId(24);
	const session: SessionData = {};
	sessions.set(newSid, session);
	return { sid: newSid, session };
}

function withSessionCookie(headers: Headers, sid: string): void {
	// Demo-only cookie. In production: Secure + signed/encrypted cookie or server-side store.
	headers.append(
		"set-cookie",
		`${COOKIE_NAME}=${sid}; Path=/; HttpOnly; SameSite=Lax`,
	);
}

async function discover(
	authServer: string,
): Promise<
	Required<Pick<OIDCDiscovery, "authorization_endpoint" | "token_endpoint">> &
		OIDCDiscovery
> {
	try {
		const res = await fetch(`${authServer}/.well-known/openid-configuration`, {
			headers: { Accept: "application/json" },
		});
		if (res.ok) {
			const d = (await res.json()) as OIDCDiscovery;
			if (d.authorization_endpoint && d.token_endpoint) {
				return d as Required<
					Pick<OIDCDiscovery, "authorization_endpoint" | "token_endpoint">
				> &
					OIDCDiscovery;
			}
		}
	} catch {
		// Ignore and fall back.
	}

	return {
		authorization_endpoint: `${authServer}/api/auth/oauth2/authorize`,
		token_endpoint: `${authServer}/api/auth/oauth2/token`,
		userinfo_endpoint: `${authServer}/api/auth/oauth2/userinfo`,
	};
}

function redirect(location: string, headers?: Headers): Response {
	const h = headers ?? new Headers();
	h.set("location", location);
	return new Response(null, { status: 302, headers: h });
}

async function tokenRequest(
	tokenEndpoint: string,
	params: Record<string, string>,
): Promise<TokenResponse> {
	const form = new URLSearchParams();
	for (const [k, v] of Object.entries(params)) {
		form.set(k, v);
	}

	const res = await fetch(tokenEndpoint, {
		method: "POST",
		headers: {
			"content-type": "application/x-www-form-urlencoded",
			Origin: APP_ORIGIN,
		},
		body: form,
	});

	const text = await res.text();
	let data: unknown;
	try {
		data = JSON.parse(text);
	} catch {
		throw new Error(`Token endpoint returned non-JSON (${res.status})`);
	}

	if (!res.ok) {
		const err = data as Record<string, unknown>;
		const msg =
			(typeof err.error_description === "string" && err.error_description) ||
			(typeof err.error === "string" && err.error) ||
			`Token request failed (${res.status})`;
		throw new Error(msg);
	}

	const tr = data as TokenResponse;
	if (!tr.access_token) {
		throw new Error("Token response missing access_token");
	}

	return tr;
}

function isExpired(expiresAt: number): boolean {
	return Date.now() / 1000 >= expiresAt - 15;
}

async function fetchUserInfo(userinfoEndpoint: string, accessToken: string) {
	const res = await fetch(userinfoEndpoint, {
		headers: {
			Authorization: `Bearer ${accessToken}`,
			Accept: "application/json",
		},
	});
	if (!res.ok) {
		throw new Error(`userinfo failed (${res.status})`);
	}
	return (await res.json()) as Record<string, unknown>;
}

async function provisionClientIdIfNeeded(): Promise<void> {
	if (CLIENT_ID) {
		return;
	}

	if (!SUPER_ADMIN_EMAIL || !SUPER_ADMIN_PASSWORD) {
		console.error(
			"Missing OAUTH_CLIENT_ID, and no SUPER_ADMIN_EMAIL/PASSWORD to auto-provision.",
		);
		console.error(
			"Either set OAUTH_CLIENT_ID (and optionally OAUTH_CLIENT_SECRET) OR set SUPER_ADMIN_EMAIL + SUPER_ADMIN_PASSWORD.",
		);
		process.exit(1);
	}

	console.log("\nAuto-provisioning OAuth client via admin + REG_JWT...");

	const admin = new MCPAdminClient({ authServer: AUTH_SERVER });
	const ok = await admin.login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD);
	if (!ok) {
		console.error("Admin login failed; cannot auto-provision client.");
		process.exit(1);
	}

	const uniqueSlug = `oauth-demo-${Date.now()}`;
	const { status: orgStatus, data: orgData } = await admin.request<{
		id?: string;
		organization?: { id: string };
	}>("POST", "/api/auth/organization/create", {
		name: `OAuth Demo Org ${uniqueSlug}`,
		slug: uniqueSlug,
	});
	if (orgStatus !== 200 && orgStatus !== 201) {
		console.error(`Create org failed: ${orgStatus}`);
		process.exit(1);
	}
	const orgId = orgData.id ?? orgData.organization?.id;
	if (!orgId) {
		console.error("Create org returned no org id");
		process.exit(1);
	}

	const invite = await admin.createInvite({
		orgId,
		budget: 1,
		ttlSeconds: 900,
		allowedScopes: SCOPES,
		allowedAudiences: [DEMO_AUDIENCE],
		allowedRoles: [],
	});

	const registrar = new MCPAgentClient({
		authServer: AUTH_SERVER,
		regJwt: invite.token,
	});
	const creds = await registrar.register("oauth-demo-web-app", {
		isPublic: false,
		redirectUris: [REDIRECT_URI],
		metadata: { purpose: "oauth_user_flow_demo" },
	});

	CLIENT_ID = creds.clientId;
	CLIENT_SECRET = creds.clientSecret;

	console.log("✅ OAuth client provisioned");
	console.log(`   client_id: ${CLIENT_ID}`);
	console.log(`   client_secret: ${CLIENT_SECRET ? "(present)" : "(none)"}`);
}

async function main(): Promise<void> {
	await provisionClientIdIfNeeded();

	const discovery = await discover(AUTH_SERVER);

	console.log("OAuth Demo (Bun)\n");
	console.log(`Auth Server:   ${AUTH_SERVER}`);
	console.log(`Client ID:     ${CLIENT_ID}`);
	console.log(`Redirect URI:  ${REDIRECT_URI}`);
	console.log(`Scopes:        ${SCOPES.join(" ")}`);
	console.log(`Authorize:     ${discovery.authorization_endpoint}`);
	console.log(`Token:         ${discovery.token_endpoint}`);
	console.log(
		`Userinfo:      ${discovery.userinfo_endpoint ?? "(not provided)"}`,
	);
	console.log(`\nOpen ${APP_ORIGIN}\n`);

	Bun.serve({
		port: PORT,
		fetch: async (req) => {
			const url = new URL(req.url);
			const { sid, session } = getOrCreateSession(req);
			const headers = new Headers();
			withSessionCookie(headers, sid);

			try {
				if (url.pathname === "/") {
					const tokens = session.tokens;
					if (!tokens) {
						return htmlPage(
							"Welcome",
							`<p class="muted">OAuth 2.1 Authorization Code + PKCE demo.</p>
<div class="row">
  <a class="btn" href="/login">Login</a>
</div>`,
						);
					}

					let meHtml = "";
					if (discovery.userinfo_endpoint) {
						try {
							const me = await fetchUserInfo(
								discovery.userinfo_endpoint,
								tokens.accessToken,
							);
							meHtml = `<dl>
  <dt>sub</dt><dd><code>${escapeHtml(String(me.sub ?? ""))}</code></dd>
  <dt>email</dt><dd>${escapeHtml(String(me.email ?? ""))}</dd>
  <dt>name</dt><dd>${escapeHtml(String(me.name ?? ""))}</dd>
</dl>`;
						} catch (e) {
							meHtml = `<p class="muted">userinfo failed: ${escapeHtml(String(e))}</p>`;
						}
					}

					return htmlPage(
						"Logged In",
						`${meHtml}
<div class="row">
  <a class="btn" href="/me">/me</a>
  <a class="btn secondary" href="/refresh">Refresh Token</a>
  <a class="btn danger" href="/logout">Logout</a>
</div>`,
					);
				}

				if (url.pathname === "/login") {
					const state = randomId(16);
					const codeVerifier = randomId(48);
					const codeChallenge = await sha256Base64Url(codeVerifier);

					session.state = state;
					session.codeVerifier = codeVerifier;

					const authUrl = new URL(discovery.authorization_endpoint);
					authUrl.searchParams.set("response_type", "code");
					authUrl.searchParams.set("client_id", CLIENT_ID);
					authUrl.searchParams.set("redirect_uri", REDIRECT_URI);
					authUrl.searchParams.set("scope", SCOPES.join(" "));
					authUrl.searchParams.set("state", state);
					authUrl.searchParams.set("code_challenge", codeChallenge);
					authUrl.searchParams.set("code_challenge_method", "S256");

					return redirect(authUrl.toString(), headers);
				}

				if (url.pathname === "/callback") {
					const error = url.searchParams.get("error");
					const errorDescription = url.searchParams.get("error_description");
					if (error) {
						return htmlPage(
							"Authorization Error",
							`<p><strong>error</strong>: ${escapeHtml(error)}</p>
<p><strong>error_description</strong>: ${escapeHtml(errorDescription ?? "")}</p>
<p><a href="/">Home</a></p>`,
						);
					}

					const code = url.searchParams.get("code") ?? "";
					const state = url.searchParams.get("state") ?? "";
					if (!code) {
						return new Response("Missing code", { status: 400, headers });
					}
					if (!session.state || state !== session.state) {
						return new Response("Invalid state", { status: 400, headers });
					}
					if (!session.codeVerifier) {
						return new Response("Missing PKCE verifier", {
							status: 400,
							headers,
						});
					}

					const tokenParams: Record<string, string> = {
						grant_type: "authorization_code",
						client_id: CLIENT_ID,
						redirect_uri: REDIRECT_URI,
						code,
						code_verifier: session.codeVerifier,
					};
					if (CLIENT_SECRET) {
						tokenParams.client_secret = CLIENT_SECRET;
					}

					const tr = await tokenRequest(discovery.token_endpoint, tokenParams);
					const expiresIn = tr.expires_in ?? 3600;
					session.tokens = {
						accessToken: tr.access_token,
						expiresAt: Date.now() / 1000 + expiresIn,
						refreshToken: tr.refresh_token,
						idToken: tr.id_token,
					};

					// Clear one-time values
					delete session.state;
					delete session.codeVerifier;

					return redirect("/me", headers);
				}

				if (url.pathname === "/me") {
					const tokens = session.tokens;
					if (!tokens) {
						return redirect("/login", headers);
					}

					if (isExpired(tokens.expiresAt) && tokens.refreshToken) {
						return redirect("/refresh", headers);
					}

					let userinfo: Record<string, unknown> | null = null;
					let userinfoError: string | null = null;
					if (discovery.userinfo_endpoint) {
						try {
							userinfo = await fetchUserInfo(
								discovery.userinfo_endpoint,
								tokens.accessToken,
							);
						} catch (e) {
							userinfoError = String(e);
						}
					}

					const idClaims = tokens.idToken ? decodeJWT(tokens.idToken) : null;
					const userBlock = userinfo
						? `<pre>${escapeHtml(JSON.stringify(userinfo, null, 2))}</pre>`
						: idClaims
							? `<p class="muted">userinfo unavailable; showing decoded id_token (unverified).</p><pre>${escapeHtml(JSON.stringify(idClaims, null, 2))}</pre>`
							: `<p class="muted">No userinfo endpoint available${userinfoError ? `: ${escapeHtml(userinfoError)}` : ""}</p>`;

					const body = `<div class="row" style="margin-bottom: 12px">
  <a class="btn secondary" href="/">Home</a>
  <a class="btn secondary" href="/refresh">Refresh</a>
  <a class="btn danger" href="/logout">Logout</a>
</div>

<h3>User</h3>
${userBlock}

<h3>Tokens (truncated)</h3>
<dl>
  <dt>access_token</dt><dd><code>${escapeHtml(tokens.accessToken.slice(0, 32))}...</code></dd>
  <dt>refresh_token</dt><dd><code>${escapeHtml(tokens.refreshToken ? `${tokens.refreshToken.slice(0, 16)}...` : "(none)")}</code></dd>
  <dt>id_token</dt><dd><code>${escapeHtml(tokens.idToken ? "present" : "(none)")}</code></dd>
  <dt>expires_at</dt><dd><code>${escapeHtml(new Date(tokens.expiresAt * 1000).toISOString())}</code></dd>
</dl>`;

					return htmlPage("/me", body);
				}

				if (url.pathname === "/refresh") {
					const tokens = session.tokens;
					if (!tokens?.refreshToken) {
						return redirect("/me", headers);
					}

					const tokenParams: Record<string, string> = {
						grant_type: "refresh_token",
						client_id: CLIENT_ID,
						refresh_token: tokens.refreshToken,
					};
					if (CLIENT_SECRET) {
						tokenParams.client_secret = CLIENT_SECRET;
					}

					const tr = await tokenRequest(discovery.token_endpoint, tokenParams);
					const expiresIn = tr.expires_in ?? 3600;
					session.tokens = {
						accessToken: tr.access_token,
						expiresAt: Date.now() / 1000 + expiresIn,
						refreshToken: tr.refresh_token ?? tokens.refreshToken,
						idToken: tr.id_token ?? tokens.idToken,
					};
					return redirect("/me", headers);
				}

				if (url.pathname === "/logout") {
					const idToken = session.tokens?.idToken;
					session.tokens = undefined;
					session.state = undefined;
					session.codeVerifier = undefined;

					if (discovery.end_session_endpoint && idToken) {
						const end = new URL(discovery.end_session_endpoint);
						end.searchParams.set("id_token_hint", idToken);
						end.searchParams.set("post_logout_redirect_uri", `${APP_ORIGIN}/`);
						return redirect(end.toString(), headers);
					}

					return redirect("/", headers);
				}

				return new Response("Not Found", { status: 404, headers });
			} catch (e) {
				return htmlPage(
					"Error",
					`<pre>${escapeHtml(e instanceof Error ? (e.stack ?? e.message) : String(e))}</pre>
<p><a href="/">Home</a></p>`,
				);
			}
		},
	});
}

await main();
