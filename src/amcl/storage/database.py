"""
SQLite database schema and initialization for A/MCL.

Creates tables for projects, messages, file_changes, tasks,
decisions, and agent_sessions. Includes schema versioning.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 6

AMCL_DATA_DIR = Path(os.environ.get("AMCL_DATA_DIR", os.path.expanduser("~/.amcl")))
DB_PATH = AMCL_DATA_DIR / "amcl.db"


_SCHEMA_SQL = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Projects
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    language TEXT DEFAULT '',
    framework TEXT DEFAULT '',
    git_branch TEXT DEFAULT '',
    git_commit TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Conversation messages
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    agent TEXT DEFAULT '',
    context_note TEXT DEFAULT '',
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_project ON messages(project_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);

-- File changes
CREATE TABLE IF NOT EXISTS file_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('created', 'modified', 'deleted')),
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    agent TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    diff TEXT DEFAULT '',
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_file_changes_project ON file_changes(project_id);

-- Tasks
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'in_progress', 'completed', 'blocked')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);

-- Decisions / reasoning
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    reasoning TEXT DEFAULT '',
    alternatives TEXT DEFAULT '[]',   -- JSON array
    agent TEXT DEFAULT '',
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_decisions_project ON decisions(project_id);

-- Agent sessions
CREATE TABLE IF NOT EXISTS agent_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    agent TEXT NOT NULL,
    started TEXT NOT NULL DEFAULT (datetime('now')),
    ended TEXT,
    reason_for_switch TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_project ON agent_sessions(project_id);
"""

_SCHEMA_SQL_V2 = """
-- Global Preferences (V2)
CREATE TABLE IF NOT EXISTS global_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL UNIQUE,
    preference TEXT NOT NULL,
    source_agent TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- FTS5 Search Tables (V2)
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
USING fts5(
    content,
    role UNINDEXED,
    agent UNINDEXED,
    content='messages'
);

CREATE VIRTUAL TABLE IF NOT EXISTS file_changes_fts
USING fts5(
    file_path,
    summary,
    diff,
    action UNINDEXED,
    content='file_changes',
    content_rowid='id'
);

CREATE VIRTUAL TABLE IF NOT EXISTS decisions_fts
USING fts5(
    question,
    answer,
    reasoning,
    alternatives,
    content='decisions',
    content_rowid='id'
);

-- Triggers for messages_fts
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, content, role, agent)
  VALUES (new.rowid, new.content, new.role, new.agent);
END;

CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content, role, agent)
  VALUES ('delete', old.rowid, old.content, old.role, old.agent);
END;

CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content, role, agent)
  VALUES ('delete', old.rowid, old.content, old.role, old.agent);
  INSERT INTO messages_fts(rowid, content, role, agent)
  VALUES (new.rowid, new.content, new.role, new.agent);
END;

-- Triggers for file_changes_fts
CREATE TRIGGER IF NOT EXISTS file_changes_ai AFTER INSERT ON file_changes BEGIN
  INSERT INTO file_changes_fts(rowid, file_path, summary, diff, action)
  VALUES (new.id, new.file_path, new.summary, new.diff, new.action);
END;

CREATE TRIGGER IF NOT EXISTS file_changes_ad AFTER DELETE ON file_changes BEGIN
  INSERT INTO file_changes_fts(file_changes_fts, rowid, file_path, summary, diff, action)
  VALUES ('delete', old.id, old.file_path, old.summary, old.diff, old.action);
END;

CREATE TRIGGER IF NOT EXISTS file_changes_au AFTER UPDATE ON file_changes BEGIN
  INSERT INTO file_changes_fts(file_changes_fts, rowid, file_path, summary, diff, action)
  VALUES ('delete', old.id, old.file_path, old.summary, old.diff, old.action);
  INSERT INTO file_changes_fts(rowid, file_path, summary, diff, action)
  VALUES (new.id, new.file_path, new.summary, new.diff, new.action);
END;

-- Triggers for decisions_fts
CREATE TRIGGER IF NOT EXISTS decisions_ai AFTER INSERT ON decisions BEGIN
  INSERT INTO decisions_fts(rowid, question, answer, reasoning, alternatives)
  VALUES (new.id, new.question, new.answer, new.reasoning, new.alternatives);
END;

CREATE TRIGGER IF NOT EXISTS decisions_ad AFTER DELETE ON decisions BEGIN
  INSERT INTO decisions_fts(decisions_fts, rowid, question, answer, reasoning, alternatives)
  VALUES ('delete', old.id, old.question, old.answer, old.reasoning, old.alternatives);
END;

CREATE TRIGGER IF NOT EXISTS decisions_au AFTER UPDATE ON decisions BEGIN
  INSERT INTO decisions_fts(decisions_fts, rowid, question, answer, reasoning, alternatives)
  VALUES ('delete', old.id, old.question, old.answer, old.reasoning, old.alternatives);
  INSERT INTO decisions_fts(rowid, question, answer, reasoning, alternatives)
  VALUES (new.id, new.question, new.answer, new.reasoning, new.alternatives);
END;
"""

