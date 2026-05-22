"""
Comprehensive test suite for A/MCL — Agent/Multi-Coding-agent Context Layer.

Tests every critical path to guarantee the package works for anyone who
downloads it, on any system, with any combination of agents.

Run: python3 -m pytest tests/test_amcl.py -v
  or: python3 tests/test_amcl.py  (standalone)
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


def run_async(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def make_ctx_mgr(tmp_dir, project_dir=None, agent_name="test-agent"):
    """Create a ContextManager with a temp DB for testing."""
    from amcl.context.context_manager import ContextManager

    db_path = Path(tmp_dir) / "test.db"
    return ContextManager(
        db_path=db_path,
        project_dir=project_dir,
        agent_name=agent_name,
    )


# ─────────────────────────────────────────────────────────────
# 1. DATABASE & STORAGE TESTS
# ─────────────────────────────────────────────────────────────


def test_database_creates_on_fresh_install():
    """DB is created from scratch on a brand-new system."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "subdir" / "nested" / "amcl.db"
        from amcl.storage.database import get_connection

        conn = get_connection(db_path)

        # Verify tables exist
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {r["name"] for r in tables}

        assert "projects" in table_names
        assert "messages" in table_names
        assert "file_changes" in table_names
        assert "tasks" in table_names
        assert "decisions" in table_names
        assert "agent_sessions" in table_names
        assert "ingestion_checkpoints" in table_names
        assert "schema_version" in table_names
        conn.close()
        print("✅ Test 1: Database creates on fresh install")


def test_database_wal_mode():
    """DB uses WAL mode for concurrent read access."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "amcl.db"
        from amcl.storage.database import get_connection

        conn = get_connection(db_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()
        assert mode[0] == "wal", f"Expected WAL, got {mode[0]}"
        conn.close()
        print("✅ Test 2: Database uses WAL mode for concurrent access")


def test_database_schema_idempotent():
    """Opening the same DB twice doesn't corrupt it."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "amcl.db"
        from amcl.storage.database import get_connection

        conn1 = get_connection(db_path)
        conn1.close()
        conn2 = get_connection(db_path)
        # Should not raise
        versions = conn2.execute("SELECT COUNT(*) as c FROM schema_version").fetchone()
        assert versions["c"] >= 1
        conn2.close()
        print("✅ Test 3: Database schema is idempotent")


def test_storage_manager_normalizes_agent_fields():
    """Storage writes canonical agent names across all record types."""
    from amcl.storage.storage_manager import StorageManager

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "amcl.db"
        storage = StorageManager(db_path)
        pid = storage.get_or_create_project(path=tmp, name="demo")

        storage.add_message(pid, role="user", content="hi", agent="Claude Code")
        storage.add_file_change(
            pid, file_path="src/app.py", action="modified", agent="Roo / Cline"
        )
        storage.add_decision(pid, question="q", answer="a", agent="Open Code")
        storage.start_agent_session(pid, "My New Agent 2.0")

        messages = storage.get_messages(pid, limit=5)
        assert messages[-1].agent == "claude"

        file_changes = storage.get_file_changes(pid)
        assert file_changes[-1].agent == "roo-cline"

        decisions = storage.get_decisions(pid)
        assert decisions[-1].agent == "opencode"

        sessions = storage.get_agent_sessions(pid)
        assert sessions[-1].agent == "my-new-agent-2-0"

        storage.close()
        print("✅ Test 4: Storage manager normalizes agent fields")


# ─────────────────────────────────────────────────────────────
# 2. PROJECT DETECTION TESTS
# ─────────────────────────────────────────────────────────────
EXPECTED_VERSION = "1.3.1"


def test_detect_project_with_explicit_path():
    """Project detection works when given an explicit directory."""
    from amcl.context.project_detector import detect_project

    with tempfile.TemporaryDirectory() as tmp:
        info = detect_project(tmp)
        assert info["path"] == str(Path(tmp).resolve())
        assert info["name"] == Path(tmp).name
        assert info["language"] == ""  # no project files
        print("✅ Test 4: Detect project with explicit path")


def test_detect_project_from_root_directory():
    """When CWD is /, detection redirects to ~/.amcl/_no_project sentinel
    instead of treating the entire filesystem as a project (which would
    cause the token backfill to scan billions of bytes)."""
    from amcl.context.project_detector import detect_project

    info = detect_project("/")
    assert info["path"] != "/"
    assert info["path"].endswith("_no_project")
    assert info["name"] == "_no_project"
    print("✅ Test 5: Detect project from root directory — redirects to sentinel")


def test_detect_python_project():
    """Detects Python projects via pyproject.toml."""
    from amcl.context.project_detector import detect_project

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "pyproject.toml").write_text('[project]\nname = "test"\n')
        info = detect_project(tmp)
        assert info["language"] == "python"
        print("✅ Test 6: Detects Python project from pyproject.toml")


def test_detect_js_project():
    """Detects JavaScript projects via package.json."""
    from amcl.context.project_detector import detect_project

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "package.json").write_text(
            '{"name":"test","dependencies":{"react":"^18"}}'
        )
        info = detect_project(tmp)
        assert info["language"] == "javascript"
        assert info["framework"] == "react"
        print("✅ Test 7: Detects JS project + React framework")


def test_detect_typescript_project():
    """Detects TypeScript via tsconfig.json presence."""
    from amcl.context.project_detector import detect_project

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "package.json").write_text(
            '{"dependencies":{"next":"^14","typescript":"^5"}}'
        )
        (Path(tmp) / "tsconfig.json").write_text("{}")
        info = detect_project(tmp)
        assert info["language"] == "typescript"
        assert info["framework"] == "next.js"
        print("✅ Test 8: Detects TypeScript + Next.js")


# ─────────────────────────────────────────────────────────────
# 3. LAZY INITIALIZATION TESTS
# ─────────────────────────────────────────────────────────────


def test_server_creation_is_lazy():
    """Server starts with project_id=None, no eager init."""
    from amcl.mcp.server import create_server

    mcp, ctx = create_server()
    assert ctx._project_id is None, "Project should NOT be initialized eagerly"
    ctx.shutdown()
    print("✅ Test 9: Server creation is lazy")


