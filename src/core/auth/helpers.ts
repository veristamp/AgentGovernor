/**
 * MCP Identity SDK - Convenience Functions
 *
 * One-shot helper functions for common operations.
 */

import { MCPAgentClient } from "./agent-client";
import type { ValidateTokenOptions } from "./resource-server";
import { MCPResourceServer } from "./resource-server";
import type { MCPCredentials, MCPToken, ValidationResult } from "./types";

/**
 * One-shot agent registration.
 *
 * @param authServer - Authorization server URL
 * @param regJwt - Registration invite token
 * @param clientName - Name for this agent
 * @returns MCPCredentials
 */
export async function registerAgent(
	authServer: string,
	regJwt: string,
	clientName: string,
): Promise<MCPCredentials> {
	const client = new MCPAgentClient({ authServer, regJwt });
	return client.register(clientName);
}

/**
 * One-shot token acquisition.
 *
 * @param authServer - Authorization server URL
 * @param clientId - Registered client ID
 * @param clientSecret - Client secret
 * @param scopes - Scopes to request
 * @param audience - Optional audience for JWT token
 * @returns Access token string
 */
export async function getAccessToken(
	authServer: string,
	clientId: string,
	clientSecret: string,
	scopes?: string[],
	audience?: string,
): Promise<string> {
	const client = new MCPAgentClient({ authServer, clientId, clientSecret });
	const token = await client.getToken(scopes, audience);
	return token.accessToken;
}

/**
 * One-shot token validation.
 *
 * @param authServer - Authorization server URL
 * @param myAudience - This resource server's audience
 * @param token - Token to validate
 * @param options - Validation options
 * @returns ValidationResult
 */
export async function validateToken(
	authServer: string,
	myAudience: string,
	token: string,
	options?: ValidateTokenOptions,
): Promise<ValidationResult> {
	const server = new MCPResourceServer({ authServer, myAudience });
	return server.validateToken(token, options);
}

/**
 * Extract Bearer token from Authorization header.
 */
export function extractBearerToken(authHeader?: string): string | null {
	if (!authHeader || !authHeader.startsWith("Bearer ")) {
		return null;
	}
	return authHeader.slice(7);
}
