import crypto from "node:crypto";

export function sha256Hex(data: string | Buffer) {
	return crypto.createHash("sha256").update(data).digest("hex");
}
