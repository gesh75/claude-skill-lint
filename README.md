# claude-skill-lint

[![ci](https://github.com/gesh75/claude-skill-lint/actions/workflows/lint.yml/badge.svg)](https://github.com/gesh75/claude-skill-lint/actions/workflows/lint.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python: 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)

A tiny, **zero-dependency** linter for [Claude Code](https://claude.com/claude-code) skills.
Point it at your `~/.claude/skills` directory and it flags the things that quietly
degrade a skills library: broken frontmatter, descriptions that are too long
(they're loaded into context on *every* turn), bloated skill bodies that should
use progressive disclosure, dead `reference/` links, and outdated model IDs.

```console
$ skill_lint.py ~/.claude/skills
  ! [WARN ] api-design: body is 417 lines (> 400); move detail to reference/*.md  (bloated-body)
  ✗ [ERROR] token-budget-advisor: link points to a missing file: ../context-budget/SKILL.md  (dead-reference)

Scanned 124 skills in /Users/me/.claude/skills
  122 clean · 1 errors · 1 warnings · 0 info
```

## Why

A Claude Code skill has two cost surfaces:

- its **`description`** is loaded into context on *every* turn — so a bloated or
  vague description is a permanent tax and a trigger-reliability problem;
- its **body** is loaded only when the skill fires — so large bodies should push
  detail into `reference/*.md` (progressive disclosure) instead of sitting inline.

This linter encodes those rules, plus the structural checks (valid frontmatter,
names that match, no dead links) that keep a library trustworthy.

## Install

No dependencies beyond Python 3.8+.

### Option 1 — install script

Installs a `skill-lint` command to `~/.local/bin` (review the script first, as you should with any installer):

```bash
curl -fsSL https://raw.githubusercontent.com/gesh75/claude-skill-lint/main/install.sh -o install.sh
bash install.sh          # then run:  skill-lint ~/.claude/skills
```

Customize with env vars — `VERSION=v0.1.0` pins a release, `BIN_DIR=/usr/local/bin` changes the location:

```bash
VERSION=v0.1.0 BIN_DIR=/usr/local/bin bash install.sh
```

### Option 2 — single file

```bash
curl -O https://raw.githubusercontent.com/gesh75/claude-skill-lint/main/skill_lint.py
chmod +x skill_lint.py
```

## Usage

```bash
skill_lint.py [PATH] [--json] [--max-desc N] [--max-body N] [--quiet]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `PATH` | `~/.claude/skills` | directory to scan |
| `--json` | off | machine-readable output |
| `--max-desc` | `350` | max description length (chars) before a warning |
| `--max-body` | `400` | max body length (lines) before a warning |
| `--quiet` | off | hide INFO findings |

Exit code is **non-zero when any ERROR-level finding exists**, so it drops
straight into CI or a pre-commit hook.

## Examples

**Audit your whole skills library** (the default path):

```console
$ skill_lint.py
  ! [WARN ] api-design: body is 417 lines (> 400); move detail to reference/*.md (progressive disclosure)  (bloated-body)
  ! [WARN ] blueprint: description is 364 chars (> 350); it's loaded every turn — tighten it  (long-description)
  ✗ [ERROR] token-budget-advisor: link points to a missing file: ../context-budget/SKILL.md  (dead-reference)

Scanned 124 skills in /Users/me/.claude/skills
  121 clean · 1 errors · 2 warnings · 0 info
$ echo $?
1
```

**Scan a specific directory, errors/warnings only:**

```bash
skill_lint.py ./my-plugin/skills --quiet
```

**Machine-readable output** (pipe to `jq`, a dashboard, or a bot):

```console
$ skill_lint.py --json | jq '.summary'
{
  "errors": 1,
  "warnings": 2,
  "info": 0
}
```

**Tighten the budgets** — fail on descriptions over 250 chars or bodies over 300 lines:

```bash
skill_lint.py --max-desc 250 --max-body 300
```

**As a pre-commit hook** (`.git/hooks/pre-commit`):

```bash
#!/usr/bin/env bash
python3 skill_lint.py "$HOME/.claude/skills" --quiet || {
  echo "skill-lint found errors — commit aborted."; exit 1;
}
```

## What counts as a skill

Exactly two shapes — nothing else:

- a top-level **`<name>.md`**, or
- a **`<dir>/SKILL.md`**.

`reference/`, `rules/`, `agents/`, and sibling content files are supporting
material and are deliberately **not** linted as skills (so counts stay accurate).

## Checks

| Code | Level | What it catches |
|------|-------|-----------------|
| `no-frontmatter` | ERROR | no `---` frontmatter block |
| `no-name` | ERROR | missing `name:` (skill won't register) |
| `no-description` | ERROR | missing `description:` |
| `dead-reference` | ERROR | a Markdown link to a local `.md` that doesn't exist |
| `name-mismatch` | WARN | `name:` doesn't match the file/dir name |
| `long-description` | WARN | description over `--max-desc` chars |
| `bloated-body` | WARN | body over `--max-body` lines (use progressive disclosure) |
| `stale-model-id` | WARN | an outdated Claude model id (e.g. `claude-3-*`, `claude-opus-4-1`) |
| `short-description` | INFO | description under 30 chars (may not trigger) |

Current model ids — Opus 4.8 (`claude-opus-4-8`), Sonnet 4.6 (`claude-sonnet-4-6`),
Haiku 4.5 (`claude-haiku-4-5`) — are not flagged.

## CI

```yaml
# .github/workflows/lint.yml
name: skill-lint
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.x" }
      - run: python3 skill_lint.py . --quiet
```

## License

MIT — see [LICENSE](LICENSE).
