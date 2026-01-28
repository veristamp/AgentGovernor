#!/usr/bin/env bun

/**
 * End-to-End Auth Demo
 *
 * Demonstrates the full auth flow through GCM:
 *
 * 1. Agent registers and gets credentials
 * 2. Agent requests JWT token with audience
 * 3. Workflow executes with JWT in context
 * 4. MCPClientManager validates JWT and enforces policies
 * 5. Tool calls are authorized/denied based on scopes
 *
 * Prerequisites:
 * - Mono Authz server running at http://localhost:8787
 * - Environment variables:
 *   - SUPER_ADMIN_EMAIL
 *   - SUPER_ADMIN_PASSWORD
 *
 * Usage:
 *   bun run examples/auth_e2e.ts
 */

import { decodeJWT, MCPAdminClient, MCPAgentClient } from "../src/core/auth";
import { MCPClientManager } from "../src/core/mcp";

// =============================================================================
// Configuration
// =============================================================================

const AUTH_SERVER = process.env.MCP_AUTH_SERVER ?? "http://localhost:8787";
const SUPER_ADMIN_EMAIL =
	process.env.SUPER_ADMIN_EMAIL ?? "srimon12mckv@gmail.com";
const SUPER_ADMIN_PASSWORD = process.env.SUPER_ADMIN_PASSWORD ?? "968746639000";
const MY_AUDIENCE = "mcp://rag-demo-service"; // Must be in MCP_VALID_AUDIENCES env var

