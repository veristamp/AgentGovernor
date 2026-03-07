### Acknowledgement & Analysis of Current Codebase

I have analyzed your entire `mcp-inspector` / `AgentGovernor` codebase. It is a sophisticated, working implementation of a **Declarative (YAML-based) Agent**.

**Current State Assessment:**
* [cite_start]**The Brain (Planner):** You have a robust RAG pipeline (`tool_retriever.py` [cite: 348][cite_start], `workflow_retriever.py` [cite: 374]) that effectively scaffolds the LLM. [cite_start]The `run_planner.py` correctly implements the "Plan-Validate-Repair" loop[cite: 177].
* [cite_start]**The Guard (Validator):** Your `PlanValidator` [cite: 275] is currently doing heavy lifting, validating YAML structure and tool arguments against schemas.
* [cite_start]**The Hands (Executor):** Your `workflow_executor.py` [cite: 500] is essentially a **custom interpreter**. [cite_start]You have re-implemented control flow (`if`, `loop`, `set`) in Python to execute the YAML DAG [cite: 518-524].
* [cite_start]**The Backbone (MCP):** Your `MCPClientManager` [cite: 402] is a clean, centralized hub for managing connections and routing tool calls.

---

### The Upgradation Path: From "Interpreter" to "Governor"

Your move to **"Governed Code Mode"** (The Final Plan) is not a refactor; it is a **paradigm shift**.

Currently, you are limiting the LLM to YAML, forcing you to write a complex interpreter (`workflow_executor.py`) to handle basic logic like loops.

**The Upgrade:** You will stop *interpreting* logic and start *sandboxing* it.

Here is the concrete roadmap to transform this codebase into the "Governed Code Mode" architecture:

