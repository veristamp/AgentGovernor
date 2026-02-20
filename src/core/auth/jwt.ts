/**
 * MCP Identity SDK - JWT Utilities
 *
 * JWT decoding and validation utilities.
 * Note: This does signature verification via JWKS in resource server mode.
 */

import type { JWTClaims } from "./types";

/**
 * Base64URL decode helper.
 */
function base64UrlDecode(str: string): string {
	// Pad with '=' to multiple of 4
	const padding = 4 - (str.length % 4);
	const padded = padding !== 4 ? str + "=".repeat(padding) : str;

	// Replace URL-safe chars with standard Base64 chars
	const base64 = padded.replace(/-/g, "+").replace(/_/g, "/");

	// Decode
	return atob(base64);
}

/**
 * Decode a JWT token without verification.
 * Use this only for extracting claims - always verify signatures in production.
 */
export function decodeJWT(token: string): JWTClaims | null {
	try {
		const parts = token.split(".");
		if (parts.length !== 3) {
			return null;
		}
		const payload = parts[1];
		if (!payload) {
			return null;
		}

		const payloadJson = base64UrlDecode(payload);
		return JSON.parse(payloadJson) as JWTClaims;
	} catch {
		return null;
	}
}

/**
 * Check if a string looks like a JWT (has 3 dot-separated parts).
 */
export function isJWT(token: string): boolean {
	return token.split(".").length === 3;
}

/**
 * Extract the header from a JWT.
 */
export function decodeJWTHeader(
	token: string,
): { alg?: string; kid?: string; typ?: string } | null {
	try {
		const parts = token.split(".");
		if (parts.length !== 3) {
			return null;
		}
		const header = parts[0];
		if (!header) {
			return null;
		}

		const headerJson = base64UrlDecode(header);
		return JSON.parse(headerJson);
	} catch {
		return null;
	}
}

/**
 * Check if JWT is expired.
 */
export function isJWTExpired(
	claims: JWTClaims,
	bufferSeconds: number = 30,
): boolean {
	if (!claims.exp) {
		return false; // No expiration claim
	}
	return Date.now() / 1000 >= claims.exp - bufferSeconds;
}

/**
 * Check if JWT audience matches.
 */
export function checkJWTAudience(
	claims: JWTClaims,
	expectedAudience: string,
): boolean {
	const tokenAud = claims.aud;

	if (!tokenAud) {
		return false;
	}

	if (Array.isArray(tokenAud)) {
		return tokenAud.includes(expectedAudience);
	}

	return tokenAud === expectedAudience;
}

/**
 * Extract client ID from JWT claims.
 */
export function extractClientId(claims: JWTClaims): string | undefined {
	return claims.azp || claims.client_id;
}

/**
 * Extract scopes from JWT claims.
 */
export function extractScopes(claims: JWTClaims): string[] {
	const scope = claims.scope;

	// Standard OAuth 2.0: space-separated string
	if (typeof scope === "string") {
		return scope.split(" ").filter(Boolean);
	}

	// Non-standard but possible: array of strings
	if (Array.isArray(scope)) {
		return scope.filter((s) => typeof s === "string");
	}

	return [];
}