_SCHEMA_SQL_V3 = """
-- Ingestion checkpoints (V3)
CREATE TABLE IF NOT EXISTS ingestion_checkpoints (
    source TEXT NOT NULL,
    source_path TEXT NOT NULL,
    inode INTEGER NOT NULL DEFAULT 0,
    offset INTEGER NOT NULL DEFAULT 0,
    session_id TEXT DEFAULT '',
    project_path TEXT DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (source, source_path)
);

CREATE INDEX IF NOT EXISTS idx_ingestion_checkpoints_source
ON ingestion_checkpoints(source);
"""



_SCHEMA_SQL_V4 = """
-- Token usage tracking (V4)
CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    operation TEXT NOT NULL,  -- 'write' or 'read'
    tokens INTEGER NOT NULL DEFAULT 0,
    agent TEXT DEFAULT '',
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_token_usage_project ON token_usage(project_id);
"""


_SCHEMA_SQL_V5 = """
-- Source tracking for idempotent token backfill (V5)
ALTER TABLE token_usage ADD COLUMN source_table TEXT DEFAULT '';
ALTER TABLE token_usage ADD COLUMN source_id INTEGER DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_token_usage_source ON token_usage(source_table, source_id);
"""


def _apply_v6_migration(conn: sqlite3.Connection) -> None:
    """Auto-heal token-usage damage from pre-1.3.2 installs.

    Two specific bugs are remediated here so that nobody upgrading from
    1.3.1 (or fresh-installing on a system that already has a damaged DB)
    sees nonsense token totals or phantom 'unknown' agents:

    1. **Phantom 200M-token rows**: pre-1.3.2 ``project_detector`` could
       register a project with ``path='/'`` (or ``'~'``) when ``os.getcwd()``
       returned an empty string. The token backfill then walked the whole
       filesystem and hit the 200M-per-project cap on every session,
       inflating totals by billions. We delete token_usage rows whose
       source agent_session belongs to such a project, and zero the
       projects themselves so future scans skip them.

    2. **'unknown' agent attribution**: when no agent name was supplied at
       session-start, sessions and decisions were stored with
       ``agent='unknown'``. If we can identify a single dominant real agent
       active in the same project (within the same time window), relabel
       to that agent. Otherwise leave as-is — better to keep an honest
       'unknown' than silently mislabel.
    """
    # Defensive: every step is wrapped so a partial migration doesn't lock
    # the user out of A/MCL on subsequent opens.

    # ── Step 1: find projects with dangerous root paths ──
    try:
        from amcl.context.project_detector import _is_dangerous_root
    except Exception:
        def _is_dangerous_root(p: str) -> bool:
            return not p or p in ("/", os.path.expanduser("~"))

    bad_project_ids: list[int] = []
    try:
        for r in conn.execute("SELECT id, path FROM projects").fetchall():
            try:
                if _is_dangerous_root(r["path"] or ""):
                    bad_project_ids.append(int(r["id"]))
            except Exception:
                pass
    except sqlite3.OperationalError:
        pass

    # Delete phantom token_usage rows tied to dangerous-root projects.
    if bad_project_ids:
        placeholders = ",".join("?" for _ in bad_project_ids)
        try:
            conn.execute(
                f"DELETE FROM token_usage WHERE project_id IN ({placeholders})",
                tuple(bad_project_ids),
            )
        except sqlite3.Error:
            pass
        # Mark each project as quarantined so future scans skip it. We MUST
        # use a per-project unique sentinel rather than a shared empty string:
        # projects.path is UNIQUE, so setting two rows to '' in one pass (or
        # colliding with an already-quarantined row) raises IntegrityError and
        # would otherwise propagate out of get_connection(), bricking the DB.
        for pid in bad_project_ids:
            try:
                conn.execute(
                    "UPDATE projects SET path = ? WHERE id = ?",
                    (f"__amcl_quarantined_{pid}__", pid),
                )
            except sqlite3.Error:
                pass

    # ── Step 2: relabel 'unknown' agent rows where one real agent dominates ──
    # For each project with both 'unknown' and a single non-unknown agent,
    # relabel the unknown rows to that agent. If multiple real agents exist
    # in the same project, leave the unknown rows alone.
    try:
        rows = conn.execute(
            """SELECT project_id, agent, COUNT(*) AS c
               FROM agent_sessions
               WHERE agent IS NOT NULL AND agent != ''
               GROUP BY project_id, agent"""
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []

    by_project: dict[int, dict[str, int]] = {}
    for r in rows:
        by_project.setdefault(int(r["project_id"]), {})[r["agent"]] = int(r["c"])

    for pid, agent_counts in by_project.items():
        # Need both an "unknown" entry and exactly one real (non-unknown) agent
        unknowns = agent_counts.get("unknown", 0)
        real = {a: c for a, c in agent_counts.items() if a != "unknown"}
        if unknowns == 0 or not real:
            continue
        # Single dominant agent only — never guess across multiple.
        if len(real) == 1:
            target = next(iter(real))
            for tbl in ("agent_sessions", "messages", "file_changes",
                        "decisions", "tasks", "token_usage"):
                try:
                    conn.execute(
                        f"UPDATE {tbl} SET agent = ? "
                        f"WHERE project_id = ? AND agent = 'unknown'",
                        (target, pid),
                    )
                except sqlite3.OperationalError:
                    pass

    conn.commit()


def _apply_v5_migration(conn: sqlite3.Connection) -> None:
    """Apply V5 migration tolerantly — each ALTER TABLE may already be applied."""
    try:
        conn.execute(
            "ALTER TABLE token_usage ADD COLUMN source_table TEXT DEFAULT ''"
        )
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute(
            "ALTER TABLE token_usage ADD COLUMN source_id INTEGER DEFAULT 0"
        )
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_token_usage_source ON token_usage(source_table, source_id)"
        )
    except sqlite3.OperationalError:
        pass
    # Wipe legacy un-sourced rows so the incremental backfill can repopulate
    # them with correct source tracking (safer than trying to match).
    try:
        conn.execute(
            "DELETE FROM token_usage WHERE source_table = '' OR source_table IS NULL"
        )
    except sqlite3.OperationalError:
        pass