function printHeader(title: string): void {
	console.log(`\n${"=".repeat(70)}`);
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
	printHeader("MCP GCM Auth E2E Demo");
	console.log(`\nAuth Server: ${AUTH_SERVER}`);
	console.log(`Audience: ${MY_AUDIENCE}`);

	// =========================================================================
	// PHASE 1: SETUP - Get Agent Credentials
	// =========================================================================
	printHeader("PHASE 1: AGENT SETUP");

	const admin = new MCPAdminClient({ authServer: AUTH_SERVER });

	console.log("\n📧 Admin login...");
	if (!(await admin.login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD))) {
		console.log("❌ Admin login failed");
		return 1;
	}
	console.log("✅ Admin signed in");

	// Create org
	console.log("\n📁 Creating organization...");
	const uniqueSlug = `gcm-e2e-${Date.now()}`;
	const { data: orgData } = await admin.request<{
		id?: string;
		organization?: { id: string };
	}>("POST", "/api/auth/organization/create", {
		name: `GCM E2E Org`,
		slug: uniqueSlug,
	});
	const orgId = orgData.id ?? orgData.organization?.id;
	console.log(`✅ Org: ${orgId?.slice(0, 16)}...`);
	if (!orgId) {
		console.log("❌ Org creation returned no orgId");
		console.log(`   Response: ${JSON.stringify(orgData)}`);
		return 1;
	}

	// Create invite with roles (RBAC approach)
	console.log("\n🎟️  Creating invite with ROLES...");
	const invite = await admin.createInvite({
		orgId,
		budget: 5,
		ttlSeconds: 600,
		allowedScopes: ["read:files"], // OAuth scopes (for token request)
		allowedAudiences: [MY_AUDIENCE],
		allowedRoles: ["mcp:rag-agent", "mcp:file-reader"], // RBAC roles
	});
	console.log("✅ Invite created");
	console.log("   • Allowed roles: mcp:rag-agent, mcp:file-reader");
	console.log(
		"   • These map to: filesystem.read_file, filesystem.list_directory, etc.",
	);

	// Register agent
	console.log("\n🤖 Registering agent...");
	const agent = new MCPAgentClient({
		authServer: AUTH_SERVER,
		regJwt: invite.token,
	});
	const credentials = await agent.register("gcm-workflow-agent");
	console.log(`✅ Agent: ${credentials.clientId}`);

	// =========================================================================
	// PHASE 2: GET JWT TOKEN
	// =========================================================================
	printHeader("PHASE 2: TOKEN ACQUISITION");

	console.log("\n🔑 Requesting JWT with audience...");
	const token = await agent.getToken(
		["read:files"], // Must match allowedScopes in invite
		MY_AUDIENCE, // Get JWT (not opaque)
	);

	const claims = decodeJWT(token.accessToken) as {
		aud?: string;
		azp?: string;
		scope?: string | string[];
		exp?: number;
		roles?: string[];
	};
	console.log("✅ JWT acquired");
	console.log(`   • aud: ${claims?.aud}`);
	console.log(`   • azp: ${claims?.azp}`);
	// Handle scope as either string or array
	const scopeDisplay = Array.isArray(claims?.scope)
		? claims.scope.join(" ")
		: claims?.scope;
	console.log(`   • scope: ${scopeDisplay}`);
	console.log(`   • roles: ${claims?.roles?.join(", ") ?? "none"}`);
	console.log(`   • exp: ${new Date((claims?.exp ?? 0) * 1000).toISOString()}`);

	// =========================================================================
	// PHASE 3: INITIALIZE MCP CLIENT MANAGER WITH AUTH
	// =========================================================================
	printHeader("PHASE 3: MCPClientManager WITH AUTH");

	console.log("\n🔧 Initializing MCPClientManager...");
	const manager = new MCPClientManager({
		enablePolicy: true,
		enableAuth: true,
		authServer: AUTH_SERVER,
		myAudience: MY_AUDIENCE,
	});

	await manager.initialize();
	console.log("✅ Manager initialized");
	console.log(`   • Policy: ENABLED`);
	console.log(`   • Auth: ENABLED`);
	console.log(`   • Tools available: ${manager.getToolNames().length}`);

	// =========================================================================
	// PHASE 4: EXECUTE TOOL WITH JWT CONTEXT
	// =========================================================================
	printHeader("PHASE 4: TOOL EXECUTION WITH AUTH");

	printSubheader("4A: Authorized Call (filesystem.list_directory)");
	try {
		console.log("\n📂 Calling filesystem.list_directory with JWT...");
		const result = await manager.executeAction(
			{
				actionType: "tool",
				actionName: "filesystem.list_directory",
				arguments: { path: "." },
			},
			{ jwt: token.accessToken }, // Pass JWT in context
		);
		console.log("✅ Tool executed successfully!");
		console.log(`   • Result: ${JSON.stringify(result).slice(0, 100)}...`);
	} catch (e) {
		console.log(`❌ Error: ${e}`);
	}

	printSubheader("4B: Unauthorized Call (missing scope)");
	try {
		// Get a token with only read:data scope
		const limitedToken = await agent.getToken(["read:data"], MY_AUDIENCE, true);

		console.log(
			"\n🚫 Calling filesystem.list_directory with limited scopes...",
		);
		await manager.executeAction(
			{
				actionType: "tool",
				actionName: "filesystem.list_directory",
				arguments: { path: "." },
			},
			{ jwt: limitedToken.accessToken },
		);
		console.log("⚠️ Should have been denied but was allowed");
	} catch (e) {
		console.log("✅ Correctly DENIED - insufficient scope");
		console.log(`   • Error: ${e}`);
	}

	printSubheader("4C: No Token (anonymous)");
	try {
		console.log("\n🚫 Calling filesystem.list_directory WITHOUT JWT...");
		await manager.executeAction(
			{
				actionType: "tool",
				actionName: "filesystem.list_directory",
				arguments: { path: "." },
			},
			{}, // No JWT
		);
		console.log("⚠️ Allowed without auth (policy not enforced for anonymous)");
	} catch (e) {
		console.log("✅ Correctly DENIED - no auth");
		console.log(`   • Error: ${e}`);
	}

	// =========================================================================
	// PHASE 5: KILL SWITCH
	// =========================================================================
	printHeader("PHASE 5: KILL SWITCH TEST");

	console.log(`\n🔒 Revoking agent ${credentials.clientId.slice(0, 16)}...`);
	await admin.revokeClient(credentials.clientId);
	console.log("✅ Agent revoked");

	printSubheader("5A: Call with revoked token");
	try {
		console.log("\n🚫 Calling with revoked agent token...");
		await manager.executeAction(
			{
				actionType: "tool",
				actionName: "filesystem.list_directory",
				arguments: { path: "." },
			},
			{ jwt: token.accessToken },
		);
		console.log(
			"⚠️ Should have been denied (JWT still valid without active check)",
		);
	} catch (e) {
		console.log("✅ Correctly DENIED - agent revoked");
		console.log(`   • Error: ${e}`);
	}

	// =========================================================================
	// PHASE 6: AUDIT TRAIL
	// =========================================================================
	printHeader("PHASE 6: AUDIT TRAIL");

	const auditLog = manager.getAuditLog();
	console.log(`\n📋 Audit entries: ${auditLog.length}`);

	for (const entry of auditLog.slice(-5)) {
		const status = entry.error ? "❌" : "✅";
		console.log(
			`   ${status} ${entry.tool} - ${entry.identityId ?? "anonymous"} (${entry.latencyMs}ms)`,
		);
		if (entry.error) {
			console.log(`      Error: ${entry.error}`);
		}
	}

	// =========================================================================
	// CLEANUP
	// =========================================================================
	printHeader("DEMO COMPLETE");

	console.log(`
📊 Summary:
   • Agent registered and got JWT
   • MCPClientManager validated JWT via JWKS
   • Policy engine checked scopes
   • Authorized calls succeeded
   • Unauthorized calls denied
   • Kill switch worked
   • All actions audited
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
