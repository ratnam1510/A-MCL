"""
SQLite database schema and initialization for A/MCL.

Creates tables for projects, messages, file_changes, tasks,
decisions, and agent_sessions. Includes schema versioning.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

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


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """
    Open (or create) the A/MCL SQLite database and ensure the schema
    is applied.  Returns a connection with row_factory = sqlite3.Row.
    """
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
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
        conn.executescript(_SCHEMA_SQL)
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
        conn.commit()

    return conn
