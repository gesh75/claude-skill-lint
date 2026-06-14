#!/usr/bin/env python3
"""claude-skill-lint — audit a Claude Code skills directory.

A zero-dependency linter for ~/.claude/skills (or any directory of Claude Code
skills). It checks the things that actually matter for a healthy skills library:

  * valid frontmatter (name + description)
  * name matches the file/dir
  * description length (always in context on every turn — keep it tight)
  * body size (loaded on trigger — bloated bodies should use progressive disclosure)
  * dead references (reference/*.md links that point nowhere)
  * stale model IDs (configurable list of retired Claude ids)

A "skill" is exactly one of two shapes — a top-level ``<name>.md`` or a
``<dir>/SKILL.md``. Everything else (reference/, rules/, agents/, sibling
content files) is supporting material and is not linted as a skill.

Usage:
    skill_lint.py [PATH] [--json] [--max-desc N] [--max-body N] [--quiet]

Exit code is non-zero if any ERROR-level findings exist (useful in CI).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

DEFAULT_MAX_DESC = 350          # chars — description is always in context
DEFAULT_MAX_BODY = 400          # lines — over this, use progressive disclosure

# Retired Claude model id patterns. Current ids (Opus 4.8 / Sonnet 4.6 /
# Haiku 4.5) are intentionally NOT flagged. Override with --allow-model.
STALE_MODEL_PATTERNS = [
    r"claude-3(?:-|\b)",             # claude-3*, claude-3-5-*
    r"claude-2(?:-|\b)",
    r"claude-instant",
    r"claude-opus-4-[0-7]\b",        # opus 4.0-4.7 (current is 4.8)
    r"claude-sonnet-4-[0-5]\b",      # sonnet 4.0-4.5 (current is 4.6)
    r"claude-haiku-4-[0-4]\b",       # haiku 4.0-4.4 (current is 4.5)
    r"claude-4-(?:opus|sonnet|haiku)",  # wrong ordering
]

ERROR, WARN, INFO = "ERROR", "WARN", "INFO"


class Finding:
    __slots__ = ("skill", "level", "code", "message")

    def __init__(self, skill: str, level: str, code: str, message: str):
        self.skill = skill
        self.level = level
        self.code = code
        self.message = message

    def as_dict(self) -> dict:
        return {"skill": self.skill, "level": self.level,
                "code": self.code, "message": self.message}


def find_skill_files(root: str) -> list[str]:
    """Return skill files only: top-level *.md and */SKILL.md (any depth>=2)."""
    skills: list[str] = []
    for entry in sorted(os.listdir(root)):
        full = os.path.join(root, entry)
        if os.path.isfile(full) and entry.endswith(".md") and entry not in (
            "README.md", "CONTRIBUTING.md", "LICENSE.md", "SECURITY.md",
        ):
            skills.append(full)
    for dirpath, _dirnames, filenames in os.walk(root):
        if dirpath == root:
            continue
        if "SKILL.md" in filenames:
            skills.append(os.path.join(dirpath, "SKILL.md"))
    return sorted(skills)


def parse_frontmatter(text: str) -> tuple[dict | None, int]:
    """Extract top-level scalar keys from a leading '---' frontmatter block.

    Zero-dependency: handles quoted values and block scalars (>- / |). Returns
    (mapping, body_line_count). mapping is None if there is no frontmatter.
    """
    if not text.startswith("---"):
        return None, text.count("\n") + 1
    lines = text.splitlines()
    # find closing '---'
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, len(lines)

    fm: dict[str, str] = {}
    i = 1
    key_re = re.compile(r"^([A-Za-z0-9_-]+):\s?(.*)$")
    while i < end:
        line = lines[i]
        m = key_re.match(line)
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2).strip()
        if val in (">-", ">", "|", "|-"):  # block scalar — gather indented lines
            block: list[str] = []
            i += 1
            while i < end and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            fm[key] = " ".join(b for b in block if b).strip()
            continue
        if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
            val = val[1:-1]
        fm[key] = val
        i += 1
    body_lines = len(lines) - (end + 1)
    return fm, body_lines


def skill_label(path: str, root: str) -> str:
    rel = os.path.relpath(path, root)
    return rel[:-len("/SKILL.md")] if rel.endswith("/SKILL.md") else rel[:-3]


def find_dead_refs(text: str, skill_path: str) -> list[str]:
    """Markdown links to local .md files that don't exist on disk."""
    base = os.path.dirname(skill_path)
    dead = []
    for m in re.finditer(r"\]\(([^)]+\.md)\)", text):
        link = m.group(1).split("#")[0].strip()
        if link.startswith(("http://", "https://", "/")):
            continue
        if not os.path.exists(os.path.normpath(os.path.join(base, link))):
            dead.append(link)
    return dead


