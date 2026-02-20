/**
 * Governed Code Mode - Main Entry Point
 *
 * This is the main orchestrator that:
 * 1. Initializes MCPClientManager
 * 2. Starts Unix socket server
 * 3. Optionally launches NsJail sandbox
 *
 * Usage:
 *   bun run src/cli/index.ts                    # Start server mode
 *   bun run src/cli/index.ts --execute code.py  # Execute workflow
 */

import { platform } from "node:os";
import {
	isNsJailAvailable,
	launchSandbox,
	launchUnsafe,
} from "../../sandbox/launcher";
import { MCPClientManager } from "../core/mcp";
import { PolicyEngine } from "../core/policy";
import { createSocketServer, type SocketServer } from "../core/socket";

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
	_gcm: GovernedCodeMode,
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
  bun run src/cli/index.ts [options]

Options:
  --config <path>      Path to MCP servers config (default: mcp_servers.json)
	  --execute <file>     Execute a workflow file and exit
	  --socket <path>      Unix socket path (default: /tmp/mcp-workflow.sock)
	  --skill-create       Run admin skill creator agent
	  --workflow-create    Run workflow creation agent
	  --help, -h           Show this help

Server Mode:
  bun run src/cli/index.ts
  
  Starts the socket server and waits for workflow execution requests.

Execute Mode:
  bun run src/cli/index.ts --execute workflow.py
  
  Executes a workflow file and exits.

	Skill Creation Mode:
	  bun run src/cli/index.ts --skill-create "Your goal" --role mcp:team-role --org org_123

	Workflow Creation Mode:
	  bun run src/cli/index.ts --workflow-create "Your goal" --role mcp:docs-curator --org org_123
`);
		process.exit(0);
	}

	// Parse arguments
	let configPath = "mcp_servers.json";
	let executeFile: string | null = null;
	let skillGoal: string | null = null;
	let workflowGoal: string | null = null;
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
		} else if (args[i] === "--workflow-create" && args[i + 1]) {
			workflowGoal = args[++i] as string;
		} else if (args[i] === "--role" && args[i + 1]) {
			skillRoles.push(args[++i] as string);
		} else if (args[i] === "--org" && args[i + 1]) {
			skillOrg = args[++i] as string;
		} else if (args[i] === "--team" && args[i + 1]) {
			skillTeam = args[++i] as string;
		}
	}

	const llmKey = process.env.LLM_API_KEY || process.env.OPENAI_API_KEY || "";
	const llmModel = process.env.LLM_MODEL_NAME || "gpt-4o-mini";

	if (skillGoal) {
		const policy = new PolicyEngine();
		await policy.loadRulesFromFile("policy/policy_rules.json");
		const mcp = new MCPClientManager(configPath);
		await mcp.initialize();

		const { createOpenAI } = await import("@ai-sdk/openai");
		const model = createOpenAI({ apiKey: llmKey })(llmModel);

		const { runAgent } = await import("../agents");
		const result = await runAgent(
			"skill-creator",
			{
				identity: {
					id: "admin",
					type: "user",
					roles: ["mcp:admin", ...skillRoles],
					scopes: [],
					orgId: skillOrg,
					missionId: `miss_${Date.now()}`,
					sessionId: `sess_${Date.now()}`,
				},
				mcp,
				policy,
				model,
			},
			{
				goal: skillGoal,
				constraints: [],
				requester: {
					id: "admin",
					roles: ["mcp:admin", ...skillRoles],
					orgId: skillOrg,
					teamId: skillTeam,
				},
			},
		);

		await mcp.close();
		console.log("[SkillCreator] Result:", result.final);
		process.exit(0);
	}

	if (workflowGoal) {
		const policy = new PolicyEngine();
		await policy.loadRulesFromFile("policy/policy_rules.json");
		const mcp = new MCPClientManager(configPath);
		await mcp.initialize();

		const { createOpenAI } = await import("@ai-sdk/openai");
		const model = createOpenAI({ apiKey: llmKey })(llmModel);

		const { runAgent } = await import("../agents");
		const result = await runAgent(
			"orchestrator",
			{
				identity: {
					id: "admin",
					type: "user",
					roles: ["mcp:admin", ...skillRoles],
					scopes: [],
					orgId: skillOrg,
					missionId: `miss_${Date.now()}`,
					sessionId: `sess_${Date.now()}`,
				},
				mcp,
				policy,
				model,
			},
			{ goal: workflowGoal },
		);

		await mcp.close();
		console.error("[Orchestrator] Generated workflow:");
		console.log(result.final);
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
