/**
 * MCP Identity SDK - Versioning
 */

export const SDK_VERSION = "0.0.1";
export const SDK_LANGUAGE = "typescript";
export const SDK_VERSION_HEADER = "x-mcp-sdk-version";
export const SDK_LANGUAGE_HEADER = "x-mcp-sdk-language";

export function getSdkHeaders(): Record<string, string> {
	return {
		[SDK_VERSION_HEADER]: SDK_VERSION,
		[SDK_LANGUAGE_HEADER]: SDK_LANGUAGE,
	};
}