def lint_skill(path: str, root: str, max_desc: int, max_body: int,
               stale_res: list[re.Pattern]) -> list[Finding]:
    label = skill_label(path, root)
    findings: list[Finding] = []
    try:
        text = open(path, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError) as e:  # pragma: no cover
        return [Finding(label, ERROR, "read", f"cannot read file: {e}")]

    fm, body_lines = parse_frontmatter(text)
    if fm is None:
        findings.append(Finding(label, ERROR, "no-frontmatter",
                                "missing YAML frontmatter (--- block)"))
        return findings

    name = fm.get("name", "").strip()
    desc = fm.get("description", "").strip()
    expected = os.path.basename(os.path.dirname(path)) if path.endswith("/SKILL.md") \
        else os.path.basename(path)[:-3]

    if not name:
        findings.append(Finding(label, ERROR, "no-name",
                                "frontmatter has no `name:` (won't register)"))
    elif name != expected:
        findings.append(Finding(label, WARN, "name-mismatch",
                                f"name '{name}' != expected '{expected}'"))

    if not desc:
        findings.append(Finding(label, ERROR, "no-description",
                                "frontmatter has no `description:`"))
    else:
        if len(desc) > max_desc:
            findings.append(Finding(label, WARN, "long-description",
                                    f"description is {len(desc)} chars (> {max_desc}); "
                                    "it's loaded every turn — tighten it"))
        if len(desc) < 30:
            findings.append(Finding(label, INFO, "short-description",
                                    f"description is only {len(desc)} chars; "
                                    "may not trigger reliably"))

    if body_lines > max_body:
        findings.append(Finding(label, WARN, "bloated-body",
                                f"body is {body_lines} lines (> {max_body}); "
                                "move detail to reference/*.md (progressive disclosure)"))

    for link in find_dead_refs(text, path):
        findings.append(Finding(label, ERROR, "dead-reference",
                                f"link points to a missing file: {link}"))

    for rx in stale_res:
        m = rx.search(text)
        if m:
            findings.append(Finding(label, WARN, "stale-model-id",
                                    f"possible outdated model id: '{m.group(0)}'"))
            break

    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit a Claude Code skills directory.")
    ap.add_argument("path", nargs="?", default=os.path.expanduser("~/.claude/skills"),
                    help="skills directory (default: ~/.claude/skills)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--max-desc", type=int, default=DEFAULT_MAX_DESC)
    ap.add_argument("--max-body", type=int, default=DEFAULT_MAX_BODY)
    ap.add_argument("--quiet", action="store_true", help="only show ERROR/WARN")
    args = ap.parse_args(argv)

    root = os.path.abspath(os.path.expanduser(args.path))
    if not os.path.isdir(root):
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    stale_res = [re.compile(p) for p in STALE_MODEL_PATTERNS]
    skills = find_skill_files(root)
    all_findings: list[Finding] = []
    for s in skills:
        all_findings.extend(lint_skill(s, root, args.max_desc, args.max_body, stale_res))

    errors = sum(1 for f in all_findings if f.level == ERROR)
    warns = sum(1 for f in all_findings if f.level == WARN)
    infos = sum(1 for f in all_findings if f.level == INFO)

    if args.json:
        print(json.dumps({
            "root": root,
            "skills_scanned": len(skills),
            "summary": {"errors": errors, "warnings": warns, "info": infos},
            "findings": [f.as_dict() for f in all_findings],
        }, indent=2))
        return 1 if errors else 0

    icon = {ERROR: "✗", WARN: "!", INFO: "·"}
    shown = [f for f in all_findings if not (args.quiet and f.level == INFO)]
    for f in shown:
        print(f"  {icon[f.level]} [{f.level:5}] {f.skill}: {f.message}  ({f.code})")
    clean = len(skills) - len({f.skill for f in all_findings})
    print(f"\nScanned {len(skills)} skills in {root}")
    print(f"  {clean} clean · {errors} errors · {warns} warnings · {infos} info")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
