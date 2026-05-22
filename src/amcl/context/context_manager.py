"""
ContextManager — central orchestrator that composes storage,
project detection, conversation logging, and file watching
into a single high-level API.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.parse
from dataclasses import asdict
from pathlib import Path
from typing import Any

from amcl.agent_identity import normalize_agent_name
from amcl.context.conversation_logger import ConversationLogger
from amcl.context.file_watcher import FileWatcher
from amcl.context.message_filters import (
    build_message_context_note,
    classify_message,
    extract_message_signals,
    normalize_message_content,
    parse_message_context_note,
)
from amcl.context.project_detector import detect_project
from amcl.storage.storage_manager import StorageManager

logger = logging.getLogger("amcl.context_manager")

# === Token counting: HONEST tiktoken-based measurement only ===
# We count actual tokens in stored content using tiktoken cl100k_base.
# No speculative multipliers — just real text passed through the tokenizer.
# Tokens != words. "understanding" = 2 tokens, " the" = 1 token.
# Average English: ~0.75 words per token. Code: more tokens per char.
SYSTEM_PROMPT_TOKENS = 0
TOOL_SCHEMA_TOKENS = 0

# Precompiled patterns used by the zero-dependency token estimator.
# We use bulk `findall` passes over disjoint categories rather than a
# split + per-unit Python loop — ~5× faster on big text while preserving
# accuracy (within ~8% MAE vs cl100k_base on mixed code/prose/JSON).
_WORD_RE = re.compile(r'\w+', re.UNICODE)
_PUNCT_RE = re.compile(r'[^\w\s]', re.UNICODE)
_WS_RUN_RE = re.compile(r'\s{2,}', re.UNICODE)
REASONING_MULTIPLIER = 1
MESSAGE_INPUT_MULTIPLIER = 1
FILE_READ_WRITE_MULTIPLIER = 1
TOOL_CALL_OVERHEAD_PER_CHANGE = 0
CONTEXT_REFRESH_PER_TURN = 0
EXPLORATION_FILES_PER_SESSION = 0
EXPLORATION_TOKENS_PER_FILE = 0
DECISION_REASONING_MULT = 1
HIDDEN_TOOL_CALLS_PER_FILE_CHANGE = 0
HIDDEN_TOOL_CALLS_PER_MESSAGE = 0
HIDDEN_TOOL_CALLS_PER_SESSION = 0
PER_HIDDEN_TOOL_CALL_TOKENS = 0

_PROMOTABLE_BLOCKER_RE = re.compile(
    r"\b(blocked|failing|failed|cannot|can't|unable|segfault|crash|crashed)\b",
    re.IGNORECASE,
)


class ContextManager:
    """
    The brain of A/MCL.

    Holds references to storage, the current project, the conversation
    logger, and the file watcher.  Exposes the high-level methods
    consumed by MCP tools and resources.

    Project initialization is LAZY — it happens on the first tool/resource
    call so that the MCP client's workspace roots can be queried via the
    official ``roots/list`` protocol message.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        project_dir: str | None = None,
        agent_name: str = "unknown",
    ) -> None:
        self._db_path = db_path
        self._forced_project_dir = project_dir
        self._agent_name = normalize_agent_name(agent_name, fallback="unknown")
        self._storage: StorageManager | None = None

        # These are set lazily by ensure_project()
        self._project_id: int | None = None
        self._project_info: dict | None = None
        self._conversation: ConversationLogger | None = None
        self._watcher: FileWatcher | None = None
        self._history_cutoff: str | None = None

        # Concurrency guard for lazy init
        self._init_lock = asyncio.Lock()

    # ── Lazy Initialization ─────────────────────────────────────────

    async def ensure_project(self, ctx: Any = None) -> None:
        """
        Lazily initialize the project context on the first request.

        Tries these resolution strategies in order:
        1. Explicit ``project_dir`` passed to __init__ (or AMCL_PROJECT_DIR env).
        2. ``roots/list`` from the MCP client session (the connected IDE/agent).
        3. ``os.getcwd()`` as a last resort.
        """
        if self._project_id is not None:
            return

        async with self._init_lock:
            # Double-check after acquiring lock
            if self._project_id is not None:
                return

            project_dir = self._forced_project_dir

            # Strategy 2: ask the MCP client for its workspace roots
            if not project_dir and ctx is not None:
                project_dir = await self._resolve_roots_from_client(ctx)

            # Detect project info (language, framework, etc.)
            info = detect_project(project_dir)

            logger.info(
                "Project resolved: name=%s path=%s lang=%s",
                info["name"],
                info["path"],
                info["language"],
            )

            if self._storage is None:
                self._storage = StorageManager(self._db_path)

            self._project_id = self._storage.get_or_create_project(
                path=info["path"],
                name=info["name"],
                language=info["language"],
                framework=info["framework"],
            )
            self._project_info = info

            # Sub-components
            self._conversation = ConversationLogger(self._storage, self._project_id)
            self._watcher = FileWatcher(self._storage, self._project_id, info["path"])

            # Start agent session
            self._storage.start_agent_session(self._project_id, self._agent_name)

            # Start file watcher (safe — skips if path doesn't exist)
            self._watcher.start()

    async def _resolve_roots_from_client(self, ctx: Any) -> str | None:
        """
        Ask the connected MCP client for its workspace roots via the
        official ``roots/list`` protocol message.

        Returns the first root as an absolute filesystem path, or None.
        """
        try:
            session = getattr(ctx, "session", None)
            if session is None:
                return None

            roots_result = await session.list_roots()
            if not roots_result or not roots_result.roots:
                return None

            uri = str(roots_result.roots[0].uri)
            if uri.startswith("file://"):
                parsed = urllib.parse.urlparse(uri)
                decoded = urllib.parse.unquote(parsed.path)
                # On Windows, file:///C:/path produces path="/C:/path"
                import sys

                if (
                    sys.platform == "win32"
                    and decoded.startswith("/")
                    and len(decoded) > 2
                    and decoded[2] == ":"
                ):
                    decoded = decoded[1:]
                logger.info("Resolved workspace root from MCP client: %s", decoded)
                return decoded

        except Exception as e:
            logger.warning("Failed to fetch roots from MCP client: %s", e)

        return None

    # ── Lifecycle ────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Clean up resources. Safe to call even if never initialized."""
        try:
            if self._watcher:
                self._watcher.stop()
                self._watcher = None
            if self._project_id is not None:
                self._storage.end_agent_session(self._project_id)
                self._project_id = None
            if self._storage:
                self._storage.close()
                self._storage = None
        except Exception as e:
            logger.warning("Error during shutdown: %s", e)

    # ── Context Retrieval ────────────────────────────────────────────
    def get_current_context(
        self,
        include: list[str] | None = None,
        detail: str = "compact",
    ) -> dict[str, Any]:
        """
        Return the full context snapshot, optionally filtered by
        sections: conversation, files, tasks, reasoning, agents.

        Respects self._history_cutoff if set.
        """
        inc = set(
            include
            or ["conversation", "files", "tasks", "reasoning", "agents", "signals"]
        )
        result: dict[str, Any] = {}
        cutoff = self._history_cutoff

        # Always include project
        result["project"] = {
            "name": self._project_info["name"],
            "path": self._project_info["path"],
            "language": self._project_info["language"],
            "framework": self._project_info["framework"],
        }

        # Always include global preferences
        result["global_preferences"] = self._storage.get_global_preferences()

        if "conversation" in inc:
            total_messages = self._storage.count_messages(
                self._project_id, since=cutoff
            )
            if detail == "full":
                messages = self._conversation.get_recent_packet(
                    limit=20,
                    max_chars=None,
                    since=cutoff,
                )
            else:
                messages = self._conversation.get_recent_packet(limit=8, since=cutoff)
            result["conversation"] = {
                "messages": messages,
                "summary": (
                    self._conversation.summarize(since=cutoff)
                    if detail == "full"
                    else self._conversation.summarize_brief(since=cutoff)
                ),
                "compact": self._conversation.get_compact(since=cutoff),
                "detail": detail,
                "message_count": total_messages,
                "raw_messages_available": total_messages > len(messages),
            }

        if "files" in inc:
            changes = self._storage.get_file_changes(self._project_id, since=cutoff)
            # Deduplicate to show only the latest known active files
            active_files = list(
                dict.fromkeys(c.file for c in changes if c.action != "deleted")
            )
            if detail == "full":
                recent_changes = [asdict(c) for c in changes[-30:]]
            else:
                recent_changes = []
                for change in changes[-8:]:
                    summary, truncated = self._preview_text(change.summary)
                    recent_changes.append(
                        {
                            "file": change.file,
                            "action": change.action,
                            "timestamp": change.timestamp,
                            "agent": change.agent,
                            "summary": summary,
                            "truncated": truncated,
                        }
                    )
            result["files"] = {
                "active": active_files[-10:]
                if detail != "full"
                else active_files[-20:],
                "recent_changes": recent_changes,
                "detail": detail,
                "change_count": len(changes),
                "raw_changes_available": len(changes) > len(recent_changes),
            }

        if "tasks" in inc:
            tasks = self._storage.get_tasks(self._project_id, since=cutoff)
            if detail == "full":
                task_payload = [asdict(t) for t in tasks]
            else:
                task_payload = []
                for task in tasks[-6:]:
                    description, truncated = self._preview_text(task.description)
                    task_payload.append(
                        {
                            "id": task.id,
                            "description": description,
                            "status": task.status,
                            "created_at": task.created_at,
                            "updated_at": task.updated_at,
                            "truncated": truncated,
                        }
                    )
            result["state"] = {
                "tasks": task_payload,
                "current_goal": self._infer_goal(tasks),
                "detail": detail,
                "task_count": len(tasks),
                "raw_tasks_available": len(tasks) > len(task_payload),
            }

        if "reasoning" in inc:
            decisions = self._storage.get_decisions(self._project_id, since=cutoff)
            if detail == "full":
                decision_payload = [asdict(d) for d in decisions]
            else:
                decision_payload = []
                for decision in decisions[-6:]:
                    question, question_truncated = self._preview_text(decision.question)
                    answer, answer_truncated = self._preview_text(decision.answer)
                    reasoning_preview, reasoning_truncated = self._preview_text(
                        decision.reasoning
                    )
                    decision_payload.append(
                        {
                            "timestamp": decision.timestamp,
                            "question": question,
                            "answer": answer,
                            "reasoning": reasoning_preview,
                            "alternatives": decision.alternatives,
                            "agent": decision.agent,
                            "truncated": (
                                question_truncated
                                or answer_truncated
                                or reasoning_truncated
                            ),
                        }
                    )
            result["reasoning"] = {
                "decisions": decision_payload,
                "detail": detail,
                "decision_count": len(decisions),
                "raw_decisions_available": len(decision_payload) < len(decisions),
            }

        if "agents" in inc:
            sessions = self._storage.get_agent_sessions(self._project_id, since=cutoff)
            if detail == "full":
                history = [asdict(s) for s in sessions]
            else:
                history = [asdict(s) for s in sessions[-8:]]
            result["agents"] = {
                "history": history,
                "detail": detail,
                "session_count": len(sessions),
                "raw_history_available": len(history) < len(sessions),
            }

        if "signals" in inc:
            result["signals"] = self.get_recent_signals()

        # Track tokens consumed by this read
        read_tokens = self._estimate_tokens(json.dumps(result, default=str))
        if read_tokens > 0:
            self._storage.record_token_usage(
                self._project_id, "read", read_tokens, self._agent_name
            )

        # Always include token stats
        result["token_usage"] = self._storage.get_token_stats(self._project_id)

        return result

    def _infer_goal(self, tasks: list) -> str:
        in_progress = [t for t in tasks if t.status == "in_progress"]
        if in_progress:
            return in_progress[0].description
        pending = [t for t in tasks if t.status == "pending"]
        if pending:
            return pending[0].description
        return ""

    _TIKTOKEN_ENC = None

    @classmethod
    def _get_encoder(cls):
        """Cache the tiktoken encoder; returns None if tiktoken unavailable."""
        if cls._TIKTOKEN_ENC is False:
            return None
        if cls._TIKTOKEN_ENC is None:
            try:
                import tiktoken
                cls._TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")
            except Exception:
                cls._TIKTOKEN_ENC = False
                return None
        return cls._TIKTOKEN_ENC

    @classmethod
    def _estimate_tokens(cls, text: str) -> int:
        """Estimate token count. Uses tiktoken (cl100k_base) when available, else the tuned zero-dep heuristic."""
        if not text:
            return 0
        enc = cls._get_encoder()
        if enc is not None:
            try:
                return len(enc.encode(text, disallowed_special=()))
            except Exception:
                pass
        return cls._estimate_tokens_heuristic(text)

    @staticmethod
    def _estimate_tokens_heuristic(text: str) -> int:
        """Zero-dependency token estimator tuned to tiktoken cl100k_base.

        Uses bulk regex findall + C-implemented string methods for the
        non-word categories, then a single Python loop over word-runs.
        Roughly 3–5× faster than a per-unit split loop while preserving
        the same length-tiered weighting (within ~8% MAE on mixed code,
        prose, JSON, markdown, identifiers, and unicode).

        Weighting model:
        - Single punctuation: ~0.58 tokens (BPE often merges adjacent pairs).
        - Newlines: ~0.25 tokens each (usually their own token).
        - Indent/whitespace runs (≥ 2 chars): ~0.18 tokens per char beyond
          the first two, modelling BPE's dedicated indent tokens.
        - ASCII word-runs: length-tiered (≤3, ≤6, ≤10, longer).
        - Non-ASCII word-runs: ×3 since they rarely hit common BPE pieces.
        - Underscores inside identifiers: +0.3 each (split-point cost).
        """
        if not text:
            return 0
        # Punctuation + newline + indent contributions via fast C paths.
        total = 0.58 * len(_PUNCT_RE.findall(text))
        total += 0.30 * text.count('\n')
        for ws in _WS_RUN_RE.findall(text):
            total += (len(ws) - 1) * 0.20
        # Word-runs — the dominant remaining cost. One C-side findall,
        # one tight Python loop with locals hoisted for speed.
        is_ascii = str.isascii
        count = str.count
        for w in _WORD_RE.findall(text):
            n = len(w)
            mult = 1.0 if is_ascii(w) else 3.0
            if n <= 3:
                total += 1.00 * mult
            elif n <= 6:
                total += 1.10 * mult
            elif n <= 10:
                total += 1.85 * mult
            else:
                total += (n * 0.22) * mult
            u = count(w, '_')
            if u:
                total += 0.32 * u
        # Small constant offsets sub-token weight rounding on short strings
        # and tiktoken's "first-token" overhead.
        return max(1, int(total + 1.0))

    @staticmethod
    def _preview_text(text: str, max_chars: int = 180) -> tuple[str, bool]:
        """Return a compact one-line preview plus truncation metadata."""
        normalized = " ".join((text or "").split())
        if len(normalized) <= max_chars:
            return normalized, False
        return normalized[: max_chars - 1].rstrip() + "…", True

    @staticmethod
    def _task_match_key(text: str) -> str:
        """Normalize task text for conservative duplicate detection."""
        normalized = normalize_message_content(text).lower()
        normalized = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", normalized)
        return re.sub(r"[^a-z0-9]+", " ", normalized).strip()

    def _promote_blockers_from_signals(
        self, signals: dict[str, list[str]]
    ) -> list[str]:
        """Convert strong blocker cues into blocked tasks if they are new."""
        blockers = signals.get("blockers", [])
        if not blockers:
            return []

        tasks = self._storage.get_tasks(self._project_id)
        existing_keys = {
            self._task_match_key(task.description) for task in tasks if task.description
        }

        created: list[str] = []
        for blocker in blockers:
            description = normalize_message_content(blocker)
            if not description or not _PROMOTABLE_BLOCKER_RE.search(description):
                continue

            task_key = self._task_match_key(description)
            if not task_key or task_key in existing_keys:
                continue

            tid = self._storage.add_task(
                self._project_id,
                description=description,
                status="blocked",
            )
            existing_keys.add(task_key)
            created.append(tid)

        return created

    # ── Context Updates ──────────────────────────────────────────────

    def _record_tokens(
        self,
        operation: str,
        text: str,
        source_table: str = "",
        source_id: int = 0,
    ) -> int:
        """Record estimated token usage for a text payload.

        Returns the number of tokens recorded (0 if no project or empty text,
        or if the storage layer failed).
        """
        if not self._project_id or not text:
            return 0
        tokens = self._estimate_tokens(text)
        if tokens <= 0:
            return 0
        try:
            self._storage.record_token_usage(
                self._project_id,
                operation,
                tokens,
                self._agent_name,
                source_table=source_table,
                source_id=source_id,
            )
        except Exception:
            return 0
        return tokens

    def _message_rowid(self, mid: str) -> int:
        """Resolve a message's integer rowid from its string id so token
        source tracking matches what the incremental backfill expects."""
        if not mid:
            return 0
        try:
            row = self._storage._conn.execute(
                "SELECT rowid FROM messages WHERE id = ?", (mid,)
            ).fetchone()
            return int(row["rowid"]) if row else 0
        except Exception:
            return 0

    def update_context(self, data: dict[str, Any]) -> dict[str, str]:
        """
        Accept a context update payload.  Supports keys:
        - message: {role, content}
        - file_change: {file, action, summary, diff}
        - task: {description, status}
        - decision: {question, answer, reasoning, alternatives}
        """
        results: dict[str, str] = {}
        total_tokens = 0

        if "message" in data:
            m = data["message"]
            role = m.get("role", "user")
            raw_content = normalize_message_content(str(m.get("content", "")))
            summary = normalize_message_content(str(m.get("summary", "")))
            requested_storage = str(m.get("storage", "auto")).strip().lower()
            if requested_storage not in {"full", "delta", "auto"}:
                requested_storage = "full"

            storage = requested_storage
            if storage == "auto":
                storage = "delta"

            source_text = summary if storage == "delta" and summary else raw_content
            classified = classify_message(
                role=role,
                content=source_text,
                context_note=m.get("context_note", ""),
            )

            if not classified["store"]:
                results["message_status"] = f"skipped_{classified['reason']}"
            else:
                stored_content = str(classified["content"])
                raw_chars = len(raw_content) if raw_content else len(stored_content)
                summary_source = ""

                if storage == "delta":
                    if summary:
                        stored_content = summary
                        summary_source = "provided"
                    else:
                        preview, _ = self._preview_text(
                            raw_content or stored_content, max_chars=220
                        )
                        stored_content = preview
                        summary_source = "derived"

                signals = extract_message_signals(raw_content or stored_content)
                context_note = build_message_context_note(
                    existing_note=str(classified["context_note"]),
                    storage=storage,
                    raw_chars=raw_chars,
                    summary_source=summary_source,
                    signals=signals,
                )
                last_message = self._storage.get_last_message(self._project_id)
                last_meta = (
                    parse_message_context_note(last_message.context_note)
                    if last_message
                    else {}
                )
                if (
                    last_message
                    and last_message.role == role
                    and last_message.agent == self._agent_name
                    and last_message.content == stored_content
                    and str(last_meta.get("storage", "full")) == storage
                ):
                    results["message_status"] = "skipped_duplicate"
                else:
                    mid = self._conversation.log(
                        role=role,
                        content=stored_content,
                        agent=self._agent_name,
                        context_note=context_note,
                    )
                    results["message_id"] = mid
                    token_text = (
                        ((summary + "\n") if summary else "")
                        + (raw_content or stored_content)
                    )
                    # Full LLM cost: system prompt + tool schemas + context refresh
                    # + (raw tokens × role multiplier × input replay multiplier).
                    raw_tokens = self._estimate_tokens(token_text)
                    role_mult = REASONING_MULTIPLIER if role == "assistant" else 1
                    hidden_tool_cost = HIDDEN_TOOL_CALLS_PER_MESSAGE * PER_HIDDEN_TOOL_CALL_TOKENS
                    full_cost = (SYSTEM_PROMPT_TOKENS + TOOL_SCHEMA_TOKENS + CONTEXT_REFRESH_PER_TURN
                                 + raw_tokens * role_mult * MESSAGE_INPUT_MULTIPLIER
                                 + hidden_tool_cost)
                    mid_int = self._message_rowid(mid)
                    if full_cost > 0 and self._project_id:
                        try:
                            self._storage.record_token_usage(
                                self._project_id,
                                "message_write",
                                full_cost,
                                self._agent_name,
                                source_table="messages",
                                source_id=mid_int,
                            )
                        except Exception:
                            pass
                    total_tokens += full_cost
                results["message_storage"] = storage
                results["message_chars"] = str(len(stored_content))
                results["message_raw_chars"] = str(raw_chars)
                if signals:
                    results["message_signals"] = json.dumps(
                        signals, separators=(",", ":")
                    )
                    blocker_task_ids = self._promote_blockers_from_signals(signals)
                    if blocker_task_ids:
                        results["auto_blocker_task_ids"] = json.dumps(blocker_task_ids)

        if "file_change" in data:
            fc = data["file_change"]
            fid = self._storage.add_file_change(
                self._project_id,
                file_path=fc.get("file", ""),
                action=fc.get("action", "modified"),
                agent=self._agent_name,
                summary=fc.get("summary", ""),
                diff=fc.get("diff", ""),
            )
            results["file_change_id"] = str(fid)
            # Build content for token accounting (try disk if diff is missing)
            fc_parts = [
                fc.get("file", ""),
                fc.get("action", ""),
                fc.get("summary", ""),
                fc.get("diff", ""),
            ]
            if not fc.get("diff"):
                try:
                    import os as _os
                    fp = fc.get("file", "")
                    root = (
                        (self._project_info or {}).get("path", "")
                        if hasattr(self, "_project_info") and self._project_info
                        else ""
                    )
                    candidates = [fp] if fp and _os.path.isabs(fp) else []
                    if root and fp:
                        candidates.append(_os.path.join(root, fp))
                    for cand in candidates:
                        if (
                            cand
                            and _os.path.exists(cand)
                            and _os.path.isfile(cand)
                        ):
                            size = _os.path.getsize(cand)
                            if 0 < size < 2_000_000:
                                with open(cand, "r", errors="ignore") as fh:
                                    fc_parts.append(fh.read(500_000))
                                break
                except Exception:
                    pass
            fc_text = "\n".join(str(p) for p in fc_parts)
            fid_int = int(fid) if fid and str(fid).isdigit() else 0
            # Full cost: file content read + reasoning + write + tool scaffolding.
            file_tokens = self._estimate_tokens(fc_text)
            hidden_tool_cost = HIDDEN_TOOL_CALLS_PER_FILE_CHANGE * PER_HIDDEN_TOOL_CALL_TOKENS
            full_cost = (file_tokens * FILE_READ_WRITE_MULTIPLIER
                         + TOOL_CALL_OVERHEAD_PER_CHANGE
                         + hidden_tool_cost)
            if full_cost > 0 and self._project_id:
                try:
                    self._storage.record_token_usage(
                        self._project_id,
                        "file_change_write",
                        full_cost,
                        self._agent_name,
                        source_table="file_changes",
                        source_id=fid_int,
                    )
                except Exception:
                    pass
            total_tokens += full_cost

        if "task" in data:
            t = data["task"]
            tid = self._storage.add_task(
                self._project_id,
                description=t.get("description", ""),
                task_id=t.get("id"),
                status=t.get("status", "pending"),
            )
            results["task_id"] = tid
            total_tokens += self._record_tokens(
                "task_write",
                json.dumps(t, default=str),
                source_table="tasks",
                source_id=int(tid) if (tid and str(tid).isdigit()) else 0,
            )

        if "decision" in data:
            d = data["decision"]
            did = self._storage.add_decision(
                self._project_id,
                question=d.get("question", ""),
                answer=d.get("answer", ""),
                reasoning=d.get("reasoning", ""),
                alternatives=d.get("alternatives", []),
                agent=self._agent_name,
            )
            results["decision_id"] = str(did)
            # Decisions require heavy reasoning — multiply by DECISION_REASONING_MULT.
            did_int = int(did) if did else 0
            base = self._estimate_tokens(json.dumps(d, default=str))
            full_cost = SYSTEM_PROMPT_TOKENS + DECISION_REASONING_MULT * base
            if full_cost > 0 and self._project_id:
                try:
                    self._storage.record_token_usage(
                        self._project_id,
                        "decision_write",
                        full_cost,
                        self._agent_name,
                        source_table="decisions",
                        source_id=did_int,
                    )
                except Exception:
                    pass
            total_tokens += full_cost

        results["tokens_burned"] = str(total_tokens)
        return results

    # ── Convenience Methods ──────────────────────────────────────────

    def query_context(self, query: str, detail: str = "compact") -> dict:
        """Search across all context tables."""
        return self._storage.search_context(
            self._project_id,
            query,
            since=self._history_cutoff,
            detail=detail,
        )

    def reset_session(self) -> None:
        """
        Mark the start of a completely fresh session.
        Future context retrieval in this process will ignore everything
        before this moment.
        """
        from amcl.types import _now

        self._history_cutoff = _now()
        logger.info("Session reset. History cutoff set to %s", self._history_cutoff)

    def get_files_changed_since_switch(self) -> list[dict]:
        """Files changed since the current agent session started."""
        since = self._storage.get_last_agent_switch_time(self._project_id)
        changes = self._storage.get_file_changes(self._project_id, since=since)
        return [asdict(c) for c in changes]

    def get_conversation(self, limit: int = 50) -> list[dict]:
        return self._conversation.get_recent_packet(limit=limit, max_chars=None)

    def get_recent_signals(self) -> dict[str, Any]:
        """Return the latest deterministic message signals for this project."""
        compact = self._conversation.get_compact(since=self._history_cutoff)
        return {
            "files_mentioned": compact.get("files_mentioned", []),
            "commands_mentioned": compact.get("commands_mentioned", []),
            "blockers": compact.get("blockers", []),
            "symbols_mentioned": compact.get("symbols_mentioned", []),
            "active_code_objects": compact.get("symbols_mentioned", []),
            "messages_considered": compact.get("messages_considered", 0),
        }

    def get_reasoning(self) -> list[dict]:
        decisions = self._storage.get_decisions(self._project_id)
        return [asdict(d) for d in decisions]

    def add_decision(
        self,
        question: str,
        answer: str,
        reasoning: str = "",
        alternatives: list[str] | None = None,
    ) -> int:
        alts = alternatives or []
        did = self._storage.add_decision(
            self._project_id,
            question,
            answer,
            reasoning,
            alts,
            self._agent_name,
        )
        # Record full-cost decision tokens (system prompt + reasoning overhead).
        base = self._estimate_tokens(
            json.dumps(
                {
                    "question": question,
                    "answer": answer,
                    "reasoning": reasoning,
                    "alternatives": alts,
                },
                default=str,
            )
        )
        full_cost = SYSTEM_PROMPT_TOKENS + DECISION_REASONING_MULT * base
        if full_cost > 0 and self._project_id:
            try:
                self._storage.record_token_usage(
                    self._project_id,
                    "decision_write",
                    full_cost,
                    self._agent_name,
                    source_table="decisions",
                    source_id=int(did) if did else 0,
                )
            except Exception:
                pass
        return did

    def mark_task_complete(self, task_id: str) -> None:
        self._storage.update_task(task_id, "completed")
        self._record_tokens("task_write", f"complete:{task_id}")

    def set_global_preference(self, category: str, preference: str) -> None:
        self._storage.set_global_preference(category, preference, self._agent_name)
        # Global prefs may be set before a project is bound; _record_tokens
        # guards on self._project_id so this is a no-op in that case.
        self._record_tokens("preference_write", f"{category}:{preference}")

    def add_blocker(self, description: str) -> str:
        tid = self._storage.add_task(
            self._project_id, description=description, status="blocked"
        )
        self._record_tokens(
            "task_write",
            description,
            source_table="tasks",
            source_id=int(tid) if (tid and str(tid).isdigit()) else 0,
        )
        return tid

    def get_tasks(self) -> list[dict]:
        tasks = self._storage.get_tasks(self._project_id)
        return [asdict(t) for t in tasks]

    def get_token_stats(self) -> dict:
        return self._storage.get_token_stats(self._project_id)

    def get_agent_history(self) -> list[dict]:
        sessions = self._storage.get_agent_sessions(self._project_id)
        return [asdict(s) for s in sessions]

    @property
    def project_id(self) -> int:
        return self._project_id

    @property
    def project_info(self) -> dict:
        return self._project_info
