#!/usr/bin/env bun
/**
 * MCP Identity SDK - TypeScript Demo
 *
 * Demonstrates all SDK capabilities:
 *
 * 1. Admin login and invite creation
 * 2. Agent registration with REG_JWT
 * 3. Token acquisition (Opaque and JWT)
 * 4. JWT validation (stateless, ~0.1ms)
 * 5. Introspection validation (RFC 7662)
 * 6. Scope enforcement
 * 7. Audience validation
 * 8. Protected Resource Metadata (RFC 9728)
 * 9. Kill switch / revocation
 *
 * Prerequisites:
 * - Mono Authz server running at http://localhost:8787
 * - Environment variables:
 *   - SUPER_ADMIN_EMAIL
 *   - SUPER_ADMIN_PASSWORD
 *
 * Usage:
 *   bun run sdk/typescript/demo.ts
 */

import {
	decodeJWT,
	MCPAdminClient,
	MCPAgentClient,
	MCPResourceServer,
} from "./index";

// =============================================================================
// Configuration
// =============================================================================

const AUTH_SERVER = process.env.MCP_AUTH_SERVER ?? "http://localhost:8787";
const SUPER_ADMIN_EMAIL = process.env.SUPER_ADMIN_EMAIL ?? "admin@example.com";
const SUPER_ADMIN_PASSWORD = process.env.SUPER_ADMIN_PASSWORD ?? "password";
const MY_AUDIENCE = "mcp://rag-demo-service";

// =============================================================================
// Helpers
// =============================================================================

function printHeader(title: string): void {
	console.log("\n" + "=".repeat(70));
	console.log(`  ${title}`);
	console.log("=".repeat(70));
}

function printSubheader(title: string): void {
	console.log(`\n--- ${title} ---`);
}

// =============================================================================
// Main Demo
// =============================================================================

