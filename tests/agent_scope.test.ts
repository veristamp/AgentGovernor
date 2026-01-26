import { expect, test } from "bun:test";
import { WorkflowAgent, LlmClient } from "../src/agents/main";
import { PolicyEngine } from "../src/core/policy/engine";

class FakeLlm extends LlmClient {
  private callCount = 0;

  constructor() {
    super("http://localhost", "");
  }

  override async complete(
    messages: { role: string; content: string }[],
  ): Promise<string> {
    this.callCount += 1;
    const promptText = messages.map((message) => message.content).join("\n");
    if (
      !promptText.includes("CONTEXT:") ||
      !promptText.includes("Available Skills:")
    ) {
      throw new Error("Prompt missing RICECO context.");
    }

    if (this.callCount === 1) {
      const bad = [
        "# PLAN: demo with invalid skill",
        "import skills",
        "",
        "async def main():",
        '    result = await skills.load("repo-insight").analyze_repo(query="routing", output_dir="output/docs", note_key="demo")',
        "    return result",
      ].join("\n");
      return JSON.stringify({ type: "final", result: { code: bad } });
    }

    if (
      !promptText.includes("docs-to-files") ||
      !promptText.includes("EXAMPLES:")
    ) {
      throw new Error("Prompt did not include required context for repair.");
    }

    if (!promptText.includes("CONSTRAINTS:")) {
      throw new Error("Repair prompt missing constraints.");
    }

    const ok = [
      "# PLAN: demo",
      "import skills",
      "",
      "async def main():",
      '    result = await skills.load("docs-to-files").fetch_and_store(library="/vercel/next.js", topic="routing", output_dir="output/docs")',
      "    return result",
    ].join("\n");
    return JSON.stringify({ type: "final", result: { code: ok } });
  }
}

test("agent limits skills to scope", async () => {
  const agent = new WorkflowAgent({
    llm: new FakeLlm(),
    policy: new PolicyEngine(),
    model: "test-model",
    maxRepairAttempts: 2,
  });

  const result = await agent.run({
    goal: "Fetch docs about Next.js routing and store them",
    identity: {
      roles: ["mcp:docs-curator"],
      scopes: [],
    },
  });

  expect(result.selectedSkills).toContain("skills:docs-to-files@1");
  expect(result.selectedSkills).not.toContain("skills:repo-insight@1");
  expect(result.code).toContain('skills.load("docs-to-files").fetch_and_store');
  expect(result.repairAttempts).toBe(2);
  expect(result.prompt).toContain("CONTEXT:");
  expect(result.prompt).toContain("Available Skills:");
  expect(result.prompt).toContain("EXAMPLES:");
});
