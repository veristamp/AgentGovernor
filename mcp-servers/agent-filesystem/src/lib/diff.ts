import { createTwoFilesPatch } from "diff";
import { normalizeLineEndings } from "./text.js";

export function createUnifiedDiff(
	originalContent: string,
	newContent: string,
	filepath: string,
): string {
	const original = normalizeLineEndings(originalContent);
	const modified = normalizeLineEndings(newContent);
	return createTwoFilesPatch(
		filepath,
		filepath,
		original,
		modified,
		"original",
		"modified",
	);
}
