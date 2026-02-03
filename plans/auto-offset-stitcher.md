# Auto-Offset Stitcher Design

## Problem Statement

Current `stitch_file` requires LLM to calculate byte offsets:
```typescript
{
  source: "src/utils.ts",
  start: 1234,  // LLM must calculate this
  end: 1567,    // LLM must calculate this
}
```

This is **error-prone** and **cognitively expensive** for LLMs.

## Simplified Interface for New File Creation

For stitching **new files** (the primary use case):

| Parameter | Meaning | Default |
|-----------|---------|---------|
| `grafts` | Chunks to assemble | Required |
| `output_path` | Where to save | Required |
| `overwrite` | Replace if exists? | `false` |
| `preview` | Just show assembled content? | `true` |

**Key Insight**: `preview=true` (dry_run) is the DEFAULT for new files. You must explicitly set `preview=false` to write.

### No Overwrite by Default (Safest)

```typescript
// Safe: Fails if output exists
stitch_file({
  grafts: [...],
  output_path: "generated/new-file.ts"
})

// Explicitly allow overwrite
stitch_file({
  grafts: [...],
  output_path: "generated/new-file.ts",
  overwrite: true  // Must explicitly allow
})
```

## Solution: Smart Stitcher with Auto-Offset Calculation

Create a new abstraction that accepts **human-friendly inputs** and calculates offsets internally.

### Input Types Supported

| Input Type | Example | When to Use |
|------------|---------|-------------|
| Line Range | `{ start_line: 10, end_line: 20 }` | When you know line numbers |
| Pattern Match | `{ find: "function foo()", after: 2 }` | Find by content |
| Symbol Reference | `{ symbol: "AuthService", type: "class" }` | From KB/graph |

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SmartStitcher                             │
├─────────────────────────────────────────────────────────────┤
│  stitch_from_lines()  │  stitch_from_pattern()              │
│       │                       │                              │
│       ▼                       ▼                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │            OffsetCalculator                          │   │
│  │  - read_file()                                       │   │
│  │  - line_to_byte_offset(line)                         │   │
│  │  - find_pattern(pattern) → (start, end)              │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │                                  │
│                           ▼                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │            assemble()                                 │   │
│  │  - Concatenate chunks                                │   │
│  │  - Add glue code                                     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Example Usage

**Before (LLM calculates offsets):**
```typescript
// Error-prone! LLM must count bytes
{
  source: "src/auth.ts",
  start: 1234,
  end: 1456,
  comment: "Auth logic"
}
```

**After (LLM uses line numbers):**
```typescript
// Natural for LLMs - just use line numbers
{
  type: "lines",
  source: "src/auth.ts",
  start_line: 42,
  end_line: 58,
  comment: "Auth logic"
}
```

**Or by pattern:**
```typescript
// Let the tool find the content
{
  type: "pattern",
  source: "src/auth.ts",
  find: "class AuthService {",
  comment: "Auth logic"
}
```

### MCP Tool Schema

```typescript
server.registerTool("stitch_file", {
  title: "Stitch File",
  description: "Assemble a new file from source code chunks. Uses line numbers - no offset calculation needed.",
  inputSchema: {
    grafts: z.array(z.object({
      // Smart input (one of these required)
      start_line: z.number().optional(),     // Line-based
      end_line: z.number().optional(),       // Line-based
      find: z.string().optional(),           // Pattern-based
      
      // Metadata
      source: z.string(),                    // Source file
      comment: z.string().optional(),        // Auto-formatted comment
      glue: z.string().optional(),           // Code between chunks
    })),
    output_path: z.string(),
    overwrite: z.boolean().default(false),   // Fail if exists
    preview: z.boolean().default(true),      // Don't write by default
  }
});
```

### Simplified Implementation

```typescript
// mcp-servers/agent-filesystem/src/lib/smart-stitcher.ts

export type SmartGraft =
  | { type: "lines"; start_line: number; end_line: number; source: string; comment?: string; glue?: string }
  | { type: "pattern"; find: string; source: string; comment?: string; glue?: string };

export async function stitchFile(
  grafts: SmartGraft[],
  outputPath: string,
  options: { overwrite?: boolean; preview?: boolean } = {}
): Promise<StitchResult> {
  const preview = options.preview ?? true;  // Default to preview!
  const overwrite = options.overwrite ?? false;
  
  // 1. Read all source files
  const sources: Record<string, string> = {};
  for (const graft of grafts) {
    if (!sources[graft.source]) {
      sources[graft.source] = await readFile(graft.source);
    }
  }
  
  // 2. Convert smart grafts to byte offsets
  const byteGrafts = grafts.map(graft => {
    const content = sources[graft.source];
    if (graft.type === "lines") {
      return linesToByteGraft(graft, content);
    } else {
      return patternToByteGraft(graft, content);
    }
  });
  
  // 3. Assemble
  const { content, stats } = assemble(byteGrafts, sources);
  
  // 4. Write or return preview
  if (preview) {
    return { preview: true, content, ...stats };
  }
  
  if (exists(outputPath) && !overwrite) {
    throw new Error(`File exists: ${outputPath}. Use overwrite=true to replace.`);
  }
  
  await writeFile(outputPath, content);
  return { success: true, ...stats };
}

function linesToByteGraft(graft, content) {
  const lines = content.split("\n");
  const startLineIdx = graft.start_line - 1;
  const endLineIdx = graft.end_line;
  
  // Calculate byte offsets
  const start = content.indexOf(lines[startLineIdx]);
  const end = start + lines.slice(startLineIdx, endLineIdx).join("\n").length;
  
  return {
    start,
    end,
    comment: graft.comment,
    glue: graft.glue
  };
}

function patternToByteGraft(graft, content) {
  const idx = content.indexOf(graft.find);
  if (idx === -1) {
    throw new Error(`Pattern not found: ${graft.find}`);
  }
  
  return {
    start: idx,
    end: idx + graft.find.length,
    comment: graft.comment,
    glue: graft.glue
  };
}
```

### Benefits

1. **No Math Required**: LLM uses line numbers (natural for code)
2. **Safe by Default**: `preview=true` prevents accidental writes
3. **Fail on Overwrite**: Explicit `overwrite=true` required to replace files
4. **Error-Proof**: Offsets calculated programmatically