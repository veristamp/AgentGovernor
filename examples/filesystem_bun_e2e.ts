import path from 'node:path';
import { mkdir } from 'node:fs/promises';

import { MCPClientManager } from '../src/mcp-client/index.js';

const prefix = 'filesystem';

const run = async () => {
  const manager = new MCPClientManager();
  await manager.initialize();

  const baseDir = path.join(process.cwd(), 'output', 'filesystem-bun-e2e');
  await mkdir(baseDir, { recursive: true });

  const tool = async (name: string, args: Record<string, unknown> = {}) => {
    const actionName = `${prefix}.${name}`;
    return manager.executeAction({ actionType: 'tool', actionName, arguments: args });
  };

  console.log(await tool('list-allowed-directories'));
  console.log(await tool('create-directory', { path: baseDir }));
  console.log(await tool('set-allowed-directories', { directories: [baseDir] }));

  const helloPath = path.join(baseDir, 'hello.txt');
  const notePath = path.join(baseDir, 'notes.txt');
  const renamedPath = path.join(baseDir, 'hello-renamed.txt');

  console.log(await tool('write-file', { path: helloPath, content: 'Hello World\n' }));
  console.log(await tool('write-file', { path: notePath, content: 'Alpha\nBeta\n' }));
  console.log(await tool('read-file', { path: helloPath }));

  console.log(
    await tool('edit-file', {
      path: helloPath,
      edits: [{ oldText: 'World', newText: 'Bun' }],
      dry_run: false,
    })
  );

  console.log(await tool('read-multiple-files', { paths: [helloPath, notePath] }));
  console.log(await tool('list-directory', { path: baseDir }));
  console.log(await tool('directory-tree', { path: baseDir }));
  console.log(await tool('search-files', { path: baseDir, pattern: 'hello' }));
  console.log(await tool('get-file-info', { path: helloPath }));

  console.log(await tool('move-file', { source: helloPath, destination: renamedPath }));
  console.log(await tool('read-file', { path: renamedPath }));

  await manager.close();
};

run().catch((err) => {
  console.error('Filesystem MCP E2E failed:', err);
  process.exit(1);
});