def test_agent_identity_normalization_aliases_and_slugging():
    """Agent identity normalization is stable across aliases and unknown names."""
    from amcl.agent_identity import normalize_agent_name

    assert normalize_agent_name("Claude Code") == "claude"
    assert normalize_agent_name("claude-code") == "claude"
    assert normalize_agent_name("Roo / Cline") == "roo-cline"
    assert normalize_agent_name("Open Code") == "opencode"
    assert normalize_agent_name("My New Agent 2.0") == "my-new-agent-2-0"
    assert normalize_agent_name("AMCL_AGENT_NAME=codex") == "codex"
    assert normalize_agent_name("", fallback="generic") == "generic"
    print("✅ Test 10: Agent identity normalization is robust")


def test_create_server_normalizes_agent_name_input():
    """create_server canonicalizes incoming agent labels before session logging."""
    from amcl.mcp.server import create_server

    with tempfile.TemporaryDirectory() as tmp:
        mcp, ctx = create_server(project_dir=tmp, agent_name="Claude Code")
        run_async(ctx.ensure_project())
        history = ctx.get_agent_history()
        assert len(history) == 1
        assert history[0]["agent"] == "claude"
        ctx.shutdown()
        print("✅ Test 11: create_server normalizes agent name input")


def test_ensure_project_with_explicit_dir():
    """ensure_project() works with forced project directory."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp)
        run_async(ctx.ensure_project())
        assert ctx._project_id is not None
        assert ctx._project_info["path"] == str(Path(tmp).resolve())
        ctx.shutdown()
        print("✅ Test 10: ensure_project() with explicit directory")


def test_ensure_project_without_context():
    """ensure_project() works even without a Context (resources/prompts)."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp)
        # Called with None — simulates resources and prompts
        run_async(ctx.ensure_project(None))
        assert ctx._project_id is not None
        ctx.shutdown()
        print("✅ Test 11: ensure_project() without Context")


def test_ensure_project_idempotent():
    """Calling ensure_project() twice doesn't duplicate anything."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp)
        run_async(ctx.ensure_project())
        pid1 = ctx._project_id
        run_async(ctx.ensure_project())
        pid2 = ctx._project_id
        assert pid1 == pid2, "Multiple calls should return same project"
        ctx.shutdown()
        print("✅ Test 12: ensure_project() is idempotent")


def test_ensure_project_with_mock_roots():
    """ensure_project() correctly resolves path from MCP list_roots."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp)

        # Mock an MCP Context with session.list_roots()
        mock_root = MagicMock()
        mock_root.uri = f"file://{tmp}"

        mock_result = MagicMock()
        mock_result.roots = [mock_root]

        mock_session = AsyncMock()
        mock_session.list_roots = AsyncMock(return_value=mock_result)

        mock_ctx = MagicMock()
        mock_ctx.session = mock_session

        run_async(ctx.ensure_project(mock_ctx))

        assert ctx._project_id is not None
        assert ctx._project_info["path"] == str(Path(tmp).resolve())
        ctx.shutdown()
        print("✅ Test 13: ensure_project() resolves from MCP list_roots")


def test_ensure_project_roots_failure_graceful():
    """If list_roots() throws, fallback to CWD without crashing."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp)

        # Mock a Context that throws on list_roots
        mock_session = AsyncMock()
        mock_session.list_roots = AsyncMock(side_effect=Exception("Connection refused"))
        mock_ctx = MagicMock()
        mock_ctx.session = mock_session

        # Should NOT crash — falls back to forced dir
        run_async(ctx.ensure_project(mock_ctx))
        assert ctx._project_id is not None
        ctx.shutdown()
        print("✅ Test 14: list_roots() failure is handled gracefully")


def test_ensure_project_no_session_attribute():
    """If ctx has no .session attribute, don't crash."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp)

        # Object with no session attribute
        mock_ctx = MagicMock(spec=[])  # no attributes at all

        run_async(ctx.ensure_project(mock_ctx))
        assert ctx._project_id is not None
        ctx.shutdown()
        print("✅ Test 15: Context without .session attribute is safe")


# ─────────────────────────────────────────────────────────────
# 4. CONTEXT TRANSFER TESTS (THE CORE FEATURE)
# ─────────────────────────────────────────────────────────────


