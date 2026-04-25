"""
Retroactive history importers for AI coding agents.

Scans local history files from Cursor, Claude Code, Codex, and other agents,
and imports conversation messages into A/MCL's database.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from amcl.agent_identity import normalize_agent_name


def _extract_text_parts(content: list, allowed_types: set[str]) -> list[str]:
    """Collect plain text fragments from a structured content array."""
    parts: list[str] = []

    for part in content:
        if isinstance(part, dict) and part.get("type") in allowed_types:
            text = part.get("text", "").strip()
            if text:
                parts.append(text)
        elif isinstance(part, str):
            stripped = part.strip()
            if stripped:
                parts.append(stripped)

    return parts


def _is_codex_bootstrap_message(text: str) -> bool:
    """Filter out Codex's injected AGENTS/environment bootstrap payloads."""
    prefixes = (
        "# AGENTS.md instructions for ",
        "<environment_context>",
        "<permissions instructions>",
        "<collaboration_mode>",
    )
    return text.startswith(prefixes)


def _normalized_import_agent(value: str | None) -> str:
    return normalize_agent_name(value, fallback="unknown")


def _slug_to_path(slug: str) -> str:
    """Convert Cursor's path slug back to a filesystem path.
    e.g. 'Users-ratnamshah-A-MCL' → '/Users/ratnamshah/A:MCL'
    """
    import sys

    parts = slug.split("-")

    if sys.platform == "win32":
        if len(parts[0]) == 1 and parts[0].isalpha():
            current = parts[0] + ":\\"
            remaining = parts[1:]
        else:
            current = "C:\\"
            remaining = parts
    else:
        current = "/"
        remaining = parts

    # Try simple exact match first
    candidate = os.path.join(current, *remaining) if remaining else current
    if os.path.exists(candidate):
        return candidate

    # Try matching incrementally
    for i, part in enumerate(remaining):
        test = os.path.join(current, part)
        if os.path.exists(test):
            current = test
        else:
            # Maybe it should be joined with Previous using :
            test_colon = current + ":" + part
            if os.path.exists(test_colon):
                current = test_colon
            else:
                test_hyphen = current + "-" + part
                if os.path.exists(test_hyphen):
                    current = test_hyphen
                else:
                    rest = os.path.join(*remaining[i:]) if remaining[i:] else ""
                    current = os.path.join(current, rest)
                    break

    return current


