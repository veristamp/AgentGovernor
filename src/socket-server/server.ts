/**
 * Unix Socket Server
 *
 * Provides a JSON-RPC interface over Unix socket for sandbox communication.
 * This is the communication channel between NsJail sandbox and MCPClientManager.
 */

import { createServer, type Server, type Socket } from "net";
import type { MCPClientManager } from "../mcp-client/manager";
import type { ExecutionContext } from "../mcp-client/types";
import { GcmRegistrySearch } from "../skills_registry/search";
import {
	createError,
	createResponse,
	ErrorCodes,
	type JsonRpcRequest,
	type JsonRpcResponse,
	parseRequest,
	serializeResponse,
} from "./protocol";

export interface SocketServerOptions {
	socketPath: string;
	manager: MCPClientManager;
	context?: ExecutionContext;
}

export class SocketServer {
	private server: Server | null = null;
	private socketPath: string;
	private manager: MCPClientManager;
	private context: ExecutionContext;
	private connections: Set<Socket> = new Set();
	private skillRegistry: GcmRegistrySearch;

	constructor(options: SocketServerOptions) {
		this.socketPath = options.socketPath;
		this.manager = options.manager;
		this.context = options.context || {};
		this.skillRegistry = new GcmRegistrySearch();
		this.skillRegistry.load();
	}

	async start(): Promise<void> {
		// Clean up existing socket file (not needed for Windows named pipes)
		const isWindowsPipe = this.socketPath.startsWith("\\\\.\\pipe\\");
		if (!isWindowsPipe && (await Bun.file(this.socketPath).exists())) {
			// await unlink(this.socketPath);
			// Note: Bun.file().delete() is cleaner but `unlink` is standard for sockets
			// Bun doesn't expose unlink directly on Bun.file() for sockets usually,
			// but we can try removing it via shell or node:fs shim if needed.
			// Actually Bun.file(path).delete() should work if it's a file-like object.
			// Let's try it.
			// Sockets are special files.
			// If Bun.file().delete() fails, we might need `rm` from 'node:fs/promises' but we want to avoid it.
			// Let's rely on standard node:net behavior or try Bun native.
			// Actually, `net.createServer` might fail if file exists.
			// We'll use `rm` from `node:fs/promises` as it's the safest cross-platform way in Bun for "files".
			// Since I'm supposed to replace `fs`...
			// Bun.file(this.socketPath).delete() IS the way.
			await Bun.file(this.socketPath).delete();
		}

		return new Promise((resolve, reject) => {
			this.server = createServer((socket) => this.handleConnection(socket));

			this.server.on("error", (err) => {
				console.error("[SocketServer] Server error:", err);
				reject(err);
			});

			this.server.listen(this.socketPath, () => {
				console.log(`[SocketServer] Listening on ${this.socketPath}`);
				resolve();
			});
		});
	}

	async stop(): Promise<void> {
		// Close all connections
		for (const socket of this.connections) {
			socket.destroy();
		}
		this.connections.clear();

		// Close server
		if (this.server) {
			return new Promise((resolve) => {
				this.server!.close(async () => {
					console.log("[SocketServer] Stopped");

					// Clean up socket file (not needed for Windows named pipes)
					const isWindowsPipe = this.socketPath.startsWith("\\\\.\\pipe\\");
					if (!isWindowsPipe && (await Bun.file(this.socketPath).exists())) {
						await Bun.file(this.socketPath).delete();
					}

					resolve();
				});
			});
		}
	}

	private handleConnection(socket: Socket): void {
		console.log("[SocketServer] New connection");
		this.connections.add(socket);

		let buffer = "";

		socket.on("data", async (data) => {
			buffer += data.toString();

			// Process complete lines (JSON-RPC messages are newline-delimited)
			let newlineIndex;
			while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
				const line = buffer.slice(0, newlineIndex);
				buffer = buffer.slice(newlineIndex + 1);

				if (line.trim()) {
					const response = await this.handleMessage(line);
					socket.write(serializeResponse(response));
				}
			}
		});

		socket.on("close", () => {
			console.log("[SocketServer] Connection closed");
			this.connections.delete(socket);
		});

		socket.on("error", (err) => {
			console.error("[SocketServer] Socket error:", err);
			this.connections.delete(socket);
		});
	}

	private async handleMessage(line: string): Promise<JsonRpcResponse> {
		let request: JsonRpcRequest;

		try {
			request = parseRequest(line);
		} catch (e) {
			return createError(
				null,
				ErrorCodes.PARSE_ERROR,
				"Parse error: " + String(e),
			);
		}

		console.log(`[SocketServer] Request: ${request.method}`);

		// Handle special methods
		if (request.method === "__ping__") {
			return createResponse(request.id, "pong");
		}

		if (request.method === "__complete__") {
			// Workflow completed - return the result
			return createResponse(request.id, request.params?.result);
		}

		if (request.method === "__capabilities__") {
			// Return available tool names
			const tools = this.manager.getToolNames();
			return createResponse(request.id, { tools });
		}

		// Handle Skill Discovery
		if (request.method === "__tool_search__") {
			try {
				const query = String(request.params?.query || "");
				const limit = Number(request.params?.limit || 5);

				// Use GcmRegistrySearch
				const result = this.skillRegistry.search(query, limit);

				// Return result wrapped in expected structure
				return createResponse(request.id, { result });
			} catch (e) {
				console.error(`[SocketServer] Error in __tool_search__:`, e);
				return createError(request.id, ErrorCodes.INTERNAL_ERROR, String(e));
			}
		}

		if (request.method === "__inspect_skill__") {
			try {
				const skillRef = String(request.params?.skill || "");

				// Use legacyRegistry inspection logic which is wrapped by GcmRegistrySearch
				// But GcmRegistrySearch class doesn't expose inspect directly, it exposes legacyRegistry
				const summary = this.skillRegistry.legacyRegistry.inspect(skillRef);

				// Return metadata wrapped in expected structure
				// skill_discovery.py expects { "skill": { ... } }
				if (summary) {
					return createResponse(request.id, { skill: summary });
				} else {
					return createResponse(request.id, { skill: null });
				}
			} catch (e) {
				console.error(`[SocketServer] Error in __inspect_skill__:`, e);
				return createError(request.id, ErrorCodes.INTERNAL_ERROR, String(e));
			}
		}

		// Route to MCPClientManager
		try {
			const result = await this.manager.executeAction(
				{
					actionType: "tool",
					actionName: request.method,
					arguments: request.params,
				},
				this.context,
			);

			return createResponse(request.id, result);
		} catch (e) {
			console.error(`[SocketServer] Error executing ${request.method}:`, e);

			// Map error to appropriate code
			const message = String(e);
			let code: number = ErrorCodes.INTERNAL_ERROR;

			if (message.includes("No client found")) {
				code = ErrorCodes.METHOD_NOT_FOUND;
			} else if (message.includes("Unauthorized")) {
				code = ErrorCodes.UNAUTHORIZED;
			} else if (message.includes("Forbidden") || message.includes("policy")) {
				code = ErrorCodes.POLICY_DENIED;
			}

			return createError(request.id, code, message);
		}
	}

	/** Update execution context (e.g., after identity verification) */
	setContext(context: ExecutionContext): void {
		this.context = context;
	}
}

// Convenience function to create and start server
export async function createSocketServer(
	socketPath: string,
	manager: MCPClientManager,
	context?: ExecutionContext,
): Promise<SocketServer> {
	const server = new SocketServer({ socketPath, manager, context });
	await server.start();
	return server;
}
