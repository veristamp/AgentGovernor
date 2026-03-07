export function normalizeLineEndings(text: string) {
	return text.replace(/\r\n/g, "\n");
}

export function fileLinesToSpan(
	content: string,
	startLine1: number,
	endLine1: number,
): { start: number; end: number } {
	if (startLine1 < 1 || endLine1 < 1 || endLine1 < startLine1) {
		throw new Error(
			"Invalid line range: start_line/end_line are 1-based and end_line must be >= start_line",
		);
	}

	const lines = normalizeLineEndings(content).split("\n");
	if (startLine1 > lines.length || endLine1 > lines.length) {
		throw new Error(`Line range out of bounds. File has ${lines.length} lines`);
	}

	let start = 0;
	for (let i = 1; i < startLine1; i += 1) {
		start += (lines[i - 1]?.length ?? 0) + 1;
	}

	let end = start;
	for (let i = startLine1; i <= endLine1; i += 1) {
		end += lines[i - 1]?.length ?? 0;
		if (i !== lines.length) end += 1;
	}

	return { start, end };
}