def test_full_context_roundtrip():
    """Write context from Agent A, read it back from Agent B."""
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = tmp

        # ── Agent A writes context ──
        agent_a = make_ctx_mgr(tmp, project_dir=project_dir, agent_name="cursor")
        run_async(agent_a.ensure_project())

        agent_a.update_context(
            {
                "message": {
                    "role": "user",
                    "content": "Build a login page with OAuth support",
                }
            }
        )
        agent_a.update_context(
            {
                "message": {
                    "role": "assistant",
                    "content": "I'll create an auth module with Google and GitHub OAuth.",
                }
            }
        )
        agent_a.update_context(
            {
                "task": {
                    "description": "Implement OAuth login flow",
                    "status": "in_progress",
                }
            }
        )
        agent_a.update_context(
            {
                "decision": {
                    "question": "Which OAuth library?",
                    "answer": "next-auth",
                    "reasoning": "Best integration with Next.js",
                    "alternatives": ["passport.js", "auth0-sdk"],
                }
            }
        )
        agent_a.update_context(
            {
                "file_change": {
                    "file": "src/auth/login.tsx",
                    "action": "created",
                    "summary": "New login component with OAuth buttons",
                }
            }
        )

        agent_a.shutdown()

        # ── Agent B reads context ──
        agent_b = make_ctx_mgr(tmp, project_dir=project_dir, agent_name="antigravity")
        run_async(agent_b.ensure_project())

        context = agent_b.get_current_context()

        # Project is correct
        assert context["project"]["path"] == str(Path(tmp).resolve())

        # Conversation transferred
        msgs = context["conversation"]["messages"]
        assert len(msgs) == 2
        all_content = " ".join(m["content"] for m in msgs)
        assert "login page" in all_content.lower() or "oauth" in all_content.lower()
        # Both messages are from cursor
        assert all(m["agent"] == "cursor" for m in msgs)

        # Tasks transferred
        tasks = context["state"]["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["description"] == "Implement OAuth login flow"
        assert tasks[0]["status"] == "in_progress"

        # Decisions transferred
        decisions = context["reasoning"]["decisions"]
        assert len(decisions) == 1
        assert decisions[0]["answer"] == "next-auth"
        assert "passport.js" in decisions[0]["alternatives"]

        # File changes transferred
        files = context["files"]["recent_changes"]
        assert len(files) == 1
        assert files[0]["file"] == "src/auth/login.tsx"

        # Agent history shows BOTH agents
        agents = context["agents"]["history"]
        agent_names = [a["agent"] for a in agents]
        assert "cursor" in agent_names
        assert "antigravity" in agent_names

        # Previous agent session is marked as ended
        cursor_sessions = [a for a in agents if a["agent"] == "cursor"]
        assert cursor_sessions[0]["ended"] is not None

        agent_b.shutdown()
        print("✅ Test 16: Full context roundtrip — Agent A → Agent B")


def test_three_agent_handoff():
    """Context survives across 3 agent switches: Cursor → Antigravity → Claude."""
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = tmp

        # Agent 1: Cursor
        a1 = make_ctx_mgr(tmp, project_dir=project_dir, agent_name="cursor")
        run_async(a1.ensure_project())
        a1.update_context(
            {"message": {"role": "user", "content": "Set up the database schema"}}
        )
        a1.add_decision(
            "Database choice",
            "PostgreSQL",
            "Scalable and reliable",
            ["MySQL", "MongoDB"],
        )
        a1.shutdown()

        # Agent 2: Antigravity
        a2 = make_ctx_mgr(tmp, project_dir=project_dir, agent_name="antigravity")
        run_async(a2.ensure_project())
        a2.update_context(
            {
                "message": {
                    "role": "assistant",
                    "content": "Created users and posts tables",
                }
            }
        )
        a2.update_context(
            {"task": {"description": "Add API endpoints", "status": "pending"}}
        )
        a2.shutdown()

        # Agent 3: Claude
        a3 = make_ctx_mgr(tmp, project_dir=project_dir, agent_name="claude")
        run_async(a3.ensure_project())

        ctx = a3.get_current_context()

        # All 2 messages from all agents
        msgs = ctx["conversation"]["messages"]
        assert len(msgs) == 2

        # All agent sessions recorded (3 total)
        agents = ctx["agents"]["history"]
        assert len(agents) == 3
        agent_names = [a["agent"] for a in agents]
        assert agent_names == ["cursor", "antigravity", "claude"]

        # Previous two agents are ended, current is active
        assert agents[0]["ended"] is not None  # cursor ended
        assert agents[1]["ended"] is not None  # antigravity ended
        assert agents[2]["ended"] is None  # claude active

        # Decision from cursor is available to claude
        decisions = ctx["reasoning"]["decisions"]
        assert len(decisions) == 1
        assert decisions[0]["answer"] == "PostgreSQL"
        assert decisions[0]["agent"] == "cursor"

        a3.shutdown()
        print("✅ Test 17: Three-agent handoff — Cursor → Antigravity → Claude")


def test_context_query_search():
    """Search works across messages, decisions, and tasks."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="test")
        run_async(ctx.ensure_project())

        ctx.update_context(
            {"message": {"role": "user", "content": "We need authentication"}}
        )
        ctx.update_context(
            {"task": {"description": "Build OAuth login flow", "status": "pending"}}
        )
        ctx.add_decision("Auth provider?", "Firebase Auth", "Easy to set up")

        results = ctx.query_context("auth")
        assert len(results["messages"]) >= 1
        assert len(results["tasks"]) >= 1
        assert len(results["decisions"]) >= 1

        ctx.shutdown()
        print("✅ Test 18: Context search works across all tables")


def test_context_query_defaults_to_compact_results():
    """Search returns compact previews by default, with full detail on demand."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="test")
        run_async(ctx.ensure_project())

        long_message = "Auth issue " + ("A" * 260)
        long_reasoning = "Authentication reasoning " + ("B" * 260)

        ctx.update_context(
            {"message": {"role": "user", "content": long_message, "storage": "full"}}
        )
        ctx.add_decision("Auth provider?", "Firebase Auth", long_reasoning)

        compact = ctx.query_context("Auth")
        assert compact["detail"] == "compact"
        assert compact["messages"][0]["truncated"] is True
        assert compact["messages"][0]["content"].endswith("…")
        assert compact["decisions"][0]["truncated"] is True

        full = ctx.query_context("Auth", detail="full")
        assert full["detail"] == "full"
        assert full["messages"][0]["content"] == long_message
        assert full["decisions"][0]["reasoning"] == long_reasoning

        ctx.shutdown()
        print("✅ Test 19: Context search defaults to compact previews")


def test_context_query_exposes_delta_message_metadata():
    """Search results label messages stored as compact deltas."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="test")
        run_async(ctx.ensure_project())

        ctx.update_context(
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        "Implemented the webhook retry flow with queue instrumentation and replay safeguards in src/amcl/cli.py. "
                        "Updated ContextManager around context_get_current while keeping pytest wiring intact. "
                        "Run `pytest -q` after the patch. The webhook worker is still blocked by a flaky retry test. "
                    )
                    * 3,
                    "summary": "Implemented webhook retry flow and replay safeguards.",
                    "storage": "delta",
                }
            }
        )

        compact = ctx.query_context("webhook")
        assert compact["messages"][0]["storage"] == "delta"
        assert compact["messages"][0]["summary_source"] == "provided"
        assert compact["messages"][0]["signals"]["commands"] == ["pytest -q"]
        assert any(
            "blocked" in blocker.lower()
            for blocker in compact["messages"][0]["signals"]["blockers"]
        )
        assert "context_get_current" in compact["messages"][0]["signals"]["symbols"]
        assert "ContextManager" in compact["messages"][0]["signals"]["symbols"]
        assert "branches" not in compact["messages"][0]["signals"]
        assert "commits" not in compact["messages"][0]["signals"]
        assert "work_items" not in compact["messages"][0]["signals"]

        full = ctx.query_context("webhook", detail="full")
        assert full["messages"][0]["storage"] == "delta"
        assert full["messages"][0]["signals"]["commands"] == ["pytest -q"]
        assert "ContextManager" in full["messages"][0]["signals"]["symbols"]
        assert "branches" not in full["messages"][0]["signals"]

        ctx.shutdown()
        print("✅ Test 20: Search exposes delta message metadata")


def test_prompt_recent_signals_formatter():
    """Prompt helper renders extracted signals in a compact readable block."""
    from amcl.mcp.prompts import _append_recent_signals

    lines = ["# Header"]
    _append_recent_signals(
        lines,
        {
            "files_mentioned": ["src/amcl/cli.py"],
            "commands_mentioned": ["python3.11 -m pytest tests/test_amcl.py -q"],
            "symbols_mentioned": ["ContextManager", "context_get_current"],
            "blockers": ["Build is blocked by a flaky CSS test."],
        },
    )
    rendered = "\n".join(lines)

    assert "## Recent Signals" in rendered
    assert "Files mentioned: src/amcl/cli.py" in rendered
    assert "Commands mentioned: python3.11 -m pytest tests/test_amcl.py -q" in rendered
    assert "Symbols mentioned: ContextManager, context_get_current" in rendered
    assert "Build is blocked by a flaky CSS test." in rendered
    print("✅ Test 21: Prompt helper renders recent signals")


def test_context_selective_include():
    """get_current_context() respects the `include` filter."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="test")
        run_async(ctx.ensure_project())

        ctx.update_context({"message": {"role": "user", "content": "Hello"}})
        ctx.update_context({"task": {"description": "Task 1", "status": "pending"}})

        # Only request conversation
        result = ctx.get_current_context(include=["conversation"])
        assert "conversation" in result
        assert "state" not in result
        assert "files" not in result

        # Only request tasks
        result = ctx.get_current_context(include=["tasks"])
        assert "state" in result
        assert "conversation" not in result

        # Only request signals
        result = ctx.get_current_context(include=["signals"])
        assert "signals" in result
        assert "conversation" not in result
        assert "state" not in result

        ctx.shutdown()
        print("✅ Test 19: Selective include filter works correctly")


def test_context_filters_noise_and_duplicates():
    """Noise-only payloads and exact duplicate messages are skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="codex")
        run_async(ctx.ensure_project())

        skipped = ctx.update_context(
            {
                "message": {
                    "role": "user",
                    "content": "@[TerminalName: zsh, ProcessId: 61151]",
                }
            }
        )
        assert skipped["message_status"] == "skipped_terminal_artifact"

        first = ctx.update_context(
            {"message": {"role": "user", "content": "Investigate the auth bug"}}
        )
        second = ctx.update_context(
            {"message": {"role": "user", "content": "Investigate the auth bug"}}
        )

        assert "message_id" in first
        assert second["message_status"] == "skipped_duplicate"

        result = ctx.get_current_context(include=["conversation"])
        assert len(result["conversation"]["messages"]) == 1
        assert (
            result["conversation"]["messages"][0]["content"]
            == "Investigate the auth bug"
        )

        ctx.shutdown()
        print("✅ Test 20: Noise and duplicate messages are skipped")


def test_context_compact_conversation_packet():
    """Conversation payload includes a compact high-signal summary packet."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="cursor")
        run_async(ctx.ensure_project())

        ctx.update_context(
            {
                "message": {
                    "role": "user",
                    "content": "Build a dashboard for billing alerts",
                }
            }
        )
        ctx.update_context(
            {
                "message": {
                    "role": "assistant",
                    "content": "I'll start with the alerts data model and dashboard shell.",
                }
            }
        )
        ctx.update_context(
            {
                "message": {
                    "role": "user",
                    "content": "Focus on the failing webhook sync first",
                }
            }
        )

        result = ctx.get_current_context(include=["conversation"])
        compact = result["conversation"]["compact"]

        assert compact["original_goal"] == "Build a dashboard for billing alerts"
        assert (
            compact["latest_user_request"] == "Focus on the failing webhook sync first"
        )
        assert "dashboard shell" in compact["latest_assistant_outcome"]
        assert compact["messages_considered"] == 3

        ctx.shutdown()
        print("✅ Test 21: Compact conversation packet is generated")


def test_context_compact_conversation_packet_includes_signals():
    """Compact conversation packet aggregates files, commands, and blocker cues."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="cursor")
        run_async(ctx.ensure_project())

        ctx.update_context(
            {
                "message": {
                    "role": "user",
                    "content": (
                        "Fix src/amcl/cli.py and tests/test_amcl.py. "
                        "Inspect ContextManager and context_get_current() while updating amcl.context.manager. "
                        "Run `python3.11 -m pytest tests/test_amcl.py -q`. "
                        "The build is failing with a segfault right now."
                    ),
                }
            }
        )

        result = ctx.get_current_context(include=["conversation"])
        compact = result["conversation"]["compact"]
        preview = result["conversation"]["messages"][0]

        assert "src/amcl/cli.py" in compact["files_mentioned"]
        assert "tests/test_amcl.py" in compact["files_mentioned"]
        assert (
            "python3.11 -m pytest tests/test_amcl.py -q"
            in compact["commands_mentioned"]
        )
        assert any("segfault" in blocker.lower() for blocker in compact["blockers"])
        assert "ContextManager" in compact["symbols_mentioned"]
        assert any(
            symbol.startswith("context_get_current")
            for symbol in compact["symbols_mentioned"]
        )
        assert "branches_mentioned" not in compact
        assert "commits_mentioned" not in compact
        assert "work_items_mentioned" not in compact
        assert preview["signals"]["files"][:2] == [
            "src/amcl/cli.py",
            "tests/test_amcl.py",
        ]
        assert "ContextManager" in preview["signals"]["symbols"]

        ctx.shutdown()
        print("✅ Test 22: Compact conversation packet includes deterministic signals")


def test_context_get_recent_signals_returns_compact_signal_bundle():
    """Recent signals can be retrieved directly without the full context payload."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="cursor")
        run_async(ctx.ensure_project())

        ctx.update_context(
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        "Updated src/amcl/mcp/prompts.py and src/amcl/mcp/resources.py. "
                        "Touch ContextManager, register_prompts, and context_get_current(). "
                        "Run `amcl check` after the patch. The current build is blocked by a flaky CSS test."
                    ),
                    "summary": "Updated MCP prompts/resources; build still blocked by a flaky CSS test.",
                    "storage": "delta",
                }
            }
        )

        signals = ctx.get_recent_signals()
        assert "src/amcl/mcp/prompts.py" in signals["files_mentioned"]
        assert "amcl check" in signals["commands_mentioned"]
        assert any("blocked" in blocker.lower() for blocker in signals["blockers"])
        assert "ContextManager" in signals["symbols_mentioned"]
        assert "register_prompts" in signals["symbols_mentioned"]
        assert signals["active_code_objects"] == signals["symbols_mentioned"]
        assert "branches_mentioned" not in signals
        assert "commits_mentioned" not in signals
        assert "work_items_mentioned" not in signals
        assert "active_change_refs" not in signals

        ctx.shutdown()
        print("✅ Test 23: get_recent_signals returns compact signal bundle")


