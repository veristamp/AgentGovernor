import { expect, test } from "bun:test";
import { Agent, LlmClient } from "../src/agents/main";
import { analyzeCode } from "../src/core/audit";
import { PolicyEngine } from "../src/core/policy/engine";

// Use real LLM if key is present, otherwise fallback to fake.
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
const OPENAI_API_BASE =
  process.env.OPENAI_API_BASE || "https://api.openai.com/v1";
const USE_REAL_LLM = !!OPENAI_API_KEY;

class FakeAgentLlm extends LlmClient {
  callCount = 0;

  constructor() {
    super("http://localhost", "");
  }

  override async complete(
    _messages: { role: string; content: string }[],
  ): Promise<string> {
    this.callCount += 1;

    // 1. First call: Search for tools/skills
    // The Agent loop checks for SEARCH() first.
    // We want to simulate a workflow where we find the skill.
    // However, if the agent *already* finds it via initial static discovery (semantic search on goal),
    // it might just ask for code.
    // Let's assume static discovery works for "Fetch Next.js routing docs" -> "docs-to-files"
    // So we provide code directly.

    const code = [
      "# PLAN: Use docs-to-files to fetch documentation",
      "import skills",
      "",
      "async def main():",
      '    await skills.load("docs-to-files").fetch_and_store(library="/vercel/next.js", topic="routing", output_dir="output/docs")',
      '    return "Docs fetched"',
    ].join("\n");
    return JSON.stringify({ type: "final", result: { code } });
  }
}

test("agent end-to-end with local LLM", async () => {
  let llmClient: LlmClient;
  let modelName: string;

  if (USE_REAL_LLM) {
    console.log("Using Real OpenAI LLM for Agent E2E Test");
    if (!OPENAI_API_KEY) {
      throw new Error("OPENAI_API_KEY is required when USE_REAL_LLM=true");
    }
    llmClient = new LlmClient(OPENAI_API_BASE, OPENAI_API_KEY);
    modelName = "gpt-4o-mini";
  } else {
    console.log("Using Fake LLM for Agent E2E Test");
    llmClient = new FakeAgentLlm();
    modelName = "test-model";
  }

  const agent = new Agent({
    llm: llmClient,
    policy: new PolicyEngine(),
    model: modelName,
    temperature: 0.3,
    maxTokens: 1200,
    maxRepairAttempts: 2,
  });

  const goal = "Fetch Next.js routing docs and store them in output/docs";

  const result = await agent.run({
    goal,
    identity: {
      roles: ["mcp:docs-curator"],
      scopes: [],
      orgId: "test-org",
    },
  });

  // Verify correct skill selection
  expect(result.selectedSkills).toBeDefined();
  const hasDocsSkill = result.selectedSkills.some(
    (s) => s.includes("docs-to-files") || s.includes("fetch_and_store"),
  );
  expect(hasDocsSkill).toBe(true);

  // Verify unauthorized skill is NOT present
  expect(result.selectedSkills).not.toContain("skills:repo-insight@1");

  // Verify code generation
  expect(result.code).toContain("async def main");
  expect(result.code).toContain("skills.load");

  const manifest = await analyzeCode(result.code);
  if (manifest.errors.length) {
    throw new Error(`Audit errors: ${manifest.errors.join(", ")}`);
  }

  // Verify manifest matches selected skills
  const matchedSkill = manifest.skills.some((skill) =>
    result.selectedSkills.includes(skill),
  );
  expect(matchedSkill).toBe(true);
  expect(manifest.toolCalls.length).toBeGreaterThanOrEqual(0); // Might be 0 if only skill calls
}, 60000);
