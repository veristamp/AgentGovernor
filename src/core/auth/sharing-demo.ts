#!/usr/bin/env bun
/**
 * MCP Server Sharing Demo - TypeScript SDK
 *
 * Validates MCP server management + sharing operations via MCPAdminClient.
 *
 * Usage:
 *   bun run sdk/typescript/sharing-demo.ts
 *
 * Optional env:
 *   MCP_AUTH_SERVER=http://localhost:8787
 *   SUPER_ADMIN_EMAIL=admin@example.com
 *   SUPER_ADMIN_PASSWORD=password
 *   SHARE_TARGET_USER_ID=<existing-user-id>
 */

import {
	MCPAdminClient,
	MCPAuthError,
	type ShareMCPServerResponse,
} from "./index";

const AUTH_SERVER = process.env.MCP_AUTH_SERVER ?? "http://localhost:8787";
const SUPER_ADMIN_EMAIL = process.env.SUPER_ADMIN_EMAIL ?? "admin@example.com";
const SUPER_ADMIN_PASSWORD = process.env.SUPER_ADMIN_PASSWORD ?? "password";
const SHARE_TARGET_USER_ID = process.env.SHARE_TARGET_USER_ID;

function header(title: string): void {
	console.log(`\n${"=".repeat(70)}`);
	console.log(`  ${title}`);
	console.log("=".repeat(70));
}

function ok(message: string): void {
	console.log(`✅ ${message}`);
}

function fail(message: string): never {
	throw new Error(message);
}

function pickUserId(payload: unknown): string | undefined {
	if (!payload || typeof payload !== "object") return undefined;
	const data = payload as Record<string, unknown>;
	const user = data.user as Record<string, unknown> | undefined;
	if (typeof user?.id === "string") return user.id;
	if (typeof data.id === "string") return data.id;
	return undefined;
}

async function resolveTargetUserId(admin: MCPAdminClient): Promise<string> {
	if (SHARE_TARGET_USER_ID) {
		return SHARE_TARGET_USER_ID;
	}

	const ts = Date.now();
	const email = `sdk-share-${ts}@example.com`;

	for (const createPath of [
		"/api/auth/admin/create-user",
		"/api/admin/create-user",
	]) {
		const create = await admin.request<Record<string, unknown>>(
			"POST",
			createPath,
			{
				email,
				name: `SDK Share User ${ts}`,
				password: "Passw0rd!123",
			},
		);

		if (create.status === 200 || create.status === 201) {
			const userId = pickUserId(create.data);
			if (userId) {
				return userId;
			}
		}
		console.log(`ℹ️ ${createPath} returned ${create.status}`);
	}

	for (const listPath of [
		"/api/auth/admin/list-users?limit=50&offset=0",
		"/api/admin/list-users?limit=50&offset=0",
	]) {
		const listed = await admin.request<Record<string, unknown>>(
			"GET",
			listPath,
		);
		if (
			listed.status === 200 &&
			listed.data &&
			typeof listed.data === "object"
		) {
			const users =
				(listed.data as { users?: Array<{ id?: string }> }).users ?? [];
			const candidate = users.find((u) => typeof u.id === "string")?.id;
			if (candidate) {
				return candidate;
			}
		}
		console.log(`ℹ️ ${listPath} returned ${listed.status}`);
	}

	const signupEmail = `sdk-share-signup-${ts}@example.com`;
	const signupRes = await fetch(`${AUTH_SERVER}/api/auth/sign-up/email`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({
			email: signupEmail,
			password: "Passw0rd!123",
			name: `SDK Share Signup ${ts}`,
		}),
	});
	if (signupRes.ok) {
		const payload = (await signupRes.json().catch(() => ({}))) as Record<
			string,
			unknown
		>;
		const userId = pickUserId(payload);
		if (userId) {
			return userId;
		}
	}
	console.log(`ℹ️ /api/auth/sign-up/email returned ${signupRes.status}`);

	throw new MCPAuthError(
		"Could not determine share target user. Set SHARE_TARGET_USER_ID or ensure /api/admin/create-user or /api/admin/list-users is available.",
	);
}

