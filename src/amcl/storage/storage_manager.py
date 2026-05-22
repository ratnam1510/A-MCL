"""
StorageManager — typed CRUD layer over the A/MCL SQLite database.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from amcl.agent_identity import normalize_agent_name
from amcl.storage.database import get_connection
from amcl.context.message_filters import parse_message_context_note
from amcl.types import (
    AgentSession,
    ConversationMessage,
    Decision,
    FileChange,
    TaskItem,
)


class StorageManager:
    """High-level CRUD interface wrapping the SQLite database."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._conn = get_connection(db_path)

    def close(self) -> None:
        self._conn.close()

    def _normalize_agent(self, agent: str | None, fallback: str = "unknown") -> str:
        return normalize_agent_name(agent, fallback=fallback)

    # ── Projects ─────────────────────────────────────────────────────

    def get_or_create_project(
        self,
        path: str,
        name: str = "",
        language: str = "",
        framework: str = "",
        git_branch: str = "",
        git_commit: str = "",
    ) -> int:
        """Return the project id, creating the row if needed."""
        row = self._conn.execute(
            "SELECT id FROM projects WHERE path = ?", (path,)
        ).fetchone()
        if row:
            # Update metadata on reconnect
            self._conn.execute(
                """UPDATE projects
                   SET name=?, language=?, framework=?,
                       git_branch=?, git_commit=?, updated_at=datetime('now')
                   WHERE id=?""",
                (name or "", language, framework, git_branch, git_commit, row["id"]),
            )
            self._conn.commit()
            return row["id"]

        cur = self._conn.execute(
            """INSERT INTO projects (name, path, language, framework, git_branch, git_commit)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                name or Path(path).name,
                path,
                language,
                framework,
                git_branch,
                git_commit,
            ),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_project_info(self, project_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return dict(row) if row else None

    # ── Messages ─────────────────────────────────────────────────────

    def add_message(
        self,
        project_id: int,
        role: str,
        content: str,
        agent: str = "",
        context_note: str = "",
        msg_id: str | None = None,
        ignore_existing: bool = False,
    ) -> str:
        mid = msg_id or f"msg-{uuid.uuid4().hex[:8]}"
        insert = "INSERT OR IGNORE" if ignore_existing else "INSERT"
        normalized_agent = self._normalize_agent(agent, fallback="unknown")
        cur = self._conn.execute(
            f"""{insert} INTO messages (id, project_id, role, content, agent, context_note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (mid, project_id, role, content, normalized_agent, context_note),
        )
        self._conn.commit()
        if ignore_existing and cur.rowcount == 0:
            return ""
        return mid

    def get_messages(
        self,
        project_id: int,
        limit: int = 50,
        since: str | None = None,
        include_noise: bool = False,
    ) -> list[ConversationMessage]:
        noise_filter = ""
        if not include_noise:
            noise_filter = " AND (context_note = '' OR context_note NOT LIKE 'noise:%')"

        if since:
            rows = self._conn.execute(
                f"""SELECT * FROM messages
                   WHERE project_id = ? AND timestamp >= ?{noise_filter}
                   ORDER BY timestamp DESC, rowid DESC
                   LIMIT ?""",
                (project_id, since, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"""SELECT * FROM messages
                   WHERE project_id = ?{noise_filter}
                   ORDER BY timestamp DESC, rowid DESC
                   LIMIT ?""",
                (project_id, limit),
            ).fetchall()
        return [
            ConversationMessage(
                id=r["id"],
                timestamp=r["timestamp"],
                role=r["role"],
                content=r["content"],
                agent=r["agent"],
                context_note=r["context_note"],
            )
            for r in reversed(rows)  # oldest first
        ]

    def get_last_message(
        self,
        project_id: int,
        include_noise: bool = False,
    ) -> ConversationMessage | None:
        """Return the latest stored message, or None if no messages exist."""
        noise_filter = ""
        if not include_noise:
            noise_filter = " AND (context_note = '' OR context_note NOT LIKE 'noise:%')"

        row = self._conn.execute(
            f"""SELECT * FROM messages
               WHERE project_id = ?{noise_filter}
               ORDER BY timestamp DESC, rowid DESC
               LIMIT 1""",
            (project_id,),
        ).fetchone()
        if not row:
            return None

        return ConversationMessage(
            id=row["id"],
            timestamp=row["timestamp"],
            role=row["role"],
            content=row["content"],
            agent=row["agent"],
            context_note=row["context_note"],
        )

    def count_messages(
        self,
        project_id: int,
        since: str | None = None,
        include_noise: bool = False,
    ) -> int:
        """Return the number of stored conversation messages."""
        noise_filter = ""
        if not include_noise:
            noise_filter = " AND (context_note = '' OR context_note NOT LIKE 'noise:%')"

        if since:
            row = self._conn.execute(
                f"""SELECT COUNT(*) AS c FROM messages
                   WHERE project_id = ? AND timestamp >= ?{noise_filter}""",
                (project_id, since),
            ).fetchone()
        else:
            row = self._conn.execute(
                f"""SELECT COUNT(*) AS c FROM messages
                   WHERE project_id = ?{noise_filter}""",
                (project_id,),
            ).fetchone()
        return int(row["c"]) if row else 0

    # ── File Changes ─────────────────────────────────────────────────

    def add_file_change(
        self,
        project_id: int,
        file_path: str,
        action: str = "modified",
        agent: str = "",
        summary: str = "",
        diff: str = "",
    ) -> int:
        normalized_agent = self._normalize_agent(agent, fallback="unknown")
        cur = self._conn.execute(
            """INSERT INTO file_changes (project_id, file_path, action, agent, summary, diff)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, file_path, action, normalized_agent, summary, diff),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_file_changes(
        self, project_id: int, since: str | None = None
    ) -> list[FileChange]:
        if since:
            rows = self._conn.execute(
                """SELECT * FROM file_changes
                   WHERE project_id = ? AND timestamp >= ?
                   ORDER BY timestamp""",
                (project_id, since),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM file_changes
                   WHERE project_id = ?
                   ORDER BY timestamp""",
                (project_id,),
            ).fetchall()
        return [
            FileChange(
                file=r["file_path"],
                action=r["action"],
                timestamp=r["timestamp"],
                agent=r["agent"],
                summary=r["summary"],
                diff=r["diff"],
            )
            for r in rows
        ]

    # ── Tasks ────────────────────────────────────────────────────────

    def add_task(
        self,
        project_id: int,
        description: str,
        task_id: str | None = None,
        status: str = "pending",
    ) -> str:
        tid = task_id or f"t-{uuid.uuid4().hex[:6]}"
        self._conn.execute(
            """INSERT INTO tasks (id, project_id, description, status)
               VALUES (?, ?, ?, ?)""",
            (tid, project_id, description, status),
        )
        self._conn.commit()
        return tid

    def update_task(self, task_id: str, status: str) -> None:
        self._conn.execute(
            """UPDATE tasks SET status = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (status, task_id),
        )
        self._conn.commit()

    def get_tasks(self, project_id: int, since: str | None = None) -> list[TaskItem]:
        if since:
            rows = self._conn.execute(
                "SELECT * FROM tasks WHERE project_id = ? AND created_at >= ? ORDER BY created_at",
                (project_id, since),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM tasks WHERE project_id = ? ORDER BY created_at",
                (project_id,),
            ).fetchall()
        return [
            TaskItem(
                id=r["id"],
                description=r["description"],
                status=r["status"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    # ── Decisions ────────────────────────────────────────────────────

    def add_decision(
        self,
        project_id: int,
        question: str,
        answer: str,
        reasoning: str = "",
        alternatives: list[str] | None = None,
        agent: str = "",
    ) -> int:
        normalized_agent = self._normalize_agent(agent, fallback="unknown")
        cur = self._conn.execute(
            """INSERT INTO decisions
               (project_id, question, answer, reasoning, alternatives, agent)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                question,
                answer,
                reasoning,
                json.dumps(alternatives or []),
                normalized_agent,
            ),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_decisions(
        self, project_id: int, since: str | None = None
    ) -> list[Decision]:
        if since:
            rows = self._conn.execute(
                "SELECT * FROM decisions WHERE project_id = ? AND timestamp >= ? ORDER BY timestamp",
                (project_id, since),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM decisions WHERE project_id = ? ORDER BY timestamp",
                (project_id,),
            ).fetchall()
        return [
            Decision(
                timestamp=r["timestamp"],
                question=r["question"],
                answer=r["answer"],
                reasoning=r["reasoning"],
                alternatives=json.loads(r["alternatives"]),
                agent=r["agent"],
            )
            for r in rows
        ]

    # ── Global Preferences ───────────────────────────────────────────

    def set_global_preference(self, category: str, preference: str, agent: str) -> None:
        normalized_agent = self._normalize_agent(agent, fallback="unknown")
        self._conn.execute(
            """INSERT INTO global_preferences (category, preference, source_agent)
               VALUES (?, ?, ?)
               ON CONFLICT(category) DO UPDATE SET
                   preference=excluded.preference,
                   source_agent=excluded.source_agent,
                   updated_at=datetime('now')""",
            (category, preference, normalized_agent),
        )
        self._conn.commit()

    def get_global_preferences(self) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT category, preference FROM global_preferences ORDER BY category"
        ).fetchall()
        return {r["category"]: r["preference"] for r in rows}

    # ── Agent Sessions ───────────────────────────────────────────────

    def start_agent_session(self, project_id: int, agent: str) -> int:
        """Close any open sessions and start a new one."""
        normalized_agent = self._normalize_agent(agent, fallback="unknown")
        # Close previous open session
        self._conn.execute(
            """UPDATE agent_sessions
               SET ended = datetime('now'),
                   reason_for_switch = 'Agent switch detected'
               WHERE project_id = ? AND ended IS NULL""",
            (project_id,),
        )
        cur = self._conn.execute(
            """INSERT INTO agent_sessions (project_id, agent)
               VALUES (?, ?)""",
            (project_id, normalized_agent),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def end_agent_session(
        self,
        project_id: int,
        reason: str = "",
    ) -> None:
        self._conn.execute(
            """UPDATE agent_sessions
               SET ended = datetime('now'), reason_for_switch = ?
               WHERE project_id = ? AND ended IS NULL""",
            (reason, project_id),
        )
        self._conn.commit()

    def get_agent_sessions(
        self, project_id: int, since: str | None = None
    ) -> list[AgentSession]:
        if since:
            rows = self._conn.execute(
                """SELECT * FROM agent_sessions
                   WHERE project_id = ? AND started >= ?
                   ORDER BY started""",
                (project_id, since),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM agent_sessions
                   WHERE project_id = ?
                   ORDER BY started""",
                (project_id,),
            ).fetchall()
        return [
            AgentSession(
                agent=r["agent"],
                started=r["started"],
                ended=r["ended"],
                reason_for_switch=r["reason_for_switch"],
            )
            for r in rows
        ]

    def get_last_agent_switch_time(self, project_id: int) -> str | None:
        """Return the start time of the current agent session."""
        row = self._conn.execute(
            """SELECT started FROM agent_sessions
               WHERE project_id = ? AND ended IS NULL
               ORDER BY started DESC LIMIT 1""",
            (project_id,),
        ).fetchone()
        return row["started"] if row else None

    # ── Ingestion Checkpoints ───────────────────────────────────────

    def get_ingestion_checkpoint(
        self, source: str, source_path: str
    ) -> dict[str, int | str]:
        row = self._conn.execute(
            """SELECT source, source_path, inode, offset, session_id, project_path
               FROM ingestion_checkpoints
               WHERE source = ? AND source_path = ?""",
            (source, source_path),
        ).fetchone()
        if not row:
            return {
                "source": source,
                "source_path": source_path,
                "inode": 0,
                "offset": 0,
                "session_id": "",
                "project_path": "",
            }
        return {
            "source": row["source"],
            "source_path": row["source_path"],
            "inode": int(row["inode"] or 0),
            "offset": int(row["offset"] or 0),
            "session_id": row["session_id"] or "",
            "project_path": row["project_path"] or "",
        }

    def upsert_ingestion_checkpoint(
        self,
        *,
        source: str,
        source_path: str,
        inode: int,
        offset: int,
        session_id: str = "",
        project_path: str = "",
    ) -> None:
        self._conn.execute(
            """INSERT INTO ingestion_checkpoints
               (source, source_path, inode, offset, session_id, project_path)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(source, source_path) DO UPDATE SET
                   inode=excluded.inode,
                   offset=excluded.offset,
                   session_id=excluded.session_id,
                   project_path=excluded.project_path,
                   updated_at=datetime('now')""",
            (source, source_path, inode, offset, session_id, project_path),
        )
        self._conn.commit()

    # ── Token Usage ──────────────────────────────────────────────────

    def record_token_usage(
        self,
        project_id: int,
        operation: str,
        tokens: int,
        agent: str = "",
        source_table: str = "",
        source_id: int = 0,
    ) -> int:
        """Record a token usage event."""
        normalized_agent = self._normalize_agent(agent, fallback="unknown")
        cur = self._conn.execute(
            """INSERT INTO token_usage
                 (project_id, operation, tokens, agent, source_table, source_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, operation, tokens, normalized_agent, source_table, source_id),
        )
        self._conn.commit()
        return cur.lastrowid

    # Maps detailed operation types to the buckets surfaced in the UI.
    _OPERATION_BUCKETS = {
        "message_write": "messages",
        "file_change_write": "file_changes",
        "decision_write": "decisions",
        "task_write": "tasks",
        "preference_write": "preferences",
        "read": "reads",
    }

    # Operations considered "writes" for the legacy write_tokens tally.
    _WRITE_OPERATIONS = (
        "write",
        "message_write",
        "file_change_write",
        "decision_write",
        "task_write",
        "preference_write",
    )

    def get_token_stats(self, project_id: int) -> dict:
        """Return aggregate token usage stats for a project, including a
        per-operation breakdown so the UI can show where tokens went."""
        write_ops_placeholders = ",".join("?" for _ in self._WRITE_OPERATIONS)
        row = self._conn.execute(
            f"""SELECT
                 COALESCE(SUM(tokens), 0) as total_tokens,
                 COALESCE(SUM(CASE WHEN operation IN ({write_ops_placeholders}) THEN tokens ELSE 0 END), 0) as write_tokens,
                 COALESCE(SUM(CASE WHEN operation = 'read' THEN tokens ELSE 0 END), 0) as read_tokens,
                 COUNT(*) as total_operations
               FROM token_usage WHERE project_id = ?""",
            (*self._WRITE_OPERATIONS, project_id),
        ).fetchone()

        per_agent = self._conn.execute(
            """SELECT COALESCE(NULLIF(agent, ''), 'unknown') as agent,
                      SUM(tokens) as tokens, COUNT(*) as operations
               FROM token_usage WHERE project_id = ?
               GROUP BY COALESCE(NULLIF(agent, ''), 'unknown')
               ORDER BY tokens DESC""",
            (project_id,),
        ).fetchall()

        per_op = self._conn.execute(
            """SELECT operation, COALESCE(SUM(tokens), 0) as tokens,
                      COUNT(*) as operations
               FROM token_usage WHERE project_id = ?
               GROUP BY operation
               ORDER BY tokens DESC""",
            (project_id,),
        ).fetchall()

        breakdown = {
            "messages": 0,
            "file_changes": 0,
            "decisions": 0,
            "tasks": 0,
            "preferences": 0,
            "reads": 0,
            "other": 0,
        }
        for r in per_op:
            bucket = self._OPERATION_BUCKETS.get(r["operation"], "other")
            breakdown[bucket] += int(r["tokens"] or 0)

        return {
            "total_tokens": int(row["total_tokens"]),
            "write_tokens": int(row["write_tokens"]),
            "read_tokens": int(row["read_tokens"]),
            "total_operations": int(row["total_operations"]),
            "per_agent": [
                {"agent": r["agent"], "tokens": int(r["tokens"]), "operations": int(r["operations"])}
                for r in per_agent
            ],
            "per_operation": [
                {"operation": r["operation"], "tokens": int(r["tokens"]), "operations": int(r["operations"])}
                for r in per_op
            ],
            "breakdown": breakdown,
        }

    # ── Search ───────────────────────────────────────────────────────

    @staticmethod
    def _preview_text(text: str, max_chars: int = 180) -> tuple[str, bool]:
        """Return a compact text preview plus truncation metadata."""
        normalized = " ".join((text or "").split())
        if len(normalized) <= max_chars:
            return normalized, False
        return normalized[: max_chars - 1].rstrip() + "…", True

    def search_context(
        self,
        project_id: int,
        query: str,
        since: str | None = None,
        detail: str = "compact",
    ) -> dict:
        """Full-text search across messages, decisions, and tasks using FTS5."""
        # Sanitize query for FTS5 syntax (wrap in quotes if not already valid)
        clean_query = query.replace('"', '""')
        fts_query = f'"{clean_query}"*'

        # Fallback LIKE query for tasks which aren't FTS5 indexed yet
        q = f"%{query}%"

        since_str = since if since else "1970-01-01"

        messages = self._conn.execute(
            """SELECT m.* 
               FROM messages m
               JOIN messages_fts fts ON m.rowid = fts.rowid
               WHERE m.project_id = ? AND m.timestamp >= ? AND messages_fts MATCH ?
                 AND (m.context_note = '' OR m.context_note NOT LIKE 'noise:%')
               ORDER BY m.timestamp LIMIT 20""",
            (project_id, since_str, fts_query),
        ).fetchall()

        decisions = self._conn.execute(
            """SELECT d.* 
               FROM decisions d
               JOIN decisions_fts fts ON d.id = fts.rowid
               WHERE d.project_id = ? AND d.timestamp >= ? AND decisions_fts MATCH ?
               ORDER BY d.timestamp LIMIT 20""",
            (project_id, since_str, fts_query),
        ).fetchall()

        # Tasks still use regular LIKE since they're metadata-heavy
        tasks = self._conn.execute(
            """SELECT * FROM tasks
               WHERE project_id = ? AND created_at >= ? AND description LIKE ?
               ORDER BY created_at LIMIT 20""",
            (project_id, since_str, q),
        ).fetchall()

        # Also search file changes now that we have FTS5!
        file_changes = self._conn.execute(
            """SELECT fc.* 
               FROM file_changes fc
               JOIN file_changes_fts fts ON fc.id = fts.rowid
               WHERE fc.project_id = ? AND fc.timestamp >= ? AND file_changes_fts MATCH ?
               ORDER BY fc.timestamp LIMIT 20""",
            (project_id, since_str, fts_query),
        ).fetchall()

        if detail == "full":
            full_messages = []
            for row in messages:
                meta = parse_message_context_note(row["context_note"])
                item = dict(row)
                item["storage"] = str(meta.get("storage", "full"))
                item["raw_chars"] = meta.get("raw_chars")
                item["summary_source"] = meta.get("summary_source")
                item["signals"] = meta.get("signals", {})
                item["source"] = meta.get("source")
                full_messages.append(item)
            return {
                "detail": "full",
                "messages": full_messages,
                "decisions": [dict(r) for r in decisions],
                "tasks": [dict(r) for r in tasks],
                "file_changes": [dict(r) for r in file_changes],
            }

        compact_messages = []
        for row in messages:
            preview, truncated = self._preview_text(row["content"])
            meta = parse_message_context_note(row["context_note"])
            compact_messages.append(
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "role": row["role"],
                    "agent": row["agent"],
                    "content": preview,
                    "truncated": truncated,
                    "storage": str(meta.get("storage", "full")),
                    "raw_chars": meta.get("raw_chars"),
                    "summary_source": meta.get("summary_source"),
                    "signals": meta.get("signals", {}),
                    "source": meta.get("source"),
                }
            )

        compact_decisions = []
        for row in decisions:
            answer_preview, answer_truncated = self._preview_text(row["answer"])
            reasoning_preview, reasoning_truncated = self._preview_text(
                row["reasoning"]
            )
            compact_decisions.append(
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "question": row["question"],
                    "answer": answer_preview,
                    "reasoning": reasoning_preview,
                    "agent": row["agent"],
                    "truncated": answer_truncated or reasoning_truncated,
                }
            )

        compact_file_changes = []
        for row in file_changes:
            summary_preview, summary_truncated = self._preview_text(row["summary"])
            compact_file_changes.append(
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "file_path": row["file_path"],
                    "action": row["action"],
                    "agent": row["agent"],
                    "summary": summary_preview,
                    "truncated": summary_truncated,
                }
            )

        return {
            "detail": "compact",
            "messages": compact_messages,
            "decisions": compact_decisions,
            "tasks": [dict(r) for r in tasks],
            "file_changes": compact_file_changes,
        }