#### 1. Transform `mcp_client/manager.py` into the "Policy Gate" (Pillar 1)
Currently, `manager.py` is just a client. It needs to become the **Governance Layer**.
* [cite_start]**Current:** `execute_action` [cite: 428] blindly calls the tool.
* **Upgrade:** In `execute_action`, inject the **Auth/ABAC logic** we discussed.
    * Before calling `session.call_tool`, check the "Derived Manifest" (allowlist).
    * If allowed, inject the `X-User-ID` / `X-ABAC-Filter` headers (if the tool is your FastAPI service) or attach API keys (if it's an external tool).
    * **This is where the "Zero Trust" happens.**

#### 2. Replace `workflow_executor.py` with the "Sandbox Runner"
* [cite_start]**Current:** You parse YAML and manually execute `if` / `loop` logic in Python [cite: 513-524].
* **Upgrade:** Delete the custom logic parser. Replace it with a secure runtime (e.g., a V8 Isolate wrapper or a secure Python micro-VM).
* **The Interaction:**
    * The LLM generates a `.ts` or `.py` file.
    * The Sandbox executes it.
    * When the code calls `await gdrive.list()`, the Sandbox pauses and calls back to your `MCPClientManager`.

#### 3. Refactor `run_planner.py` (Pillar 2 & 3)
* [cite_start]**Current:** Prompts for YAML using `SYSTEM_PROMPT_PLAN`[cite: 182].
* **Upgrade:** Change the prompt to request **Code** (TypeScript/Python) using the "Single-Artifact" template.
* [cite_start]**Retention:** Keep your excellent `tool_retriever.py` (RAG)[cite: 348]. The "Progressive Discovery" logic stays exactly the same; it just feeds a Code Generator instead of a YAML Generator.

#### 4. Transform `PlanValidator` into the "Static Auditor" (Pillar 4)
* [cite_start]**Current:** Validates YAML schema and arguments[cite: 275].
* **Upgrade:** Change this to an **AST Parser**.
    * Instead of checking `yaml.safe_load`, it will use `ast.parse()` (Python) or a TS parser.
    * It will traverse the code to find *imports* and *function calls*.
    * **Output:** It generates the "Derived Manifest" (e.g., `{"io_calls": ["gdrive.list_files"]}`) which you hand to the **Policy Gate**.

### Summary of the Pivot

| Component | Current Codebase | **Governed Code Mode (Target)** |
| :--- | :--- | :--- |
| **Language** | YAML (DSL) | TypeScript / Python (Native) |
| **Logic Engine** | `workflow_executor.py` (Custom Interpreter) | V8 Isolate / Micro-VM (Sandbox) |
| **Validation** | `PlanValidator` (Schema Check) | **Static Auditor** (AST Analysis) |
| **Security** | Validator checks inputs pre-execution | **Policy Gate** checks I/O at runtime + ABAC |
| **Context** | RAG finds tools for YAML | RAG finds tools for **Types/Bindings** |

**Verdict:** You have a rock-solid foundation. The "skeleton" (RAG, MCP connection, Orchestration loop) is perfect. You are simply swapping out the "muscle" (YAML execution) for a much stronger one (Sandboxed Code).

**Next Step:** Would you like to start by designing the **Static Auditor** (Pillar 4) to parse a Python AST and generate a manifest, or would you prefer to build the **Policy Gate** logic into your `MCPClientManager` first?
===================================================

**No, we do not lose workflows.** In fact, we make them much more powerful.

In your current YAML system, a "workflow" is just a text file sitting in `workflows/*.yaml` that you upsert into Qdrant.

In **Governed Code Mode**, a "workflow" becomes a **Standardized Script**. It is still a file, it is still saved, and it is still reusable by RAG. The only difference is that instead of `steps:` in YAML, it uses `async function main()` in Python/TypeScript.

Here is how we save, index, and reuse workflows in the new system.

### 1\. The New "Workflow Artifact"

Currently, your system saves a `.yaml` file. In the new system, when a user confirms a plan, we save a **`.py` (or `.ts`) file** into the `workflows/` directory.

**Old YAML Artifact (`workflows/wf_123.yaml`):**

```yaml
description: "Count pending users"
steps:
  get_users:
    tool: gdrive.get_sheet ...
```

**New Code Artifact (`workflows/wf_123.py`):**

```python
"""
METADATA:
description: Count pending users and post to Slack
tags: [reporting, slack, gdrive]
inputs:
  sheet_name: str
  channel_id: str
"""
import gdrive
import slack

async def main(sheet_name: str, channel_id: str):
    # 1. Fetch
    users = await gdrive.get_sheet(name=sheet_name)
    # 2. Logic (The part YAML couldn't do easily)
    pending_count = len([u for u in users if u['status'] == 'pending'])
    # 3. Action
    await slack.post_message(channel=channel_id, text=f"Pending: {pending_count}")
```

### 2\. How We "Save" It (The Ingestion Update)

[cite_start]You already have `upsert.py`[cite: 229]. We just need to slightly modify it to read these new `.py` files instead of `.yaml`.

  * [cite_start]**Current Logic:** Reads `workflows/*.yaml`, parses the `description` field, embeds it, and saves it to Qdrant [cite: 243-246].
  * **New Logic:** Reads `workflows/*.py`.
      * It extracts the **Docstring** (the comment at the top) as the description.
      * It extracts the `inputs` section from the docstring to know what variables are needed.
      * It embeds the Docstring + Code into Qdrant.

**Result:** Your RAG database `mcp_workflows` now contains **Python scripts** instead of YAML snippets.

### 3\. How We "Reuse" It (The RAG Hit)

When the user asks: *"Run the weekly pending user report"*, your Planner (Pillar 2) works exactly the same way, but better.

1.  [cite_start]**Retrieval:** `workflow_retriever.py` [cite: 374] searches Qdrant. It finds `wf_123.py` because the description matches.
2.  **The Prompt:** instead of dumping a YAML example into the prompt, it dumps the **Python function signature** and docstring.
3.  **The Generation:** The LLM sees: *Ah, I don't need to write a new plan from scratch. I just need to call this existing script.*

**The LLM's new output becomes:**

```python
# PLAN: Execute the saved workflow for pending users
import workflows.wf_123 as report

async def main():
    await report.main(sheet_name="Weekly Users", channel_id="C123")
```

### Summary: What Changes?

| Feature | Old (YAML) | New (Code Mode) | Benefit |
| :--- | :--- | :--- | :--- |
| **Storage** | `.yaml` file | `.py` file | Git-friendly, syntax highlight support. |
| **Metadata** | `description:` field | Python Docstring | Standard developer practice. |
| **Logic** | Custom `loop:` / `if:` DSL | Standard `for` / `if` | **Infinite complexity allowed.** |
| **Reuse** | LLM copies YAML steps | LLM calls `import` | **Modular & Composable.** |

**You lose nothing.** You gain the ability to treat your "workflows" like a standard library of Python scripts that your agent can import and combine.

### Immediate Action Plan

To verify this, we don't need to build the whole sandbox yet. We can start by:

1.  **Standardizing the Template:** Define the exact Python template (imports, main function, docstring format).
2.  **Updating `upsert.py`:** Modify it to parse a `.py` file's docstring for the description.
3.  **Updating `run.py`:** Add the logic to save the final generated Python code to `workflows/` upon success.

Would you like to see the **Python Template** and the regex for `upsert.py` to handle this transition?

====================================================================

