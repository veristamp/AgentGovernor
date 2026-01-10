/**
 * Auditor Bridge
 * 
 * TypeScript bridge to the Python static auditor.
 * Calls the Python analyzer and parses the result.
 */

import { spawn } from 'child_process';
import { resolve as resolvePath, dirname } from 'path';
import { fileURLToPath } from 'url';
import type { Manifest } from '../policy/types';

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Analyze Python code using the static auditor.
 * 
 * @param code Python workflow code
 * @returns Manifest of what the code will do
 */
export async function analyzeCode(code: string): Promise<Manifest> {
    const analyzerPath = resolvePath(__dirname, '../../auditor/analyzer.py');

    return new Promise((resolve, reject) => {
        const child = spawn('uv', ['run', analyzerPath, '--json'], {
            stdio: ['pipe', 'pipe', 'pipe'],
        });

        let stdout = '';
        let stderr = '';

        child.stdout.on('data', (data) => {
            stdout += data.toString();
        });

        child.stderr.on('data', (data) => {
            stderr += data.toString();
        });

        // Send code to stdin
        child.stdin.write(code);
        child.stdin.end();

        child.on('error', (err) => {
            reject(new Error(`Failed to run analyzer: ${err.message}`));
        });

        child.on('close', (exitCode) => {
            try {
                const result = JSON.parse(stdout) as {
                    manifest: {
                        tools: string[];
                        tool_calls: Array<{
                            tool: string;
                            line: number;
                            col: number;
                            static_args: Record<string, unknown>;
                            dynamic_args: string[];
                        }>;
                        has_loops: boolean;
                        has_conditionals: boolean;
                        max_depth: number;
                        errors: string[];
                        warnings: string[];
                    };
                    violations: string[];
                    allowed: boolean;
                };

                // Convert snake_case to camelCase
                const manifest: Manifest = {
                    tools: result.manifest.tools,
                    toolCalls: result.manifest.tool_calls.map((tc) => ({
                        tool: tc.tool,
                        line: tc.line,
                        col: tc.col,
                        staticArgs: tc.static_args,
                        dynamicArgs: tc.dynamic_args,
                    })),
                    hasLoops: result.manifest.has_loops,
                    hasConditionals: result.manifest.has_conditionals,
                    maxDepth: result.manifest.max_depth,
                    errors: result.manifest.errors,
                    warnings: result.manifest.warnings,
                };

                resolve(manifest);
            } catch (e) {
                reject(new Error(`Failed to parse analyzer output: ${stdout}\n${stderr}`));
            }
        });
    });
}

/**
 * Quick check if code has any parse errors.
 */
export async function validateSyntax(code: string): Promise<{ valid: boolean; errors: string[] }> {
    const manifest = await analyzeCode(code);

    const syntaxErrors = manifest.errors.filter((e) => e.includes('Syntax error'));

    return {
        valid: syntaxErrors.length === 0,
        errors: syntaxErrors,
    };
}
