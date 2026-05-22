"""
ProjectDetector — identifies the current project by
working directory and config files.
"""

from __future__ import annotations

import os
from pathlib import Path


_DANGEROUS_ROOTS = frozenset(
    str(Path(p).resolve()) for p in (
        "/", os.path.expanduser("~"), "/root", "/home", "/Users",
        "/var", "/etc", "/tmp", "/private/tmp", "/private",
    )
)


def _is_dangerous_root(p: str) -> bool:
    """Reject paths that would scan large swathes of the filesystem
    (root, home, /var, etc.) — projects must be a real subdirectory."""
    if not p:
        return True
    try:
        resolved = str(Path(p).resolve())
    except Exception:
        return True
    if resolved in _DANGEROUS_ROOTS:
        return True
    # Anything < 2 path components on Unix or directly equal to a drive
    # root on Windows is also unsafe.
    parts = Path(resolved).parts
    if len(parts) < 2:
        return True
    return False


def detect_project(cwd: str | None = None) -> dict:
    """
    Detect the current project.

    Args:
        cwd: Explicit project directory. If None, falls back to os.getcwd()
             and process-tree heuristics.

    Returns dict: { name, path, language, framework }
    """
    project_path = cwd

    if not project_path:
        current_cwd = os.getcwd()
        if current_cwd and not _is_dangerous_root(current_cwd):
            project_path = current_cwd
        else:
            # Agent launched A/MCL from / or ~ (likely the MCP server was
            # spawned with no cwd). Fall back to a per-host sentinel inside
            # ~/.amcl so we never accidentally treat the entire filesystem
            # as a "project" (which would balloon token estimates by GB).
            project_path = str(Path(os.path.expanduser("~/.amcl")) / "_no_project")

    # Final guard: if the resolved path is still dangerous, redirect to the
    # sentinel. This is what prevented the 200M-token phantom rows.
    if _is_dangerous_root(project_path):
        project_path = str(Path(os.path.expanduser("~/.amcl")) / "_no_project")

    info: dict = {
        "name": Path(project_path).name or "no-project",
        "path": str(Path(project_path).resolve()),
        "language": "",
        "framework": "",
    }

    # ── Language / framework heuristics ──────────────────────────
    root = Path(info["path"])

    if (root / "package.json").exists():
        info["language"] = "javascript"
        _detect_js_framework(root, info)
    elif (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        info["language"] = "python"
        _detect_py_framework(root, info)
    elif (root / "Cargo.toml").exists():
        info["language"] = "rust"
    elif (root / "go.mod").exists():
        info["language"] = "go"
    elif (root / "pom.xml").exists() or (root / "build.gradle").exists():
        info["language"] = "java"
    elif (root / "Package.swift").exists() or any(root.glob("*.swift")):
        info["language"] = "swift"

    return info


def _detect_js_framework(root: Path, info: dict) -> None:
    """Detect JavaScript/TypeScript frameworks."""
    try:
        import json

        pkg = json.loads((root / "package.json").read_text())
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

        if "next" in deps:
            info["framework"] = "next.js"
        elif "react" in deps:
            info["framework"] = "react"
        elif "vue" in deps:
            info["framework"] = "vue"
        elif "express" in deps:
            info["framework"] = "express"

        # Detect TypeScript
        if "typescript" in deps or (root / "tsconfig.json").exists():
            info["language"] = "typescript"
    except (json.JSONDecodeError, FileNotFoundError):
        pass


def _detect_py_framework(root: Path, info: dict) -> None:
    """Detect Python frameworks."""
    try:
        toml_text = (root / "pyproject.toml").read_text()
        if "django" in toml_text.lower():
            info["framework"] = "django"
        elif "flask" in toml_text.lower():
            info["framework"] = "flask"
        elif "fastapi" in toml_text.lower():
            info["framework"] = "fastapi"
    except FileNotFoundError:
        pass
