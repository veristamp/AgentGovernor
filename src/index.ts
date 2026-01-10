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

import { MCPClientManager } from './mcp-client';
import { createSocketServer, SocketServer } from './socket-server';
import { launchSandbox, launchUnsafe, isNsJailAvailable } from '../sandbox/launcher';
import { readFileSync, existsSync } from 'fs';
import { platform } from 'os';

// Windows uses named pipes, Unix uses file sockets
const getDefaultSocketPath = () => {
    if (platform() === 'win32') {
        return '\\\\.\\pipe\\mcp-workflow';
    }
    return '/tmp/mcp-workflow.sock';
};

const SOCKET_PATH = process.env.MCP_SOCKET_PATH || getDefaultSocketPath();

interface GovernedCodeMode {
    manager: MCPClientManager;
    server: SocketServer;
}

/**
 * Initialize the Governed Code Mode system
 */
export async function initialize(configPath?: string): Promise<GovernedCodeMode> {
    console.log('[GCM] Initializing Governed Code Mode...');

    // 1. Initialize MCP Client Manager
    const manager = new MCPClientManager(configPath);
    await manager.initialize();

    // 2. Start Unix socket server
    const server = await createSocketServer(SOCKET_PATH, manager);

    console.log('[GCM] Ready. Socket:', SOCKET_PATH);
    console.log('[GCM] Available tools:', manager.getToolNames().length);

    return { manager, server };
}

/**
 * Execute a workflow in the sandbox
 */
export async function executeWorkflow(
    gcm: GovernedCodeMode,
    code: string
): Promise<unknown> {
    console.log('[GCM] Executing workflow...');

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
        console.error('[GCM] Stderr:', result.stderr);
        throw new Error(`Workflow failed with exit code ${result.exitCode}`);
    }

    return result.stdout;
}

/**
 * Shutdown the system
 */
export async function shutdown(gcm: GovernedCodeMode): Promise<void> {
    console.log('[GCM] Shutting down...');
    await gcm.server.stop();
    await gcm.manager.close();
    console.log('[GCM] Shutdown complete');
}

// ==================== CLI ====================

async function main() {
    const args = process.argv.slice(2);

    if (args.includes('--help') || args.includes('-h')) {
        console.log(`
Governed Code Mode - Secure AI Agent Execution

Usage:
  bun run src/index.ts [options]

Options:
  --config <path>    Path to MCP servers config (default: mcp_servers.json)
  --execute <file>   Execute a workflow file and exit
  --socket <path>    Unix socket path (default: /tmp/mcp-workflow.sock)
  --help, -h         Show this help

Server Mode:
  bun run src/index.ts
  
  Starts the socket server and waits for workflow execution requests.

Execute Mode:
  bun run src/index.ts --execute workflow.py
  
  Executes a workflow file and exits.
`);
        process.exit(0);
    }

    // Parse arguments
    let configPath = 'mcp_servers.json';
    let executeFile: string | null = null;

    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--config' && args[i + 1]) {
            configPath = args[++i] as string;
        } else if (args[i] === '--execute' && args[i + 1]) {
            executeFile = args[++i] as string;
        } else if (args[i] === '--socket' && args[i + 1]) {
            process.env.MCP_SOCKET_PATH = args[++i] as string;
        }
    }

    // Initialize
    const gcm = await initialize(configPath);

    // Handle signals
    process.on('SIGINT', async () => {
        await shutdown(gcm);
        process.exit(0);
    });

    process.on('SIGTERM', async () => {
        await shutdown(gcm);
        process.exit(0);
    });

    if (executeFile) {
        // Execute mode
        if (!existsSync(executeFile)) {
            console.error(`File not found: ${executeFile}`);
            process.exit(1);
        }

        const code = readFileSync(executeFile, 'utf-8');

        try {
            const result = await executeWorkflow(gcm, code);
            console.log('[GCM] Result:', result);
            await shutdown(gcm);
            process.exit(0);
        } catch (e) {
            console.error('[GCM] Error:', e);
            await shutdown(gcm);
            process.exit(1);
        }
    } else {
        // Server mode - keep running
        console.log('[GCM] Running in server mode. Press Ctrl+C to stop.');
    }
}

// Run if main module
main().catch((e) => {
    console.error('[GCM] Fatal error:', e);
    process.exit(1);
});