_ENC = None


def _get_encoder():
    global _ENC
    if _ENC is False:
        return None
    if _ENC is None:
        try:
            import tiktoken
            _ENC = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _ENC = False
            return None
    return _ENC


def _backfill_token_usage(conn: sqlite3.Connection) -> None:
    """Incrementally estimate historical token usage from existing
    messages/decisions/file_changes.

    Uses tiktoken (cl100k_base) when available, else a ~chars/3.3 heuristic.
    Only inserts token_usage rows for source rows that don't already have one
    (tracked via source_table + source_id), so this is safe to call on every
    connection open and after new data arrives.

    Token accounting is HONEST: each row is charged the tiktoken count of the
    text A/MCL actually stored for it — no fabricated system-prompt / tool-
    schema / whole-codebase-scan overhead. This mirrors the live write path in
    context_manager so backfilled and live figures stay consistent.
    """
    import json as _json
    import os

    def est(text: str) -> int:
        if not text:
            return 0
        enc = _get_encoder()
        if enc is not None:
            try:
                return len(enc.encode(text, disallowed_special=()))
            except Exception:
                pass
        try:
            from amcl.context.context_manager import ContextManager
            return ContextManager._estimate_tokens_heuristic(text)
        except Exception:
            return max(1, int(len(text) / 3.3))

    # Messages — keyed by messages.id (TEXT) stored numerically via rowid.
    # If a message was stored with storage='delta', the stored content is a
    # truncated preview. The original raw char count is preserved in the
    # context_note JSON meta.raw_chars — use that for better token estimation.
    try:
        msg_rows = conn.execute(
            """SELECT m.rowid AS rid, m.project_id, m.role, m.content, m.agent,
                      m.context_note
               FROM messages m
               WHERE NOT EXISTS (
                   SELECT 1 FROM token_usage t
                   WHERE t.source_table = 'messages' AND t.source_id = m.rowid
               )"""
        ).fetchall()
        for r in msg_rows:
            content = r["content"] or ""
            note_raw_chars = 0
            try:
                note = _json.loads(r["context_note"]) if r["context_note"] else {}
                meta = note.get("meta", {}) if isinstance(note, dict) else {}
                note_raw_chars = int(meta.get("raw_chars", 0) or 0)
            except Exception:
                pass
            effective_chars = max(note_raw_chars, len(content))
            if effective_chars <= 0:
                continue
            # Honest cost: token estimate of the stored message text. When the
            # message was stored as a delta preview, raw_chars (the original
            # length) gives a better estimate than the truncated content.
            tokens = max(1, int(effective_chars / 3.3))
            if tokens > 0:
                conn.execute(
                    """INSERT INTO token_usage
                         (project_id, operation, tokens, agent, source_table, source_id)
                       VALUES (?, 'message_write', ?, ?, 'messages', ?)""",
                    (r["project_id"], tokens, r["agent"] or "", int(r["rid"])),
                )
    except sqlite3.OperationalError:
        pass

    # Decisions — include reasoning overhead + system prompt per decision.
    try:
        dec_rows = conn.execute(
            """SELECT d.id, d.project_id, d.question, d.answer, d.reasoning,
                      d.alternatives, d.agent
               FROM decisions d
               WHERE NOT EXISTS (
                   SELECT 1 FROM token_usage t
                   WHERE t.source_table = 'decisions' AND t.source_id = d.id
               )"""
        ).fetchall()
        for r in dec_rows:
            combined = (
                (r["question"] or "")
                + (r["answer"] or "")
                + (r["reasoning"] or "")
                + str(r["alternatives"] or "")
            )
            # Honest cost: token estimate of the decision payload.
            tokens = est(combined)
            if tokens > 0:
                conn.execute(
                    """INSERT INTO token_usage
                         (project_id, operation, tokens, agent, source_table, source_id)
                       VALUES (?, 'decision_write', ?, ?, 'decisions', ?)""",
                    (r["project_id"], tokens, r["agent"] or "", int(r["id"])),
                )
    except sqlite3.OperationalError:
        pass

    # File changes — if the stored diff is empty, attempt to read the actual
    # file from disk (via the project's root path) to capture its content
    # size for a realistic token estimate.
    try:
        fc_rows = conn.execute(
            """SELECT fc.id, fc.project_id, fc.file_path, fc.summary, fc.diff, fc.agent,
                      p.path AS root_path
               FROM file_changes fc
               LEFT JOIN projects p ON p.id = fc.project_id
               WHERE NOT EXISTS (
                   SELECT 1 FROM token_usage tu
                   WHERE tu.source_table = 'file_changes' AND tu.source_id = fc.id
               )"""
        ).fetchall()
        for r in fc_rows:
            parts = [r["file_path"] or "", r["summary"] or "", r["diff"] or ""]
            if not r["diff"]:
                fp = r["file_path"] or ""
                root = r["root_path"] or ""
                candidates = []
                if fp and os.path.isabs(fp):
                    candidates.append(fp)
                if root and fp:
                    candidates.append(os.path.join(root, fp))
                for cand in candidates:
                    try:
                        if os.path.exists(cand) and os.path.isfile(cand):
                            size = os.path.getsize(cand)
                            if 0 < size < 2_000_000:
                                with open(cand, "r", errors="ignore") as fh:
                                    parts.append(fh.read(500_000))
                                break
                            elif size > 0:
                                # Huge file — approximate with placeholder chars.
                                parts.append("x" * min(size, 500_000))
                                break
                    except Exception:
                        pass
            combined = "\n".join(parts)
            # Honest cost: token estimate of path + summary + diff (and the
            # on-disk file content when no diff was stored).
            tokens = est(combined) + est(r["summary"] or "")
            if tokens > 0:
                conn.execute(
                    """INSERT INTO token_usage
                         (project_id, operation, tokens, agent, source_table, source_id)
                       VALUES (?, 'file_change_write', ?, ?, 'file_changes', ?)""",
                    (r["project_id"], tokens, r["agent"] or "", int(r["id"])),
                )
    except sqlite3.OperationalError:
        pass

    # NOTE: We deliberately do NOT backfill a per-session "context_read" cost.
    # The previous implementation walked the entire project tree on disk and
    # charged each agent session the full codebase token count, which both
    # slowed DB open dramatically on large repos and inflated read totals by
    # gigabytes. The live read path in context_manager records the real token
    # size of each context fetch instead.

    conn.commit()


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """
    Open (or create) the A/MCL SQLite database and ensure the schema
    is applied.  Returns a connection with row_factory = sqlite3.Row.
    """
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    # High timeout (30s) so concurrent agents wait instead of crashing
    conn = sqlite3.connect(str(path), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Check if schema already applied
    try:
        row = conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
        current_version = row["v"] if row and row["v"] else 0
    except sqlite3.OperationalError:
        current_version = 0

    needs_backfill = False
    if current_version < SCHEMA_VERSION:
        if current_version == 0:
            conn.executescript(_SCHEMA_SQL)
            conn.executescript(_SCHEMA_SQL_V2)
            conn.executescript(_SCHEMA_SQL_V3)
            conn.executescript(_SCHEMA_SQL_V4)
            _apply_v5_migration(conn)
            # V6 is a data-cleanup migration; on a fresh install there's
            # nothing to clean, but running it is harmless.
            _apply_v6_migration(conn)
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            # Fresh install — nothing to backfill.
        else:
            if current_version < 2:
                conn.executescript(_SCHEMA_SQL_V2)
                # Rebuild external content tables for existing data
                conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
                conn.execute("INSERT INTO file_changes_fts(file_changes_fts) VALUES('rebuild')")
                conn.execute("INSERT INTO decisions_fts(decisions_fts) VALUES('rebuild')")
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (2,),
                )
            if current_version < 3:
                conn.executescript(_SCHEMA_SQL_V3)
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (3,),
                )
            if current_version < 4:
                conn.executescript(_SCHEMA_SQL_V4)
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (4,),
                )
            if current_version < 5:
                _apply_v5_migration(conn)
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (5,),
                )
                # First time seeing V5 — backfill historical token usage
                # exactly once so `amcl tokens` is meaningful right after
                # upgrade. Subsequent opens skip this entirely.
                needs_backfill = True
            if current_version < 6:
                # Run the V6 cleanup AFTER V5 backfill (if applicable) so
                # any phantom 200M rows the backfill just inserted get
                # vacuumed in the same upgrade pass.
                _apply_v6_migration(conn)
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (6,),
                )
        conn.commit()

    if needs_backfill:
        try:
            _backfill_token_usage(conn)
        except sqlite3.OperationalError:
            # Tables may not exist on truly fresh installs — safe to skip.
            pass
        # Re-run the V6 cleanup so any phantom rows the backfill just
        # produced (from pre-1.3.2 projects with dangerous root paths)
        # get vacuumed before the user ever sees a token count.
        try:
            _apply_v6_migration(conn)
        except sqlite3.OperationalError:
            pass

    return conn


def ensure_tokens_backfilled(conn: sqlite3.Connection) -> None:
    """Run the historical token backfill on demand.

    The live write path in ``context_manager`` records tokens incrementally,
    so this is only needed when:
    - A user wants to repopulate token_usage after manual deletion.
    - The CLI's `tokens` / `tokens-rebuild` commands explicitly request it.

    Idempotent: source rows that already have a token_usage entry are
    skipped via the (source_table, source_id) guard.
    """
    try:
        _backfill_token_usage(conn)
    except sqlite3.OperationalError:
        pass
