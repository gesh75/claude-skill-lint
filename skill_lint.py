#!/usr/bin/env python3
"""claude-skill-lint v0.2 — audit a Claude Code / Agent Skills directory.

Zero-dependency linter for ~/.claude/skills (or any directory of skills).

A skill is exactly one of two shapes — a top-level ``<name>.md`` or a
``<dir>/SKILL.md``. Everything else (references/, scripts/, assets/) is
supporting material and is not linted as a skill.

Usage:
    skill_lint.py [PATH] [--json] [--max-desc N] [--max-body N] [--quiet]
                  [--profile claude-code|spec|claude-ai]
                  [--allow-model ID] [--fail-on-warn]

Exit code is non-zero if any ERROR-level findings exist (or WARN when
``--fail-on-warn`` is set).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

DEFAULT_MAX_DESC = 350
DEFAULT_MAX_BODY = 400
SPEC_MAX_DESC = 1024
SPEC_MAX_NAME = 64
SPEC_MAX_COMPAT = 500
SPEC_MAX_TOKENS = 5000

STALE_MODEL_PATTERNS = [
    r"claude-3[\w.-]*",
    r"claude-2[\w.-]*",
    r"claude-instant[\w.-]*",
    r"claude-opus-4-[0-7]\b[\w.-]*",
    r"claude-sonnet-4-[0-5]\b[\w.-]*",
    r"claude-haiku-4-[0-4]\b[\w.-]*",
    r"claude-4-(?:opus|sonnet|haiku)[\w.-]*",
]

SPEC_FIELDS = {
    "name", "description", "license", "allowed-tools", "metadata", "compatibility",
}
CC_FIELDS = {
    "when_to_use", "argument-hint", "arguments", "disable-model-invocation",
    "user-invocable", "disallowed-tools", "model", "effort", "context",
    "agent", "background", "hooks", "paths", "shell",
}

NAME_RE = re.compile(r"^(?!-)(?!.*--)[0-9a-z]+(?:-[0-9a-z]+)*$")
TRIGGER_RE = re.compile(
    r"\b(use when|when the user|when you(?:'re| are)|triggers on|reach for this|invoke when)\b",
    re.I,
)
SECRET_RES = [
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"), "Anthropic API key"),
    (re.compile(r"xai-[A-Za-z0-9]{16,}"), "xAI API key"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "GitHub PAT"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "GitHub PAT"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
]
DANGEROUS_RES = [
    (re.compile(r"curl[^\n]*\|\s*(?:sudo\s+)?(?:ba)?sh", re.I), "curl piped to a shell"),
    (re.compile(r"wget[^\n]*\|\s*(?:sudo\s+)?(?:ba)?sh", re.I), "wget piped to a shell"),
    (re.compile(r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/(?:\s|$)"), "rm -rf /"),
    (re.compile(r"\beval\s*\("), "eval("),
    (re.compile(r"chmod\s+777"), "chmod 777"),
]
MD_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
BARE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])((?:scripts|references|reference|assets|rules)/[A-Za-z0-9_./-]+\.[A-Za-z0-9]+)"
)
PLACEHOLDER_RE = re.compile(r"(?:your|example|dummy|placeholder|xxx|\.\.\.|…|<.*>)", re.I)

ERROR, WARN, INFO = "ERROR", "WARN", "INFO"


class Finding:
    __slots__ = ("skill", "level", "code", "message", "line")

    def __init__(self, skill: str, level: str, code: str, message: str, line: int | None = None):
        self.skill = skill
        self.level = level
        self.code = code
        self.message = message
        self.line = line

    def as_dict(self) -> dict:
        d = {"skill": self.skill, "level": self.level, "code": self.code, "message": self.message}
        if self.line is not None:
            d["line"] = self.line
        return d


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def find_skill_files(root: str) -> list[str]:
    skills: list[str] = []
    skip = {"README.md", "CONTRIBUTING.md", "LICENSE.md", "SECURITY.md"}
    for entry in sorted(os.listdir(root)):
        full = os.path.join(root, entry)
        if os.path.isfile(full) and entry.endswith(".md") and entry not in skip:
            skills.append(full)
    for dirpath, _dirnames, filenames in os.walk(root):
        if dirpath == root:
            continue
        for name in filenames:
            if name == "SKILL.md" or name.lower() == "skill.md":
                skills.append(os.path.join(dirpath, name))
                break
    return sorted(skills)


def parse_frontmatter(text: str) -> tuple[dict | None, int, dict[str, int], str | None, bool]:
    """Return (mapping, body_line_count, field_lines, error, bom)."""
    bom = text.startswith("\ufeff")
    if bom:
        text = text[1:]
    if not text.startswith("---"):
        return None, text.count("\n") + 1, {}, None, bom
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, len(lines), {}, "unclosed YAML frontmatter — missing closing ---", bom

    fm: dict = {}
    field_lines: dict[str, int] = {}
    key_re = re.compile(r"^(\s*)([A-Za-z0-9_-]+):\s?(.*)$")
    i = 1
    while i < end:
        line = lines[i]
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue
        m = key_re.match(line)
        if not m or (m.group(1) and len(m.group(1)) > 0):
            i += 1
            continue
        key, val = m.group(2), m.group(3).split("#")[0].strip()
        field_lines[key] = i + 1
        if val in (">-", ">", "|", "|-"):
            block: list[str] = []
            i += 1
            while i < end and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            fm[key] = " ".join(b for b in block if b).strip()
            continue
        if val == "":
            nested: dict[str, str] = {}
            i += 1
            while i < end and (not lines[i].strip() or lines[i].startswith((" ", "\t"))):
                if not lines[i].strip() or lines[i].strip().startswith("#"):
                    i += 1
                    continue
                nm = key_re.match(lines[i])
                if nm:
                    nested[nm.group(2)] = nm.group(3).strip().strip("\"'")
                i += 1
            fm[key] = nested if nested else ""
            continue
        if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
            val = val[1:-1]
        fm[key] = val
        i += 1
    body_lines = len(lines) - (end + 1)
    return fm, body_lines, field_lines, None, bom


def skill_label(path: str, root: str) -> str:
    rel = _norm(os.path.relpath(path, root))
    if rel.lower().endswith("/skill.md"):
        return rel[: rel.rfind("/")]
    return rel[:-3] if rel.endswith(".md") else rel


def expected_name(path: str) -> str:
    norm = _norm(path)
    if norm.lower().endswith("/skill.md"):
        return norm.rsplit("/", 2)[-2]
    base = norm.rsplit("/", 1)[-1]
    return base[:-3] if base.lower().endswith(".md") else base


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def collect_files(skill_path: str) -> set[str]:
    base = os.path.dirname(skill_path)
    known: set[str] = set()
    if not os.path.isdir(base):
        return known
    for dirpath, _dns, fns in os.walk(base):
        for fn in fns:
            full = os.path.join(dirpath, fn)
            rel = _norm(os.path.relpath(full, base))
            known.add(rel)
    return known


def lint_skill(
    path: str,
    root: str,
    max_desc: int,
    max_body: int,
    stale_res: list[re.Pattern],
    profile: str,
    sibling_names: list[str] | None = None,
) -> list[Finding]:
    label = skill_label(path, root)
    findings: list[Finding] = []
    try:
        raw = open(path, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError) as e:  # pragma: no cover
        return [Finding(label, ERROR, "read", f"cannot read file: {e}")]

    fm, body_lines, field_lines, parse_err, bom = parse_frontmatter(raw)
    if bom:
        findings.append(Finding(label, INFO, "bom-present",
                                "UTF-8 BOM at byte 0 — would have been reported as no-frontmatter in v0.1", 1))

    base = os.path.basename(path)
    if base.lower() == "skill.md" and base != "SKILL.md":
        findings.append(Finding(label, WARN, "filename-casing",
                                f"file is '{base}'; clients that match exactly will not find SKILL.md", 1))

    if fm is None:
        code = "unclosed-frontmatter" if parse_err else "no-frontmatter"
        findings.append(Finding(label, ERROR, code,
                                parse_err or "missing YAML frontmatter (--- block)", 1))
        return findings

    name = str(fm.get("name", "") or "").strip()
    desc = str(fm.get("description", "") or "").strip()
    expected = expected_name(path)

    if not name:
        findings.append(Finding(label, ERROR, "no-name",
                                "frontmatter has no `name:` (won't register)", field_lines.get("name")))
    else:
        if len(name) > SPEC_MAX_NAME or not NAME_RE.match(name):
            findings.append(Finding(label, ERROR, "name-format",
                                    f"name '{name}' is not 1–{SPEC_MAX_NAME} lowercase letters/digits/hyphens",
                                    field_lines.get("name")))
        if name != expected:
            level = WARN if profile == "claude-code" else ERROR
            findings.append(Finding(label, level, "name-mismatch",
                                    f"name '{name}' != expected '{expected}'", field_lines.get("name")))
        if profile == "claude-ai" and re.search(r"anthropic|claude", name, re.I):
            findings.append(Finding(label, ERROR, "reserved-name",
                                    "Claude.ai rejects names containing 'anthropic' or 'claude'",
                                    field_lines.get("name")))
        if "<" in name or ">" in name:
            findings.append(Finding(label, ERROR, "xml-in-frontmatter",
                                    "name contains < or > (forbidden XML / tool-call markup)",
                                    field_lines.get("name")))

    if not desc:
        findings.append(Finding(label, ERROR, "no-description",
                                "frontmatter has no `description:`", field_lines.get("description")))
    else:
        if len(desc) > SPEC_MAX_DESC:
            findings.append(Finding(label, ERROR, "description-too-long",
                                    f"description is {len(desc)} chars — spec hard limit is {SPEC_MAX_DESC}",
                                    field_lines.get("description")))
        elif len(desc) > max_desc:
            findings.append(Finding(label, WARN, "long-description",
                                    f"description is {len(desc)} chars (> {max_desc}); "
                                    "it's loaded every turn — tighten it",
                                    field_lines.get("description")))
        if len(desc) < 30:
            findings.append(Finding(label, INFO, "short-description",
                                    f"description is only {len(desc)} chars; may not trigger reliably",
                                    field_lines.get("description")))
        elif not TRIGGER_RE.search(desc):
            findings.append(Finding(label, WARN, "vague-description",
                                    "description never says when to use this skill",
                                    field_lines.get("description")))
        if "<" in desc or ">" in desc:
            level = ERROR if profile == "claude-ai" else WARN
            findings.append(Finding(label, level, "xml-in-frontmatter",
                                    "description contains < or > — Claude.ai rejects XML tags",
                                    field_lines.get("description")))

    compat = str(fm.get("compatibility", "") or "")
    if "compatibility" in fm and compat and len(compat) > SPEC_MAX_COMPAT:
        findings.append(Finding(label, ERROR, "compatibility-too-long",
                                f"compatibility is {len(compat)} chars (must be 1–{SPEC_MAX_COMPAT})",
                                field_lines.get("compatibility")))

    tools = str(fm.get("allowed-tools", "") or "")
    if tools and ("," in tools and "(" not in tools):
        findings.append(Finding(label, WARN, "allowed-tools-format",
                                "allowed-tools looks comma-separated — spec wants space-separated",
                                field_lines.get("allowed-tools")))

    meta = fm.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        findings.append(Finding(label, WARN, "metadata-format",
                                "metadata must be a mapping of string keys to string values",
                                field_lines.get("metadata")))

    for key in fm:
        if key in SPEC_FIELDS:
            continue
        if key in CC_FIELDS:
            if profile == "claude-code":
                findings.append(Finding(label, INFO, "cc-extension",
                                        f"frontmatter field '{key}' is a Claude Code extension",
                                        field_lines.get(key)))
            else:
                findings.append(Finding(label, ERROR, "cc-extension",
                                        f"frontmatter field '{key}' is not in the Agent Skills spec",
                                        field_lines.get(key)))
        else:
            level = WARN if profile == "claude-code" else ERROR
            findings.append(Finding(label, level, "unknown-field",
                                    f"unknown frontmatter field '{key}'", field_lines.get(key)))

    body_start = raw.find("\n---\n", 3)
    body = raw[body_start + 5:] if body_start != -1 else ""
    if not body.strip():
        findings.append(Finding(label, WARN, "empty-body",
                                "SKILL.md has no instructions after the frontmatter"))

    if body_lines > max_body:
        findings.append(Finding(label, WARN, "bloated-body",
                                f"body is {body_lines} lines (> {max_body}); "
                                "move detail to references/*.md (progressive disclosure)"))

    tokens = (len(body) + 3) // 4
    if tokens > SPEC_MAX_TOKENS:
        findings.append(Finding(label, WARN, "body-token-budget",
                                f"body is ~{tokens} tokens (spec recommends < {SPEC_MAX_TOKENS})"))

    known = collect_files(path)
    seen_links: set[str] = set()
    for rx, via in ((MD_LINK_RE, "md"), (BARE_PATH_RE, "bare")):
        for m in rx.finditer(raw):
            link = m.group(1).split("#")[0].strip().lstrip("./")
            if link.startswith(("http://", "https://", "/", "mailto:")):
                continue
            if via == "md" and not ("/" in link or link.endswith((".md", ".py", ".sh", ".js", ".ts", ".json"))):
                continue
            if link in seen_links:
                continue
            seen_links.add(link)
            if link not in known and os.path.normpath(link) not in known:
                findings.append(Finding(label, ERROR, "dead-reference",
                                        f"link points to a missing file: {link}",
                                        _line_of(raw, m.start())))
            if link.count("/") > 1:
                findings.append(Finding(label, WARN, "reference-too-deep",
                                        f"reference '{link}' is more than one directory deep",
                                        _line_of(raw, m.start())))

    for rel in known:
        if not rel.startswith(("references/", "reference/")):
            continue
        leaf = os.path.basename(rel)
        if leaf not in raw and rel not in raw:
            findings.append(Finding(label, WARN, "unreferenced-file",
                                    f"{rel} is never mentioned — progressive disclosure will never load it"))

    for rx in stale_res:
        m = rx.search(raw)
        if m:
            findings.append(Finding(label, WARN, "stale-model-id",
                                    f"possible outdated model id: '{m.group(0)}'",
                                    _line_of(raw, m.start())))
            break

    for rx, what in SECRET_RES:
        m = rx.search(raw)
        if m and not PLACEHOLDER_RE.search(m.group(0)):
            findings.append(Finding(label, ERROR, "secret-leak",
                                    f"possible {what} committed in the skill",
                                    _line_of(raw, m.start())))

    for rx, what in DANGEROUS_RES:
        m = rx.search(raw)
        if m:
            findings.append(Finding(label, WARN, "dangerous-command",
                                    f"skill instructs {what}",
                                    _line_of(raw, m.start())))

    if len(re.findall(r"^```", raw, re.M)) % 2 == 1:
        findings.append(Finding(label, WARN, "unclosed-fence",
                                "unclosed fenced code block"))

    if re.search(r"\b(TODO|FIXME|XXX)\b", body):
        findings.append(Finding(label, INFO, "todo-left", "unfinished marker left in the body"))

    if sibling_names and name:
        n = sibling_names.count(name)
        if n > 1:
            findings.append(Finding(label, WARN, "duplicate-name",
                                    f"name '{name}' is declared by {n} skills in this library",
                                    field_lines.get("name")))

    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit a Claude Code / Agent Skills directory.")
    ap.add_argument("path", nargs="?", default=os.path.expanduser("~/.claude/skills"),
                    help="skills directory (default: ~/.claude/skills)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--max-desc", type=int, default=DEFAULT_MAX_DESC)
    ap.add_argument("--max-body", type=int, default=DEFAULT_MAX_BODY)
    ap.add_argument("--quiet", action="store_true", help="only show ERROR/WARN")
    ap.add_argument("--profile", choices=("claude-code", "spec", "claude-ai"),
                    default="claude-code",
                    help="rule profile (default: claude-code)")
    ap.add_argument("--allow-model", action="append", default=[], metavar="ID",
                    help="do not flag this model id as stale (repeatable)")
    ap.add_argument("--fail-on-warn", action="store_true",
                    help="exit 1 on warnings as well as errors")
    args = ap.parse_args(argv)

    root = os.path.abspath(os.path.expanduser(args.path))
    if not os.path.isdir(root):
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    stale_res = [re.compile(p) for p in STALE_MODEL_PATTERNS]
    allowed = set(args.allow_model)

    skills = find_skill_files(root)
    names: list[str] = []
    for s in skills:
        try:
            text = open(s, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            names.append("")
            continue
        fm, *_rest = parse_frontmatter(text)
        names.append(str((fm or {}).get("name", "") or "").strip())

    all_findings: list[Finding] = []
    for s in skills:
        found = lint_skill(s, root, args.max_desc, args.max_body, stale_res, args.profile, names)
        if allowed:
            found = [f for f in found if not (
                f.code == "stale-model-id" and any(a in f.message for a in allowed)
            )]
        all_findings.extend(found)

    errors = sum(1 for f in all_findings if f.level == ERROR)
    warns = sum(1 for f in all_findings if f.level == WARN)
    infos = sum(1 for f in all_findings if f.level == INFO)

    if args.json:
        print(json.dumps({
            "root": root,
            "profile": args.profile,
            "skills_scanned": len(skills),
            "summary": {"errors": errors, "warnings": warns, "info": infos},
            "findings": [f.as_dict() for f in all_findings],
        }, indent=2))
    else:
        icon = {ERROR: "✗", WARN: "!", INFO: "·"}
        shown = [f for f in all_findings if not (args.quiet and f.level == INFO)]
        for f in shown:
            loc = f"L{f.line} " if f.line else ""
            print(f"  {icon[f.level]} [{f.level:5}] {f.skill}: {loc}{f.message}  ({f.code})")
        clean = len(skills) - len({f.skill for f in all_findings})
        print(f"\nScanned {len(skills)} skills in {root}")
        print(f"  {clean} clean · {errors} errors · {warns} warnings · {infos} info")

    if errors:
        return 1
    if args.fail_on_warn and warns:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