async function main(): Promise<number> {
	header("MCP Server Sharing Demo");
	console.log(`Auth Server: ${AUTH_SERVER}`);

	const admin = new MCPAdminClient({ authServer: AUTH_SERVER });
	const loggedIn = await admin.login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD);
	if (!loggedIn) {
		console.log("❌ Admin login failed");
		return 1;
	}
	ok("Admin login succeeded");

	const targetUserId = await resolveTargetUserId(admin);
	ok(`Resolved share target user: ${targetUserId}`);

	const registerResult = await admin.registerMcpServer({
		name: `sdk-share-demo-${Date.now()}`,
		transport: "stdio",
		visibility: "private",
		description: "SDK sharing demo server",
		config: {
			command: "echo",
			args: ["share"],
		},
	});
	ok(`Server registered: ${registerResult.serverId}`);

	const list = await admin.listMcpServers();
	if (!list.some((s) => s.id === registerResult.serverId)) {
		fail("Registered server not present in listMcpServers()");
	}
	ok("listMcpServers includes the new server");

	const detail = await admin.getMcpServer(registerResult.serverId);
	if (detail.server.id !== registerResult.serverId) {
		fail("getMcpServer returned unexpected server");
	}
	ok(`getMcpServer returned URL: ${detail.server.url}`);

	await admin.updateMcpServer(registerResult.serverId, {
		description: "SDK sharing demo server (updated)",
	});
	ok("updateMcpServer succeeded");

	let shareTargetUserId = targetUserId;
	let share: ShareMCPServerResponse;
	try {
		share = await admin.shareMcpServer(registerResult.serverId, {
			userId: shareTargetUserId,
			permission: "use",
		});
	} catch (error) {
		if (
			error instanceof Error &&
			error.message.includes("Cannot share server with yourself")
		) {
			let alternate: string | undefined;
			for (const listPath of [
				"/api/auth/admin/list-users?limit=100&offset=0",
				"/api/admin/list-users?limit=100&offset=0",
			]) {
				const listed = await admin.request<Record<string, unknown>>(
					"GET",
					listPath,
				);
				const users =
					(listed.data as { users?: Array<{ id?: string }> }).users ?? [];
				alternate = users
					.map((u) => u.id)
					.find((id) => typeof id === "string" && id !== shareTargetUserId);
				if (alternate) {
					break;
				}
			}
			if (!alternate) {
				throw error;
			}
			shareTargetUserId = alternate;
			share = await admin.shareMcpServer(registerResult.serverId, {
				userId: shareTargetUserId,
				permission: "use",
			});
		} else {
			throw error;
		}
	}
	ok(`shareMcpServer created share: ${share.shareId}`);

	const sharesAfterGrant = await admin.getMcpServerShares(
		registerResult.serverId,
	);
	if (!sharesAfterGrant.some((s) => s.sharedWithUserId === shareTargetUserId)) {
		fail("getMcpServerShares missing expected user after share");
	}
	ok("getMcpServerShares contains target user after sharing");

	const revoked = await admin.revokeMcpServerShare(
		registerResult.serverId,
		shareTargetUserId,
	);
	if (!revoked) {
		fail("revokeMcpServerShare returned false");
	}
	ok("revokeMcpServerShare succeeded");

	const sharesAfterRevoke = await admin.getMcpServerShares(
		registerResult.serverId,
	);
	if (sharesAfterRevoke.some((s) => s.sharedWithUserId === shareTargetUserId)) {
		fail("Share still present after revoke");
	}
	ok("Share removed after revoke");

	const deleted = await admin.deleteMcpServer(registerResult.serverId);
	if (!deleted) {
		fail("deleteMcpServer returned false");
	}
	ok("deleteMcpServer succeeded");

	header("Sharing Demo Complete");
	return 0;
}

main()
	.then((code) => process.exit(code))
	.catch((err) => {
		console.error("\n❌ Sharing demo failed");
		console.error(err);
		process.exit(1);
	});
