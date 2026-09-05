# Changelog

## Unreleased

- Fail closed when a scan finds zero skills (exit 2, score 0) so `--min-score` and CI cannot go green on an empty walk.
- Discover `.claude/skills/` from a repo-root / Action `path: "."` scan; other hidden directories stay skipped.

## 0.5.0 — 2026-08-29

- Current model IDs: Opus 5, Sonnet 5, Fable 5, Mythos 5. Opus 4.8 / Sonnet 4.6 / Haiku 4.5 stay current.
- `--fix` rewrites Claude 3.x ids to `claude-sonnet-5`.
- Model aliases: `fable`, `mythos`.
- New checks: `computer-unscoped`, `beta-header-stale`, `plugin-colon-name`.
- 22-skill NetOps pack under `skills/netops/` (SD-WAN, SASE, EVPN, CAB, NetBox, MCP safety).
- GitHub Action example pin `@v0.5.0`.
- Docs: https://gesh75.github.io/claude-skill-lint/

## 0.4.0 — 2026-08-23

- 50 authoring/safety rules, `--stdin` / `--min-score` / `--ignore` / `--exclude`.
- Automatic GitHub Actions annotations.

## 0.3.0

- Path escape, Claude Code enums, SARIF, `--fix`.

## 0.2.0

- 32-rule engine, `--profile`, `--fail-on-warn`, composite GitHub Action.

## 0.1.0 — 2026-06-17

- First public release. Nine checks.