def test_context_get_current_exposes_signals_top_level():
    """Current context includes a first-class signals section by default."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="cursor")
        run_async(ctx.ensure_project())

        ctx.update_context(
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        "Updated src/amcl/context/context_manager.py. "
                        "Inspect ContextManager and context_get_current() next. "
                        "Run `pytest -q` after the patch."
                    ),
                    "summary": "Updated context manager and next retrieval flow.",
                    "storage": "delta",
                }
            }
        )

        context = ctx.get_current_context()
        assert "signals" in context
        assert "ContextManager" in context["signals"]["active_code_objects"]
        assert "pytest -q" in context["signals"]["commands_mentioned"]
        assert "active_change_refs" not in context["signals"]
        assert "work_items_mentioned" not in context["signals"]
        assert "git" not in context["project"]

        ctx.shutdown()
        print("✅ Test 24: get_current_context exposes top-level signals")


def test_context_auto_promotes_strong_blocker_signals_to_tasks():
    """Strong blocker phrasing becomes a blocked task automatically."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="cursor")
        run_async(ctx.ensure_project())

        result = ctx.update_context(
            {
                "message": {
                    "role": "user",
                    "content": "The build is blocked by a flaky CSS test in src/amcl/mcp/prompts.py.",
                }
            }
        )

        assert "auto_blocker_task_ids" in result
        tasks = ctx.get_tasks()
        blocked = [task for task in tasks if task["status"] == "blocked"]
        assert len(blocked) == 1
        assert "blocked by a flaky css test" in blocked[0]["description"].lower()

        ctx.shutdown()
        print("✅ Test 24: Strong blocker signals auto-promote to blocked tasks")


