function extractJsonFence(text: string): string | null {
	const fence = text.match(/```json\s*([\s\S]*?)```/i);
	if (fence?.[1]) return fence[1].trim();
	const looseFence = text.match(/```\s*([\s\S]*?)```/);
	if (looseFence?.[1]) return looseFence[1].trim();
	return null;
}

function findFirstJsonObject(text: string): string | null {
	const start = text.indexOf("{");
	if (start === -1) return null;

	let depth = 0;
	let inString = false;
	let escaped = false;
	for (let i = start; i < text.length; i++) {
		const ch = text[i];
		if (!ch) continue;
		if (inString) {
			if (escaped) {
				escaped = false;
			} else if (ch === "\\") {
				escaped = true;
			} else if (ch === '"') {
				inString = false;
			}
			continue;
		}

		if (ch === '"') {
			inString = true;
			continue;
		}
		if (ch === "{") depth++;
		if (ch === "}") depth--;
		if (depth === 0) {
			return text.slice(start, i + 1).trim();
		}
	}
	return null;
}

export function parseJsonObject<T>(text: string): T {
	const fenced = extractJsonFence(text);
	if (fenced) {
		return JSON.parse(fenced) as T;
	}

	const first = findFirstJsonObject(text);
	if (first) {
		return JSON.parse(first) as T;
	}

	return JSON.parse(text) as T;
}
