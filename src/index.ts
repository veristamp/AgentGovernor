/**
 * Governed Code Mode - Main Entry Point
 *
 * This is the main orchestrator that:
 * 1. Initializes MCPClientManager
 * 2. Starts Unix socket server
 * 3. Optionally launches NsJail sandbox
 *
 * Usage:
 *   bun run src/index.ts                    # Start server mode
 *   bun run src/index.ts --execute code.py  # Execute workflow
 */

import { platform } from "os";
import { createInterface } from "readline/promises";
import {
	isNsJailAvailable,
	launchSandbox,
	launchUnsafe,
} from "../sandbox/launcher";
import { LlmClient } from "./agent";
import { MCPClientManager } from "./mcp-client";
import { applyAbacProposalToOrgPolicy, PolicyEngine } from "./policy";
import { SkillCreatorAgent } from "./skill_creator";
import { createSocketServer, type SocketServer } from "./socket-server";

// Windows uses named pipes, Unix uses file sockets
const getDefaultSocketPath = () => {
	if (platform() === "win32") {
		return "\\\\.\\pipe\\mcp-workflow";
	}
	return "/tmp/mcp-workflow.sock";
};

const SOCKET_PATH = process.env.MCP_SOCKET_PATH || getDefaultSocketPath();

interface GovernedCodeMode {
	manager: MCPClientManager;
	server: SocketServer;
}

/**
 * Initialize the Governed Code Mode system
 */
export async function initialize(
	configPath?: string,
): Promise<GovernedCodeMode> {
	console.log("[GCM] Initializing Governed Code Mode...");

	// 1. Initialize MCP Client Manager
	const manager = new MCPClientManager(configPath);
	await manager.initialize();

	// 2. Start Unix socket server
	const server = await createSocketServer(SOCKET_PATH, manager);

	console.log("[GCM] Ready. Socket:", SOCKET_PATH);
	console.log("[GCM] Available tools:", manager.getToolNames().length);

	return { manager, server };
}

/**
 * Execute a workflow in the sandbox
 */
export async function executeWorkflow(
	gcm: GovernedCodeMode,
	code: string,
): Promise<unknown> {
	console.log("[GCM] Executing workflow...");

	// Check if NsJail is available
	const hasNsJail = await isNsJailAvailable();

	const launcher = hasNsJail ? launchSandbox : launchUnsafe;

	const result = await launcher({
		code,
		socketPath: SOCKET_PATH,
		timeout: 60,
		memoryLimit: 512,
		cpuLimit: 10,
	});

	console.log(`[GCM] Workflow completed in ${result.executionTimeMs}ms`);

	if (result.exitCode !== 0) {
		console.error("[GCM] Stderr:", result.stderr);
		throw new Error(`Workflow failed with exit code ${result.exitCode}`);
	}

	return result.stdout;
}

/**
 * Shutdown the system
 */
export async function shutdown(gcm: GovernedCodeMode): Promise<void> {
	console.log("[GCM] Shutting down...");
	await gcm.server.stop();
	await gcm.manager.close();
	console.log("[GCM] Shutdown complete");
}

// ==================== CLI ====================