def test_context_does_not_duplicate_auto_promoted_blockers():
    """Repeating the same blocker message does not create duplicate blocked tasks."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="cursor")
        run_async(ctx.ensure_project())

        payload = {
            "message": {
                "role": "user",
                "content": "The build is blocked by a flaky CSS test in src/amcl/mcp/prompts.py.",
            }
        }
        first = ctx.update_context(payload)
        second = ctx.update_context(payload)

        assert "auto_blocker_task_ids" in first
        assert "auto_blocker_task_ids" not in second
        blocked = [task for task in ctx.get_tasks() if task["status"] == "blocked"]
        assert len(blocked) == 1

        ctx.shutdown()
        print("✅ Test 25: Auto-promoted blockers are deduplicated")


def test_context_does_not_promote_weak_blocker_language():
    """Weak issue/problem wording stays as a signal and does not become a blocked task."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="cursor")
        run_async(ctx.ensure_project())

        result = ctx.update_context(
            {
                "message": {
                    "role": "user",
                    "content": "There is an auth issue in src/amcl/cli.py that we should inspect.",
                }
            }
        )

        assert "message_signals" in result
        assert "auto_blocker_task_ids" not in result
        blocked = [task for task in ctx.get_tasks() if task["status"] == "blocked"]
        assert blocked == []

        ctx.shutdown()
        print("✅ Test 26: Weak blocker language is not auto-promoted")


def test_context_get_current_defaults_to_preview_messages():
    """Default current-context retrieval returns compact message previews."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="cursor")
        run_async(ctx.ensure_project())

        long_reply = "A" * 260
        ctx.update_context(
            {"message": {"role": "user", "content": "Investigate the retries issue"}}
        )
        ctx.update_context(
            {"message": {"role": "assistant", "content": long_reply, "storage": "full"}}
        )

        result = ctx.get_current_context(include=["conversation"])
        convo = result["conversation"]

        assert convo["detail"] == "compact"
        assert convo["message_count"] == 2
        assert convo["raw_messages_available"] is False
        assert len(convo["messages"]) == 2
        assert convo["messages"][1]["truncated"] is True
        assert convo["messages"][1]["content"].endswith("…")
        assert len(convo["messages"][1]["content"]) <= 220

        full = ctx.get_current_context(include=["conversation"], detail="full")
        assert full["conversation"]["detail"] == "full"
        assert full["conversation"]["messages"][1]["content"] == long_reply

        ctx.shutdown()
        print("✅ Test 27: context_get_current defaults to compact previews")


def test_context_get_current_uses_brief_summary_in_compact_mode():
    """Compact current-context retrieval uses the shorter conversation summary."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="cursor")
        run_async(ctx.ensure_project())

        ctx.update_context(
            {"message": {"role": "user", "content": "Build a billing dashboard"}}
        )
        ctx.update_context(
            {
                "message": {
                    "role": "assistant",
                    "content": "I will start with the shell and alert cards",
                }
            }
        )
        ctx.update_context(
            {"message": {"role": "user", "content": "Focus on webhook retries first"}}
        )

        compact = ctx.get_current_context(include=["conversation"])
        assert "Recent activity" not in compact["conversation"]["summary"]
        assert "Total messages: 3" in compact["conversation"]["summary"]

        full = ctx.get_current_context(include=["conversation"], detail="full")
        assert "Recent activity" in full["conversation"]["summary"]

        ctx.shutdown()
        print("✅ Test 28: Compact current-context uses a brief conversation summary")


