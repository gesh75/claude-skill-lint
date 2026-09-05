# claude-skill-lint

[![ci](https://github.com/gesh75/claude-skill-lint/actions/workflows/lint.yml/badge.svg)](https://github.com/gesh75/claude-skill-lint/actions/workflows/lint.yml)
[![docs](https://img.shields.io/badge/docs-gesh75.github.io-e4e4e7?labelColor=09090b)](https://gesh75.github.io/claude-skill-lint/)
[![release](https://img.shields.io/github/v/release/gesh75/claude-skill-lint)](https://github.com/gesh75/claude-skill-lint/releases/tag/v0.5.0)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python: 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)

A tiny, **zero-dependency** linter for [Claude Code](https://claude.com/claude-code) and [Agent Skills](https://agentskills.io).
Point it at your `~/.claude/skills` directory and it flags the things that quietly
degrade a skills library: broken frontmatter, descriptions that are too long
(they're loaded into context on *every* turn), bloated skill bodies that should
use progressive disclosure, dead `references/` links, secrets, and outdated model IDs.

**Docs:** [gesh75.github.io/claude-skill-lint](https://gesh75.github.io/claude-skill-lint/) · **Release:** [v0.5.0](https://github.com/gesh75/claude-skill-lint/releases/tag/v0.5.0)

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

v0.5 also encodes the 2026 model lineup (Opus 5, Sonnet 5, Fable 5, Mythos 5 —
Opus 4.8 / Sonnet 4.6 / Haiku 4.5 stay current), GitHub-mounted `.claude/skills`,
computer-use + unscoped Bash as a fail-closed pair, and a 22-skill NetOps pack
under `skills/netops/`. v0.4 encoded the authoring guides (Anthropic, Codex
60-char frontload, Antigravity do-not-use + Safety heading), Claude Code 2026
fields (`when_to_use` listing cap at 1536, `argument-hint`, reserved slash
commands), and a second safety pass (TLS verification off, reverse shells,
unpinned installs, bundled `.env` / `id_rsa`). The original nine-rule engine
never ran any of these.

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
              [--stdin] [--min-score N] [--ignore CODE] [--exclude GLOB]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `PATH` | `~/.claude/skills` | directory to scan (label, when used with `--stdin`) |
| `--json` | off | machine-readable output (`line`, `score`, per-skill `scores`) |
| `--sarif FILE` | off | write SARIF 2.1.0 (GitHub code scanning) |
| `--max-desc` | `350` | max description length (chars) before a warning |
| `--max-body` | `400` | max body length (lines) before a warning |
| `--quiet` | off | hide INFO findings |
| `--profile` | `claude-code` | `claude-code` (CC extensions are info), `spec` (strict), `claude-ai` (reserved words + XML) |
| `--allow-model` | none | do not flag this model id as stale (repeatable) |
| `--fail-on-warn` | off | exit 1 on warnings as well as errors |
| `--fix` | off | apply safe auto-fixes in place (BOM, LF, name, trigger language, model ids) |
| `--stdin` | off | lint SKILL.md text from stdin |
| `--min-score` | none | exit 1 if any skill scores below N (0–100; errors 16, warns 6, infos 1) |
| `--ignore CODE` | none | skip these finding codes (comma-separated or repeatable) |
| `--exclude GLOB` | none | skip skill paths matching this glob (repeatable) |
| `--version` | | print `claude-skill-lint 0.5.0` |

Exit codes:

| Code | Meaning |
|------|---------|
| `0` | Scan found skills and none failed the selected gate |
| `1` | ERROR findings, `--fail-on-warn` warnings, or `--min-score` miss |
| `2` | Path is not a directory, **or zero skills were found** |

A directory with no skills used to report score 100 and exit 0, which made
`--min-score` and CI go green without linting anything. Empty scans now
print `error: no skills found` and exit 2. `--fail-on-warn` also fails on
warnings. `--min-score 80` fails the job if the worst skill scores below 80.
Running inside GitHub Actions emits `::error` / `::warning` / `::notice`
annotations on stderr automatically.

Pipe a single file:

```bash
skill_lint.py pdf-extract/SKILL.md --stdin < SKILL.md --min-score 90
```

## What counts as a skill

Exactly two shapes — nothing else:

- a top-level **`<name>.md`**, or
- a **`<dir>/SKILL.md`**.

Hidden directories are skipped, except **`.claude/skills/`** (the Claude Code
project-skill location). A repo-root scan or the GitHub Action default
`path: "."` therefore lints project skills. Other `.claude/` trees
(`projects/`, transcripts, settings) are not walked.

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
| `typo-field` | WARN | unknown key within edit-distance 2 of a real field (`descrption`) | v0.4 |
| `desc-no-verb` | INFO | description does not open with an action verb | v0.4 |
| `first-person-desc` | INFO | description uses I/we/you instead of third person | v0.4 |
| `frontloaded-triggers` | INFO | first 60 characters have no concrete keywords (Codex) | v0.4 |
| `no-boundary` | INFO | no `do not use` / `not for` clause (Antigravity) | v0.4 |
| `desc-truncation` | WARN | `use when` sits after character 250 | v0.4 |
| `desc-this-skill` | INFO | description starts with `This skill` | v0.4 |
| `always-trigger` | WARN | description says to always fire | v0.4 |
| `listing-truncation` | WARN | `description` + `when_to_use` over Claude Code's 1536-char listing cap | v0.4 |
| `broad-scope` | INFO | `and` appears 3+ times in the description | v0.4 |
| `generic-name` | WARN | name is `helper` / `utils` / `tools` / `misc` | v0.4 |
| `reserved-command` | WARN | name collides with a Claude Code builtin (`compact`, `help`, …) | v0.4 |
| `explainer-bloat` | INFO | body defines common knowledge (`JSON stands for`) | v0.4 |
| `or-chain` | INFO | long A or B or C or D optionality | v0.4 |
| `no-numbered-steps` | INFO | no numbered procedure or checklist | v0.4 |
| `no-code-example` | INFO | no language-tagged fence | v0.4 |
| `no-anti-pattern` | INFO | body never says what not to do | v0.4 |
| `no-validate-loop` | INFO | no verify / confirm / assert step | v0.4 |
| `time-sensitive` | WARN | `as of 2024` / `new in v3` will rot | v0.4 |
| `no-disclosure` | INFO | body over 200 lines with no `references/` | v0.4 |
| `missing-arg-hint` | INFO | `$ARGUMENTS` used without `argument-hint` | v0.4 |
| `unquoted-colon` | WARN | unquoted YAML value contains `:` | v0.4 |
| `tabs-in-yaml` | INFO | tabs in frontmatter | v0.4 |
| `missing-newline` | INFO | no trailing newline | v0.4 |
| `long-line` | INFO | a line over 240 characters | v0.4 |
| `multiple-h1` | INFO | more than one `#` heading | v0.4 |
| `script-no-shebang` | INFO | bundled `.py`/`.sh` has no `#!` | v0.4 |
| `script-interactive` | WARN | `input()` / `read -p` in a bundled script | v0.4 |
| `junk-file` | WARN | `.DS_Store` / `__MACOSX` / `Thumbs.db` | v0.4 |
| `unexpected-root` | INFO | top-level file outside spec layout | v0.4 |
| `nested-skill` | WARN | a supporting folder contains another `SKILL.md` | v0.4 |
| `hardcoded-home` | WARN | `/Users`, `/home`, `~/Desktop` | v0.4 |
| `localhost-url` | INFO | hard-coded `localhost:port` | v0.4 |
| `large-file` / `binary-file` | WARN | extra file over ~400 KiB, or contains a NUL | v0.4 |
| `empty-fence` | INFO | fenced block with nothing inside | v0.4 |
| `unscoped-bash` | WARN | `allowed-tools` grants bare `Bash` | v0.4 |
| `wildcard-tool` | WARN | `allowed-tools` contains `(*)` | v0.4 |
| `sudo-command` | WARN | `sudo rm` / `dd` / `mkfs` | v0.4 |
| `force-push` | WARN | `git push --force` | v0.4 |
| `disk-wipe` | ERROR | `mkfs`, `dd if=/dev/zero`, `rm -rf ~` | v0.4 |
| `env-dump` | WARN | `printenv` / `cat .env` | v0.4 |
| `insecure-tls` | WARN | `curl -k`, `verify=False`, `NODE_TLS_REJECT_UNAUTHORIZED=0` | v0.4 |
| `reverse-shell` | ERROR | `nc -e`, `/dev/tcp`, `pty.spawn` | v0.4 |
| `unpinned-install` | INFO | `pip install pkg` / `docker pull :latest` with no pin | v0.4 |
| `bundled-secret-file` | WARN | `.env`, `id_rsa`, `credentials.json`, `*.pem` in the skill | v0.4 |
| `dead-skill` | WARN | `user-invocable: false` AND `disable-model-invocation: true` | v0.4 |
| `fork-no-agent` | INFO | `context: fork` with no `agent:` | v0.4 |
| `placeholder-text` | INFO | `YOUR_API_KEY`, `lorem ipsum`, `replace-me` | v0.4 |
| `no-safety-section` | INFO | `scripts/` present but no Safety/Caution heading | v0.4 |
| `computer-unscoped` | WARN | computer use / `computer_toolset` paired with unscoped Bash | v0.5 |
| `beta-header-stale` | INFO | `skills-2025-10-02` treated as still required — Agent Skills are out of beta | v0.5 |
| `plugin-colon-name` | WARN | `name` contains a colon; plugin namespace is `/plugin:name` at invoke time | v0.5 |

\* `name-mismatch` is a warning on `--profile claude-code` and an error on `spec` / `claude-ai`.

v0.4 also scans GitLab PATs (`glpat-`), JWTs, SendGrid keys, and Discord webhooks
as `secret-leak`.

Current model ids — Opus 5 (`claude-opus-5`), Opus 4.8 (`claude-opus-4-8`),
Sonnet 5 (`claude-sonnet-5`), Sonnet 4.6 (`claude-sonnet-4-6`),
Haiku 4.5 (`claude-haiku-4-5`), Fable 5 (`claude-fable-5`),
Mythos 5 (`claude-mythos-5`) — are not flagged. Override leftovers with
`--allow-model`. `--fix` rewrites Claude 3.x ids to `claude-sonnet-5`.

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
      - uses: gesh75/claude-skill-lint@v0.5.0
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
- run: python3 skill_lint.py skills/netops --quiet
```

## NetOps pack

22 production skills for SD-WAN, SASE, EVPN Clos, CAB cadence, NetBox, hybrid
interconnect, and MCP safety live in [`skills/netops/`](skills/netops). Each file
has a do-not-use boundary, numbered steps, and a verify loop. Copy one into
`~/.claude/skills/<name>/SKILL.md` or mount the repo so Claude Code discovers
`.claude/skills` at the root.

```bash
cp -R skills/netops/netops-change-guard ~/.claude/skills/
```

## Docs

- Project page: [gesh75.github.io/claude-skill-lint](https://gesh75.github.io/claude-skill-lint/)
- GESH Lab hub: [gesh75.github.io](https://gesh75.github.io/)
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- NetOps pack: [skills/README.md](skills/README.md)

## License

MIT — see [LICENSE](LICENSE).
