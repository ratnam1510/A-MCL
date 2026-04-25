"""
Message filtering helpers for reducing low-value memory writes.
"""

from __future__ import annotations

import json
import re
from typing import Any


_TERMINAL_ARTIFACT_RE = re.compile(r"^@\[\s*TerminalName:.*\]$", re.DOTALL)
_BOOTSTRAP_PATTERNS = (
    "# AGENTS.md instructions for ",
    "# AGENTS.override.md instructions for ",
)
_MESSAGE_META_PREFIX = "meta:"
_FILE_REF_RE = re.compile(
    r"(?<![\w/.-])((?:[\w.-]+/)+[\w.-]+|[\w.-]+\.(?:py|ts|tsx|js|jsx|json|md|toml|yaml|yml|css|html|sql|sh|txt))(?![\w/.-])"
)
_BACKTICK_RE = re.compile(r"`([^`\n]{2,160})`")
_DOTTED_SYMBOL_RE = re.compile(r"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)+[A-Za-z_][A-Za-z0-9_]*\b")
_CAMEL_SYMBOL_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*\b")
_SNAKE_SYMBOL_RE = re.compile(r"\b[a-z_][a-z0-9_]*_[a-z0-9_]+\b")
_CALL_SYMBOL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\(\)")
_COMMAND_PREFIXES = (
    "amcl",
    "npm",
    "pnpm",
    "yarn",
    "npx",
    "node",
    "python",
    "python3",
    "pytest",
    "uv",
    "pip",
    "cargo",
    "make",
    "next",
)
_BLOCKER_KEYWORDS = (
    "blocked",
    "blocker",
    "failing",
    "failed",
    "failure",
    "error",
    "issue",
    "problem",
    "bug",
    "cannot",
    "can't",
    "unable",
    "segfault",
    "crash",
)


def normalize_message_content(content: str) -> str:
    """Normalize whitespace while preserving the original wording."""
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    normalized = "\n".join(line.rstrip() for line in lines).strip()
    return normalized


def build_message_context_note(
    *,
    existing_note: str = "",
    storage: str = "full",
    raw_chars: int | None = None,
    summary_source: str = "",
    signals: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
) -> str:
    """Encode non-noise message metadata into the context_note field."""
    note = (existing_note or "").strip()
    if note.startswith("noise:"):
        return note

    meta: dict[str, Any] = {"storage": storage}
    if raw_chars is not None:
        meta["raw_chars"] = raw_chars
    if summary_source:
        meta["summary_source"] = summary_source
    if signals:
        meta["signals"] = signals
    if source:
        meta["source"] = source
    if note:
        meta["note"] = note
    return _MESSAGE_META_PREFIX + json.dumps(meta, separators=(",", ":"), sort_keys=True)


def parse_message_context_note(note: str) -> dict[str, Any]:
    """Decode storage metadata stored in context_note."""
    stripped = (note or "").strip()
    if stripped.startswith("noise:"):
        return {"storage": "noise", "note": stripped}
    if not stripped.startswith(_MESSAGE_META_PREFIX):
        return {"storage": "full", "note": stripped}

    try:
        parsed = json.loads(stripped[len(_MESSAGE_META_PREFIX):])
    except json.JSONDecodeError:
        return {"storage": "full", "note": stripped}

    if not isinstance(parsed, dict):
        return {"storage": "full", "note": stripped}

    parsed.setdefault("storage", "full")
    return parsed