def test_context_update_supports_delta_message_storage():
    """Messages can be stored as compact deltas instead of full transcripts."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="codex")
        run_async(ctx.ensure_project())

        full_text = (
            "Implemented the retry reconciliation flow, added queue metrics, "
            "updated the failure handling path, and documented the rollout steps. "
        ) * 6
        result = ctx.update_context(
            {
                "message": {
                    "role": "assistant",
                    "content": full_text,
                    "summary": "Implemented retry reconciliation, metrics, and rollout notes.",
                    "storage": "delta",
                }
            }
        )

        assert result["message_storage"] == "delta"
        assert int(result["message_raw_chars"]) == len(full_text.strip())
        assert int(result["message_chars"]) < int(result["message_raw_chars"])

        compact = ctx.get_current_context(include=["conversation"])
        message = compact["conversation"]["messages"][0]
        assert message["storage"] == "delta"
        assert (
            message["content"]
            == "Implemented retry reconciliation, metrics, and rollout notes."
        )
        assert message["summary_source"] == "provided"
        assert message["raw_chars"] == len(full_text.strip())

        full = ctx.get_current_context(include=["conversation"], detail="full")
        full_message = full["conversation"]["messages"][0]
        assert full_message["storage"] == "delta"
        assert (
            full_message["content"]
            == "Implemented retry reconciliation, metrics, and rollout notes."
        )

        transcript = ctx.get_conversation(limit=10)
        assert transcript[0]["storage"] == "delta"

        ctx.shutdown()
        print("✅ Test 29: context_update supports delta message storage")


def test_context_update_defaults_messages_to_delta_storage():
    """Omitted storage defaults to compact delta storage for routine messages."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="codex")
        run_async(ctx.ensure_project())

        full_text = (
            "The user wants the retry dashboard updated with queue metrics, "
            "failure handling notes, and clearer rollout guidance. "
        ) * 5

        result = ctx.update_context(
            {
                "message": {
                    "role": "user",
                    "content": full_text,
                }
            }
        )

        assert result["message_storage"] == "delta"
        assert int(result["message_chars"]) < len(full_text.strip())

        compact = ctx.get_current_context(include=["conversation"])
        message = compact["conversation"]["messages"][0]
        assert message["storage"] == "delta"
        assert message["summary_source"] == "derived"
        assert message["raw_chars"] == len(full_text.strip())
        assert message["content"].endswith("…")

        ctx.shutdown()
        print("✅ Test 30: Omitted storage defaults to delta")


def test_context_update_full_storage_preserves_exact_message_text():
    """Explicit full storage remains the escape hatch for exact wording."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="codex")
        run_async(ctx.ensure_project())

        full_text = (
            "Preserve this exact wording with every implementation detail intact. " * 5
        )
        result = ctx.update_context(
            {
                "message": {
                    "role": "assistant",
                    "content": full_text,
                    "storage": "full",
                }
            }
        )

        assert result["message_storage"] == "full"
        full = ctx.get_current_context(include=["conversation"], detail="full")
        assert full["conversation"]["messages"][0]["storage"] == "full"
        assert full["conversation"]["messages"][0]["content"] == full_text.strip()

        ctx.shutdown()
        print("✅ Test 31: Explicit full storage preserves exact text")


def test_context_get_current_compacts_non_conversation_sections():
    """Compact current-context retrieval trims files, tasks, and decisions too."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="cursor")
        run_async(ctx.ensure_project())

        long_task = (
            "Implement the billing retry recovery flow with idempotency tracking and detailed observability hooks "
            * 2
        )
        long_decision = (
            "Use a retry queue with explicit dedupe keys and delayed backoff windows "
            * 4
        )
        long_reasoning = (
            "The webhook provider retries aggressively and we need stable replay semantics without duplicate invoice mutations "
            * 2
        )
        long_summary = (
            "Added retry queue plumbing, replay guards, and telemetry wiring for the webhook processor "
            * 4
        )

        ctx.update_context(
            {"task": {"description": long_task, "status": "in_progress"}}
        )
        ctx.update_context(
            {
                "decision": {
                    "question": "How should webhook retries be handled?",
                    "answer": long_decision,
                    "reasoning": long_reasoning,
                    "alternatives": ["Synchronous retries only"],
                }
            }
        )
        ctx.update_context(
            {
                "file_change": {
                    "file": "src/amcl/retries.py",
                    "action": "modified",
                    "summary": long_summary,
                }
            }
        )

        result = ctx.get_current_context(include=["files", "tasks", "reasoning"])

        assert result["files"]["detail"] == "compact"
        assert result["files"]["change_count"] == 1
        assert result["files"]["recent_changes"][0]["truncated"] is True
        assert result["files"]["recent_changes"][0]["summary"].endswith("…")

        assert result["state"]["detail"] == "compact"
        assert result["state"]["task_count"] == 1
        assert result["state"]["tasks"][0]["truncated"] is True
        assert result["state"]["tasks"][0]["description"].endswith("…")

        assert result["reasoning"]["detail"] == "compact"
        assert result["reasoning"]["decision_count"] == 1
        assert result["reasoning"]["decisions"][0]["truncated"] is True
        assert result["reasoning"]["decisions"][0]["answer"].endswith("…")

        full = ctx.get_current_context(
            include=["files", "tasks", "reasoning"],
            detail="full",
        )
        assert full["files"]["detail"] == "full"
        assert full["files"]["recent_changes"][0]["summary"] == long_summary
        assert full["state"]["tasks"][0]["description"] == long_task
        assert full["reasoning"]["decisions"][0]["answer"] == long_decision

        ctx.shutdown()
        print("✅ Test 30: context_get_current compacts files/tasks/decisions")


def test_generate_share_html_uses_summary_first_conversation():
    """Share HTML shows compact conversation summary and collapsible raw timeline."""
    from amcl.share import generate_share_html

    messages = [
        {
            "role": "user",
            "content": "Build a billing dashboard",
            "agent": "cursor",
            "timestamp": "2026-03-25 10:00:00",
        },
        {
            "role": "assistant",
            "content": "I will start with the shell and alert cards",
            "agent": "cursor",
            "timestamp": "2026-03-25 10:01:00",
        },
        {
            "role": "user",
            "content": "Focus on webhook retries first",
            "agent": "cursor",
            "timestamp": "2026-03-25 10:02:00",
        },
        {
            "role": "assistant",
            "content": "Retry flow audited",
            "agent": "cursor",
            "timestamp": "2026-03-25 10:03:00",
        },
        {
            "role": "user",
            "content": "Add compact summaries too",
            "agent": "cursor",
            "timestamp": "2026-03-25 10:04:00",
        },
        {
            "role": "assistant",
            "content": "Done",
            "agent": "cursor",
            "timestamp": "2026-03-25 10:05:00",
        },
        {
            "role": "user",
            "content": "Keep raw details available",
            "agent": "cursor",
            "timestamp": "2026-03-25 10:06:00",
        },
    ]

    html = generate_share_html(
        projects=[
            {
                "name": "A:MCL",
                "path": "/tmp/amcl",
                "messages": messages,
                "decisions": [],
                "file_changes": [],
                "agent_stats": [{"agent": "cursor", "count": len(messages)}],
            }
        ],
        preferences={},
    )

    assert "summary first, raw timeline on demand" in html
    assert "Original Goal" in html
    assert "Latest User Request" in html
    assert "Latest Assistant Outcome" in html
    assert 'class="thread-wrap"' in html
    assert 'class="thread-toggle-label">Raw Timeline<' in html
    assert 'class="thread-wrap" open' not in html
    print("✅ Test 23: Share HTML defaults to summary-first conversation")


