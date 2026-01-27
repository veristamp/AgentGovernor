/**
 * MCP Identity SDK - JWT Utilities
 *
 * JWT decoding and validation utilities.
 * Note: This does signature verification via JWKS in resource server mode.
 */

import type { JWTClaims } from "./types";

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

		// Base64URL decode the payload (second part)
		const payloadB64 = parts[1]!;
		const padding = 4 - (payloadB64.length % 4);
		const paddedB64 =
			padding !== 4 ? payloadB64 + "=".repeat(padding) : payloadB64;

		// Convert base64url to base64
		const base64 = paddedB64.replace(/-/g, "+").replace(/_/g, "/");

		// Decode
		const payloadJson = atob(base64);
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

		const headerB64 = parts[0]!;
		const padding = 4 - (headerB64.length % 4);
		const paddedB64 =
			padding !== 4 ? headerB64 + "=".repeat(padding) : headerB64;
		const base64 = paddedB64.replace(/-/g, "+").replace(/_/g, "/");
		const headerJson = atob(base64);

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
	if (!scope) {
		return [];
	}
	if (typeof scope === "string") {
		return scope.split(" ").filter(Boolean);
	}
	return [];
}
