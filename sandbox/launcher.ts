/**
 * NsJail Launcher
 *
 * Spawns NsJail to execute Python workflow code in a secure sandbox.
 * The sandbox can only communicate via Unix socket to MCPClientManager.
 */

import { spawn } from "node:child_process";
import { dirname, resolve as resolvePath } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

export interface LaunchOptions {
	/** Workflow code to execute */
	code: string;
	/** Path to Unix socket for MCP communication */
	socketPath: string;
	/** Optional skills directory to mount in sandbox */
	skillsDir?: string;
	/** Optional environment overrides */
	env?: Record<string, string>;
	/** Wall-clock timeout in seconds (default: 60) */
	timeout?: number;
	/** Memory limit in MB (default: 512) */
	memoryLimit?: number;
	/** CPU time limit in seconds (default: 10) */
	cpuLimit?: number;
}

export interface LaunchResult {
	/** Exit code (0 = success) */
	exitCode: number;
	/** Stdout output */
	stdout: string;
	/** Stderr output */
	stderr: string;
	/** Execution time in ms */
	executionTimeMs: number;
}

export async function launchSandbox(
	options: LaunchOptions,
): Promise<LaunchResult> {
	const {
		code,
		socketPath,
		skillsDir,
		env,
		timeout = 60,
		memoryLimit = 512,
		cpuLimit = 10,
	} = options;

	const configPath = resolvePath(__dirname, "nsjail.cfg");
	const runtimePath = resolvePath(__dirname, "runtime");

	const startTime = Date.now();

	return new Promise((promiseResolve, promiseReject) => {
		const args = [
			"--config",
			configPath,
			"--time_limit",
			String(timeout),
			"--rlimit_as",
			String(memoryLimit),
			"--rlimit_cpu",
			String(cpuLimit),
			// Override socket path
			"--bindmount",
			`${socketPath}:/mcp.sock`,
			"--env",
			"MCP_SOCKET_PATH=/mcp.sock",
			// Override runtime path
			"--bindmount_ro",
			`${runtimePath}:/runtime`,
			// Add PYTHONPATH
			"--env",
			"PYTHONPATH=/runtime",
			// Command to run
			"--",
			"python3",
			"/runtime/runner.py",
		];

		if (skillsDir) {
			const resolvedSkills = resolvePath(skillsDir);
			args.splice(
				args.indexOf("--") - 0,
				0,
				"--bindmount_ro",
				`${resolvedSkills}:/skills`,
				"--env",
				"MCP_SKILLS_DIR=/skills",
			);
		}

		if (env) {
			for (const [key, value] of Object.entries(env)) {
				args.splice(args.indexOf("--") - 0, 0, "--env", `${key}=${value}`);
			}
		}

		const child = spawn("nsjail", args, {
			stdio: ["pipe", "pipe", "pipe"],
		});

		let stdout = "";
		let stderr = "";

		child.stdout.on("data", (data) => {
			stdout += data.toString();
		});

		child.stderr.on("data", (data) => {
			stderr += data.toString();
		});

		// Send code to stdin
		child.stdin.write(code);
		child.stdin.end();

		child.on("error", (err) => {
			promiseReject(new Error(`Failed to spawn nsjail: ${err.message}`));
		});

		child.on("close", (exitCode) => {
			promiseResolve({
				exitCode: exitCode ?? 1,
				stdout,
				stderr,
				executionTimeMs: Date.now() - startTime,
			});
		});

		// Timeout handling (nsjail has its own, but this is a fallback)
		setTimeout(
			() => {
				if (!child.killed) {
					child.kill("SIGKILL");
				}
			},
			(timeout + 5) * 1000,
		);
	});
}

/**
 * Check if NsJail is available on the system
 */
export async function isNsJailAvailable(): Promise<boolean> {
	return new Promise((promiseResolve) => {
		const child = spawn("nsjail", ["--version"], {
			stdio: ["ignore", "pipe", "pipe"],
		});

		child.on("error", () => promiseResolve(false));
		child.on("close", (code) => promiseResolve(code === 0));
	});
}

/**
 * For development/testing on Windows (no NsJail), run using uv
 * WARNING: This is NOT secure and should only be used for testing!
 */
export async function launchUnsafe(
	options: LaunchOptions,
): Promise<LaunchResult> {
	const { code, socketPath } = options;

	console.warn("[Launcher] WARNING: Running in unsafe mode (no NsJail)");

	const runtimePath = resolvePath(__dirname, "runtime");
	const startTime = Date.now();

	return new Promise((promiseResolve, promiseReject) => {
		// Use uv run to handle python environment
		const child = spawn("uv", ["run", resolvePath(runtimePath, "runner.py")], {
			stdio: ["pipe", "pipe", "pipe"],
			env: {
				...process.env,
				PYTHONPATH: runtimePath,
				MCP_SOCKET_PATH: socketPath,
				MCP_SKILLS_DIR: options.skillsDir || process.env.MCP_SKILLS_DIR || "",
				...(options.env ?? {}),
			},
		});

		let stdout = "";
		let stderr = "";

		child.stdout.on("data", (data) => {
			stdout += data.toString();
		});

		child.stderr.on("data", (data) => {
			stderr += data.toString();
		});

		child.stdin.write(code);
		child.stdin.end();

		child.on("error", (err) => {
			promiseReject(new Error(`Failed to spawn uv: ${err.message}`));
		});

		child.on("close", (exitCode) => {
			promiseResolve({
				exitCode: exitCode ?? 1,
				stdout,
				stderr,
				executionTimeMs: Date.now() - startTime,
			});
		});
	});
}