# ─────────────────────────────────────────────────────────────
# 5. SHUTDOWN & LIFECYCLE TESTS
# ─────────────────────────────────────────────────────────────


def test_shutdown_before_init():
    """Shutting down before any init doesn't crash."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp)
        ctx.shutdown()  # Should not raise
        print("✅ Test 20: Shutdown before initialization is safe")


def test_shutdown_after_init():
    """Shutting down after init properly ends the session."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="test")
        run_async(ctx.ensure_project())
        pid = ctx._project_id
        ctx.shutdown()

        # Verify the session was ended in the DB
        db_path = Path(tmp) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT ended FROM agent_sessions WHERE project_id = ? ORDER BY started DESC LIMIT 1",
            (pid,),
        ).fetchone()
        assert row["ended"] is not None, "Session should be ended"
        conn.close()
        print("✅ Test 21: Shutdown properly ends agent session")


def test_double_shutdown():
    """Calling shutdown twice doesn't crash."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="test")
        run_async(ctx.ensure_project())
        ctx.shutdown()
        ctx.shutdown()  # Should not raise
        print("✅ Test 22: Double shutdown is safe")


# ─────────────────────────────────────────────────────────────
# 6. FILE WATCHER SAFETY TESTS
# ─────────────────────────────────────────────────────────────


def test_file_watcher_skips_root():
    """FileWatcher refuses to watch / to avoid flooding."""
    from amcl.context.file_watcher import FileWatcher
    from amcl.storage.storage_manager import StorageManager

    with tempfile.TemporaryDirectory() as tmp:
        storage = StorageManager(Path(tmp) / "test.db")
        pid = storage.get_or_create_project(path="/", name="root")
        watcher = FileWatcher(storage, pid, "/")
        watcher.start()
        assert watcher._observer is None, "Should NOT watch /"
        storage.close()
        print("✅ Test 23: FileWatcher skips root directory")


def test_file_watcher_skips_nonexistent():
    """FileWatcher skips non-existent directories gracefully."""
    from amcl.context.file_watcher import FileWatcher
    from amcl.storage.storage_manager import StorageManager

    with tempfile.TemporaryDirectory() as tmp:
        storage = StorageManager(Path(tmp) / "test.db")
        pid = storage.get_or_create_project(path="/nonexistent/path", name="ghost")
        watcher = FileWatcher(storage, pid, "/nonexistent/path")
        watcher.start()  # Should not raise
        assert watcher._observer is None
        storage.close()
        print("✅ Test 24: FileWatcher skips non-existent directories")


def test_file_watcher_uses_polling_observer_on_macos():
    """macOS uses PollingObserver to avoid native watchdog shutdown crashes."""
    from watchdog.observers.polling import PollingObserver
    from amcl.context import file_watcher as file_watcher_module

    with patch.object(file_watcher_module.sys, "platform", "darwin"):
        observer = file_watcher_module._make_observer()

    assert isinstance(observer, PollingObserver)
    observer.stop()
    print("✅ Test 25: macOS watcher uses PollingObserver")


# ─────────────────────────────────────────────────────────────
# 7. CLI TESTS
# ─────────────────────────────────────────────────────────────


def test_cli_version():
    """CLI reports the correct version."""
    from click.testing import CliRunner
    from amcl.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert "1.3.1" in result.output
    print("✅ Test 26: CLI version is correct (1.3.1)")


def test_cli_status():
    """CLI status command runs without errors."""
    from click.testing import CliRunner
    from amcl.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "A/MCL Status" in result.output
    print("✅ Test 27: CLI status command works")


# ─────────────────────────────────────────────────────────────
# 8. CODEX SUPPORT TESTS
# ─────────────────────────────────────────────────────────────


def test_scan_codex_sessions_filters_bootstrap_and_commentary():
    """Codex importer keeps real user/final assistant messages only."""
    from amcl.importers import scan_codex

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        project_dir = home / "workspace" / "demo"
        project_dir.mkdir(parents=True)

        sessions_dir = home / ".codex" / "sessions" / "2026" / "03" / "20"
        sessions_dir.mkdir(parents=True)
        session_file = sessions_dir / "rollout-2026-03-20T00-00-00-test.jsonl"

        entries = [
            {
                "timestamp": "2026-03-20T12:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "codex-session-1",
                    "cwd": str(project_dir),
                },
            },
            {
                "timestamp": "2026-03-20T12:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "# AGENTS.md instructions for /tmp/demo\n\n<INSTRUCTIONS>skip me</INSTRUCTIONS>",
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-03-20T12:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Add Codex support"}],
                },
            },
            {
                "timestamp": "2026-03-20T12:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": [
                        {"type": "output_text", "text": "I’m exploring first."}
                    ],
                },
            },
            {
                "timestamp": "2026-03-20T12:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": [
                        {"type": "output_text", "text": "Codex support is in."}
                    ],
                },
            },
        ]
        session_file.write_text(
            "\n".join(json.dumps(entry) for entry in entries) + "\n"
        )

        with patch("amcl.importers.Path.home", return_value=home):
            results = scan_codex()

        assert len(results) == 1
        session = results[0]
        assert session["project_path"] == str(project_dir)
        assert session["agent"] == "codex"
        assert [m["role"] for m in session["messages"]] == ["user", "assistant"]
        assert session["messages"][0]["content"] == "Add Codex support"
        assert session["messages"][1]["content"] == "Codex support is in."
        print("✅ Test 28: Codex session import filters bootstrap/commentary")


def test_try_auto_register_writes_codex_toml():
    """Codex MCP registration updates ~/.codex/config.toml without clobbering other tables."""
    from amcl.cli import _load_toml_config, _try_auto_register

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        codex_dir = home / ".codex"
        codex_dir.mkdir(parents=True)
        config_file = codex_dir / "config.toml"
        config_file.write_text(
            'model = "gpt-5.4"\n\n'
            "[mcp_servers.amcl]\n"
            'command = "old-amcl"\n'
            'args = ["serve"]\n'
            'env = { AMCL_AGENT_NAME = "old" }\n\n'
            "[mcp_servers.pencil]\n"
            'command = "pencil-server"\n'
        )

        with patch("amcl.cli.Path.home", return_value=home):
            registered = _try_auto_register("/usr/local/bin/amcl-server")

        parsed = _load_toml_config(config_file)
        assert any(item.startswith("Codex") for item in registered)
        assert parsed["mcp_servers"]["amcl"]["command"] == "/usr/local/bin/amcl-server"
        assert parsed["mcp_servers"]["amcl"]["args"] == ["start"]
        assert parsed["mcp_servers"]["amcl"]["env"]["AMCL_AGENT_NAME"] == "codex"
        assert parsed["mcp_servers"]["pencil"]["command"] == "pencil-server"
        assert config_file.read_text().count("[mcp_servers.amcl]") == 1
        print("✅ Test 29: Codex TOML registration updates cleanly")


def test_install_agent_rules_creates_codex_global_agents_file():
    """setup installs a global Codex AGENTS.md when ~/.codex exists."""
    from amcl.cli import _install_agent_rules

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        codex_dir = home / ".codex"
        codex_dir.mkdir(parents=True)
        (codex_dir / "config.toml").write_text('model = "gpt-5.4"\n')

        with patch("amcl.cli.Path.home", return_value=home):
            installed = _install_agent_rules()

        codex_agents = codex_dir / "AGENTS.md"
        assert codex_agents.exists()
        content = codex_agents.read_text()
        assert "A/MCL PROJECT AUTO-CONTEXT" in content
        assert "context_update" in content
        assert any(item.startswith("Codex") for item in installed)
        print("✅ Test 30: Global Codex AGENTS.md is installed")


def test_cli_check_reports_codex_and_global_agents():
    """check reports Codex MCP config and global Codex AGENTS.md status."""
    from click.testing import CliRunner
    from amcl.cli import _install_agent_rules, main

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        home.mkdir(parents=True)

        codex_dir = home / ".codex"
        codex_dir.mkdir(parents=True)
        (codex_dir / "config.toml").write_text(
            "[mcp_servers.amcl]\n"
            'command = "/usr/local/bin/amcl-server"\n'
            'args = ["start"]\n'
            'env = { AMCL_AGENT_NAME = "codex", AMCL_DATA_DIR = "/tmp/amcl", AMCL_LOG_LEVEL = "info" }\n'
        )

        with patch("amcl.cli.Path.home", return_value=home):
            _install_agent_rules()

        runner = CliRunner()
        with patch("amcl.cli.Path.home", return_value=home):
            result = runner.invoke(main, ["check"])

        assert result.exit_code == 0
        assert "✅ Codex: agent=codex" in result.output
        assert "✅ Codex: Rule installed" in result.output
        print("✅ Test 31: check reports Codex config and global AGENTS.md")


# ─────────────────────────────────────────────────────────────
# 9. CONCURRENT ACCESS TEST
# ─────────────────────────────────────────────────────────────


def test_concurrent_ensure_project():
    """Multiple concurrent ensure_project() calls don't race."""
    with tempfile.TemporaryDirectory() as tmp:
        ctx = make_ctx_mgr(tmp, project_dir=tmp, agent_name="test")

        async def run():
            # Fire 10 concurrent ensure_project calls
            await asyncio.gather(
                ctx.ensure_project(),
                ctx.ensure_project(),
                ctx.ensure_project(),
                ctx.ensure_project(),
                ctx.ensure_project(),
                ctx.ensure_project(),
                ctx.ensure_project(),
                ctx.ensure_project(),
                ctx.ensure_project(),
                ctx.ensure_project(),
            )

        run_async(run())
        assert ctx._project_id is not None

        # Verify only one session was created (not 10)
        sessions = ctx.get_agent_history()
        assert len(sessions) == 1, f"Expected 1 session, got {len(sessions)}"

        ctx.shutdown()
        print("✅ Test 32: Concurrent ensure_project() is race-safe")


