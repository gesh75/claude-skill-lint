#!/usr/bin/env python3
"""claude-skill-lint v0.3 — audit a Claude Code / Agent Skills directory.

Zero-dependency linter for ~/.claude/skills (or any directory of skills).

A skill is exactly one of two shapes — a top-level ``<name>.md`` or a
``<dir>/SKILL.md``. Everything else (references/, scripts/, assets/) is
supporting material and is not linted as a skill.

Usage:
    skill_lint.py [PATH] [--json] [--sarif FILE] [--max-desc N] [--max-body N]
                  [--quiet] [--profile claude-code|spec|claude-ai]
                  [--allow-model ID] [--fail-on-warn] [--fix] [--version]

Exit code is non-zero if any ERROR-level findings exist (or WARN when
``--fail-on-warn`` is set).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

__version__ = "0.3.0"

DEFAULT_MAX_DESC = 350
DEFAULT_MAX_BODY = 400
SPEC_MAX_DESC = 1024
SPEC_MAX_NAME = 64
SPEC_MAX_COMPAT = 500
SPEC_MAX_TOKENS = 5000

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".tox",
    "dist", "build", ".hg", ".svn", ".idea", ".vscode",
}

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
CC_BOOL_FIELDS = ("user-invocable", "disable-model-invocation", "background")
CC_EFFORT = {"low", "medium", "high", "xhigh", "max"}
CC_CONTEXT = {"fork"}
CC_MODEL_ALIASES = {"inherit", "haiku", "sonnet", "opus", "best"}

NAME_RE = re.compile(r"^(?!-)(?!.*--)[0-9a-z]+(?:-[0-9a-z]+)*$")
TRIGGER_RE = re.compile(
    r"\b(use when|when the user|when you(?:'re| are)|triggers on|reach for this|invoke when)\b",
    re.I,
)
INJECT_RE = re.compile(
    r"\b((ignore|disregard|forget)\s+(all\s+)?(previous|prior|above|your)\s+(instructions|prompts|rules)"
    r"|you are now (?:dan|jailbroken)|jailbreak this|developer mode override)\b",
    re.I,
)
SECRET_RES = [
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"), "Anthropic API key"),
    (re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}"), "OpenAI project key"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "OpenAI API key"),
    (re.compile(r"xai-[A-Za-z0-9]{16,}"), "xAI API key"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "GitHub PAT"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "GitHub PAT"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"npm_[A-Za-z0-9]{20,}"), "npm token"),
    (re.compile(r"sk_live_[A-Za-z0-9]{16,}"), "Stripe live key"),
    (re.compile(r"hf_[A-Za-z0-9]{20,}"), "Hugging Face token"),
    (re.compile(r"AIza[0-9A-Za-z_-]{20,}"), "Google API key"),
]
DANGEROUS_RES = [
    (re.compile(r"curl[^\n]*\|\s*(?:sudo\s+)?(?:ba)?sh", re.I), "curl piped to a shell"),
    (re.compile(r"wget[^\n]*\|\s*(?:sudo\s+)?(?:ba)?sh", re.I), "wget piped to a shell"),
    (re.compile(r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/(?:\s|$)"), "rm -rf /"),
    (re.compile(r"\beval\s*\("), "eval("),
    (re.compile(r"chmod\s+777"), "chmod 777"),
    (re.compile(r"iex\s*\(\s*.{0,80}downloadstring", re.I), "PowerShell IEX download"),
    (re.compile(r"pip[^\n]*\|\s*python", re.I), "pip piped to python"),
    (re.compile(r"base64\s+-d[^\n]*\|\s*(?:ba)?sh", re.I), "base64 piped to a shell"),
]
MD_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
BARE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])((?:scripts|references|reference|assets|rules)/[A-Za-z0-9_./-]+\.[A-Za-z0-9]+)"
)
PLACEHOLDER_RE = re.compile(r"(?:your|example|dummy|placeholder|xxx|\.\.\.|…|<.*>)", re.I)

ERROR, WARN, INFO = "ERROR", "WARN", "INFO"

FIX_FOR = {
    "bom-present": "strip-bom",
    "crlf-newlines": "lf-only",
    "no-frontmatter": "add-frontmatter",
    "unclosed-frontmatter": "add-frontmatter",
    "no-name": "set-name",
    "name-mismatch": "match-name",
    "name-format": "kebab-name",
    "reserved-name": "strip-reserved",
    "xml-in-frontmatter": "strip-angles",
    "no-description": "add-description",
    "short-description": "expand-desc",
    "vague-description": "add-when",
    "description-too-long": "trim-desc",
    "long-description": "trim-desc-soft",
    "empty-body": "stub-body",
    "no-heading": "stub-body",
    "h1-mismatch": "sync-h1",
    "windows-path": "forward-slashes",
    "stale-model-id": "refresh-model",
    "invalid-boolean": "coerce-bool",
}


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


def _kebab(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.U).strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:64]


def find_skill_files(root: str) -> list[str]:
    skills: list[str] = []
    skip = {"README.md", "CONTRIBUTING.md", "LICENSE.md", "SECURITY.md"}
    for entry in sorted(os.listdir(root)):
        full = os.path.join(root, entry)
        if os.path.isfile(full) and entry.endswith(".md") and entry not in skip:
            skills.append(full)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        if dirpath == root:
            continue
        for name in filenames:
            if name == "SKILL.md" or name.lower() == "skill.md":
                skills.append(os.path.join(dirpath, name))
                break
    return sorted(skills)


def parse_frontmatter(text: str) -> tuple[dict | None, int, dict[str, int], str | None, bool, dict]:
    """Return (mapping, body_line_count, field_lines, error, bom, extras)."""
    extras: dict = {"dups": [], "crlf": "\r\n" in text or ("\r" in text and "\n" not in text)}
    bom = text.startswith("\ufeff")
    if bom:
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.startswith("---"):
        return None, text.count("\n") + 1, {}, None, bom, extras
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, len(lines), {}, "unclosed YAML frontmatter — missing closing ---", bom, extras

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
        if key in fm:
            extras["dups"].append((key, i + 1))
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
        if val in ("true", "yes", "on"):
            fm[key] = True
        elif val in ("false", "no", "off"):
            fm[key] = False
        else:
            fm[key] = val
        i += 1
    body_lines = len(lines) - (end + 1)
    return fm, body_lines, field_lines, None, bom, extras


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
    for dirpath, dirnames, fns in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in fns:
            full = os.path.join(dirpath, fn)
            rel = _norm(os.path.relpath(full, base))
            known.add(rel)
    return known


def _as_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


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

    fm, body_lines, field_lines, parse_err, bom, extras = parse_frontmatter(raw)
    if bom:
        findings.append(Finding(label, INFO, "bom-present",
                                "UTF-8 BOM at byte 0 — would have been reported as no-frontmatter in v0.1", 1))
    if extras.get("crlf"):
        findings.append(Finding(label, INFO, "crlf-newlines", "file uses CRLF line endings", 1))

    base = os.path.basename(path)
    if base.lower() == "skill.md" and base != "SKILL.md":
        findings.append(Finding(label, WARN, "filename-casing",
                                f"file is '{base}'; clients that match exactly will not find SKILL.md", 1))

    if fm is None:
        code = "unclosed-frontmatter" if parse_err else "no-frontmatter"
        findings.append(Finding(label, ERROR, code,
                                parse_err or "missing YAML frontmatter (--- block)", 1))
        return findings

    for key, line in extras.get("dups") or []:
        findings.append(Finding(label, WARN, "duplicate-key",
                                f"frontmatter key '{key}' is declared more than once — last write wins", line))

    name = _as_str(fm.get("name", "") or "").strip()
    desc = _as_str(fm.get("description", "") or "").strip()
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

    compat = _as_str(fm.get("compatibility", "") or "")
    if "compatibility" in fm and compat and len(compat) > SPEC_MAX_COMPAT:
        findings.append(Finding(label, ERROR, "compatibility-too-long",
                                f"compatibility is {len(compat)} chars (must be 1–{SPEC_MAX_COMPAT})",
                                field_lines.get("compatibility")))

    tools = fm.get("allowed-tools", "")
    if isinstance(tools, list):
        findings.append(Finding(label, WARN, "allowed-tools-format",
                                "allowed-tools is a YAML list — spec wants a space-separated string",
                                field_lines.get("allowed-tools")))
    else:
        tools_s = _as_str(tools or "")
        if tools_s and ("," in tools_s and "(" not in tools_s):
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

    for key in CC_BOOL_FIELDS:
        if key not in fm:
            continue
        val = fm[key]
        if not isinstance(val, bool):
            findings.append(Finding(label, WARN, "invalid-boolean",
                                    f"'{key}' must be true or false, got {val!r}",
                                    field_lines.get(key)))

    effort = _as_str(fm.get("effort", "") or "").strip()
    if effort and effort not in CC_EFFORT:
        findings.append(Finding(label, WARN, "invalid-enum",
                                f"effort '{effort}' is not one of low, medium, high, xhigh, max",
                                field_lines.get("effort")))
    context = _as_str(fm.get("context", "") or "").strip()
    if context and context not in CC_CONTEXT:
        findings.append(Finding(label, WARN, "invalid-enum",
                                f"context '{context}' is not 'fork' (the only documented value)",
                                field_lines.get("context")))
    model = _as_str(fm.get("model", "") or "").strip()
    if model and model not in CC_MODEL_ALIASES and not re.match(r"^claude-[\w.-]+$", model):
        findings.append(Finding(label, WARN, "invalid-enum",
                                f"model '{model}' is not inherit/haiku/sonnet/opus or a claude-* id",
                                field_lines.get("model")))
    hooks = fm.get("hooks")
    if hooks not in (None, "") and not isinstance(hooks, dict):
        findings.append(Finding(label, WARN, "hooks-format",
                                "hooks must be a YAML mapping of lifecycle events, not a scalar or list",
                                field_lines.get("hooks")))

    body_start = raw.replace("\r\n", "\n").find("\n---\n", 3)
    body = raw.replace("\r\n", "\n")[body_start + 5:] if body_start != -1 else ""
    if not body.strip():
        findings.append(Finding(label, WARN, "empty-body",
                                "SKILL.md has no instructions after the frontmatter"))
    else:
        hm = re.search(r"^#{1,6}\s+(.+)$", body, re.M)
        if not hm:
            findings.append(Finding(label, INFO, "no-heading",
                                    "instruction body has no Markdown heading"))
        elif name:
            hk = _kebab(hm.group(1))
            if hk and hk != name and not hk.startswith(name) and not name.startswith(hk):
                findings.append(Finding(label, INFO, "h1-mismatch",
                                        f"heading '{hm.group(1).strip()}' does not match name '{name}'"))

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
            link = m.group(1).split("#")[0].strip()
            while link.startswith("./"):
                link = link[2:]
            if link.startswith(("http://", "https://", "/", "mailto:")):
                continue
            if via == "md" and not ("/" in link or link.endswith((".md", ".py", ".sh", ".js", ".ts", ".json"))):
                continue
            if link in seen_links:
                continue
            seen_links.add(link)
            segs = link.replace("\\", "/").split("/")
            if ".." in segs:
                findings.append(Finding(label, ERROR, "path-escape",
                                        f"path leaves the skill directory: {link}",
                                        _line_of(raw, m.start())))
                continue
            if link not in known and os.path.normpath(link) not in known:
                findings.append(Finding(label, ERROR, "dead-reference",
                                        f"link points to a missing file: {link}",
                                        _line_of(raw, m.start())))
            if link.count("/") > 1:
                findings.append(Finding(label, WARN, "reference-too-deep",
                                        f"reference '{link}' is more than one directory deep",
                                        _line_of(raw, m.start())))

    for rel in known:
        leaf = os.path.basename(rel)
        if rel.startswith(("references/", "reference/")):
            if leaf not in raw and rel not in raw:
                findings.append(Finding(label, WARN, "unreferenced-file",
                                        f"{rel} is never mentioned — progressive disclosure will never load it"))
        elif rel.startswith("scripts/"):
            if leaf not in raw and rel not in raw:
                findings.append(Finding(label, WARN, "unreferenced-script",
                                        f"{rel} is never mentioned — the agent will not know to run it"))

    license_v = _as_str(fm.get("license", "") or "").strip()
    if license_v and (
        "/" in license_v or "\\" in license_v
        or re.search(r"\.(md|txt|rst)$", license_v, re.I)
        or re.match(r"^(LICENSE|LICENCE|COPYING)(\.|$)", license_v, re.I)
    ):
        if license_v not in known and os.path.basename(license_v) not in {os.path.basename(k) for k in known}:
            findings.append(Finding(label, WARN, "license-missing",
                                    f"license points at '{license_v}' but that file is not in the skill",
                                    field_lines.get("license")))

    for rx in stale_res:
        m = rx.search(raw)
        if m:
            findings.append(Finding(label, WARN, "stale-model-id",
                                    f"possible outdated model id: '{m.group(0)}'",
                                    _line_of(raw, m.start())))
            break

    for rx, what in SECRET_RES:
        m = rx.search(raw)
        if not m or PLACEHOLDER_RE.search(m.group(0)):
            continue
        if what == "OpenAI API key" and m.group(0).startswith(("sk-ant-", "sk-proj-")):
            continue
        findings.append(Finding(label, ERROR, "secret-leak",
                                f"possible {what} committed in the skill",
                                _line_of(raw, m.start())))

    for rx, what in DANGEROUS_RES:
        m = rx.search(raw)
        if m:
            findings.append(Finding(label, WARN, "dangerous-command",
                                    f"skill instructs {what}",
                                    _line_of(raw, m.start())))

    inj = INJECT_RE.search(body)
    if inj:
        findings.append(Finding(label, WARN, "prompt-injection",
                                "body contains prompt-injection phrasing (ignore previous instructions / jailbreak)",
                                _line_of(raw, raw.find(inj.group(0)))))

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


def _set_field(text: str, key: str, value: str) -> str:
    fm, _bl, field_lines, err, _bom, _ex = parse_frontmatter(text)
    if fm is None:
        return f"---\n{key}: {value}\n---\n{text}"
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    line_no = field_lines.get(key)
    rendered = f"{key}: {value}"
    if line_no:
        lines[line_no - 1] = rendered
        return "\n".join(lines)
    for i, line in enumerate(lines):
        if i > 0 and line.strip() == "---":
            lines.insert(i, rendered)
            return "\n".join(lines)
    return text


def apply_fix(text: str, fix_id: str, path: str) -> str:
    expected = _kebab(expected_name(path) or "skill")
    fm, _bl, _fl, _err, _bom, _ex = parse_frontmatter(text)
    name = _as_str((fm or {}).get("name", ""))
    desc = _as_str((fm or {}).get("description", ""))
    if fix_id == "strip-bom":
        return text[1:] if text.startswith("\ufeff") else text
    if fix_id == "lf-only":
        return text.replace("\r\n", "\n").replace("\r", "\n")
    if fix_id == "add-frontmatter":
        if fm is not None:
            return text
        return (
            f"---\nname: {expected}\ndescription: >-\n"
            f"  Describe what this skill does and when to use it.\n"
            f"  Use when the user asks about {expected.replace('-', ' ')}.\n---\n\n"
            f"# {expected}\n\nWrite the procedure the agent should follow.\n"
        )
    if fix_id in ("set-name", "match-name"):
        return _set_field(text, "name", expected)
    if fix_id == "kebab-name":
        return _set_field(text, "name", _kebab(name or expected))
    if fix_id == "strip-reserved":
        return _set_field(text, "name", _kebab(re.sub(r"anthropic|claude", "", name, flags=re.I)))
    if fix_id == "strip-angles":
        next_t = text
        if "<" in name or ">" in name:
            next_t = _set_field(next_t, "name", name.replace("<", "").replace(">", ""))
        if "<" in desc or ">" in desc:
            next_t = _set_field(next_t, "description", re.sub(r"<[^>]*>", "", desc).replace("<", "").replace(">", ""))
        return next_t
    if fix_id == "add-description":
        return _set_field(text, "description",
                          f"Performs {expected.replace('-', ' ')}. Use when the user asks to {expected.replace('-', ' ')}.")
    if fix_id == "expand-desc":
        return _set_field(text, "description",
                          f"{desc or expected.replace('-', ' ')}. Use when the user asks to {expected.replace('-', ' ')}."[:350])
    if fix_id == "add-when":
        if re.search(r"\buse when\b", desc, re.I):
            return text
        return _set_field(text, "description", f"{desc.rstrip()} Use when the user asks to {expected.replace('-', ' ')}.")
    if fix_id == "trim-desc":
        return _set_field(text, "description", desc[:SPEC_MAX_DESC])
    if fix_id == "trim-desc-soft":
        cut = desc[:350]
        return _set_field(text, "description", re.sub(r"\s+\S*$", "", cut) or cut)
    if fix_id == "stub-body":
        if body_has := (fm is not None):
            start = text.replace("\r\n", "\n").find("\n---\n", 3)
            body = text[start + 5:] if start != -1 else ""
            if body.strip() and re.search(r"^#{1,6}\s", body, re.M):
                return text
            stub = f"\n\n# {name or expected}\n\n1. Restate the goal in one line.\n2. Follow the steps for this skill.\n3. Return the artifact the user asked for.\n"
            if not body.strip():
                return text.rstrip() + stub
            return text.rstrip() + f"\n\n# {name or expected}\n"
        return text
    if fix_id == "sync-h1":
        return re.sub(r"^#{1,6}\s+.+$", f"# {(name or expected).replace('-', ' ')}", text, count=1, flags=re.M)
    if fix_id == "coerce-bool":
        next_t = text
        for key in CC_BOOL_FIELDS:
            if fm and key in fm and not isinstance(fm[key], bool):
                next_t = _set_field(next_t, key, "true")
        return next_t
    if fix_id == "forward-slashes":
        return re.sub(r"((?:scripts|references|reference|assets|rules)\\[A-Za-z0-9_\\.-]+)",
                      lambda m: m.group(0).replace("\\", "/"), text)
    if fix_id == "refresh-model":
        t = re.sub(r"claude-3(?:-[\w.]+)*", "claude-sonnet-4-6", text, flags=re.I)
        t = re.sub(r"claude-opus-4-[0-7]\b", "claude-opus-4-8", t, flags=re.I)
        t = re.sub(r"claude-sonnet-4-[0-5]\b", "claude-sonnet-4-6", t, flags=re.I)
        t = re.sub(r"claude-haiku-4-[0-4]\b", "claude-haiku-4-5", t, flags=re.I)
        t = re.sub(r"claude-4-opus", "claude-opus-4-8", t, flags=re.I)
        t = re.sub(r"claude-4-sonnet", "claude-sonnet-4-6", t, flags=re.I)
        t = re.sub(r"claude-4-haiku", "claude-haiku-4-5", t, flags=re.I)
        return t
    return text


def to_sarif(findings: list[Finding], root: str) -> dict:
    level_map = {ERROR: "error", WARN: "warning", INFO: "note"}
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "claude-skill-lint",
                    "version": __version__,
                    "informationUri": "https://github.com/gesh75/claude-skill-lint",
                }
            },
            "results": [{
                "ruleId": f.code,
                "level": level_map.get(f.level, "note"),
                "message": {"text": f.message},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": f.skill},
                        "region": {"startLine": f.line or 1},
                    }
                }],
            } for f in findings],
        }],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit a Claude Code / Agent Skills directory.")
    ap.add_argument("path", nargs="?", default=os.path.expanduser("~/.claude/skills"),
                    help="skills directory (default: ~/.claude/skills)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--sarif", metavar="FILE", help="write SARIF 2.1.0 to FILE")
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
    ap.add_argument("--fix", action="store_true",
                    help="apply safe auto-fixes in place")
    ap.add_argument("--version", action="version", version=f"claude-skill-lint {__version__}")
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

    if args.fix:
        for s in skills:
            found = lint_skill(s, root, args.max_desc, args.max_body, stale_res, args.profile, names)
            ids = []
            for f in found:
                fid = FIX_FOR.get(f.code)
                if fid and fid not in ids:
                    ids.append(fid)
            if not ids:
                continue
            original = open(s, encoding="utf-8").read()
            next_t = original
            for fid in ids:
                next_t = apply_fix(next_t, fid, s)
            if next_t != original:
                open(s, "w", encoding="utf-8", newline="\n").write(next_t)

        names = []
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

    if args.sarif:
        with open(args.sarif, "w", encoding="utf-8") as fh:
            json.dump(to_sarif(all_findings, root), fh, indent=2)
            fh.write("\n")

    if args.json:
        print(json.dumps({
            "root": root,
            "profile": args.profile,
            "version": __version__,
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
