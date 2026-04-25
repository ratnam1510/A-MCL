"""Agent identity normalization and runtime detection helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path


_ALIAS_TO_CANONICAL: dict[str, str] = {
    "cursor": "cursor",
    "cursor ai": "cursor",
    "codex": "codex",
    "openai codex": "codex",
    "claude": "claude",
    "claude code": "claude",
    "claude desktop": "claude",
    "antigravity": "antigravity",
    "gemini": "antigravity",
    "gemini cli": "antigravity",
    "amp": "amp",
    "sourcegraph amp": "amp",
    "opencode": "opencode",
    "open code": "opencode",
    "windsurf": "windsurf",
    "codeium": "windsurf",
    "copilot": "copilot",
    "github copilot": "copilot",
    "cline": "roo-cline",
    "roo": "roo-cline",
    "roo cline": "roo-cline",
    "roo code": "roo-cline",
    "roocode": "roo-cline",
    "vscode": "vscode",
    "visual studio code": "vscode",
    "code oss": "vscode",
    "generic": "generic",
    "auto": "auto",
    "unknown": "unknown",
}

_GENERIC_PROCESS_NAMES = {
    "python",
    "python3",
    "pythonw",
    "node",
    "npm",
    "pnpm",
    "yarn",
    "bun",
    "deno",
    "bash",
    "zsh",
    "sh",
    "fish",
    "env",
    "uv",
    "uvx",
    "amcl",
    "amcl-server",
    "mcp",
}


def _normalize_alias_key(value: str) -> str:
    lowered = value.lower().strip()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(lowered.split())


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)


def _extract_env_agent(text: str) -> str:
    match = re.search(r"amcl_agent_name\s*=\s*([a-zA-Z0-9._-]+)", text, re.IGNORECASE)
    if not match:
        return ""
    return match.group(1)


def _match_known_agent(text: str) -> str:
    key = _normalize_alias_key(text)
    if not key:
        return ""

    exact = _ALIAS_TO_CANONICAL.get(key, "")
    if exact and exact not in {"auto", "generic", "unknown"}:
        return exact

    for alias, canonical in _ALIAS_TO_CANONICAL.items():
        if canonical in {"auto", "generic", "unknown"}:
            continue
        if len(alias) >= 4 and alias in key:
            return canonical

    return ""


def normalize_agent_name(value: str | None, fallback: str = "unknown") -> str:
    """Normalize a raw agent name to a canonical stable identifier."""
    if value is None:
        return fallback

    raw = str(value).strip()
    if not raw:
        return fallback

    env_hint = _extract_env_agent(raw)
    if env_hint:
        raw = env_hint

    known = _match_known_agent(raw)
    if known:
        return known

    key = _normalize_alias_key(raw)
    if not key:
        return fallback

    slug = _slugify(key)
    if not slug or slug in {"auto", "generic", "unknown", "unset", "not-set"}:
        return fallback

    return slug


def _candidate_process_slug(cmdline: list[str], process_name: str) -> str:
    candidates: list[str] = []
    if process_name:
        candidates.append(process_name)
    candidates.extend(cmdline[:4])

    for candidate in candidates:
        value = str(candidate).strip()
        if not value or "=" in value:
            continue

        stem = Path(value).name
        if not stem:
            continue

        slug = _slugify(stem)
        if not slug or slug in _GENERIC_PROCESS_NAMES:
            continue

        return slug

    return ""


def detect_agent_from_process_tree(max_depth: int = 30) -> str:
    """Best-effort runtime detection of the currently running coding agent."""
    try:
        import psutil

        current = psutil.Process(os.getpid())
    except Exception:
        return "unknown"

    fallback = ""
    depth = 0

    while current and current.pid != 1 and depth < max_depth:
        depth += 1
        try:
            cmdline = current.cmdline()
            proc_name = current.name()
            blob = " ".join([proc_name, " ".join(cmdline)])
        except Exception:
            break

        env_hint = _extract_env_agent(blob)
        if env_hint:
            normalized = normalize_agent_name(env_hint, fallback="")
            if normalized:
                return normalized

        known = _match_known_agent(blob)
        if known:
            return known

        if not fallback:
            fallback = _candidate_process_slug(cmdline, proc_name)

        try:
            current = current.parent()
        except Exception:
            break

    return fallback or "unknown"


def resolve_runtime_agent_name(
    explicit: str | None = None,
    env_value: str | None = None,
) -> str:
    """Resolve the final runtime agent identifier used for storage."""
    raw = explicit if explicit is not None else env_value
    normalized = normalize_agent_name(raw, fallback="unknown")

    if normalized in {"unknown", "generic", "auto"}:
        detected = detect_agent_from_process_tree()
        if detected != "unknown":
            return detected
        if normalized in {"generic", "auto"}:
            return "generic"
        return "unknown"

    return normalized