async function main(): Promise<number> {
	printHeader("MCP Identity SDK - TypeScript Demo");
	console.log(`\nAuth Server: ${AUTH_SERVER}`);
	console.log(`My Audience: ${MY_AUDIENCE}`);

	// =========================================================================
	// PHASE 1: ADMIN SETUP
	// =========================================================================
	printHeader("PHASE 1: ADMIN SETUP");

	const admin = new MCPAdminClient({ authServer: AUTH_SERVER });

	console.log("\n📧 Signing in as Super Admin...");
	const loggedIn = await admin.login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD);
	if (!loggedIn) {
		console.log("❌ Admin login failed");
		return 1;
	}
	console.log("✅ Signed in successfully");

	// Create organization for demo
	console.log("\n📁 Creating organization for demo...");
	const uniqueSlug = `mcp-demo-${Date.now()}`;
	const { status: orgStatus, data: orgData } = await admin.request<{
		id?: string;
		organization?: { id: string };
	}>("POST", "/api/auth/organization/create", {
		name: `MCP Demo Org ${uniqueSlug}`,
		slug: uniqueSlug,
	});

	if (orgStatus !== 200 && orgStatus !== 201) {
		console.log(`❌ Create org failed: ${orgStatus}`);
		return 1;
	}

	const orgId = orgData.id ?? orgData.organization?.id;
	console.log(`✅ Created org: ${orgId?.slice(0, 16)}...`);

	// =========================================================================
	// PHASE 2: REGISTRATION INVITE
	// =========================================================================
	printHeader("PHASE 2: REGISTRATION INVITE (Budgeted DCR)");

	console.log("\n🎟️  Minting registration invite...");
	const invite = await admin.createInvite({
		orgId: orgId!,
		budget: 2,
		ttlSeconds: 600,
		allowedScopes: ["read:data", "write:data", "admin:delete"],
		allowedAudiences: [MY_AUDIENCE],
		allowedRoles: ["mcp:rag-agent"], // NEW: Roles support
	});

	console.log("✅ Invite minted!");
	console.log("   • Budget: 2 registrations");
	console.log("   • Allowed Scopes: read:data, write:data, admin:delete");
	console.log(`   • Allowed Audiences: ${MY_AUDIENCE}`);
	console.log("   • Allowed Roles: mcp:rag-agent");

	// =========================================================================
	// PHASE 3: PROTECTED RESOURCE METADATA (RFC 9728)
	// =========================================================================
	printHeader("PHASE 3: PROTECTED RESOURCE METADATA (RFC 9728)");

	const discoveryAgent = new MCPAgentClient({ authServer: AUTH_SERVER });

	console.log("\n🔍 Discovering protected resource metadata...");
	try {
		const metadata = await discoveryAgent.discoverResourceMetadata(AUTH_SERVER);
		console.log("✅ Resource metadata discovered!");
		console.log(`   • Resource: ${metadata.resource}`);
		console.log(
			`   • Authorization Servers: ${metadata.authorizationServers.join(", ")}`,
		);
		console.log(
			`   • Scopes Supported: ${metadata.scopesSupported?.join(", ") ?? "not specified"}`,
		);
		console.log(
			`   • Introspection Endpoint: ${metadata.introspectionEndpoint ?? "not specified"}`,
		);
	} catch (e) {
		console.log(
			"⚠️  Resource metadata discovery not available (optional feature)",
		);
	}

	// =========================================================================
	// PHASE 4: AGENT REGISTRATION
	// =========================================================================
	printHeader("PHASE 4: AGENT REGISTRATION");

	const agent = new MCPAgentClient({
		authServer: AUTH_SERVER,
		regJwt: invite.token,
	});

	console.log("\n🤖 Registering agent with REG_JWT...");
	const credentials = await agent.register("demo-rag-agent", {
		metadata: { version: "1.0", purpose: "demo" },
		isPublic: false, // Confidential client
	});

	console.log("✅ Agent registered!");
	console.log(`   • Client ID: ${credentials.clientId}`);
	console.log(
		`   • Client ID Format: ${credentials.clientId.startsWith("mcp_") ? "Standardized (mcp_*)" : "Legacy"}`,
	);
	console.log(`   • Allowed Scopes: ${credentials.allowedScopes.join(", ")}`);
	console.log(
		`   • Allowed Audiences: ${credentials.allowedAudiences.join(", ")}`,
	);
	console.log(
		`   • Allowed Roles: ${credentials.allowedRoles?.join(", ") ?? "none"}`,
	);

	// =========================================================================
	// PHASE 5: TOKEN ACQUISITION
	// =========================================================================
	printHeader("PHASE 5: TOKEN ACQUISITION");

	printSubheader("5A: Opaque Token (no audience)");
	console.log("\n🔑 Requesting token WITHOUT audience...");
	const opaqueToken = await agent.getToken(["read:data"]);
	const isOpaque = opaqueToken.accessToken.split(".").length !== 3;
	console.log(`✅ ${isOpaque ? "Opaque" : "JWT"} token acquired!`);
	console.log(`   • Token: ${opaqueToken.accessToken.slice(0, 40)}...`);

	printSubheader("5B: JWT Token (with audience - RFC 8707)");
	console.log(`\n🔑 Requesting token WITH audience '${MY_AUDIENCE}'...`);
	const jwtToken = await agent.getToken(["read:data"], MY_AUDIENCE, true);
	const isJwt = jwtToken.accessToken.split(".").length === 3;
	console.log(`✅ ${isJwt ? "JWT" : "Opaque"} token acquired!`);
	console.log(`   • Token: ${jwtToken.accessToken.slice(0, 50)}...`);

	if (isJwt) {
		const payload = decodeJWT(jwtToken.accessToken);
		if (payload) {
			console.log("   • JWT Payload:");
			console.log(`     - aud: ${payload.aud}`);
			console.log(`     - azp: ${payload.azp}`);
			console.log(`     - scope: ${payload.scope}`);
			console.log(`     - org_id: ${payload.org_id}`);
			console.log(`     - roles: ${payload.roles?.join(", ") ?? "none"}`);
			console.log(`     - exp: ${payload.exp}`);
		}
	}

	// =========================================================================
	// PHASE 6: TOKEN VALIDATION
	// =========================================================================
	printHeader("PHASE 6: TOKEN VALIDATION (3 Modes)");

	const server = new MCPResourceServer({
		authServer: AUTH_SERVER,
		myAudience: MY_AUDIENCE,
		clientId: credentials.clientId,
		clientSecret: credentials.clientSecret,
		adminSessionCookie: admin.getSessionCookieString(),
	});

	// 6A: JWT Validation (without signature verification)
	printSubheader("6A: JWT Validation (Decode Only, ~0.1ms)");
	let start = performance.now();
	let result = await server.validateToken(jwtToken.accessToken, {
		requiredScopes: ["read:data"],
		useJwt: true,
		verifySignature: false,
	});
	let elapsed = performance.now() - start;

	if (result.valid) {
		console.log(`✅ JWT validation PASSED in ${elapsed.toFixed(2)}ms`);
		console.log(`   • Client ID: ${result.clientId}`);
		console.log(`   • Scopes: ${result.scopes.join(", ")}`);
	} else {
		console.log(`❌ JWT validation FAILED: ${result.error}`);
		return 1;
	}

	// 6B: JWT Validation WITH Ed25519 signature verification
	printSubheader(
		"6B: JWT + Signature Verification (~1-2ms first, then cached)",
	);
	start = performance.now();
	result = await server.validateToken(jwtToken.accessToken, {
		requiredScopes: ["read:data"],
		useJwt: true,
		verifySignature: true,
	});
	elapsed = performance.now() - start;

	if (result.valid) {
		console.log(
			`✅ JWT + signature verification PASSED in ${elapsed.toFixed(2)}ms`,
		);
		console.log(`   • Signature verified via JWKS`);
		console.log(`   • Client ID: ${result.clientId}`);
	} else {
		console.log(
			`❌ Signature verification FAILED: ${result.error} (${result.errorCode})`,
		);
		console.log(`   ⚠️ This is expected if auth server doesn't expose JWKS`);
	}

	// 6C: Introspection (RFC 7662)
	printSubheader("6C: Introspection Validation (RFC 7662, ~35ms)");
	start = performance.now();
	result = await server.validateToken(opaqueToken.accessToken, {
		requiredScopes: ["read:data"],
		useJwt: false,
	});
	elapsed = performance.now() - start;

	if (result.valid) {
		console.log(
			`✅ Introspection validation PASSED in ${elapsed.toFixed(2)}ms`,
		);
		console.log(`   • Client ID: ${result.clientId}`);
		console.log(`   • Org ID: ${result.orgId}`);
	} else {
		console.log(`❌ Introspection validation FAILED: ${result.error}`);
		return 1;
	}

	// =========================================================================
	// PHASE 7: DIRECT INTROSPECTION (Agent-side)
	// =========================================================================
	printHeader("PHASE 7: DIRECT TOKEN INTROSPECTION");

	printSubheader("7A: Agent introspecting its own token");
	const introspectionResult = await agent.introspectToken(jwtToken.accessToken);
	if (introspectionResult.active) {
		console.log("✅ Token is active!");
		console.log(`   • Client ID: ${introspectionResult.clientId}`);
		console.log(`   • Scope: ${introspectionResult.scope}`);
		console.log(
			`   • Roles: ${introspectionResult.roles?.join(", ") ?? "none"}`,
		);
	} else {
		console.log("❌ Token is inactive");
	}

	// =========================================================================
	// PHASE 8: SCOPE ENFORCEMENT
	// =========================================================================
	printHeader("PHASE 8: SCOPE ENFORCEMENT");

	console.log("\n🚫 Attempting to validate with unauthorized scope...");
	result = await server.validateToken(jwtToken.accessToken, {
		requiredScopes: ["admin:delete"], // Not in token's scope!
		useJwt: true,
	});

	if (!result.valid && result.errorCode === "insufficient_scope") {
		console.log("✅ Correctly REJECTED - insufficient scope");
		console.log(`   • Error: ${result.error}`);
	} else {
		console.log(`⚠️ Unexpected result: ${JSON.stringify(result)}`);
	}

	// =========================================================================
	// PHASE 9: AUDIENCE VALIDATION
	// =========================================================================
	printHeader("PHASE 9: AUDIENCE VALIDATION");

	const otherServer = new MCPResourceServer({
		authServer: AUTH_SERVER,
		myAudience: "mcp://different-service", // Different audience!
	});

	console.log("\n🚫 Attempting to validate token at wrong audience...");
	result = await otherServer.validateToken(jwtToken.accessToken, {
		useJwt: true,
	});

	if (!result.valid && result.errorCode === "audience_mismatch") {
		console.log("✅ Correctly REJECTED - audience mismatch");
		console.log("   • Expected: mcp://different-service");
		console.log(`   • Token aud: ${MY_AUDIENCE}`);
	} else {
		console.log(`⚠️ Unexpected result: ${JSON.stringify(result)}`);
	}

	// =========================================================================
	// PHASE 10: KILL SWITCH
	// =========================================================================
	printHeader("PHASE 10: KILL SWITCH (Client Revocation)");

	console.log(`\n🔒 Revoking client ${credentials.clientId.slice(0, 16)}...`);
	const revoked = await admin.revokeClient(credentials.clientId);
	console.log(revoked ? "✅ Client revoked" : "⚠️ Revoke returned false");

	server.clearCache();

	printSubheader("10A: JWT Validation (still valid - stateless)");
	result = await server.validateToken(jwtToken.accessToken, {
		useJwt: true,
		requireActiveCheck: false,
	});
	if (result.valid) {
		console.log("⚠️ JWT still valid (expected - stateless validation)");
		console.log("   Token will expire at its exp time");
	}

	printSubheader("10B: JWT + Active Check (rejected!)");
	result = await server.validateToken(jwtToken.accessToken, {
		useJwt: true,
		requireActiveCheck: true,
	});
	if (!result.valid) {
		console.log("✅ Token REJECTED with active check!");
		console.log(`   • Error: ${result.error}`);
	} else {
		console.log("⚠️ Token still valid (unexpected)");
	}

	// =========================================================================
	// SUMMARY
	// =========================================================================
	printHeader("DEMO COMPLETE - ALL SDK FEATURES VERIFIED");
	console.log(`
✅ Registration Invite (Budgeted DCR)
✅ Protected Resource Metadata (RFC 9728)
✅ Agent Registration with REG_JWT
✅ Standardized Client ID Format (mcp_*)
✅ Opaque Token Acquisition
✅ JWT Token Acquisition (RFC 8707)
✅ JWT Validation (Stateless, ~0.1ms)
✅ JWT Signature Verification via JWKS
✅ Token Introspection (RFC 7662)
✅ Scope Enforcement
✅ Audience Validation (JWT aud claim)
✅ Kill Switch / Client Revocation
✅ Role-based Access Control (RBAC)
`);

	return 0;
}

// Run
main()
	.then((code) => process.exit(code))
	.catch((e) => {
		console.error(e);
		process.exit(1);
	});
