# 🧠 AgentGovernor: A Declarative AI Workflow Planner

**AgentGovernor** is an advanced AI agent architecture that moves **Beyond Code Mode**.
It addresses the **security**, **auditability**, and **reliability** gaps of `eval()`-based agents by enforcing a strict separation between **planning** and **execution**.

Instead of generating and running code, **LLMs are used as planners** to generate declarative **PlanYAML** files.
These plans are then validated and executed by a **trusted, deterministic workflow engine**.

---

## 🏗️ Core Architecture

This project is built on a **Plan-Validate-Execute** model that ensures **governance by design**.

### 🪄 Plan

A user's natural language goal is decomposed by an LLM into multiple sub-queries.
These queries are fed into a **Multi-Query RAG system** to retrieve relevant tools and past workflow examples.
This context is used to build a **RICECO (Role, Instruction, Context, Examples, Constraints, Output)** prompt,
which the planner LLM uses to generate a **PlanYAML**.

### 🔍 Validate

The **PlanYAML** is immediately passed to a **PlanValidator**.
This is the core of the **Self-Healing Loop**:

* **RAG Failure:** If the plan uses a tool that wasn't retrieved (a RAG failure), the agent asks the LLM to generate an expansion query to find the missing tools and retries the plan.
* **Syntax Failure:** If the plan has a schema error (e.g., missing argument), the agent asks the LLM to perform a standard syntax repair.

### ⚙️ Execute

Once a plan is 100% valid, it is presented to the user.
After approval, a **deterministic DAG Executor** runs the plan, managing parallel tasks and dependencies to call the MCP tool servers.

---

## ✨ Key Features

### 🧾 Declarative Planning

The LLM's only output is **data (YAML)** — not code.
This completely eliminates the attack surface of `eval()`-based agents.

### 🔁 Deterministic DAG Execution

A trusted `workflow_executor.py` runs the validated plan as a **Directed Acyclic Graph**,
enabling parallel execution of independent steps for high efficiency.

### 🧩 Advanced Multi-RAG

The agent uses two separate **Qdrant collections** for “scaffolding” the LLM:

* **Tool RAG:** A multi-query, per-query-reranked retriever (`tool_retriever.py`) finds the specific tools needed for the job.
* **Workflow RAG:** A second retriever (`workflow_retriever.py`) finds past successful plans to use as dynamic examples in the prompt.

### 🛠️ Multi-Stage Self-Healing

The planner intelligently distinguishes between a **RAG Failure** (missing tool) and a **Syntax Failure** (bad YAML)
and applies the correct repair strategy.

---

## 🛡️ Governance by Design

* **Secure:** No arbitrary code execution.
* **Auditable:** The PlanYAML is the audit log — human-readable and shows intent before execution.
* **Reliable:** Deterministic validation and execution prevent LLM hallucinations from running.

---

## 🚀 Getting Started

### 🧩 Prerequisites

* **Python 3.12+ (and uv)**
* **Docker & Docker Compose** (for Qdrant)
* **An LLM endpoint** (e.g., OpenRouter, LM Studio)

---

### 1️⃣ Setup Environment

Clone the repository:

```bash
git clone https://github.com/veristamp/AgentGovernor
cd AgentGovernor
```

Install dependencies:

```bash
uv venv
source .venv/bin/activate
uv sync
```

Create your `.env` file:
Copy the `.env.example` (if one exists) or create a new `.env` file and add your LLM API keys and model names.

```bash
OPENROUTER_API_KEY="sk-or-..." #use only if you are using any open router model
LLM_MODEL_NAME="granite-4.0-micro" # Use your own LLM
```

Start services (launches Qdrant):

```bash
docker-compose up -d
```

---

### 2️⃣ Ingest Data

Before you can run the planner, you must populate the RAG databases.
Update the mcp_server.json file with the mcp servers you want to use.
```bash
uv run -m list_tools.py
```
this emits the tools to the tools_schema.json

The `upsert.py` script ingests both tools and workflows.

```bash
# This finds tools in tools_schema.json and workflows in /workflows
uv run upsert.py

```

This will populate two collections in Qdrant:

* `mcp_tools`: The schemas for all available MCP tools.
* `mcp_workflows`: The successful, human-approved workflow examples for RAG.

---

## 🧠 How to Use

The main entrypoint is **run.py**.
It takes a natural language goal, generates a plan, and prompts you for execution.

```bash
uv run .\run.py --goal "Your natural language goal here"
```

### 💡 Example

```bash
uv run .\run.py --goal "list all files in the root, save the list to list.md, and then create a memory entity with the content"
```

---

### 🧩 Example Workflow

The agent will find the tools, generate a plan, and ask for approval:

```yaml
INFO :: --- ✅ FINAL VALIDATED PLAN ---
version: 1
description: list all files in the root, save the list to list.md, and then create
  a memory entity with the content
vars:
  target_dir: .
  output_file: list.md
steps:
  list_files:
    tool: filesystem.list_directory
    args:
      path: ${vars.target_dir}
    save_as: file_list
  write_report:
    tool: filesystem.write_file
    args:
      path: ${vars.output_file}
      content: ${steps.list_files.output}
    depends_on:
    - list_files
  save_to_memory:
    tool: memory.create_entities
    args:
      entities:
      - name: FileReport
        entityType: Report
        observations:
        - ${steps.list_files.output}
    depends_on:
    - write_report
```

After execution:

```
Press [Enter] to execute this plan, or [Ctrl+C] to cancel...
```

After the plan executes:

```
Do you want to save this successful workflow for RAG? [y/n]: y
INFO :: --- ✅ Workflow saved successfully to workflows/wf_...yaml ---
INFO :: You can run 'uv run -m upsert' to add it to the RAG database.
```

---

## 📁 Project Structure

```
AgentGovernor/
│
├── Agent/                    # The "brain" of the planner
│   ├── tool_retriever.py     # RAG for finding tools
│   ├── workflow_retriever.py # RAG for finding past examples
│   ├── prompt_builder.py     # Builds the RICECO prompt
│   ├── plan_validator.py     # The security/reliability gate
│   ├── llm_client.py         # Handles communication with the LLM
│   └── ...
│
├── mcp_client/               # The "hands" of the executor
│   ├── workflow_executor.py  # The core DAG execution engine
│   ├── manager.py            # Manages MCP connections
│   └── ...
│
├── workflows/                # Stores successful, human-approved plans
│   ├── code.yaml
│   ├── context.yaml
│   └── ...
│
├── run.py                    # Main entrypoint: Plan -> Confirm -> Execute
├── run_planner.py            # The core planning & self-healing loop
├── upsert.py                 # Ingests tools AND workflows into Qdrant
│
├── mcp_servers.json          # Defines all MCP tool microservices
├── tools_schema.json         # The master schema of all available tools
│
├── filesystem.py             # MCP server for filesystem tools
├── terminal.py               # MCP server for terminal commands
├── memory.py                 # MCP server for knowledge graph memory
│
├── docker-compose.yml        # Starts Qdrant
└── pyproject.toml
```

---

💡 **Tip:** For a complete audit trail, every successful plan is stored in `/workflows`, making your AI operations reproducible, secure, and inspectable.

---