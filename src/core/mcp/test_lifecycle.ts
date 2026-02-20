import { MCPClientManager } from "./manager";

/**
 * Lifecycle Test for MCPClientManager
 * Verifies that the manager can initialize, connect to configured servers,
 * and shutdown cleanly without hanging.
 */
async function main() {
	console.log("=== MCP Manager Lifecycle Test ===");

	// 1. Initialize
	console.log("1. Initializing Manager...");
	const manager = new MCPClientManager({
		configPath: "mcp_servers.json",
		enablePolicy: false,
		enableAuth: false,
	});

	try {
		await manager.initialize();
		console.log("   Manager Initialized.");

		// 2. Check connections
		const tools = manager.getToolNames();
		console.log(`   Connected. Found ${tools.length} tools.`);
	} catch (e) {
		console.error("   Initialization Failed:", e);
	}

	// 3. Shutdown
	console.log("2. Shutting Down...");
	const start = Date.now();
	try {
		await manager.close();
		const duration = Date.now() - start;
		console.log(`   Shutdown Complete in ${duration}ms.`);
	} catch (e) {
		console.error("   Shutdown Failed:", e);
	}

	// 4. Force Exit check
	console.log("3. Test Complete. Exiting process.");
	// If the process hangs after this, it means there are lingering handles.
}

if (import.meta.main) {
	// Set a hard timeout for the test process
	setTimeout(() => {
		console.error("!!! TEST TIMED OUT - FORCE EXIT !!!");
		process.exit(1);
	}, 10000); // 10s timeout

	main().catch((e) => {
		console.error("Test Error:", e);
		process.exit(1);
	});
}