def scan_cursor() -> list[dict]:
    """Scan Cursor's agent transcripts for conversation history.

    Cursor stores transcripts at:
    ~/.cursor/projects/{path-slug}/agent-transcripts/{session-id}.jsonl

    Returns list of dicts with: project_path, agent, session_id, messages[]
    """
    cursor_dir = Path.home() / ".cursor" / "projects"
    if not cursor_dir.exists():
        return []

    results = []

    for project_dir in cursor_dir.iterdir():
        if not project_dir.is_dir():
            continue

        transcripts_dir = project_dir / "agent-transcripts"
        if not transcripts_dir.exists():
            continue

        project_path = _slug_to_path(project_dir.name)
        project_name = os.path.basename(project_path) or project_dir.name

        for jsonl_file in transcripts_dir.glob("*.jsonl"):
            session_id = jsonl_file.stem
            messages = []

            try:
                with open(jsonl_file, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            role = entry.get("role", "user")

                            # Extract text from content array
                            msg_obj = entry.get("message", {})
                            content_arr = msg_obj.get("content", [])
                            text_parts = []
                            for part in content_arr:
                                if (
                                    isinstance(part, dict)
                                    and part.get("type") == "text"
                                ):
                                    t = part.get("text", "")
                                    # Strip XML-like wrapper tags
                                    t = t.replace("<user_query>", "").replace(
                                        "</user_query>", ""
                                    )
                                    t = t.strip()
                                    if t:
                                        text_parts.append(t)
                                elif isinstance(part, str):
                                    text_parts.append(part)

                            if text_parts:
                                messages.append(
                                    {
                                        "role": role,
                                        "content": "\n".join(text_parts),
                                        "agent": _normalized_import_agent("cursor"),
                                    }
                                )
                        except (json.JSONDecodeError, KeyError):
                            continue
            except (OSError, IOError):
                continue

            if messages:
                results.append(
                    {
                        "project_path": project_path,
                        "project_name": project_name,
                        "agent": _normalized_import_agent("cursor"),
                        "session_id": session_id,
                        "messages": messages,
                    }
                )

    return results


def scan_claude_code() -> list[dict]:
    """Scan Claude Code's history for conversation messages.

    Claude Code stores at:
    ~/.claude/history.jsonl — JSONL with {display, timestamp, project, sessionId}

    Note: Claude Code only stores user messages in history.jsonl.
    """
    history_file = Path.home() / ".claude" / "history.jsonl"
    if not history_file.exists():
        return []

    # Group by session
    sessions: dict[str, dict] = {}

    try:
        with open(history_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    display = entry.get("display", "").strip()
                    if not display or display.startswith("/"):
                        continue  # Skip slash commands

                    session_id = entry.get("sessionId", "unknown")
                    project = entry.get("project", "/")
                    ts = entry.get("timestamp", 0)

                    if session_id not in sessions:
                        project_name = os.path.basename(project) or "unknown"
                        sessions[session_id] = {
                            "project_path": project,
                            "project_name": project_name,
                            "agent": "claude-code",
                            "session_id": session_id,
                            "messages": [],
                        }

                    sessions[session_id]["messages"].append(
                        {
                            "role": "user",
                            "content": display,
                            "agent": _normalized_import_agent("claude-code"),
                            "timestamp": datetime.utcfromtimestamp(ts / 1000).strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )
                            if ts
                            else "",
                        }
                    )
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
    except (OSError, IOError):
        return []

    return [s for s in sessions.values() if s["messages"]]


def scan_codex() -> list[dict]:
    """Scan Codex session logs for user and assistant messages."""
    sessions_dir = Path.home() / ".codex" / "sessions"
    if not sessions_dir.exists():
        return []

    results = []

    for jsonl_file in sorted(sessions_dir.rglob("*.jsonl")):
        session_id = jsonl_file.stem
        project_path = ""
        project_name = ""
        messages = []

        try:
            with open(jsonl_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    payload = entry.get("payload", {})
                    if entry.get("type") == "session_meta":
                        session_id = payload.get("id", session_id)
                        project_path = payload.get("cwd", "") or project_path
                        project_name = os.path.basename(project_path) or project_name
                        continue

                    if (
                        entry.get("type") != "response_item"
                        or payload.get("type") != "message"
                    ):
                        continue

                    role = payload.get("role")
                    if role not in {"user", "assistant"}:
                        continue

                    if role == "assistant" and payload.get("phase") == "commentary":
                        continue

                    allowed_types = (
                        {"input_text"} if role == "user" else {"output_text"}
                    )
                    text_parts = _extract_text_parts(
                        payload.get("content", []), allowed_types
                    )
                    if not text_parts:
                        continue

                    text = "\n".join(text_parts).strip()
                    if not text:
                        continue
                    if role == "user" and _is_codex_bootstrap_message(text):
                        continue

                    messages.append(
                        {
                            "role": role,
                            "content": text,
                            "agent": _normalized_import_agent("codex"),
                            "timestamp": entry.get("timestamp", ""),
                        }
                    )
        except (OSError, IOError):
            continue

        if project_path and messages:
            results.append(
                {
                    "project_path": project_path,
                    "project_name": project_name
                    or os.path.basename(project_path)
                    or "unknown",
                    "agent": _normalized_import_agent("codex"),
                    "session_id": session_id,
                    "messages": messages,
                }
            )

    return results


def scan_all() -> dict[str, list[dict]]:
    """Scan all known agents and return results grouped by agent name."""
    results = {}

    cursor = scan_cursor()
    if cursor:
        results["Cursor"] = cursor

    claude = scan_claude_code()
    if claude:
        results["Claude Code"] = claude

    codex = scan_codex()
    if codex:
        results["Codex"] = codex

    return results


def import_into_db(conn, scan_results: dict[str, list[dict]]) -> dict:
    """Import scanned history into AMCL's database.

    Returns a summary dict with counts.
    Deduplicates by checking existing message content + timestamp.
    """
    imported_msgs = 0
    new_projects = 0
    skipped = 0

    for agent_name, sessions in scan_results.items():
        for sess in sessions:
            project_path = sess["project_path"]
            project_name = sess["project_name"]

            # Find or create project
            row = conn.execute(
                "SELECT id FROM projects WHERE path = ?", (project_path,)
            ).fetchone()

            if row:
                pid = row["id"]
            else:
                conn.execute(
                    "INSERT INTO projects (name, path) VALUES (?, ?)",
                    (project_name, project_path),
                )
                pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                new_projects += 1

            # Import messages with deduplication
            for msg in sess["messages"]:
                content = msg["content"]
                role = msg["role"]
                agent = _normalized_import_agent(msg.get("agent", agent_name))
                ts = msg.get("timestamp") or datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                # Check if a nearly identical message already exists
                existing = conn.execute(
                    "SELECT id FROM messages WHERE project_id = ? AND content = ? AND role = ?",
                    (pid, content, role),
                ).fetchone()

                if existing:
                    skipped += 1
                    continue

                import uuid

                msg_id = f"import-{uuid.uuid4().hex[:12]}"

                conn.execute(
                    "INSERT INTO messages (id, project_id, timestamp, role, content, agent, context_note) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        msg_id,
                        pid,
                        ts,
                        role,
                        content,
                        agent,
                        f"Imported from {agent_name}",
                    ),
                )
                imported_msgs += 1

    conn.commit()
    return {
        "imported": imported_msgs,
        "new_projects": new_projects,
        "skipped": skipped,
    }
