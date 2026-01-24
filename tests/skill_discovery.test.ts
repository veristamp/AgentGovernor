import { expect, test } from "bun:test";
import { platform } from "os";
import { launchUnsafe } from "../sandbox/launcher";
import { MCPClientManager } from "../src/mcp-client";
import { createSocketServer } from "../src/socket-server";

const getDefaultSocketPath = () => {
	if (platform() === "win32") {
		return "\\\\.\\pipe\\mcp-skill-discovery-test";
	}
	return "/tmp/mcp-skill-discovery-test.sock";
};

test("skill discovery end-to-end", async () => {
	const manager = new MCPClientManager({
		enablePolicy: false,
		enableAuth: false,
	});
	await manager.initialize();

	const socketPath = getDefaultSocketPath();
	const server = await createSocketServer(socketPath, manager);

	const result = await launchUnsafe({
		code: `from skill_discovery_demo import main as run_discovery

async def main():
    return await run_discovery()
`,
		socketPath,
	});

	await server.stop();
	await manager.close();

	if (result.exitCode !== 0) {
		throw new Error(`Sandbox failed: ${result.stderr || "(no stderr)"}`);
	}

	expect(result.stdout).toContain("docs-to-files");
}, 15000);
