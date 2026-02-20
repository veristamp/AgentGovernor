/**
 * Unified Socket Server
 *
 * JSON-RPC interface over Unix socket for sandbox communication.
 * All methods now use MCPClientManager (Gate 2) or CapabilityRegistry (Engram).
 */

import { createServer, type Server, type Socket } from "node:net";
import { CapabilityRegistry } from "../capabilities/registry";
import { getEngramService } from "../engram";
import type { MCPClientManager } from "../mcp/manager";
import type { ExecutionContext } from "../mcp/types";
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
	private capabilityRegistry: CapabilityRegistry;

	constructor(options: SocketServerOptions) {
		this.socketPath = options.socketPath;
		this.manager = options.manager;
		this.context = options.context || {};
		// Unified: Use CapabilityRegistry with Engram
		this.capabilityRegistry = new CapabilityRegistry({
			engram: getEngramService(),
			mcp: options.manager,
		});
	}

	async start(): Promise<void> {
		const isWindowsPipe = this.socketPath.startsWith("\\.pipe\\");
		if (!isWindowsPipe && (await Bun.file(this.socketPath).exists())) {
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
		for (const socket of this.connections) {
			socket.destroy();
		}
		this.connections.clear();

		if (this.server) {
			return new Promise((resolve) => {
				this.server?.close(async () => {
					console.log("[SocketServer] Stopped");
					const isWindowsPipe = this.socketPath.startsWith("\\.pipe\\");
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

			for (;;) {
				const newlineIndex = buffer.indexOf("\n");
				if (newlineIndex === -1) break;

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
				`Parse error: ${String(e)}`,
			);
		}

		console.log(`[SocketServer] Request: ${request.method}`);

		// System methods
		switch (request.method) {
			case "__ping__":
				return createResponse(request.id, "pong");

			case "__complete__":
				return createResponse(request.id, request.params?.result);

			case "__capabilities__": {
				// Unified: Return all capabilities from registry
				const identity = {
					orgId: this.context.orgId,
					roles: this.context.roles || [],
				};
				const result = await this.capabilityRegistry.search("", identity, {
					limit: 100,
				});
				return createResponse(request.id, {
					tools: result.capabilities.map((c) => c.id),
					total: result.totalFound,
				});
			}

			case "__tool_search__": {
				// Unified: Use CapabilityRegistry with Engram
				try {
					const query = String(request.params?.query || "");
					const limit = Math.min(Number(request.params?.limit || 5), 20);
					const identity = {
						orgId: this.context.orgId,
						roles: this.context.roles || [],
					};

					const result = await this.capabilityRegistry.search(query, identity, {
						limit,
					});

					return createResponse(request.id, {
						capabilities: result.capabilities,
						totalFound: result.totalFound,
					});
				} catch (e) {
					console.error(`[SocketServer] Error in __tool_search__:`, e);
					return createError(request.id, ErrorCodes.INTERNAL_ERROR, String(e));
				}
			}

			case "__inspect_skill__":
			case "__inspect__": {
				// Unified: Use CapabilityRegistry.load
				try {
					const capabilityId = String(
						request.params?.skill || request.params?.capabilityId || "",
					);
					if (!capabilityId) {
						return createError(
							request.id,
							ErrorCodes.INVALID_PARAMS,
							"Missing capabilityId",
						);
					}

					const identity = {
						orgId: this.context.orgId,
						roles: this.context.roles || [],
					};
					const result = await this.capabilityRegistry.load(
						capabilityId,
						identity,
					);

					return createResponse(request.id, result);
				} catch (e) {
					console.error(`[SocketServer] Error in __inspect__:`, e);
					return createError(request.id, ErrorCodes.INTERNAL_ERROR, String(e));
				}
			}

			case "__discover__": {
				// New: Hub-hop discovery via Engram
				try {
					const fromCapability = String(request.params?.fromCapability || "");
					const minShared = Math.min(
						Number(request.params?.minSharedConcepts || 2),
						5,
					);
					const limit = Math.min(Number(request.params?.limit || 5), 10);

					if (!fromCapability) {
						return createError(
							request.id,
							ErrorCodes.INVALID_PARAMS,
							"Missing fromCapability",
						);
					}

					const engram = getEngramService();
					const node = await engram.inspect(fromCapability);

					if (!node?.nodePointer) {
						return createResponse(request.id, {
							error: `Capability not found: ${fromCapability}`,
						});
					}

					const related = await engram.hubHop(
						node.nodePointer.id,
						minShared,
						limit,
					);

					return createResponse(request.id, {
						startedFrom: fromCapability,
						related: related.map((r) => ({
							id: r.relatedDocUrl,
							sharedConcepts: r.sharedConcepts,
							relevance: r.sharedConceptCount,
						})),
					});
				} catch (e) {
					console.error(`[SocketServer] Error in __discover__:`, e);
					return createError(request.id, ErrorCodes.INTERNAL_ERROR, String(e));
				}
			}
		}

		// All other methods route through MCPClientManager (Gate 2)
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

			const message = String(e);
			let code: number = ErrorCodes.INTERNAL_ERROR;

			if (message.includes("No client found"))
				code = ErrorCodes.METHOD_NOT_FOUND;
			else if (message.includes("Unauthorized")) code = ErrorCodes.UNAUTHORIZED;
			else if (message.includes("Forbidden") || message.includes("policy"))
				code = ErrorCodes.POLICY_DENIED;

			return createError(request.id, code, message);
		}
	}

	/** Update execution context (e.g., after identity verification) */
	setContext(context: ExecutionContext): void {
		this.context = { ...this.context, ...context };
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
