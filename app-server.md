\# Codex App Server



Codex app-server is the interface Codex uses to power rich clients (for example, the Codex VS Code extension). Use it when you want a deep integration inside your own product: authentication, conversation history, approvals, and streamed agent events. The app-server implementation is open source in the Codex GitHub repository (\[openai/codex/codex-rs/app-server](https://github.com/openai/codex/tree/main/codex-rs/app-server)). See the \[Open Source](https://developers.openai.com/codex/open-source) page for the full list of open-source Codex components.



If you are automating jobs or running Codex in CI, use the

&nbsp; <a href="/codex/sdk">Codex SDK</a> instead.



\## Protocol



Like \[MCP](https://modelcontextprotocol.io/), `codex app-server` supports bidirectional communication using JSON-RPC 2.0 messages (with the `"jsonrpc":"2.0"` header omitted on the wire).



Supported transports:



\- `stdio` (`--listen stdio://`, default): newline-delimited JSON (JSONL).

\- `websocket` (`--listen ws://IP:PORT`, experimental): one JSON-RPC message per WebSocket text frame.



In WebSocket mode, app-server uses bounded queues. When request ingress is full, the server rejects new requests with JSON-RPC error code `-32001` and message `"Server overloaded; retry later."` Clients should retry with an exponentially increasing delay and jitter.



\## Message schema



Requests include `method`, `params`, and `id`:



```json

{ "method": "thread/start", "id": 10, "params": { "model": "gpt-5.1-codex" } }

```



Responses echo the `id` with either `result` or `error`:



```json

{ "id": 10, "result": { "thread": { "id": "thr\_123" } } }

```



```json

{ "id": 10, "error": { "code": 123, "message": "Something went wrong" } }

```



Notifications omit `id` and use only `method` and `params`:



```json

{ "method": "turn/started", "params": { "turn": { "id": "turn\_456" } } }

```



You can generate a TypeScript schema or a JSON Schema bundle from the CLI. Each output is specific to the Codex version you ran, so the generated artifacts match that version exactly:



```bash

codex app-server generate-ts --out ./schemas

codex app-server generate-json-schema --out ./schemas

```



\## Getting started



1\. Start the server with `codex app-server` (default stdio transport) or `codex app-server --listen ws://127.0.0.1:4500` (experimental WebSocket transport).

2\. Connect a client over the selected transport, then send `initialize` followed by the `initialized` notification.

3\. Start a thread and a turn, then keep reading notifications from the active transport stream.



Example (Node.js / TypeScript):



```ts







const proc = spawn("codex", \["app-server"], {

&nbsp; stdio: \["pipe", "pipe", "inherit"],

});

const rl = readline.createInterface({ input: proc.stdout });



const send = (message: unknown) => {

&nbsp; proc.stdin.write(`${JSON.stringify(message)}\\n`);

};



let threadId: string | null = null;



rl.on("line", (line) => {

&nbsp; const msg = JSON.parse(line) as any;

&nbsp; console.log("server:", msg);



&nbsp; if (msg.id === 1 \&\& msg.result?.thread?.id \&\& !threadId) {

&nbsp;   threadId = msg.result.thread.id;

&nbsp;   send({

&nbsp;     method: "turn/start",

&nbsp;     id: 2,

&nbsp;     params: {

&nbsp;       threadId,

&nbsp;       input: \[{ type: "text", text: "Summarize this repo." }],

&nbsp;     },

&nbsp;   });

&nbsp; }

});



send({

&nbsp; method: "initialize",

&nbsp; id: 0,

&nbsp; params: {

&nbsp;   clientInfo: {

&nbsp;     name: "my\_product",

&nbsp;     title: "My Product",

&nbsp;     version: "0.1.0",

&nbsp;   },

&nbsp; },

});

send({ method: "initialized", params: {} });

send({ method: "thread/start", id: 1, params: { model: "gpt-5.1-codex" } });

```



\## Core primitives



\- \*\*Thread\*\*: A conversation between a user and the Codex agent. Threads contain turns.

\- \*\*Turn\*\*: A single user request and the agent work that follows. Turns contain items and stream incremental updates.

\- \*\*Item\*\*: A unit of input or output (user message, agent message, command runs, file change, tool call, and more).



Use the thread APIs to create, list, or archive conversations. Drive a conversation with turn APIs and stream progress via turn notifications.



\## Lifecycle overview



\- \*\*Initialize once per connection\*\*: Immediately after opening a transport connection, send an `initialize` request with your client metadata, then emit `initialized`. The server rejects any request on that connection before this handshake.

\- \*\*Start (or resume) a thread\*\*: Call `thread/start` for a new conversation, `thread/resume` to continue an existing one, or `thread/fork` to branch history into a new thread id.

\- \*\*Begin a turn\*\*: Call `turn/start` with the target `threadId` and user input. Optional fields override model, personality, `cwd`, sandbox policy, and more.

\- \*\*Steer an active turn\*\*: Call `turn/steer` to append user input to the currently in-flight turn without creating a new turn.

\- \*\*Stream events\*\*: After `turn/start`, keep reading notifications on stdout: `item/started`, `item/completed`, `item/agentMessage/delta`, tool progress, and other updates.

\- \*\*Finish the turn\*\*: The server emits `turn/completed` with final status when the model finishes or after a `turn/interrupt` cancellation.



\## Initialization



Clients must send a single `initialize` request per transport connection before invoking any other method on that connection, then acknowledge with an `initialized` notification. Requests sent before initialization receive a `Not initialized` error, and repeated `initialize` calls on the same connection return `Already initialized`.



The server returns the user agent string it will present to upstream services. Set `clientInfo` to identify your integration.



`initialize.params.capabilities` also supports per-connection notification opt-out via `optOutNotificationMethods`, which is a list of exact method names to suppress for that connection. Matching is exact (no wildcards/prefixes). Unknown method names are accepted and ignored.



\*\*Important\*\*: Use `clientInfo.name` to identify your client for the OpenAI Compliance Logs Platform. If you are developing a new Codex integration intended for enterprise use, please contact OpenAI to get it added to a known clients list. For more context, see the \[Codex logs reference](https://chatgpt.com/admin/api-reference#tag/Logs:-Codex).



Example (from the Codex VS Code extension):



```json

{

&nbsp; "method": "initialize",

&nbsp; "id": 0,

&nbsp; "params": {

&nbsp;   "clientInfo": {

&nbsp;     "name": "codex\_vscode",

&nbsp;     "title": "Codex VS Code Extension",

&nbsp;     "version": "0.1.0"

&nbsp;   }

&nbsp; }

}

```



Example with notification opt-out:



```json

{

&nbsp; "method": "initialize",

&nbsp; "id": 1,

&nbsp; "params": {

&nbsp;   "clientInfo": {

&nbsp;     "name": "my\_client",

&nbsp;     "title": "My Client",

&nbsp;     "version": "0.1.0"

&nbsp;   },

&nbsp;   "capabilities": {

&nbsp;     "experimentalApi": true,

&nbsp;     "optOutNotificationMethods": \[

&nbsp;       "codex/event/session\_configured",

&nbsp;       "item/agentMessage/delta"

&nbsp;     ]

&nbsp;   }

&nbsp; }

}

```



\## Experimental API opt-in



Some app-server methods and fields are intentionally gated behind `experimentalApi` capability.



\- Omit `capabilities` (or set `experimentalApi` to `false`) to stay on the stable API surface, and the server rejects experimental methods/fields.

\- Set `capabilities.experimentalApi` to `true` to enable experimental methods and fields.



```json

{

&nbsp; "method": "initialize",

&nbsp; "id": 1,

&nbsp; "params": {

&nbsp;   "clientInfo": {

&nbsp;     "name": "my\_client",

&nbsp;     "title": "My Client",

&nbsp;     "version": "0.1.0"

&nbsp;   },

&nbsp;   "capabilities": {

&nbsp;     "experimentalApi": true

&nbsp;   }

&nbsp; }

}

```



If a client sends an experimental method or field without opting in, app-server rejects it with:



`<descriptor> requires experimentalApi capability`



\## API overview



\- `thread/start` - create a new thread; emits `thread/started` and automatically subscribes you to turn/item events for that thread.

\- `thread/resume` - reopen an existing thread by id so later `turn/start` calls append to it.

\- `thread/fork` - fork a thread into a new thread id by copying stored history; emits `thread/started` for the new thread.

\- `thread/read` - read a stored thread by id without resuming it; set `includeTurns` to return full turn history.

\- `thread/list` - page through stored thread logs; supports cursor-based pagination plus `modelProviders`, `sourceKinds`, `archived`, and `cwd` filters.

\- `thread/loaded/list` - list the thread ids currently loaded in memory.

\- `thread/archive` - move a thread's log file into the archived directory; returns `{}` on success.

\- `thread/unarchive` - restore an archived thread rollout back into the active sessions directory; returns the restored `thread`.

\- `thread/compact/start` - trigger conversation history compaction for a thread; returns `{}` immediately while progress streams via `turn/\*` and `item/\*` notifications.

\- `thread/rollback` - drop the last N turns from the in-memory context and persist a rollback marker; returns the updated `thread`.

\- `turn/start` - add user input to a thread and begin Codex generation; responds with the initial `turn` and streams events. For `collaborationMode`, `settings.developer\_instructions: null` means "use built-in instructions for the selected mode."

\- `turn/steer` - append user input to the active in-flight turn for a thread; returns the accepted `turnId`.

\- `turn/interrupt` - request cancellation of an in-flight turn; success is `{}` and the turn ends with `status: "interrupted"`.

\- `review/start` - kick off the Codex reviewer for a thread; emits `enteredReviewMode` and `exitedReviewMode` items.

\- `command/exec` - run a single command under the server sandbox without starting a thread/turn.

\- `model/list` - list available models (set `includeHidden: true` to include entries with `hidden: true`) with effort options, optional `upgrade`, and `inputModalities`.

\- `experimentalFeature/list` - list feature flags with lifecycle stage metadata and cursor pagination.

\- `collaborationMode/list` - list collaboration mode presets (experimental, no pagination).

\- `skills/list` - list skills for one or more `cwd` values (supports `forceReload` and optional `perCwdExtraUserRoots`).

\- `app/list` - list available apps (connectors) with pagination plus accessibility/enabled metadata.

\- `skills/config/write` - enable or disable skills by path.

\- `mcpServer/oauth/login` - start an OAuth login for a configured MCP server; returns an authorization URL and emits `mcpServer/oauthLogin/completed` on completion.

\- `tool/requestUserInput` - prompt the user with 1-3 short questions for a tool call (experimental); questions can set `isOther` for a free-form option.

\- `config/mcpServer/reload` - reload MCP server configuration from disk and queue a refresh for loaded threads.

\- `mcpServerStatus/list` - list MCP servers, tools, resources, and auth status (cursor + limit pagination).

\- `feedback/upload` - submit a feedback report (classification + optional reason/logs + conversation id).

\- `config/read` - fetch the effective configuration on disk after resolving configuration layering.

\- `config/value/write` - write a single configuration key/value to the user's `config.toml` on disk.

\- `config/batchWrite` - apply configuration edits atomically to the user's `config.toml` on disk.

\- `configRequirements/read` - fetch requirements from `requirements.toml` and/or MDM, including allow-lists and residency requirements (or `null` if you haven't set any up).



\## Models



\### List models (`model/list`)



Call `model/list` to discover available models and their capabilities before rendering model or personality selectors.



```json

{ "method": "model/list", "id": 6, "params": { "limit": 20, "includeHidden": false } }

{ "id": 6, "result": {

&nbsp; "data": \[{

&nbsp;   "id": "gpt-5.2-codex",

&nbsp;   "model": "gpt-5.2-codex",

&nbsp;   "upgrade": "gpt-5.3-codex",

&nbsp;   "displayName": "GPT-5.2 Codex",

&nbsp;   "hidden": false,

&nbsp;   "defaultReasoningEffort": "medium",

&nbsp;   "reasoningEffort": \[{

&nbsp;     "effort": "low",

&nbsp;     "description": "Lower latency"

&nbsp;   }],

&nbsp;   "inputModalities": \["text", "image"],

&nbsp;   "supportsPersonality": true,

&nbsp;   "isDefault": true

&nbsp; }],

&nbsp; "nextCursor": null

} }

```



Each model entry can include:



\- `reasoningEffort` - supported effort options for the model.

\- `defaultReasoningEffort` - suggested default effort for clients.

\- `upgrade` - optional recommended upgrade model id for migration prompts in clients.

\- `hidden` - whether the model is hidden from the default picker list.

\- `inputModalities` - supported input types for the model (for example `text`, `image`).

\- `supportsPersonality` - whether the model supports personality-specific instructions such as `/personality`.

\- `isDefault` - whether the model is the recommended default.



By default, `model/list` returns picker-visible models only. Set `includeHidden: true` if you need the full list and want to filter on the client side using `hidden`.



When `inputModalities` is missing (older model catalogs), treat it as `\["text", "image"]` for backward compatibility.



\### List experimental features (`experimentalFeature/list`)



Use this endpoint to discover feature flags with metadata and lifecycle stage:



```json

{ "method": "experimentalFeature/list", "id": 7, "params": { "limit": 20 } }

{ "id": 7, "result": {

&nbsp; "data": \[{

&nbsp;   "name": "unified\_exec",

&nbsp;   "stage": "beta",

&nbsp;   "displayName": "Unified exec",

&nbsp;   "description": "Use the unified PTY-backed execution tool.",

&nbsp;   "announcement": "Beta rollout for improved command execution reliability.",

&nbsp;   "enabled": false,

&nbsp;   "defaultEnabled": false

&nbsp; }],

&nbsp; "nextCursor": null

} }

```



`stage` can be `beta`, `underDevelopment`, `stable`, `deprecated`, or `removed`. For non-beta flags, `displayName`, `description`, and `announcement` may be `null`.



\## Threads



\- `thread/read` reads a stored thread without subscribing to it; set `includeTurns` to include turns.

\- `thread/list` supports cursor pagination plus `modelProviders`, `sourceKinds`, `archived`, and `cwd` filtering.

\- `thread/loaded/list` returns the thread IDs currently in memory.

\- `thread/archive` moves the thread's persisted JSONL log into the archived directory.

\- `thread/unarchive` restores an archived thread rollout back into the active sessions directory.

\- `thread/compact/start` triggers compaction and returns `{}` immediately.

\- `thread/rollback` drops the last N turns from the in-memory context and records a rollback marker in the thread's persisted JSONL log.



\### Start or resume a thread



Start a fresh thread when you need a new Codex conversation.



```json

{ "method": "thread/start", "id": 10, "params": {

&nbsp; "model": "gpt-5.1-codex",

&nbsp; "cwd": "/Users/me/project",

&nbsp; "approvalPolicy": "never",

&nbsp; "sandbox": "workspaceWrite",

&nbsp; "personality": "friendly"

} }

{ "id": 10, "result": {

&nbsp; "thread": {

&nbsp;   "id": "thr\_123",

&nbsp;   "preview": "",

&nbsp;   "modelProvider": "openai",

&nbsp;   "createdAt": 1730910000

&nbsp; }

} }

{ "method": "thread/started", "params": { "thread": { "id": "thr\_123" } } }

```



To continue a stored session, call `thread/resume` with the `thread.id` you recorded earlier. The response shape matches `thread/start`. You can also pass the same configuration overrides supported by `thread/start`, such as `personality`:



```json

{ "method": "thread/resume", "id": 11, "params": {

&nbsp; "threadId": "thr\_123",

&nbsp; "personality": "friendly"

} }

{ "id": 11, "result": { "thread": { "id": "thr\_123" } } }

```



Resuming a thread doesn't update `thread.updatedAt` (or the rollout file's modified time) by itself. The timestamp updates when you start a turn.



If you mark an enabled MCP server as `required` in config and that server fails to initialize, `thread/start` and `thread/resume` fail instead of continuing without it.



`dynamicTools` on `thread/start` is an experimental field (requires `capabilities.experimentalApi = true`). Codex persists these dynamic tools in the thread rollout metadata and restores them on `thread/resume` when you don't supply new dynamic tools.



If you resume with a different model than the one recorded in the rollout, Codex emits a warning and applies a one-time model-switch instruction on the next turn.



To branch from a stored session, call `thread/fork` with the `thread.id`. This creates a new thread id and emits a `thread/started` notification for it:



```json

{ "method": "thread/fork", "id": 12, "params": { "threadId": "thr\_123" } }

{ "id": 12, "result": { "thread": { "id": "thr\_456" } } }

{ "method": "thread/started", "params": { "thread": { "id": "thr\_456" } } }

```



\### Read a stored thread (without resuming)



Use `thread/read` when you want stored thread data but don't want to resume the thread or subscribe to its events.



\- `includeTurns` - when `true`, the response includes the thread's turns; when `false` or omitted, you get the thread summary only.



```json

{ "method": "thread/read", "id": 19, "params": { "threadId": "thr\_123", "includeTurns": true } }

{ "id": 19, "result": { "thread": { "id": "thr\_123", "turns": \[] } } }

```



Unlike `thread/resume`, `thread/read` doesn't load the thread into memory or emit `thread/started`.



\### List threads (with pagination \& filters)



`thread/list` lets you render a history UI. Results default to newest-first by `createdAt`. Filters apply before pagination. Pass any combination of:



\- `cursor` - opaque string from a prior response; omit for the first page.

\- `limit` - server defaults to a reasonable page size if unset.

\- `sortKey` - `created\_at` (default) or `updated\_at`.

\- `modelProviders` - restrict results to specific providers; unset, null, or an empty array includes all providers.

\- `sourceKinds` - restrict results to specific thread sources. When omitted or `\[]`, the server defaults to interactive sources only: `cli` and `vscode`.

\- `archived` - when `true`, list archived threads only. When `false` or omitted, list non-archived threads (default).

\- `cwd` - restrict results to threads whose session current working directory exactly matches this path.



`sourceKinds` accepts the following values:



\- `cli`

\- `vscode`

\- `exec`

\- `appServer`

\- `subAgent`

\- `subAgentReview`

\- `subAgentCompact`

\- `subAgentThreadSpawn`

\- `subAgentOther`

\- `unknown`



Example:



```json

{ "method": "thread/list", "id": 20, "params": {

&nbsp; "cursor": null,

&nbsp; "limit": 25,

&nbsp; "sortKey": "created\_at"

} }

{ "id": 20, "result": {

&nbsp; "data": \[

&nbsp;   { "id": "thr\_a", "preview": "Create a TUI", "modelProvider": "openai", "createdAt": 1730831111, "updatedAt": 1730831111 },

&nbsp;   { "id": "thr\_b", "preview": "Fix tests", "modelProvider": "openai", "createdAt": 1730750000, "updatedAt": 1730750000 }

&nbsp; ],

&nbsp; "nextCursor": "opaque-token-or-null"

} }

```



When `nextCursor` is `null`, you have reached the final page.



\### List loaded threads



`thread/loaded/list` returns thread IDs currently loaded in memory.



```json

{ "method": "thread/loaded/list", "id": 21 }

{ "id": 21, "result": { "data": \["thr\_123", "thr\_456"] } }

```



\### Archive a thread



Use `thread/archive` to move the persisted thread log (stored as a JSONL file on disk) into the archived sessions directory.



```json

{ "method": "thread/archive", "id": 22, "params": { "threadId": "thr\_b" } }

{ "id": 22, "result": {} }

```



Archived threads won't appear in future calls to `thread/list` unless you pass `archived: true`.



\### Unarchive a thread



Use `thread/unarchive` to move an archived thread rollout back into the active sessions directory.



```json

{ "method": "thread/unarchive", "id": 24, "params": { "threadId": "thr\_b" } }

{ "id": 24, "result": { "thread": { "id": "thr\_b" } } }

```



\### Trigger thread compaction



Use `thread/compact/start` to trigger manual history compaction for a thread. The request returns immediately with `{}`.



App-server emits progress as standard `turn/\*` and `item/\*` notifications on the same `threadId`, including a `contextCompaction` item lifecycle (`item/started` then `item/completed`).



```json

{ "method": "thread/compact/start", "id": 25, "params": { "threadId": "thr\_b" } }

{ "id": 25, "result": {} }

```



\## Turns



The `input` field accepts a list of items:



\- `{ "type": "text", "text": "Explain this diff" }`

\- `{ "type": "image", "url": "https://.../design.png" }`

\- `{ "type": "localImage", "path": "/tmp/screenshot.png" }`



You can override configuration settings per turn (model, effort, personality, `cwd`, sandbox policy, summary). When specified, these settings become the defaults for later turns on the same thread. `outputSchema` applies only to the current turn. For `sandboxPolicy.type = "externalSandbox"`, set `networkAccess` to `restricted` or `enabled`; for `workspaceWrite`, `networkAccess` remains a boolean.



For `turn/start.collaborationMode`, `settings.developer\_instructions: null` means "use built-in instructions for the selected mode" rather than clearing mode instructions.



\### Sandbox read access (`ReadOnlyAccess`)



`sandboxPolicy` supports explicit read-access controls:



\- `readOnly`: optional `access` (`{ "type": "fullAccess" }` by default, or restricted roots).

\- `workspaceWrite`: optional `readOnlyAccess` (`{ "type": "fullAccess" }` by default, or restricted roots).



Restricted read access shape:



```json

{

&nbsp; "type": "restricted",

&nbsp; "includePlatformDefaults": true,

&nbsp; "readableRoots": \["/Users/me/shared-read-only"]

}

```



Examples:



```json

{ "type": "readOnly", "access": { "type": "fullAccess" } }

```



```json

{

&nbsp; "type": "workspaceWrite",

&nbsp; "writableRoots": \["/Users/me/project"],

&nbsp; "readOnlyAccess": {

&nbsp;   "type": "restricted",

&nbsp;   "includePlatformDefaults": true,

&nbsp;   "readableRoots": \["/Users/me/shared-read-only"]

&nbsp; },

&nbsp; "networkAccess": false

}

```



\### Start a turn



```json

{ "method": "turn/start", "id": 30, "params": {

&nbsp; "threadId": "thr\_123",

&nbsp; "input": \[ { "type": "text", "text": "Run tests" } ],

&nbsp; "cwd": "/Users/me/project",

&nbsp; "approvalPolicy": "unlessTrusted",

&nbsp; "sandboxPolicy": {

&nbsp;   "type": "workspaceWrite",

&nbsp;   "writableRoots": \["/Users/me/project"],

&nbsp;   "networkAccess": true

&nbsp; },

&nbsp; "model": "gpt-5.1-codex",

&nbsp; "effort": "medium",

&nbsp; "summary": "concise",

&nbsp; "personality": "friendly",

&nbsp; "outputSchema": {

&nbsp;   "type": "object",

&nbsp;   "properties": { "answer": { "type": "string" } },

&nbsp;   "required": \["answer"],

&nbsp;   "additionalProperties": false

&nbsp; }

} }

{ "id": 30, "result": { "turn": { "id": "turn\_456", "status": "inProgress", "items": \[], "error": null } } }

```



\### Steer an active turn



Use `turn/steer` to append more user input to the active in-flight turn.



\- Include `expectedTurnId`; it must match the active turn id.

\- The request fails if there is no active turn on the thread.

\- `turn/steer` doesn't emit a new `turn/started` notification.

\- `turn/steer` doesn't accept turn-level overrides (`model`, `cwd`, `sandboxPolicy`, or `outputSchema`).



```json

{ "method": "turn/steer", "id": 32, "params": {

&nbsp; "threadId": "thr\_123",

&nbsp; "input": \[ { "type": "text", "text": "Actually focus on failing tests first." } ],

&nbsp; "expectedTurnId": "turn\_456"

} }

{ "id": 32, "result": { "turnId": "turn\_456" } }

```



\### Start a turn (invoke a skill)



Invoke a skill explicitly by including `$<skill-name>` in the text input and adding a `skill` input item alongside it.



```json

{ "method": "turn/start", "id": 33, "params": {

&nbsp; "threadId": "thr\_123",

&nbsp; "input": \[

&nbsp;   { "type": "text", "text": "$skill-creator Add a new skill for triaging flaky CI and include step-by-step usage." },

&nbsp;   { "type": "skill", "name": "skill-creator", "path": "/Users/me/.codex/skills/skill-creator/SKILL.md" }

&nbsp; ]

} }

{ "id": 33, "result": { "turn": { "id": "turn\_457", "status": "inProgress", "items": \[], "error": null } } }

```



\### Interrupt a turn



```json

{ "method": "turn/interrupt", "id": 31, "params": { "threadId": "thr\_123", "turnId": "turn\_456" } }

{ "id": 31, "result": {} }

```



On success, the turn finishes with `status: "interrupted"`.



\## Review



`review/start` runs the Codex reviewer for a thread and streams review items. Targets include:



\- `uncommittedChanges`

\- `baseBranch` (diff against a branch)

\- `commit` (review a specific commit)

\- `custom` (free-form instructions)



Use `delivery: "inline"` (default) to run the review on the existing thread, or `delivery: "detached"` to fork a new review thread.



Example request/response:



```json

{ "method": "review/start", "id": 40, "params": {

&nbsp; "threadId": "thr\_123",

&nbsp; "delivery": "inline",

&nbsp; "target": { "type": "commit", "sha": "1234567deadbeef", "title": "Polish tui colors" }

} }

{ "id": 40, "result": {

&nbsp; "turn": {

&nbsp;   "id": "turn\_900",

&nbsp;   "status": "inProgress",

&nbsp;   "items": \[

&nbsp;     { "type": "userMessage", "id": "turn\_900", "content": \[ { "type": "text", "text": "Review commit 1234567: Polish tui colors" } ] }

&nbsp;   ],

&nbsp;   "error": null

&nbsp; },

&nbsp; "reviewThreadId": "thr\_123"

} }

```



For a detached review, use `"delivery": "detached"`. The response is the same shape, but `reviewThreadId` will be the id of the new review thread (different from the original `threadId`). The server also emits a `thread/started` notification for that new thread before streaming the review turn.



Codex streams the usual `turn/started` notification followed by an `item/started` with an `enteredReviewMode` item:



```json

{

&nbsp; "method": "item/started",

&nbsp; "params": {

&nbsp;   "item": {

&nbsp;     "type": "enteredReviewMode",

&nbsp;     "id": "turn\_900",

&nbsp;     "review": "current changes"

&nbsp;   }

&nbsp; }

}

```



When the reviewer finishes, the server emits `item/started` and `item/completed` containing an `exitedReviewMode` item with the final review text:



```json

{

&nbsp; "method": "item/completed",

&nbsp; "params": {

&nbsp;   "item": {

&nbsp;     "type": "exitedReviewMode",

&nbsp;     "id": "turn\_900",

&nbsp;     "review": "Looks solid overall..."

&nbsp;   }

&nbsp; }

}

```



Use this notification to render the reviewer output in your client.



\## Command execution



`command/exec` runs a single command (`argv` array) under the server sandbox without creating a thread.



```json

{ "method": "command/exec", "id": 50, "params": {

&nbsp; "command": \["ls", "-la"],

&nbsp; "cwd": "/Users/me/project",

&nbsp; "sandboxPolicy": { "type": "workspaceWrite" },

&nbsp; "timeoutMs": 10000

} }

{ "id": 50, "result": { "exitCode": 0, "stdout": "...", "stderr": "" } }

```



Use `sandboxPolicy.type = "externalSandbox"` if you already sandbox the server process and want Codex to skip its own sandbox enforcement. For external sandbox mode, set `networkAccess` to `restricted` (default) or `enabled`. For `readOnly` and `workspaceWrite`, use the same optional `access` / `readOnlyAccess` structure shown above.



Notes:



\- The server rejects empty `command` arrays.

\- `sandboxPolicy` accepts the same shape used by `turn/start` (for example, `dangerFullAccess`, `readOnly`, `workspaceWrite`, `externalSandbox`).

\- When omitted, `timeoutMs` falls back to the server default.



\## Events



Event notifications are the server-initiated stream for thread lifecycles, turn lifecycles, and the items within them. After you start or resume a thread, keep reading the active transport stream for `thread/started`, `turn/\*`, and `item/\*` notifications.



\### Notification opt-out



Clients can suppress specific notifications per connection by sending exact method names in `initialize.params.capabilities.optOutNotificationMethods`.



\- Exact-match only: `item/agentMessage/delta` suppresses only that method.

\- Unknown method names are ignored.

\- Applies to both legacy (`codex/event/\*`) and v2 (`thread/\*`, `turn/\*`, `item/\*`, etc.) notifications.

\- Doesn't apply to requests, responses, or errors.



\### Fuzzy file search events (experimental)



The fuzzy file search session API emits per-query notifications:



\- `fuzzyFileSearch/sessionUpdated` - `{ sessionId, query, files }` with the current matches for the active query.

\- `fuzzyFileSearch/sessionCompleted` - `{ sessionId }` once indexing and matching for that query completes.



\### Turn events



\- `turn/started` - `{ turn }` with the turn id, empty `items`, and `status: "inProgress"`.

\- `turn/completed` - `{ turn }` where `turn.status` is `completed`, `interrupted`, or `failed`; failures carry `{ error: { message, codexErrorInfo?, additionalDetails? } }`.

\- `turn/diff/updated` - `{ threadId, turnId, diff }` with the latest aggregated unified diff across every file change in the turn.

\- `turn/plan/updated` - `{ turnId, explanation?, plan }` whenever the agent shares or changes its plan; each `plan` entry is `{ step, status }` with `status` in `pending`, `inProgress`, or `completed`.

\- `thread/tokenUsage/updated` - usage updates for the active thread.



`turn/diff/updated` and `turn/plan/updated` currently include empty `items` arrays even when item events stream. Use `item/\*` notifications as the source of truth for turn items.



\### Items



`ThreadItem` is the tagged union carried in turn responses and `item/\*` notifications. Common item types include:



\- `userMessage` - `{id, content}` where `content` is a list of user inputs (`text`, `image`, or `localImage`).

\- `agentMessage` - `{id, text}` containing the accumulated agent reply.

\- `plan` - `{id, text}` containing proposed plan text in plan mode. Treat the final `plan` item from `item/completed` as authoritative.

\- `reasoning` - `{id, summary, content}` where `summary` holds streamed reasoning summaries and `content` holds raw reasoning blocks.

\- `commandExecution` - `{id, command, cwd, status, commandActions, aggregatedOutput?, exitCode?, durationMs?}`.

\- `fileChange` - `{id, changes, status}` describing proposed edits; `changes` list `{path, kind, diff}`.

\- `mcpToolCall` - `{id, server, tool, status, arguments, result?, error?}`.

\- `collabToolCall` - `{id, tool, status, senderThreadId, receiverThreadId?, newThreadId?, prompt?, agentStatus?}`.

\- `webSearch` - `{id, query, action?}` for web search requests issued by the agent.

\- `imageView` - `{id, path}` emitted when the agent invokes the image viewer tool.

\- `enteredReviewMode` - `{id, review}` sent when the reviewer starts.

\- `exitedReviewMode` - `{id, review}` emitted when the reviewer finishes.

\- `contextCompaction` - `{id}` emitted when Codex compacts the conversation history.



For `webSearch.action`, the action `type` can be `search` (`query?`, `queries?`), `openPage` (`url?`), or `findInPage` (`url?`, `pattern?`).



The app server deprecates the legacy `thread/compacted` notification; use the `contextCompaction` item instead.



All items emit two shared lifecycle events:



\- `item/started` - emits the full `item` when a new unit of work begins; the `item.id` matches the `itemId` used by deltas.

\- `item/completed` - sends the final `item` once work finishes; treat this as the authoritative state.



\### Item deltas



\- `item/agentMessage/delta` - appends streamed text for the agent message.

\- `item/plan/delta` - streams proposed plan text. The final `plan` item may not exactly equal the concatenated deltas.

\- `item/reasoning/summaryTextDelta` - streams readable reasoning summaries; `summaryIndex` increments when a new summary section opens.

\- `item/reasoning/summaryPartAdded` - marks a boundary between reasoning summary sections.

\- `item/reasoning/textDelta` - streams raw reasoning text (when supported by the model).

\- `item/commandExecution/outputDelta` - streams stdout/stderr for a command; append deltas in order.

\- `item/fileChange/outputDelta` - contains the tool call response of the underlying `apply\_patch` tool call.



\## Errors



If a turn fails, the server emits an `error` event with `{ error: { message, codexErrorInfo?, additionalDetails? } }` and then finishes the turn with `status: "failed"`. When an upstream HTTP status is available, it appears in `codexErrorInfo.httpStatusCode`.



Common `codexErrorInfo` values include:



\- `ContextWindowExceeded`

\- `UsageLimitExceeded`

\- `HttpConnectionFailed` (4xx/5xx upstream errors)

\- `ResponseStreamConnectionFailed`

\- `ResponseStreamDisconnected`

\- `ResponseTooManyFailedAttempts`

\- `BadRequest`, `Unauthorized`, `SandboxError`, `InternalServerError`, `Other`



When an upstream HTTP status is available, the server forwards it in `httpStatusCode` on the relevant `codexErrorInfo` variant.



\## Approvals



Depending on a user's Codex settings, command execution and file changes may require approval. The app-server sends a server-initiated JSON-RPC request to the client, and the client responds with a decision payload.



\- Command execution decisions: `accept`, `acceptForSession`, `decline`, `cancel`, or `{ "acceptWithExecpolicyAmendment": { "execpolicy\_amendment": \["cmd", "..."] } }`.

\- File change decisions: `accept`, `acceptForSession`, `decline`, `cancel`.



\- Requests include `threadId` and `turnId` - use them to scope UI state to the active conversation.

\- The server resumes or declines the work and ends the item with `item/completed`.



\### Command execution approvals



Order of messages:



1\. `item/started` shows the pending `commandExecution` item with `command`, `cwd`, and other fields.

2\. `item/commandExecution/requestApproval` includes `itemId`, `threadId`, `turnId`, optional `reason`, optional `command`, optional `cwd`, optional `commandActions`, and optional `proposedExecpolicyAmendment`.

3\. Client responds with one of the command execution approval decisions above.

4\. `item/completed` returns the final `commandExecution` item with `status: completed | failed | declined`.



\### File change approvals



Order of messages:



1\. `item/started` emits a `fileChange` item with proposed `changes` and `status: "inProgress"`.

2\. `item/fileChange/requestApproval` includes `itemId`, `threadId`, `turnId`, optional `reason`, and optional `grantRoot`.

3\. Client responds with one of the file change approval decisions above.

4\. `item/completed` returns the final `fileChange` item with `status: completed | failed | declined`.



\### MCP tool-call approvals (apps)



App (connector) tool calls can also require approval. When an app tool call has side effects, the server may elicit approval with `tool/requestUserInput` and options such as \*\*Accept\*\*, \*\*Decline\*\*, and \*\*Cancel\*\*. If the user declines or cancels, the related `mcpToolCall` item completes with an error instead of running the tool.



\## Skills



Invoke a skill by including `$<skill-name>` in the user text input. Add a `skill` input item (recommended) so the server injects full skill instructions instead of relying on the model to resolve the name.



```json

{

&nbsp; "method": "turn/start",

&nbsp; "id": 101,

&nbsp; "params": {

&nbsp;   "threadId": "thread-1",

&nbsp;   "input": \[

&nbsp;     {

&nbsp;       "type": "text",

&nbsp;       "text": "$skill-creator Add a new skill for triaging flaky CI."

&nbsp;     },

&nbsp;     {

&nbsp;       "type": "skill",

&nbsp;       "name": "skill-creator",

&nbsp;       "path": "/Users/me/.codex/skills/skill-creator/SKILL.md"

&nbsp;     }

&nbsp;   ]

&nbsp; }

}

```



If you omit the `skill` item, the model will still parse the `$<skill-name>` marker and try to locate the skill, which can add latency.



Example:



```

$skill-creator Add a new skill for triaging flaky CI and include step-by-step usage.

```



Use `skills/list` to fetch available skills (optionally scoped by `cwds`, with `forceReload`). You can also include `perCwdExtraUserRoots` to scan extra absolute paths as `user` scope for specific `cwd` values. App-server ignores entries whose `cwd` isn't present in `cwds`. `skills/list` may reuse a cached result per `cwd`; set `forceReload: true` to refresh from disk. When present, the server reads `interface` and `dependencies` from `SKILL.json`.



```json

{ "method": "skills/list", "id": 25, "params": {

&nbsp; "cwds": \["/Users/me/project", "/Users/me/other-project"],

&nbsp; "forceReload": true,

&nbsp; "perCwdExtraUserRoots": \[

&nbsp;   {

&nbsp;     "cwd": "/Users/me/project",

&nbsp;     "extraUserRoots": \["/Users/me/shared-skills"]

&nbsp;   }

&nbsp; ]

} }

{ "id": 25, "result": {

&nbsp; "data": \[{

&nbsp;   "cwd": "/Users/me/project",

&nbsp;   "skills": \[

&nbsp;     {

&nbsp;       "name": "skill-creator",

&nbsp;       "description": "Create or update a Codex skill",

&nbsp;       "enabled": true,

&nbsp;       "interface": {

&nbsp;         "displayName": "Skill Creator",

&nbsp;         "shortDescription": "Create or update a Codex skill"

&nbsp;       },

&nbsp;       "dependencies": {

&nbsp;         "tools": \[

&nbsp;           {

&nbsp;             "type": "env\_var",

&nbsp;             "value": "GITHUB\_TOKEN",

&nbsp;             "description": "GitHub API token"

&nbsp;           },

&nbsp;           {

&nbsp;             "type": "mcp",

&nbsp;             "value": "github",

&nbsp;             "transport": "streamable\_http",

&nbsp;             "url": "https://example.com/mcp"

&nbsp;           }

&nbsp;         ]

&nbsp;       }

&nbsp;     }

&nbsp;   ],

&nbsp;   "errors": \[]

&nbsp; }]

} }

```



To enable or disable a skill by path:



```json

{

&nbsp; "method": "skills/config/write",

&nbsp; "id": 26,

&nbsp; "params": {

&nbsp;   "path": "/Users/me/.codex/skills/skill-creator/SKILL.md",

&nbsp;   "enabled": false

&nbsp; }

}

```



\## Apps (connectors)



Use `app/list` to fetch available apps. In the CLI/TUI, `/apps` is the user-facing picker; in custom clients, call `app/list` directly. Each entry includes both `isAccessible` (available to the user) and `isEnabled` (enabled in `config.toml`) so clients can distinguish install/access from local enabled state.



```json

{ "method": "app/list", "id": 50, "params": {

&nbsp; "cursor": null,

&nbsp; "limit": 50,

&nbsp; "threadId": "thread-1",

&nbsp; "forceRefetch": false

} }

{ "id": 50, "result": {

&nbsp; "data": \[

&nbsp;   {

&nbsp;     "id": "demo-app",

&nbsp;     "name": "Demo App",

&nbsp;     "description": "Example connector for documentation.",

&nbsp;     "logoUrl": "https://example.com/demo-app.png",

&nbsp;     "installUrl": "https://chatgpt.com/apps/demo-app/demo-app",

&nbsp;     "isAccessible": true,

&nbsp;     "isEnabled": true

&nbsp;   }

&nbsp; ],

&nbsp; "nextCursor": null

} }

```



If you provide `threadId`, app feature gating (`features.apps`) uses that thread's config snapshot. When omitted, app-server uses the latest global config.



`app/list` returns after both accessible apps and directory apps load. Set `forceRefetch: true` to bypass app caches and fetch fresh data. Cache entries are only replaced when refreshes succeed.



The server also emits `app/list/updated` notifications whenever either source (accessible apps or directory apps) finishes loading. Each notification includes the latest merged app list.



```json

{

&nbsp; "method": "app/list/updated",

&nbsp; "params": {

&nbsp;   "data": \[

&nbsp;     {

&nbsp;       "id": "demo-app",

&nbsp;       "name": "Demo App",

&nbsp;       "description": "Example connector for documentation.",

&nbsp;       "logoUrl": "https://example.com/demo-app.png",

&nbsp;       "installUrl": "https://chatgpt.com/apps/demo-app/demo-app",

&nbsp;       "isAccessible": true,

&nbsp;       "isEnabled": true

&nbsp;     }

&nbsp;   ]

&nbsp; }

}

```



Invoke an app by inserting `$<app-slug>` in the text input and adding a `mention` input item with the `app://<id>` path (recommended).



```json

{

&nbsp; "method": "turn/start",

&nbsp; "id": 51,

&nbsp; "params": {

&nbsp;   "threadId": "thread-1",

&nbsp;   "input": \[

&nbsp;     {

&nbsp;       "type": "text",

&nbsp;       "text": "$demo-app Pull the latest updates from the team."

&nbsp;     },

&nbsp;     {

&nbsp;       "type": "mention",

&nbsp;       "name": "Demo App",

&nbsp;       "path": "app://demo-app"

&nbsp;     }

&nbsp;   ]

&nbsp; }

}

```



\## Auth endpoints



The JSON-RPC auth/account surface exposes request/response methods plus server-initiated notifications (no `id`). Use these to determine auth state, start or cancel logins, logout, and inspect ChatGPT rate limits.



\### Authentication modes



Codex supports three authentication modes. `account/updated.authMode` shows the active mode, and `account/read` also reports it.



\- \*\*API key (`apikey`)\*\* - the caller supplies an OpenAI API key and Codex stores it for API requests.

\- \*\*ChatGPT managed (`chatgpt`)\*\* - Codex owns the ChatGPT OAuth flow, persists tokens, and refreshes them automatically.

\- \*\*ChatGPT external tokens (`chatgptAuthTokens`)\*\* - a host app supplies `idToken` and `accessToken` directly. Codex stores these tokens in memory, and the host app must refresh them when asked.



\### API overview



\- `account/read` - fetch current account info; optionally refresh tokens.

\- `account/login/start` - begin login (`apiKey`, `chatgpt`, or `chatgptAuthTokens`).

\- `account/login/completed` (notify) - emitted when a login attempt finishes (success or error).

\- `account/login/cancel` - cancel a pending ChatGPT login by `loginId`.

\- `account/logout` - sign out; triggers `account/updated`.

\- `account/updated` (notify) - emitted whenever auth mode changes (`authMode`: `apikey`, `chatgpt`, `chatgptAuthTokens`, or `null`).

\- `account/chatgptAuthTokens/refresh` (server request) - request fresh externally managed ChatGPT tokens after an authorization error.

\- `account/rateLimits/read` - fetch ChatGPT rate limits.

\- `account/rateLimits/updated` (notify) - emitted whenever a user's ChatGPT rate limits change.

\- `mcpServer/oauthLogin/completed` (notify) - emitted after a `mcpServer/oauth/login` flow finishes; payload includes `{ name, success, error? }`.



\### 1) Check auth state



Request:



```json

{ "method": "account/read", "id": 1, "params": { "refreshToken": false } }

```



Response examples:



```json

{ "id": 1, "result": { "account": null, "requiresOpenaiAuth": false } }

```



```json

{ "id": 1, "result": { "account": null, "requiresOpenaiAuth": true } }

```



```json

{

&nbsp; "id": 1,

&nbsp; "result": { "account": { "type": "apiKey" }, "requiresOpenaiAuth": true }

}

```



```json

{

&nbsp; "id": 1,

&nbsp; "result": {

&nbsp;   "account": {

&nbsp;     "type": "chatgpt",

&nbsp;     "email": "user@example.com",

&nbsp;     "planType": "pro"

&nbsp;   },

&nbsp;   "requiresOpenaiAuth": true

&nbsp; }

}

```



Field notes:



\- `refreshToken` (boolean): set `true` to force a token refresh in managed ChatGPT mode. In external token mode (`chatgptAuthTokens`), app-server ignores this flag.

\- `requiresOpenaiAuth` reflects the active provider; when `false`, Codex can run without OpenAI credentials.



\### 2) Log in with an API key



1\. Send:



&nbsp;  ```json

&nbsp;  {

&nbsp;    "method": "account/login/start",

&nbsp;    "id": 2,

&nbsp;    "params": { "type": "apiKey", "apiKey": "sk-..." }

&nbsp;  }

&nbsp;  ```



2\. Expect:



&nbsp;  ```json

&nbsp;  { "id": 2, "result": { "type": "apiKey" } }

&nbsp;  ```



3\. Notifications:



&nbsp;  ```json

&nbsp;  {

&nbsp;    "method": "account/login/completed",

&nbsp;    "params": { "loginId": null, "success": true, "error": null }

&nbsp;  }

&nbsp;  ```



&nbsp;  ```json

&nbsp;  { "method": "account/updated", "params": { "authMode": "apikey" } }

&nbsp;  ```



\### 3) Log in with ChatGPT (browser flow)



1\. Start:



&nbsp;  ```json

&nbsp;  { "method": "account/login/start", "id": 3, "params": { "type": "chatgpt" } }

&nbsp;  ```



&nbsp;  ```json

&nbsp;  {

&nbsp;    "id": 3,

&nbsp;    "result": {

&nbsp;      "type": "chatgpt",

&nbsp;      "loginId": "<uuid>",

&nbsp;      "authUrl": "https://chatgpt.com/...\&redirect\_uri=http%3A%2F%2Flocalhost%3A<port>%2Fauth%2Fcallback"

&nbsp;    }

&nbsp;  }

&nbsp;  ```



2\. Open `authUrl` in a browser; the app-server hosts the local callback.

3\. Wait for notifications:



&nbsp;  ```json

&nbsp;  {

&nbsp;    "method": "account/login/completed",

&nbsp;    "params": { "loginId": "<uuid>", "success": true, "error": null }

&nbsp;  }

&nbsp;  ```



&nbsp;  ```json

&nbsp;  { "method": "account/updated", "params": { "authMode": "chatgpt" } }

&nbsp;  ```



\### 3b) Log in with externally managed ChatGPT tokens (`chatgptAuthTokens`)



Use this mode when a host application owns the user's ChatGPT auth lifecycle and supplies tokens directly.



1\. Send:



&nbsp;  ```json

&nbsp;  {

&nbsp;    "method": "account/login/start",

&nbsp;    "id": 7,

&nbsp;    "params": {

&nbsp;      "type": "chatgptAuthTokens",

&nbsp;      "idToken": "<jwt>",

&nbsp;      "accessToken": "<jwt>"

&nbsp;    }

&nbsp;  }

&nbsp;  ```



2\. Expect:



&nbsp;  ```json

&nbsp;  { "id": 7, "result": { "type": "chatgptAuthTokens" } }

&nbsp;  ```



3\. Notifications:



&nbsp;  ```json

&nbsp;  {

&nbsp;    "method": "account/login/completed",

&nbsp;    "params": { "loginId": null, "success": true, "error": null }

&nbsp;  }

&nbsp;  ```



&nbsp;  ```json

&nbsp;  {

&nbsp;    "method": "account/updated",

&nbsp;    "params": { "authMode": "chatgptAuthTokens" }

&nbsp;  }

&nbsp;  ```



When the server receives a `401 Unauthorized`, it may request refreshed tokens from the host app:



```json

{

&nbsp; "method": "account/chatgptAuthTokens/refresh",

&nbsp; "id": 8,

&nbsp; "params": { "reason": "unauthorized", "previousAccountId": "org-123" }

}

{ "id": 8, "result": { "idToken": "<jwt>", "accessToken": "<jwt>" } }

```



The server retries the original request after a successful refresh response. Requests time out after about 10 seconds.



\### 4) Cancel a ChatGPT login



```json

{ "method": "account/login/cancel", "id": 4, "params": { "loginId": "<uuid>" } }

{ "method": "account/login/completed", "params": { "loginId": "<uuid>", "success": false, "error": "..." } }

```



\### 5) Logout



```json

{ "method": "account/logout", "id": 5 }

{ "id": 5, "result": {} }

{ "method": "account/updated", "params": { "authMode": null } }

```



\### 6) Rate limits (ChatGPT)



```json

{ "method": "account/rateLimits/read", "id": 6 }

{ "id": 6, "result": {

&nbsp; "rateLimits": {

&nbsp;   "limitId": "codex",

&nbsp;   "limitName": null,

&nbsp;   "primary": { "usedPercent": 25, "windowDurationMins": 15, "resetsAt": 1730947200 },

&nbsp;   "secondary": null

&nbsp; },

&nbsp; "rateLimitsByLimitId": {

&nbsp;   "codex": {

&nbsp;     "limitId": "codex",

&nbsp;     "limitName": null,

&nbsp;     "primary": { "usedPercent": 25, "windowDurationMins": 15, "resetsAt": 1730947200 },

&nbsp;     "secondary": null

&nbsp;   },

&nbsp;   "codex\_other": {

&nbsp;     "limitId": "codex\_other",

&nbsp;     "limitName": "codex\_other",

&nbsp;     "primary": { "usedPercent": 42, "windowDurationMins": 60, "resetsAt": 1730950800 },

&nbsp;     "secondary": null

&nbsp;   }

&nbsp; }

} }

{ "method": "account/rateLimits/updated", "params": {

&nbsp; "rateLimits": {

&nbsp;   "limitId": "codex",

&nbsp;   "primary": { "usedPercent": 31, "windowDurationMins": 15, "resetsAt": 1730948100 }

&nbsp; }

} }

```



Field notes:



\- `rateLimits` is the backward-compatible single-bucket view.

\- `rateLimitsByLimitId` (when present) is the multi-bucket view keyed by metered `limit\_id` (for example `codex`).

\- `limitId` is the metered bucket identifier.

\- `limitName` is an optional user-facing label for the bucket.

\- `usedPercent` is current usage within the quota window.

\- `windowDurationMins` is the quota window length.

\- `resetsAt` is a Unix timestamp (seconds) for the next reset.