async function main() {
	const args = process.argv.slice(2);

	if (args.includes("--help") || args.includes("-h")) {
		console.log(`
Governed Code Mode - Secure AI Agent Execution

Usage:
  bun run src/index.ts [options]

Options:
  --config <path>      Path to MCP servers config (default: mcp_servers.json)
  --execute <file>     Execute a workflow file and exit
  --socket <path>      Unix socket path (default: /tmp/mcp-workflow.sock)
  --skill-create       Run admin skill creator agent
  --help, -h           Show this help

Server Mode:
  bun run src/index.ts
  
  Starts the socket server and waits for workflow execution requests.

Execute Mode:
  bun run src/index.ts --execute workflow.py
  
  Executes a workflow file and exits.

Skill Creation Mode:
  bun run src/index.ts --skill-create "Your goal" --role mcp:team-role --org org_123
`);
		process.exit(0);
	}

	// Parse arguments
	let configPath = "mcp_servers.json";
	let executeFile: string | null = null;
	let skillGoal: string | null = null;
	const skillRoles: string[] = [];
	let skillOrg: string | undefined;
	let skillTeam: string | undefined;

	for (let i = 0; i < args.length; i++) {
		if (args[i] === "--config" && args[i + 1]) {
			configPath = args[++i] as string;
		} else if (args[i] === "--execute" && args[i + 1]) {
			executeFile = args[++i] as string;
		} else if (args[i] === "--socket" && args[i + 1]) {
			process.env.MCP_SOCKET_PATH = args[++i] as string;
		} else if (args[i] === "--skill-create" && args[i + 1]) {
			skillGoal = args[++i] as string;
		} else if (args[i] === "--role" && args[i + 1]) {
			skillRoles.push(args[++i] as string);
		} else if (args[i] === "--org" && args[i + 1]) {
			skillOrg = args[++i] as string;
		} else if (args[i] === "--team" && args[i + 1]) {
			skillTeam = args[++i] as string;
		}
	}

	if (skillGoal) {
		const llmBase = process.env.LLM_API_BASE || "http://localhost:1234/v1";
		const llmModel = process.env.LLM_MODEL_NAME || "granite-4.0-micro";
		const policy = new PolicyEngine();
		await policy.loadRulesFromFile("policy/policy_rules.json");
		const agent = new SkillCreatorAgent(
			{ llm: new LlmClient(llmBase, ""), policy },
			{
				model: llmModel,
				toolsPath: "tools_schema.json",
				skillsDir: "skills",
				policyFilePath: "policy/policy_rules.json",
				rolePermissionsPath: "policy/role_permissions.json",
				maxRepairAttempts: 3,
			},
		);
		const result = await agent.run({
			goal: skillGoal,
			constraints: [],
			requester: {
				id: "admin",
				roles: ["mcp:admin", ...skillRoles],
				orgId: skillOrg,
				teamId: skillTeam,
			},
		});
		console.log(
			"[SkillCreator] Created",
			result.skillRef,
			"in",
			result.skillDir,
		);

		if (result.abacProposal) {
			console.log("\n[SkillCreator] ABAC proposal (requires human approval):");
			console.log(JSON.stringify(result.abacProposal, null, 2));

			const rl = createInterface({
				input: process.stdin,
				output: process.stdout,
			});
			const answer = await rl.question("Approve ABAC proposal? [y/N]: ");
			rl.close();

			if (answer.trim().toLowerCase() === "y") {
				const applied = await applyAbacProposalToOrgPolicy(
					result.abacProposal,
					skillOrg,
				);
				if (applied.applied) {
					console.log(
						`[SkillCreator] ABAC proposal applied to ${applied.path}`,
					);
				} else {
					console.log(
						`[SkillCreator] ABAC proposal already present in ${applied.path}`,
					);
				}
			} else {
				console.log("[SkillCreator] ABAC proposal not applied.");
			}
		}

		process.exit(0);
	}

	// Initialize
	const gcm = await initialize(configPath);

	// Handle signals
	process.on("SIGINT", async () => {
		await shutdown(gcm);
		process.exit(0);
	});

	process.on("SIGTERM", async () => {
		await shutdown(gcm);
		process.exit(0);
	});

	if (executeFile) {
		// Execute mode
		if (!(await Bun.file(executeFile).exists())) {
			console.error(`File not found: ${executeFile}`);
			process.exit(1);
		}

		const code = await Bun.file(executeFile).text();

		try {
			const result = await executeWorkflow(gcm, code);
			console.log("[GCM] Result:", result);
			await shutdown(gcm);
			process.exit(0);
		} catch (e) {
			console.error("[GCM] Error:", e);
			await shutdown(gcm);
			process.exit(1);
		}
	} else {
		// Server mode - keep running
		console.log("[GCM] Running in server mode. Press Ctrl+C to stop.");
	}
}

// Run if main module
main().catch((e) => {
	console.error("[GCM] Fatal error:", e);
	process.exit(1);
});
