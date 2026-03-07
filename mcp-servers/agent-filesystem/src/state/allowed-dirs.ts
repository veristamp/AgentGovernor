let allowedDirectories: string[] = [];

export function setAllowedDirectories(dirs: string[]) {
	allowedDirectories = [...dirs];
}

export function getAllowedDirectories() {
	return [...allowedDirectories];
}
