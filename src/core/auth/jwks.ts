/**
 * MCP Identity SDK - JWKS and Ed25519 Verification
 *
 * Fetches JWKS from auth server and verifies Ed25519 JWT signatures.
 * Uses Web Crypto API (available in Bun, Node 20+, and browsers).
 */

import { decodeJWTHeader } from "./jwt";
import type { JWTClaims } from "./types";
import { getSdkHeaders } from "./version";

// =============================================================================
// Types
// =============================================================================

interface JWK {
	kty: string;
	crv?: string;
	x?: string;
	kid?: string;
	use?: string;
	alg?: string;
}

interface JWKS {
	keys: JWK[];
}

interface JWKSCache {
	jwks: JWKS;
	fetchedAt: number;
}

// =============================================================================
// JWKS Manager
// =============================================================================

export class JWKSManager {
	private authServer: string;
	private cache: JWKSCache | null = null;
	private cacheTtl: number;
	private keyCache: Map<string, CryptoKey> = new Map();

	constructor(authServer: string, cacheTtl: number = 3600) {
		this.authServer = authServer.replace(/\/$/, "");
		this.cacheTtl = cacheTtl;
	}

	/**
	 * Fetch JWKS from auth server (with caching).
	 * Tries OpenID discovery first, then common paths.
	 */
	async getJWKS(): Promise<JWKS> {
		const now = Date.now() / 1000;

		// Return cached if still valid
		if (this.cache && now - this.cache.fetchedAt < this.cacheTtl) {
			return this.cache.jwks;
		}

		// Try to find JWKS URI from OpenID discovery
		let jwksUri = `${this.authServer}/.well-known/jwks.json`;

		try {
			const discoveryResponse = await fetch(
				`${this.authServer}/.well-known/openid-configuration`,
				{ headers: { ...getSdkHeaders() } },
			);
			if (discoveryResponse.ok) {
				const discovery = (await discoveryResponse.json()) as {
					jwks_uri?: string;
				};
				if (discovery.jwks_uri) {
					jwksUri = discovery.jwks_uri;
				}
			}
		} catch {
			// Ignore discovery errors, use default
		}

		// Fetch JWKS
		const response = await fetch(jwksUri, { headers: { ...getSdkHeaders() } });

		if (!response.ok) {
			// Try fallback path
			const fallbackResponse = await fetch(`${this.authServer}/api/auth/jwks`, {
				headers: { ...getSdkHeaders() },
			});
			if (fallbackResponse.ok) {
				const jwks = (await fallbackResponse.json()) as JWKS;
				this.cache = { jwks, fetchedAt: now };
				this.keyCache.clear();
				return jwks;
			}
			throw new Error(`Failed to fetch JWKS: ${response.status}`);
		}

		const jwks = (await response.json()) as JWKS;

		this.cache = {
			jwks,
			fetchedAt: now,
		};

		// Clear key cache when JWKS changes
		this.keyCache.clear();

		return jwks;
	}

	/**
	 * Get a specific key by kid.
	 */
	async getKey(kid: string): Promise<CryptoKey | null> {
		// Check key cache first
		const cached = this.keyCache.get(kid);
		if (cached) {
			return cached;
		}

		const jwks = await this.getJWKS();
		const jwk = jwks.keys.find((k) => k.kid === kid);

		if (!jwk) {
			return null;
		}

		// Import the key
		const cryptoKey = await this.importJWK(jwk);
		if (cryptoKey) {
			this.keyCache.set(kid, cryptoKey);
		}

		return cryptoKey;
	}

	/**
	 * Import a JWK into a CryptoKey for Ed25519 verification.
	 */
	private async importJWK(jwk: JWK): Promise<CryptoKey | null> {
		if (jwk.kty !== "OKP" || jwk.crv !== "Ed25519") {
			// Not an Ed25519 key
			return null;
		}

		if (!jwk.x) {
			return null;
		}

		try {
			// Import Ed25519 public key
			const cryptoKey = await crypto.subtle.importKey(
				"jwk",
				{
					kty: "OKP",
					crv: "Ed25519",
					x: jwk.x,
				},
				{
					name: "Ed25519",
				},
				true,
				["verify"],
			);

			return cryptoKey;
		} catch (e) {
			console.error("Failed to import JWK:", e);
			return null;
		}
	}

	/**
	 * Clear the JWKS and key caches.
	 */
	clearCache(): void {
		this.cache = null;
		this.keyCache.clear();
	}
}

// =============================================================================
// JWT Verification
// =============================================================================

/**
 * Verify a JWT signature using Ed25519.
 *
 * @param token - The JWT to verify
 * @param jwksManager - JWKS manager instance
 * @returns The verified claims, or null if verification failed
 */
export async function verifyJWT(
	token: string,
	jwksManager: JWKSManager,
): Promise<
	{ claims: JWTClaims; verified: true } | { error: string; verified: false }
> {
	const parts = token.split(".");
	if (parts.length !== 3) {
		return { error: "Invalid JWT format", verified: false };
	}

	const [headerB64, payloadB64, signatureB64] = parts as [
		string,
		string,
		string,
	];

	// Decode header to get kid
	const header = decodeJWTHeader(token);
	if (!header) {
		return { error: "Failed to decode JWT header", verified: false };
	}

	// Check algorithm
	if (header.alg !== "EdDSA") {
		return { error: `Unsupported algorithm: ${header.alg}`, verified: false };
	}

	// Get kid
	const kid = header.kid;
	if (!kid) {
		return { error: "JWT missing kid in header", verified: false };
	}

	// Get the public key
	const key = await jwksManager.getKey(kid);
	if (!key) {
		return { error: `Key not found: ${kid}`, verified: false };
	}

	// Prepare data for verification
	const signedData = `${headerB64}.${payloadB64}`;
	const signedDataBytes = new TextEncoder().encode(signedData);

	// Decode signature from base64url
	const signature = base64UrlDecode(signatureB64);

	// Verify signature
	try {
		const isValid = await crypto.subtle.verify(
			"Ed25519",
			key,
			signature,
			signedDataBytes,
		);

		if (!isValid) {
			return { error: "Invalid signature", verified: false };
		}
	} catch (e) {
		return { error: `Verification failed: ${e}`, verified: false };
	}

	// Decode payload
	const payloadJson = base64UrlDecodeString(payloadB64);
	const claims = JSON.parse(payloadJson) as JWTClaims;

	return { claims, verified: true };
}

// =============================================================================
// Base64URL helpers
// =============================================================================

function base64UrlDecode(str: string): Uint8Array<ArrayBuffer> {
	// Add padding if needed
	const padding = 4 - (str.length % 4);
	const padded = padding !== 4 ? str + "=".repeat(padding) : str;

	// Convert base64url to base64
	const base64 = padded.replace(/-/g, "+").replace(/_/g, "/");

	// Decode
	const binary = atob(base64);
	const buffer = new ArrayBuffer(binary.length);
	const bytes = new Uint8Array(buffer);
	for (let i = 0; i < binary.length; i++) {
		bytes[i] = binary.charCodeAt(i);
	}

	return bytes;
}

function base64UrlDecodeString(str: string): string {
	const bytes = base64UrlDecode(str);
	return new TextDecoder().decode(bytes);
}
