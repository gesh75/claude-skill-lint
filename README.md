# claude-skill-lint

[![ci](https://github.com/gesh75/claude-skill-lint/actions/workflows/lint.yml/badge.svg)](https://github.com/gesh75/claude-skill-lint/actions/workflows/lint.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python: 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)

A tiny, **zero-dependency** linter for [Claude Code](https://claude.com/claude-code) and [Agent Skills](https://agentskills.io).
Point it at your `~/.claude/skills` directory and it flags the things that quietly
degrade a skills library: broken frontmatter, descriptions that are too long
(they're loaded into context on *every* turn), bloated skill bodies that should
use progressive disclosure, dead `references/` links, secrets, and outdated model IDs.

```console
$ skill_lint.py ~/.claude/skills
  ! [WARN ] api-design: L3 description is 364 chars (> 350); it's loaded every turn — tighten it  (long-description)
  ✗ [ERROR] token-budget-advisor: L12 path leaves the skill directory: ../context-budget/SKILL.md  (path-escape)

Scanned 124 skills in /Users/me/.claude/skills
  122 clean · 1 errors · 1 warnings · 0 info
```

## Why

A Claude Code skill has two cost surfaces:

- its **`description`** is loaded into context on *every* turn — so a bloated or
  vague description is a permanent tax and a trigger-reliability problem;
- its **body** is loaded only when the skill fires — so large bodies should push
  detail into `references/*.md` (progressive disclosure) instead of sitting inline.

v0.3 also encodes the agentskills.io hard limits (name format, 1024-char
description, 500-char compatibility), Claude.ai rejection rules (reserved words,
angle brackets), safety checks (secrets, `curl | bash`, path escape,
prompt-injection phrasing), and Claude Code field types (`context: fork`,
booleans, hooks). The original nine-rule engine never ran any of these.

## Install

No dependencies beyond Python 3.8+.

### Option 1 — install script

Installs a `skill-lint` command to `~/.local/bin` (review the script first):

```bash
curl -fsSL https://raw.githubusercontent.com/gesh75/claude-skill-lint/main/install.sh -o install.sh
bash install.sh          # then run:  skill-lint ~/.claude/skills
```

### Option 2 — single file

```bash
curl -O https://raw.githubusercontent.com/gesh75/claude-skill-lint/main/skill_lint.py
chmod +x skill_lint.py
```

## Usage

```bash
skill_lint.py [PATH] [--json] [--sarif FILE] [--max-desc N] [--max-body N]
              [--quiet] [--profile claude-code|spec|claude-ai]
              [--allow-model ID] [--fail-on-warn] [--fix] [--version]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `PATH` | `~/.claude/skills` | directory to scan |
| `--json` | off | machine-readable output (includes `line`) |
| `--sarif FILE` | off | write SARIF 2.1.0 (GitHub code scanning) |
| `--max-desc` | `350` | max description length (chars) before a warning |
| `--max-body` | `400` | max body length (lines) before a warning |
| `--quiet` | off | hide INFO findings |
| `--profile` | `claude-code` | `claude-code` (CC extensions are info), `spec` (strict), `claude-ai` (reserved words + XML) |
| `--allow-model` | none | do not flag this model id as stale (repeatable) |
| `--fail-on-warn` | off | exit 1 on warnings as well as errors |
| `--fix` | off | apply safe auto-fixes in place (BOM, LF, name, trigger language, model ids) |
| `--version` | | print `claude-skill-lint 0.3.0` |

Exit code is **non-zero when any ERROR-level finding exists**, so it drops
straight into CI or a pre-commit hook. `--fail-on-warn` also fails on warnings.

## What counts as a skill

Exactly two shapes — nothing else:

- a top-level **`<name>.md`**, or
- a **`<dir>/SKILL.md`**.

`references/`, `scripts/`, `assets/`, and sibling content files are supporting
material and are deliberately **not** linted as skills.

## Checks

| Code | Level | What it catches | Since |
|------|-------|-----------------|-------|
| `no-frontmatter` | ERROR | no `---` frontmatter block | v0.1 |
| `unclosed-frontmatter` | ERROR | opening `---` has no closer | v0.2 |
| `no-name` | ERROR | missing `name:` | v0.1 |
| `no-description` | ERROR | missing `description:` | v0.1 |
| `name-format` | ERROR | not 1–64 lowercase / digits / hyphens | v0.2 |
| `description-too-long` | ERROR | over the spec's 1024-char hard limit | v0.2 |
| `compatibility-too-long` | ERROR | `compatibility` over 500 chars | v0.2 |
| `dead-reference` | ERROR | Markdown *or* bare `scripts/` / `references/` path that doesn't exist | v0.1, v0.2 expanded |
| `secret-leak` | ERROR | API keys, PATs, PEM blocks | v0.2 |
| `reserved-name` | ERROR | `anthropic` / `claude` in the name (`--profile claude-ai`) | v0.2 |
| `xml-in-frontmatter` | ERROR | `<` `>` in name or description (Claude.ai) | v0.2 |
| `name-mismatch` | WARN* | `name:` doesn't match the file/dir name | v0.1 |
| `long-description` | WARN | description over `--max-desc` chars (context tax) | v0.1 |
| `vague-description` | WARN | no "use when" trigger language | v0.2 |
| `bloated-body` | WARN | body over `--max-body` lines | v0.1 |
| `body-token-budget` | WARN | body over ~5000 tokens | v0.2 |
| `empty-body` | WARN | nothing after the frontmatter | v0.2 |
| `stale-model-id` | WARN | outdated Claude model id | v0.1 |
| `allowed-tools-format` | WARN | comma-separated `allowed-tools` | v0.2 |
| `metadata-format` | WARN | `metadata` is not a string map | v0.2 |
| `unknown-field` / `cc-extension` | WARN/INFO | keys outside the spec (or Claude Code extensions) | v0.2 |
| `dangerous-command` | WARN | `curl \| bash`, `rm -rf /`, `eval`, `chmod 777` | v0.2 |
| `unclosed-fence` | WARN | odd number of ` ``` ` fences | v0.2 |
| `unreferenced-file` | WARN | a file in `references/` is never mentioned | v0.2 |
| `duplicate-name` | WARN | two skills declare the same `name` | v0.2 |
| `short-description` | INFO | description under 30 chars | v0.1 |
| `bom-present` | INFO | UTF-8 BOM (v0.1 reported this as `no-frontmatter`) | v0.2 |
| `filename-casing` | WARN | file is `skill.md`, not `SKILL.md` | v0.2 |
| `todo-left` | INFO | `TODO` / `FIXME` / `XXX` in the body | v0.2 |
| `path-escape` | ERROR | local path uses `..` and leaves the skill | v0.3 |
| `duplicate-key` | WARN | same frontmatter key declared twice | v0.3 |
| `invalid-boolean` | WARN | `user-invocable` / `disable-model-invocation` / `background` not true/false | v0.3 |
| `invalid-enum` | WARN | `context` not `fork`, `effort` not low\|medium\|high\|xhigh\|max | v0.3 |
| `hooks-format` | WARN | `hooks` is not a YAML mapping | v0.3 |
| `prompt-injection` | WARN | "ignore previous instructions" / jailbreak phrasing in the body | v0.3 |
| `unreferenced-script` | WARN | a file in `scripts/` is never mentioned | v0.3 |
| `license-missing` | WARN | `license` points at a file that is not in the skill | v0.3 |
| `no-heading` / `h1-mismatch` | INFO | body has no heading, or H1 does not match `name` | v0.3 |
| `crlf-newlines` | INFO | Windows `CRLF` line endings | v0.3 |

\* `name-mismatch` is a warning on `--profile claude-code` and an error on `spec` / `claude-ai`.

Current model ids — Opus 4.8 (`claude-opus-4-8`), Sonnet 4.6 (`claude-sonnet-4-6`),
Haiku 4.5 (`claude-haiku-4-5`) — are not flagged. Override leftovers with
`--allow-model`.

## GitHub Action

```yaml
# .github/workflows/skill-lint.yml
name: skill-lint
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: gesh75/claude-skill-lint@v0.2.0
        with:
          path: skills
          profile: claude-code
          sarif: skill-lint.sarif
      - uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: skill-lint.sarif
```

## CI (this repo)

```yaml
- run: python3 test_skill_lint.py
- run: python3 skill_lint.py tests/fixtures/clean --quiet
```

## License

MIT — see [LICENSE](LICENSE).
