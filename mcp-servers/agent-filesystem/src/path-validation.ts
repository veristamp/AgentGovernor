import fs from "node:fs/promises";
import path from "node:path";
import { expandHome, normalizePath } from "./path-utils.js";
import { getAllowedDirectories } from "./state/allowed-dirs.js";

export function isPathWithinAllowedDirectories(
	absolutePath: string,
	allowedDirectories: string[],
): boolean {
	if (typeof absolutePath !== "string" || !Array.isArray(allowedDirectories))
		return false;
	if (!absolutePath || allowedDirectories.length === 0) return false;
	if (absolutePath.includes("\x00")) return false;

	let normalizedPath: string;
	try {
		normalizedPath = path.resolve(path.normalize(absolutePath));
	} catch {
		return false;
	}
	if (!path.isAbsolute(normalizedPath)) {
		throw new Error("Path must be absolute after normalization");
	}

	return allowedDirectories.some((dir) => {
		if (typeof dir !== "string" || !dir) return false;
		if (dir.includes("\x00")) return false;

		let normalizedDir: string;
		try {
			normalizedDir = path.resolve(path.normalize(dir));
		} catch {
			return false;
		}
		if (!path.isAbsolute(normalizedDir)) {
			throw new Error("Allowed directory must be absolute after normalization");
		}

		if (normalizedPath === normalizedDir) return true;

		if (normalizedDir === path.sep) return normalizedPath.startsWith(path.sep);

		// Windows drive root case (C:\).
		if (path.sep === "\\" && normalizedDir.match(/^[A-Za-z]:\\?$/)) {
			const dirDrive = normalizedDir.charAt(0).toLowerCase();
			const pathDrive = normalizedPath.charAt(0).toLowerCase();
			return (
				pathDrive === dirDrive &&
				normalizedPath.startsWith(normalizedDir.replace(/\\?$/, "\\"))
			);
		}

		return normalizedPath.startsWith(normalizedDir + path.sep);
	});
}

export type ValidatePathOptions = {
	allowCreate?: boolean;
};

export async function validatePath(
	requestedPath: string,
	opts: ValidatePathOptions = {},
) {
	const allowedDirectories = getAllowedDirectories();
	if (allowedDirectories.length === 0) {
		throw new Error(
			"Server cannot operate: no allowed directories configured (use MCP Roots or CLI args)",
		);
	}

	const expanded = expandHome(requestedPath);
	const absolute = path.isAbsolute(expanded)
		? path.resolve(expanded)
		: path.resolve(process.cwd(), expanded);
	const normalizedRequested = normalizePath(absolute);

	const ok = isPathWithinAllowedDirectories(
		normalizedRequested,
		allowedDirectories,
	);
	if (!ok) {
		throw new Error(
			`Access denied - path outside allowed directories: ${absolute} not in ${allowedDirectories.join(", ")}`,
		);
	}

	try {
		const realPath = await fs.realpath(absolute);
		const normalizedReal = normalizePath(realPath);
		if (!isPathWithinAllowedDirectories(normalizedReal, allowedDirectories)) {
			throw new Error(
				`Access denied - symlink target outside allowed directories: ${realPath} not in ${allowedDirectories.join(", ")}`,
			);
		}
		return realPath;
	} catch (error) {
		if (
			(error as NodeJS.ErrnoException).code === "ENOENT" &&
			opts.allowCreate
		) {
			const parentDir = path.dirname(absolute);
			const realParent = await fs.realpath(parentDir).catch(() => {
				throw new Error(`Parent directory does not exist: ${parentDir}`);
			});
			const normalizedParent = normalizePath(realParent);
			if (
				!isPathWithinAllowedDirectories(normalizedParent, allowedDirectories)
			) {
				throw new Error(
					`Access denied - parent directory outside allowed directories: ${realParent} not in ${allowedDirectories.join(", ")}`,
				);
			}
			return absolute;
		}
		throw error;
	}
}
