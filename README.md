# A/MCL — Agent/Multi-Coding-agent Context Layer

**Zero-intervention context persistence across AI coding agents.**

When you hit a rate limit on one agent (Codex, Antigravity, Cursor, Claude Code) and switch to another, A/MCL ensures the new agent *automatically* has access to the complete conversation history, file changes, reasoning chains, and project state. No commands. No manual handoff. It just works.

---

## How It Works

A/MCL is an **MCP (Model Context Protocol) server**. MCP-compatible agents discover it automatically at launch and gain access to shared project context via standard tools, resources, and prompts.

```
┌──────────────┐     stdio      ┌────────────────┐     SQLite     ┌──────────┐
│  AI Agent    │ ◄────────────► │  A/MCL Server  │ ◄────────────► │  Context │
│ (Codex,      │                │  (FastMCP)     │                │  Store   │
│  Cursor, etc)│                │                │                │ (~/.amcl)│
└──────────────┘                └────────────────┘                └──────────┘
```

1. **Install once** → `pip install amcl-server` (or `pip3 install`)
2. **Setup** → `amcl-server setup` (creates DB, shows MCP config)
3. **Use your agents normally** → Context is automatically shared
4. **Switch agents** → New agent picks up exactly where the last one left off

---

## Quick Start

```bash
# Install universally
pip install amcl-server  # or pip3 install amcl-server

# Initialize and Auto-Register
amcl-server setup

# Verify integrations
amcl-server check

# Check status
amcl-server status
```

### Upgrading an Existing Installation

```bash
pip install --upgrade amcl-server
amcl-server setup
amcl-server check
```

The `setup` command automatically detects all installed AI agents and IDE extensions on your system and registers A/MCL directly into their settings. Once you run setup, you are completely done.
It also installs or updates Codex's global `~/.codex/AGENTS.md` so Codex inherits the same A/MCL behavior rules without touching repository-local `AGENTS.md` files.

---

## Supported Agents (Auto-Detected)

A/MCL automatically integrates with:
- **Cursor** (`~/.cursor/mcp.json`)
- **Codex** (`~/.codex/config.toml`)
- **Claude Desktop / Antigravity** (`Library/Application Support/Claude/claude_desktop_config.json`)
- **Amp** (`~/.amp/mcp.json`)
- **Roo / Cline** (VSCode & Cursor instances)
- **Generic MCP clients** (`~/.mcp/config.json`)

If your agent isn't automatically found, the `setup` command will print the exact JSON snippet you can manually paste into its MCP configuration.

---

## What Gets Shared

| Category | Data |
|----------|------|
| **Conversation** | All messages between user and agents, with agent attribution |
| **File Changes** | Files created, modified, deleted — tracked automatically |
| **Tasks** | Current goal, active tasks, completed work, blockers |
| **Decisions** | Design decisions with rationale and alternatives considered |
| **Agent History** | Which agents worked on what, session timestamps |

---

## MCP Tools

Agents can invoke these tools:

| Tool | Description |
|------|-------------|
| `context_get_current` | Full project context snapshot |
| `context_update` | Append new conversation/file/decision data |
| `context_query` | Search context history |
| `context_get_files_changed` | Files changed since last agent switch |
| `context_get_conversation` | Recent N messages |
| `context_get_reasoning` | Decision log |
| `context_add_decision` | Log a design decision |
| `context_mark_complete` | Mark a task as completed |
| `context_add_blocker` | Record a blocking issue |

---

## MCP Resources

Read-only data endpoints:

- `context://current-project` — Complete snapshot
- `context://conversation` — Message history
- `context://files` — File state & changes
- `context://reasoning` — Decision log
- `context://tasks` — Task state
- `context://agents` — Agent session history

---

## MCP Prompts

Pre-built prompts for context injection:

- **Project Context** — Complete project overview
- **Recent Work** — Summary of last session
- **Continuation** — "Pick up where we left off"
- **Decisions Log** — Key decisions and rationale

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AMCL_DATA_DIR` | `~/.amcl` | Where context database lives |
| `AMCL_LOG_LEVEL` | `WARNING` | Logging verbosity |
| `AMCL_AGENT_NAME` | `unknown` | Name of the connecting agent |
| `AMCL_PROJECT_DIR` | `cwd` | Project directory override |

---



---

## Privacy

All data stays local on your machine in `~/.amcl/amcl.db`. Nothing is ever sent to external servers. No telemetry, no analytics.

---

## License

MIT
