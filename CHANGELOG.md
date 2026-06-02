# Changelog

All notable changes to this project will be documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.3]

### Fixed
- **Thread safety:** the file watcher now uses its own SQLite connection on
  its observer thread instead of sharing the main connection across threads,
  preventing intermittent "recursive cursor" / transaction races and possible
  corruption.
- **Migration crash:** the V6 token-cleanup migration no longer raises a
  `UNIQUE(path)` `IntegrityError` when more than one project has a dangerous
  root path — quarantined projects now get a unique sentinel path, so the
  database can no longer be bricked on open.
- **FTS search:** `context_query` no longer errors on queries containing FTS5
  syntax characters; it falls back to a `LIKE` scan.
- **Project registration:** `get_or_create_project` uses an atomic UPSERT,
  removing a race on the `UNIQUE(path)` constraint between concurrent agents.

### Changed
- **Honest token accounting:** removed the unused speculative cost multipliers
  and the per-session whole-codebase filesystem scan. Token figures now
  reflect the tiktoken size of stored context only — faster DB opens and no
  more inflated read totals.

### Security
- **Share backend is now fail-closed:** uploads are rejected unless
  `AMCL_SHARE_SECRET` is configured (`503` when unset, `401` on mismatch),
  with a 5 MB upload cap and `Content-Security-Policy` / `X-Content-Type-Options`
  / `X-Frame-Options` headers on served pages.
- **`amcl share --url`** now prompts for explicit consent before sending
  conversation history off-machine, sends a bearer token from
  `AMCL_SHARE_SECRET`, and surfaces upload errors instead of failing silently.

## [1.3.2]

- **Claude Code:** `amcl setup` now registers the MCP server in
  `~/.claude.json` (user + local scope), project `.mcp.json`, and adds
  `mcp__amcl` to Claude Code permissions. Previously only Claude Desktop
  and `CLAUDE.md` rules were configured, so tools never connected.
- Open-source release prep: `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`,
  `CODE_OF_CONDUCT.md`, GitHub CI, issue/PR templates; cleaned tracked
  build artifacts from version control.
- Fixed `amcl-share-backend` gitignore so `.env.local.example` can be
  committed; expanded root `.gitignore` for Node/Next build outputs.

## [1.3.1]

- Bumped SQLite connection timeout, refined sharing serialization, and
  fixed a number of timestamp / project-detection edge cases.

## [1.3.0]

- Added Codex to the agent auto-detection list.
- Enhanced the sharing flow with token tracking and conversation
  summaries.

See `git log` for the full history prior to this changelog.