# ─────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────

ALL_TESTS = [
    # Database
    test_database_creates_on_fresh_install,
    test_database_wal_mode,
    test_database_schema_idempotent,
    test_storage_manager_normalizes_agent_fields,
    # Project Detection
    test_detect_project_with_explicit_path,
    test_detect_project_from_root_directory,
    test_detect_python_project,
    test_detect_js_project,
    test_detect_typescript_project,
    # Lazy Initialization
    test_server_creation_is_lazy,
    test_agent_identity_normalization_aliases_and_slugging,
    test_create_server_normalizes_agent_name_input,
    test_ensure_project_with_explicit_dir,
    test_ensure_project_without_context,
    test_ensure_project_idempotent,
    test_ensure_project_with_mock_roots,
    test_ensure_project_roots_failure_graceful,
    test_ensure_project_no_session_attribute,
    # Context Transfer
    test_full_context_roundtrip,
    test_three_agent_handoff,
    test_context_query_search,
    test_context_query_defaults_to_compact_results,
    test_context_selective_include,
    test_context_filters_noise_and_duplicates,
    test_context_compact_conversation_packet,
    test_context_get_current_defaults_to_preview_messages,
    test_generate_share_html_uses_summary_first_conversation,
    # Lifecycle
    test_shutdown_before_init,
    test_shutdown_after_init,
    test_double_shutdown,
    # File Watcher
    test_file_watcher_skips_root,
    test_file_watcher_skips_nonexistent,
    test_file_watcher_uses_polling_observer_on_macos,
    # CLI
    test_cli_version,
    test_cli_status,
    # Codex support
    test_scan_codex_sessions_filters_bootstrap_and_commentary,
    test_try_auto_register_writes_codex_toml,
    test_install_agent_rules_creates_codex_global_agents_file,
    test_cli_check_reports_codex_and_global_agents,
    # Concurrency
    test_concurrent_ensure_project,
]


def main():
    """Run all tests."""
    passed = 0
    failed = 0
    errors = []

    print("=" * 60)
    print("  A/MCL v1.3.1 — Comprehensive Test Suite")
    print(f"  {len(ALL_TESTS)} tests across 9 categories")
    print("=" * 60)
    print()

    for test in ALL_TESTS:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((test.__name__, str(e)))
            print(f"❌ {test.__name__}: {e}")

    print()
    print("=" * 60)
    if failed == 0:
        print(f"  🎉 ALL {passed} TESTS PASSED")
    else:
        print(f"  ❌ {failed} FAILED, {passed} PASSED")
        for name, err in errors:
            print(f"     - {name}: {err}")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
