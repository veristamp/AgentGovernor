/**
 * Bun-native SHA256 hashing - significantly faster than Node.js crypto
 */

export function sha256Hex(data: string | Buffer): string {
	const encoder = new TextEncoder();
	const input = typeof data === "string" 
		? encoder.encode(data) 
		: new Uint8Array(data);
	
	// @ts-ignore - Bun.crypto.subtle exists at runtime
	const hashBuffer = Bun.crypto.subtle.digestSync("SHA-256", input);
	const hashArray = Array.from(new Uint8Array(hashBuffer));
	return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}