def _unique(items: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
        if len(ordered) >= limit:
            break
    return ordered


def _looks_like_command_head(head: str) -> bool:
    lowered = head.lower()
    return any(
        lowered == prefix or lowered.startswith(prefix + ".") or lowered.startswith(prefix + "-")
        for prefix in _COMMAND_PREFIXES
    )


def _looks_like_symbol(candidate: str) -> bool:
    text = candidate.strip().rstrip(".,:;)]}")
    if not text or "/" in text:
        return False

    lowered = text.lower()
    if _looks_like_command_head(lowered):
        return False

    if "." in text:
        suffix = text.rsplit(".", 1)[-1].lower()
        if suffix in {"py", "ts", "tsx", "js", "jsx", "json", "md", "toml", "yaml", "yml", "css", "html", "sql", "sh", "txt"}:
            return False

    return bool(
        _DOTTED_SYMBOL_RE.fullmatch(text)
        or _CAMEL_SYMBOL_RE.fullmatch(text)
        or _SNAKE_SYMBOL_RE.fullmatch(text)
        or _CALL_SYMBOL_RE.fullmatch(text)
    )
def extract_message_signals(content: str) -> dict[str, list[str]]:
    """Extract deterministic high-signal facts from a message."""
    normalized = normalize_message_content(content)
    if not normalized:
        return {}

    files = _unique(
        [match.group(1).rstrip(".,:;)]}") for match in _FILE_REF_RE.finditer(normalized)],
        limit=6,
    )

    commands: list[str] = []
    for match in _BACKTICK_RE.finditer(normalized):
        candidate = normalize_message_content(match.group(1))
        head = candidate.split()[0] if candidate.split() else ""
        if _looks_like_command_head(head):
            commands.append(candidate)

    for line in normalized.splitlines():
        stripped = line.strip()
        if stripped.startswith("$ "):
            stripped = stripped[2:].strip()
        head = stripped.split()[0] if stripped.split() else ""
        if _looks_like_command_head(head):
            commands.append(stripped)

    blockers: list[str] = []
    for segment in re.split(r"(?<=[.!?])\s+|\n+", normalized):
        snippet = segment.strip()
        if not snippet:
            continue
        lowered = snippet.lower()
        if any(keyword in lowered for keyword in _BLOCKER_KEYWORDS):
            blockers.append(snippet[:180].rstrip())

    symbols: list[str] = []
    for match in _BACKTICK_RE.finditer(normalized):
        candidate = normalize_message_content(match.group(1))
        if _looks_like_symbol(candidate):
            symbols.append(candidate.rstrip(".,:;)]}"))

    for match in _DOTTED_SYMBOL_RE.finditer(normalized):
        candidate = match.group(0)
        if _looks_like_symbol(candidate):
            symbols.append(candidate)

    for match in _CAMEL_SYMBOL_RE.finditer(normalized):
        candidate = match.group(0)
        if _looks_like_symbol(candidate):
            symbols.append(candidate)

    for match in _SNAKE_SYMBOL_RE.finditer(normalized):
        candidate = match.group(0)
        if _looks_like_symbol(candidate):
            symbols.append(candidate)

    for match in _CALL_SYMBOL_RE.finditer(normalized):
        candidate = match.group(1) + "()"
        if _looks_like_symbol(candidate):
            symbols.append(candidate)

    signals: dict[str, list[str]] = {}
    if files:
        signals["files"] = files
    unique_commands = _unique(commands, limit=4)
    if unique_commands:
        signals["commands"] = unique_commands
    unique_blockers = _unique(blockers, limit=3)
    if unique_blockers:
        signals["blockers"] = unique_blockers
    call_bases = {symbol[:-2] for symbol in symbols if symbol.endswith("()")}
    normalized_symbols = [
        symbol for symbol in symbols
        if not (symbol in call_bases and symbol + "()" in symbols)
    ]
    unique_symbols = _unique(normalized_symbols, limit=8)
    if unique_symbols:
        signals["symbols"] = unique_symbols
    return signals


def classify_message(role: str, content: str, context_note: str = "") -> dict[str, str | bool]:
    """Classify whether a message is worth storing in long-term memory."""
    normalized = normalize_message_content(content)
    note = (context_note or "").strip()

    if not normalized:
        return {
            "store": False,
            "content": "",
            "context_note": "noise:empty",
            "reason": "empty",
        }

    if _TERMINAL_ARTIFACT_RE.fullmatch(normalized):
        return {
            "store": False,
            "content": normalized,
            "context_note": "noise:terminal_artifact",
            "reason": "terminal_artifact",
        }

    if any(normalized.startswith(pattern) for pattern in _BOOTSTRAP_PATTERNS):
        return {
            "store": False,
            "content": normalized,
            "context_note": "noise:bootstrap",
            "reason": "bootstrap",
        }

    if note.startswith("noise:"):
        return {
            "store": False,
            "content": normalized,
            "context_note": note,
            "reason": note.split(":", 1)[1] if ":" in note else "noise",
        }

    return {
        "store": True,
        "content": normalized,
        "context_note": note,
        "reason": "",
    }
