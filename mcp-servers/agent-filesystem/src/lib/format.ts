export function formatSize(bytes: number): string {
	const units = ["B", "KB", "MB", "GB", "TB"];
	if (bytes === 0) return "0 B";
	const i = Math.floor(Math.log(bytes) / Math.log(1024));
	if (i <= 0) return `${bytes} ${units[0]}`;
	const unitIndex = Math.min(i, units.length - 1);
	return `${(bytes / 1024 ** unitIndex).toFixed(2)} ${units[unitIndex]}`;
}
