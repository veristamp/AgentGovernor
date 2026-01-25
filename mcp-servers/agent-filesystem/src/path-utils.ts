import os from "node:os";
import path from "node:path";

export function expandHome(filepath: string): string {
	if (filepath.startsWith("~/") || filepath === "~") {
		return path.join(os.homedir(), filepath.slice(1));
	}
	return filepath;
}

function convertToWindowsPath(p: string): string {
	// Preserve WSL paths (/mnt/c/...), they are valid within WSL.
	if (p.startsWith("/mnt/")) return p;

	// Convert Unix-style Windows paths (/c/...) when running on Windows.
	if (process.platform === "win32" && p.match(/^\/[a-zA-Z]\//)) {
		const driveLetter = p.charAt(1).toUpperCase();
		const rest = p.slice(2).replace(/\//g, "\\");
		return `${driveLetter}:${rest}`;
	}

	// Ensure backslashes for standard Windows paths.
	if (p.match(/^[a-zA-Z]:/)) return p.replace(/\//g, "\\");

	return p;
}

export function normalizePath(p: string): string {
	// Trim whitespace and surrounding quotes.
	p = p.trim().replace(/^["']|["']$/g, "");

	const isUnixAbsolute = p.startsWith("/");
	const isUnixStyleWindows = p.match(/^\/[a-zA-Z]\//);
	const isWsl = p.match(/^\/mnt\/[a-z]\//i);

	// Preserve Unix paths on non-Windows, and preserve WSL paths on Windows.
	if (
		isUnixAbsolute &&
		(process.platform !== "win32" || isWsl || !isUnixStyleWindows)
	) {
		return p.replace(/\/+?/g, "/").replace(/(?<!^)\/$/, "");
	}

	p = convertToWindowsPath(p);

	// Normalize UNC paths (\\server\share\...).
	if (p.startsWith("\\\\")) {
		const unc = p.replace(/^\\{2,}/, "\\\\");
		const rest = unc.substring(2).replace(/\\\\/g, "\\");
		p = `\\\\${rest}`;
	} else {
		p = p.replace(/\\\\/g, "\\");
	}

	let normalized = path.normalize(p);
	if (p.startsWith("\\\\") && !normalized.startsWith("\\\\")) {
		normalized = `\\${normalized}`;
	}

	if (normalized.match(/^[a-zA-Z]:/)) {
		let result = normalized.replace(/\//g, "\\");
		if (/^[a-z]:/.test(result))
			result = result.charAt(0).toUpperCase() + result.slice(1);
		return result;
	}

	return process.platform === "win32"
		? normalized.replace(/\//g, "\\")
		: normalized;
}

export function stripFileUri(uriOrPath: string): string {
	return uriOrPath.startsWith("file://")
		? uriOrPath.slice("file://".length)
		: uriOrPath;
}
