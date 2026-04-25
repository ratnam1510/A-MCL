"""
SQLite database schema and initialization for A/MCL.

Creates tables for projects, messages, file_changes, tasks,
decisions, and agent_sessions. Includes schema versioning.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 4

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

    if current_version < SCHEMA_VERSION:
        if current_version == 0:
            conn.executescript(_SCHEMA_SQL)
            conn.executescript(_SCHEMA_SQL_V2)
            conn.executescript(_SCHEMA_SQL_V3)
            conn.executescript(_SCHEMA_SQL_V4)
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
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
        conn.commit()

    return conn
