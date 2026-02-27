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
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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


# ─────────────────────────────────────────────────────────────
# 2. PROJECT DETECTION TESTS
# ─────────────────────────────────────────────────────────────

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
    """When CWD is /, detection doesn't crash and returns / gracefully."""
    from amcl.context.project_detector import detect_project
    info = detect_project("/")
    assert info["path"] == "/"
    assert info["name"] != ""  # should be "/" not empty
    print("✅ Test 5: Detect project from root directory — no crash")


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
        (Path(tmp) / "package.json").write_text('{"name":"test","dependencies":{"react":"^18"}}')
        info = detect_project(tmp)
        assert info["language"] == "javascript"
        assert info["framework"] == "react"
        print("✅ Test 7: Detects JS project + React framework")


def test_detect_typescript_project():
    """Detects TypeScript via tsconfig.json presence."""
    from amcl.context.project_detector import detect_project
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "package.json").write_text('{"dependencies":{"next":"^14","typescript":"^5"}}')
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

        agent_a.update_context({
            "message": {
                "role": "user",
                "content": "Build a login page with OAuth support",
            }
        })
        agent_a.update_context({
            "message": {
                "role": "assistant",
                "content": "I'll create an auth module with Google and GitHub OAuth.",
            }
        })
        agent_a.update_context({
            "task": {
                "description": "Implement OAuth login flow",
                "status": "in_progress",
            }
        })
        agent_a.update_context({
            "decision": {
                "question": "Which OAuth library?",
                "answer": "next-auth",
                "reasoning": "Best integration with Next.js",
                "alternatives": ["passport.js", "auth0-sdk"],
            }
        })
        agent_a.update_context({
            "file_change": {
                "file": "src/auth/login.tsx",
                "action": "created",
                "summary": "New login component with OAuth buttons",
            }
        })

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
        a1.update_context({"message": {"role": "user", "content": "Set up the database schema"}})
        a1.add_decision("Database choice", "PostgreSQL", "Scalable and reliable", ["MySQL", "MongoDB"])
        a1.shutdown()

        # Agent 2: Antigravity
        a2 = make_ctx_mgr(tmp, project_dir=project_dir, agent_name="antigravity")
        run_async(a2.ensure_project())
        a2.update_context({"message": {"role": "assistant", "content": "Created users and posts tables"}})
        a2.update_context({"task": {"description": "Add API endpoints", "status": "pending"}})
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
        assert agents[2]["ended"] is None      # claude active

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

        ctx.update_context({"message": {"role": "user", "content": "We need authentication"}})
        ctx.update_context({"task": {"description": "Build OAuth login flow", "status": "pending"}})
        ctx.add_decision("Auth provider?", "Firebase Auth", "Easy to set up")

        results = ctx.query_context("auth")
        assert len(results["messages"]) >= 1
        assert len(results["tasks"]) >= 1
        assert len(results["decisions"]) >= 1

        ctx.shutdown()
        print("✅ Test 18: Context search works across all tables")


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

        ctx.shutdown()
        print("✅ Test 19: Selective include filter works correctly")


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
            (pid,)
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


# ─────────────────────────────────────────────────────────────
# 7. CLI TESTS
# ─────────────────────────────────────────────────────────────

def test_cli_version():
    """CLI reports the correct version."""
    from click.testing import CliRunner
    from amcl.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert "1.0.9" in result.output
    print("✅ Test 25: CLI version is correct (1.0.9)")


def test_cli_status():
    """CLI status command runs without errors."""
    from click.testing import CliRunner
    from amcl.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "A/MCL Status" in result.output
    print("✅ Test 26: CLI status command works")


# ─────────────────────────────────────────────────────────────
# 8. CONCURRENT ACCESS TEST
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
        print("✅ Test 27: Concurrent ensure_project() is race-safe")


# ─────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────

ALL_TESTS = [
    # Database
    test_database_creates_on_fresh_install,
    test_database_wal_mode,
    test_database_schema_idempotent,
    # Project Detection
    test_detect_project_with_explicit_path,
    test_detect_project_from_root_directory,
    test_detect_python_project,
    test_detect_js_project,
    test_detect_typescript_project,
    # Lazy Initialization
    test_server_creation_is_lazy,
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
    test_context_selective_include,
    # Lifecycle
    test_shutdown_before_init,
    test_shutdown_after_init,
    test_double_shutdown,
    # File Watcher
    test_file_watcher_skips_root,
    test_file_watcher_skips_nonexistent,
    # CLI
    test_cli_version,
    test_cli_status,
    # Concurrency
    test_concurrent_ensure_project,
]


def main():
    """Run all tests."""
    passed = 0
    failed = 0
    errors = []

    print("=" * 60)
    print("  A/MCL v1.0.9 — Comprehensive Test Suite")
    print("  27 tests across 8 categories")
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
    import sys
    sys.exit(main())
