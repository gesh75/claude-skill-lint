#!/usr/bin/env python3
"""claude-skill-lint v0.4 — audit a Claude Code / Agent Skills directory.

Zero-dependency linter for ~/.claude/skills (or any directory of skills).

A skill is exactly one of two shapes — a top-level ``<name>.md`` or a
``<dir>/SKILL.md``. Everything else (references/, scripts/, assets/) is
supporting material and is not linted as a skill.

Usage:
    skill_lint.py [PATH] [--json] [--sarif FILE] [--max-desc N] [--max-body N]
                  [--quiet] [--profile claude-code|spec|claude-ai]
                  [--allow-model ID] [--fail-on-warn] [--fix] [--version]
                  [--stdin] [--min-score N] [--ignore CODE] [--exclude GLOB]

Exit code is non-zero if any ERROR-level findings exist (or WARN when
``--fail-on-warn`` is set).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import sys
import tempfile

__version__ = "0.4.0"

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
    (re.compile(r"glpat-[A-Za-z0-9_-]{20,}"), "GitLab PAT"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{10,}\."), "JWT"),
    (re.compile(r"SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"), "SendGrid key"),
    (re.compile(r"discord(?:app)?\.com/api/webhooks/\d+/[\w-]+"), "Discord webhook"),
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
    extras["raw"] = "\n".join(lines[1:end])

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



VERBS = {
    "extracts", "extract", "analyzes", "analyze", "generates", "generate", "converts", "convert",
    "lints", "lint", "validates", "validate", "deploys", "deploy", "reviews", "review",
    "formats", "format", "parses", "parse", "builds", "build", "writes", "write",
    "creates", "create", "updates", "update", "fetches", "fetch", "installs", "install",
    "tests", "test", "audits", "audit", "scans", "scan", "transforms", "transform",
    "renders", "render", "compiles", "compile", "packages", "package", "publishes", "publish",
    "migrates", "migrate", "documents", "document", "designs", "design", "debugs", "debug",
    "traces", "trace", "monitors", "monitor", "configures", "configure", "fills", "fill",
    "merges", "merge", "splits", "split", "compares", "compare", "summarizes", "summarize",
    "translates", "translate", "searches", "search", "indexes", "index", "queries", "query",
    "uploads", "upload", "downloads", "download", "archives", "archive", "restores", "restore",
    "patches", "patch", "refactors", "refactor", "authenticates", "encrypts", "signs", "sign",
    "processes", "process", "handles", "handle", "guides", "guide", "orchestrates", "orchestrate",
    "detects", "detect", "repairs", "repair", "normalizes", "normalize", "redacts", "redact",
}
GENERIC_NAMES = {
    "helper", "utils", "util", "tools", "misc", "skill", "test", "tmp", "foo", "bar",
    "demo", "sample", "example", "temp", "new", "old", "stuff", "thing", "default",
}
STOP = {
    "this", "that", "with", "from", "when", "skill", "helps", "using", "based", "into",
    "your", "their", "them", "then", "than", "also", "just", "very", "more", "some",
    "about", "after", "before", "under", "over", "does", "doing", "make", "made",
}
JUNK = {".ds_store", "thumbs.db", "desktop.ini", "__macosx"}
RESERVED_COMMANDS = {
    "help", "clear", "compact", "login", "logout", "doctor", "init", "diff",
    "review", "memory", "status", "vim", "hooks", "install", "plugin", "resume",
    "config", "permissions", "mcp", "export", "rewind", "skills", "agents",
    "model", "theme", "cost", "usage", "upgrade", "feedback", "bug", "exit", "quit",
}
SECRET_FILE_RE = re.compile(
    r"(^|/)(\.env|\.env\.[^/]+|id_rsa|id_ed25519|credentials\.json|serviceAccount\.json|.*\.(pem|p12|key))$",
    re.I,
)
WEIGHT = {ERROR: 16, WARN: 6, INFO: 1}


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if abs(len(a) - len(b)) > 2:
        return 99
    m, n = len(a), len(b)
    dp = list(range(m + 1))
    for j in range(1, n + 1):
        prev = dp[0]
        dp[0] = j
        for i in range(1, m + 1):
            tmp = dp[i]
            dp[i] = prev if a[i - 1] == b[j - 1] else 1 + min(prev, dp[i], dp[i - 1])
            prev = tmp
    return dp[m]


def closest_key(key: str, known: list[str]) -> str | None:
    k = key.lower()
    best = None
    dist = 3
    for cand in known:
        d = levenshtein(k, cand.lower())
        if 0 < d < dist:
            dist = d
            best = cand
    return best


def score_of(findings: list[Finding]) -> int:
    penalty = sum(WEIGHT.get(f.level, 1) for f in findings)
    return max(0, min(100, 100 - penalty))


def _iter_extra(skill_path: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    base = os.path.dirname(skill_path)
    if not os.path.isdir(base):
        return out
    # Top-level <name>.md skills have no supporting tree. Walking the parent
    # would flag sibling skills as unexpected-root.
    if os.path.basename(skill_path).lower() != "skill.md":
        return out
    skill_rel = _norm(os.path.relpath(skill_path, base))
    for rel in sorted(collect_files(skill_path)):
        if rel == skill_rel or os.path.basename(rel).lower() == "skill.md":
            continue
        full = os.path.join(base, rel.replace("/", os.sep))
        try:
            with open(full, "rb") as fh:
                blob = fh.read(400_001)
            text = blob.decode("utf-8", "replace")
        except OSError:
            text = ""
        out.append((rel, text))
    return out


def lint_v04(
    label: str,
    source: str,
    raw_fm: str,
    body: str,
    desc: str,
    name: str,
    fm: dict,
    extra: list[tuple[str, str]],
    field_lines: dict[str, int],
    body_start_line: int,
) -> list[Finding]:
    out: list[Finding] = []
    desc_line = field_lines.get("description", 2)

    def add(level: str, code: str, message: str, line: int | None = None) -> None:
        out.append(Finding(label, level, code, message, line))

    if desc:
        fw = re.sub(r"[^a-z]", "", (desc.strip().split() or [""])[0].lower())
        verbish = fw in VERBS or fw.endswith("ing")
        if not verbish:
            add(INFO, "desc-no-verb",
                "description does not open with an action verb (Extracts, Lints, Generates…)", desc_line)
        if re.search(
            r"\b(i['’]m|i['’]ve|i\s|we['’]ll|\bwe\b|\byou['’]re|\byou['’]ll|\byour\b|\byou\b)",
            desc, re.I,
        ):
            add(INFO, "first-person-desc",
                "description uses first/second person — Anthropic wants third person ('the user')", desc_line)
        if len(desc) >= 40:
            head = re.sub(r"[^a-z0-9\s-]", " ", desc[:60].lower())
            keywords = [w for w in head.split() if len(w) >= 4 and w not in STOP]
            if len(keywords) < 2:
                add(INFO, "frontloaded-triggers",
                    "first 60 characters of the description have no concrete trigger keywords", desc_line)
        if not re.search(r"\b(do not use|don't use|not for|never use|avoid using)\b", desc, re.I):
            add(INFO, "no-boundary",
                "description has no 'do not use' / 'not for' boundary", desc_line)
        if len(desc) > 250:
            after, before = desc[250:], desc[:250]
            if re.search(r"\b(use when|when the user)\b", after, re.I) and not re.search(
                r"\b(use when|when the user)\b", before, re.I
            ):
                add(WARN, "desc-truncation",
                    "trigger language sits after char 250 — Claude's skill list truncates there", desc_line)
        ands = re.findall(r"\band\b", desc, re.I)
        if len(ands) >= 3:
            add(INFO, "broad-scope",
                f"description uses 'and' {len(ands)} times — split into micro-skills", desc_line)
        if re.match(r"this\s+skill\b", desc.strip(), re.I):
            add(INFO, "desc-this-skill",
                "description starts with 'This skill' — that burns the 60-char Codex frontload", desc_line)
        if re.search(r"\balways\s+(?:use|consider|invoke|apply|run|load)\b|\buse for every\b", desc, re.I):
            add(WARN, "always-trigger",
                "description says to always fire — that is a context tax on every turn", desc_line)

    if name and name in GENERIC_NAMES:
        add(WARN, "generic-name",
            f"name '{name}' is too generic to route on — pick the job, not 'helper'",
            field_lines.get("name", 2))
    if name and name in RESERVED_COMMANDS:
        add(WARN, "reserved-command",
            f"name '{name}' collides with a Claude Code builtin slash command",
            field_lines.get("name", 2))

    when = _as_str(fm.get("when_to_use", "") or "")
    if desc and (len(desc) + len(when) > 1536):
        add(WARN, "listing-truncation",
            f"description + when_to_use is {len(desc) + len(when)} chars — Claude Code lists truncate at 1536",
            desc_line)

    if body.strip():
        if re.search(r"\b(is a (file|format|protocol|language|standard|library)|stands for)\b", body, re.I):
            add(INFO, "explainer-bloat",
                "body defines common knowledge the model already has — cut the textbook paragraph")
        if re.search(r"\b(?:\w+\s+or\s+){3,}\w+", body, re.I):
            add(INFO, "or-chain", "long A or B or C or D chain — pick a default, mention alternatives once")
        if not re.search(r"^\s*\d+\.\s+\S", body, re.M) and not re.search(r"^\s*[-*]\s+\[[ xX]\]", body, re.M):
            add(INFO, "no-numbered-steps",
                "body has no numbered procedure or checklist", body_start_line)
        if not re.search(r"```[a-zA-Z]", body):
            add(INFO, "no-code-example",
                "no fenced, language-tagged example", body_start_line)
        if not re.search(r"\b(do not|don't|never |avoid |must not)\b", body, re.I):
            add(INFO, "no-anti-pattern", "body never says what not to do", body_start_line)
        if not re.search(r"\b(verif(?:y|ies|ication)|validat(?:e|es|ion)|confirm|re-?run|assert|check that)\b", body, re.I):
            add(INFO, "no-validate-loop",
                "no verify/validate/confirm step — Anthropic's loop is plan → execute → check",
                body_start_line)
        blob = body + "\n" + (desc or "")
        if re.search(r"\b(as of 202[0-6]|in 202[0-5]|since 202[0-5]|new in v?\d|currently \(202)", blob, re.I):
            add(WARN, "time-sensitive", "date-anchored claim will rot — move history to an 'old patterns' section")
        h1s = re.findall(r"^# ", body, re.M)
        if len(h1s) > 1:
            add(INFO, "multiple-h1", f"body has {len(h1s)} H1 headings — keep one title, nest the rest", body_start_line)
        if re.search(r"```[a-zA-Z0-9]*[ \t]*\n[ \t]*```", body):
            add(INFO, "empty-fence", "empty fenced code block")
        if (not re.search(r"^#{1,3}\s+(safety|caution|warning|security)\b", body, re.I | re.M)
                and any(re.search(r"(^|/)scripts/", rel.replace('\\', '/')) for rel, _c in extra)):
            add(INFO, "no-safety-section", "scripts/ present but no Safety/Caution heading", body_start_line)
        if body.count("\n") + 1 > 200 and not any(
            re.search(r"(^|/)references/", rel.replace("\\", "/")) for rel, _c in extra
        ):
            add(INFO, "no-disclosure",
                "body is over 200 lines with no references/ — split for progressive disclosure",
                body_start_line)
        if re.search(r"\$ARGUMENTS\b|\$\{ARGUMENTS\}|\$[0-9]\b", body) and not _as_str(fm.get("argument-hint", "") or "").strip():
            add(INFO, "missing-arg-hint",
                "body uses $ARGUMENTS / $N but frontmatter has no argument-hint for autocomplete",
                field_lines.get("argument-hint", body_start_line))

    for line in raw_fm.split("\n"):
        if line.startswith("\t"):
            add(INFO, "tabs-in-yaml", "frontmatter uses tabs — YAML is space-indented")
            break
        if re.match(r'^[A-Za-z0-9_-]+:\s+[^"\'>\n|][^:\n]*:[^:\n]', line) and "://" not in line:
            add(WARN, "unquoted-colon", "unquoted YAML value contains a colon — wrap the value in quotes")

    if source and not source.endswith("\n"):
        add(INFO, "missing-newline", "file has no trailing newline")
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if len(line) > 240:
            add(INFO, "long-line", f"line {i + 1} is {len(line)} chars — wrap it", i + 1)
            break

    tools = _as_str(fm.get("allowed-tools", "") or "")
    if tools:
        if re.search(r"(?:^|\s)Bash(?:\s|$)", tools) and not re.search(r"(?:^|\s)Bash\(", tools):
            add(WARN, "unscoped-bash",
                "allowed-tools grants unscoped Bash — prefer Bash(git:*) style least privilege",
                field_lines.get("allowed-tools"))
        if re.search(r"\(\s*\*\s*\)", tools):
            add(WARN, "wildcard-tool",
                "allowed-tools contains a * wildcard that grants everything",
                field_lines.get("allowed-tools"))

    if fm.get("disable-model-invocation") is True and fm.get("user-invocable") is False:
        add(WARN, "dead-skill",
            "user-invocable: false and disable-model-invocation: true — nothing can fire this skill",
            field_lines.get("user-invocable") or field_lines.get("disable-model-invocation"))
    if _as_str(fm.get("context", "") or "").strip() == "fork" and not fm.get("agent"):
        add(INFO, "fork-no-agent",
            "context: fork with no agent: — defaults to general-purpose; set it explicitly",
            field_lines.get("context"))

    if re.search(r"\bsudo\s+(rm|dd|chmod|mkfs|kill|reboot|shutdown)\b", source, re.I):
        add(WARN, "sudo-command", "skill instructs sudo on a destructive command")
    if re.search(r"git\s+push\s+[^\n]*(-f\b|--force)", source):
        add(WARN, "force-push", "skill instructs git push --force")
    if re.search(r"\b(mkfs\.\w+|dd\s+if=/dev/(?:zero|urandom)|rm\s+-rf\s+~(?:\s|$|/))", source, re.I):
        add(ERROR, "disk-wipe", "skill instructs a disk-wipe / home-delete command")
    if re.search(r"\b(printenv|cat\s+\.env\b|env\s*\|\s*grep)\b", source):
        add(WARN, "env-dump", "skill dumps environment / .env — secrets leak into the transcript")
    if re.search(r"\b(lorem ipsum|YOUR_[A-Z][A-Z0-9_]+|replace-me|changeme|INSERT_\w+)\b", source, re.I):
        add(INFO, "placeholder-text", "placeholder copy (YOUR_*, lorem ipsum, replace-me) left in the skill")
    if re.search(r"\b(localhost|127\.0\.0\.1):\d+", source):
        add(INFO, "localhost-url", "hard-coded localhost URL will not work for anyone else")
    if re.search(r"/Users/|/home/[a-z]|C:\\\\Users\\|~/(Desktop|Documents|Downloads)", source, re.I):
        add(WARN, "hardcoded-home", "absolute home-directory path — use a relative path or an env var")
    if re.search(
        r"(?:curl|wget)[^\n]*\s(?:-k|--insecure)\b|verify\s*=\s*False|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*0|GIT_SSL_NO_VERIFY",
        source, re.I,
    ):
        add(WARN, "insecure-tls", "skill disables TLS verification (curl -k, verify=False, NODE_TLS_REJECT_UNAUTHORIZED)")
    if re.search(r"\bnc\s+-[a-zA-Z]*e\b|/dev/tcp/|pty\.spawn|bash\s+-i\s+>&", source, re.I):
        add(ERROR, "reverse-shell", "skill instructs a reverse shell (nc -e, /dev/tcp, pty.spawn)")
    for line in source.splitlines():
        if re.search(r"\bpip3?\s+install\b", line) and "==" not in line and " -r " not in line and "--requirement" not in line and " -e " not in line:
            add(INFO, "unpinned-install", "unpinned pip/npm/docker install — pin a version so the skill is reproducible")
            break
        if re.search(r"\bnpm\s+i(?:nstall)?\s+(-g|--global)\b", line) or re.search(r"\bdocker\s+pull\s+\S+:latest\b", line):
            add(INFO, "unpinned-install", "unpinned pip/npm/docker install — pin a version so the skill is reproducible")
            break

    for rel, content in extra:
        pth = rel.replace("\\", "/")
        base = pth.split("/")[-1]
        if base.lower() in JUNK or "__MACOSX" in pth:
            add(WARN, "junk-file", f"packaging junk in the skill: {pth}")
        if re.search(r"/SKILL\.md$", pth, re.I):
            add(WARN, "nested-skill", f"nested SKILL.md at {pth} — a skill inside a skill will be double-scanned")
        if "/" not in pth and not re.match(r"^(skill\.md|license.*|readme.*|changelog.*|copying|notice|gitignore)$", base, re.I):
            add(INFO, "unexpected-root",
                f"unexpected top-level file '{base}' — spec layout is SKILL.md + scripts/ + references/ + assets/")
        if SECRET_FILE_RE.search(pth) or "/.git/" in pth:
            add(WARN, "bundled-secret-file", f"{pth} looks like a secret file bundled into the skill")
        if len(content) > 400_000:
            add(WARN, "large-file", f"{pth} is {len(content) // 1024} KiB — agents will not load this on demand cleanly")
        if "\0" in content:
            add(WARN, "binary-file", f"{pth} looks binary — keep binaries in assets/ and mention them, or drop them")
        if re.search(r"\.(py|sh|bash|rb)$", base, re.I) and content.strip() and not content.startswith("#!"):
            add(INFO, "script-no-shebang", f"{pth} has no shebang — agents exec it as a script")
        if re.search(r"\b(input\s*\(|raw_input\s*\(|read\s+-p\s)", content):
            add(WARN, "script-interactive", f"{pth} prompts interactively — agents run non-interactive shells")
    return out


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
            hint = closest_key(key, list(SPEC_FIELDS | CC_FIELDS))
            level = WARN if profile == "claude-code" else ERROR
            if hint:
                findings.append(Finding(label, level, "typo-field",
                                        f"unknown frontmatter field '{key}' — did you mean '{hint}'?",
                                        field_lines.get(key)))
            else:
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

    body_start_line = raw.replace("\r\n", "\n").count("\n", 0, body_start) + 2 if body_start != -1 else 1
    findings.extend(lint_v04(
        label, raw, extras.get("raw") or "", body, desc, name, fm,
        _iter_extra(path), field_lines, body_start_line,
    ))
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


def emit_gha(findings: list[Finding]) -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    sev = {ERROR: "error", WARN: "warning", INFO: "notice"}
    for f in findings:
        msg = f.message.replace("%", "%25").replace("\n", " ")
        print(f"::{sev[f.level]} file={f.skill},line={f.line or 1}::{msg} [{f.code}]", file=sys.stderr)


def _ignored(raw: list[str]) -> set[str]:
    out: set[str] = set()
    for item in raw:
        out.update(c.strip() for c in item.split(",") if c.strip())
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit a Claude Code / Agent Skills directory.")
    ap.add_argument("path", nargs="?", default=None,
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
    ap.add_argument("--stdin", action="store_true",
                    help="lint SKILL.md text from stdin (path is the label)")
    ap.add_argument("--min-score", type=int, metavar="N",
                    help="exit 1 if any skill scores below N (0-100)")
    ap.add_argument("--ignore", action="append", default=[], metavar="CODE",
                    help="skip these finding codes (comma-separated or repeatable)")
    ap.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                    help="skip skill paths matching this glob (repeatable)")
    ap.add_argument("--version", action="version", version=f"claude-skill-lint {__version__}")
    args = ap.parse_args(argv)
    ignore = _ignored(args.ignore)
    exclude = args.exclude
    allowed = set(args.allow_model)
    stale_res = [re.compile(p) for p in STALE_MODEL_PATTERNS]

    def keep(found: list[Finding]) -> list[Finding]:
        out = found
        if allowed:
            out = [f for f in out if not (
                f.code == "stale-model-id" and any(a in f.message for a in allowed)
            )]
        if ignore:
            out = [f for f in out if f.code not in ignore]
        return out

    if args.stdin:
        text = sys.stdin.read()
        folder = expected_name(args.path) if args.path else "stdin"
        if not folder:
            folder = "stdin"
        td = tempfile.mkdtemp(prefix="skilllint-")
        try:
            sdir = os.path.join(td, folder)
            os.makedirs(sdir)
            virt = os.path.join(sdir, "SKILL.md")
            with open(virt, "w", encoding="utf-8") as fh:
                fh.write(text)
            found = keep(lint_skill(virt, td, args.max_desc, args.max_body, stale_res, args.profile, [folder]))
            all_findings = found
            skills_n = 1
            root = args.path or "stdin"
            per_skill = {folder: found}
        finally:
            shutil.rmtree(td, ignore_errors=True)
    else:
        root = os.path.abspath(os.path.expanduser(args.path or os.path.expanduser("~/.claude/skills")))
        if not os.path.isdir(root):
            print(f"error: not a directory: {root}", file=sys.stderr)
            return 2
        skills = find_skill_files(root)
        if exclude:
            filtered = []
            for s in skills:
                rel = _norm(os.path.relpath(s, root))
                if any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(os.path.basename(rel), g) for g in exclude):
                    continue
                filtered.append(s)
            skills = filtered
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

        all_findings = []
        per_skill: dict[str, list[Finding]] = {}
        for s in skills:
            found = keep(lint_skill(s, root, args.max_desc, args.max_body, stale_res, args.profile, names))
            all_findings.extend(found)
            per_skill[skill_label(s, root)] = found
        skills_n = len(skills)

    errors = sum(1 for f in all_findings if f.level == ERROR)
    warns = sum(1 for f in all_findings if f.level == WARN)
    infos = sum(1 for f in all_findings if f.level == INFO)
    scores = {k: score_of(v) for k, v in per_skill.items()}
    worst = min(scores.values()) if scores else 100

    emit_gha(all_findings)

    if args.sarif:
        with open(args.sarif, "w", encoding="utf-8") as fh:
            json.dump(to_sarif(all_findings, str(root)), fh, indent=2)
            fh.write("\n")

    if args.json:
        print(json.dumps({
            "root": root,
            "profile": args.profile,
            "version": __version__,
            "skills_scanned": skills_n,
            "score": worst,
            "scores": scores,
            "summary": {"errors": errors, "warnings": warns, "info": infos},
            "findings": [f.as_dict() for f in all_findings],
        }, indent=2))
    else:
        icon = {ERROR: "✗", WARN: "!", INFO: "·"}
        shown = [f for f in all_findings if not (args.quiet and f.level == INFO)]
        for f in shown:
            loc = f"L{f.line} " if f.line else ""
            print(f"  {icon[f.level]} [{f.level:5}] {f.skill}: {loc}{f.message}  ({f.code})")
        clean = skills_n - len({f.skill for f in all_findings})
        print(f"\nScanned {skills_n} skills in {root}")
        print(f"  {clean} clean · {errors} errors · {warns} warnings · {infos} info · score {worst}")

    if errors:
        return 1
    if args.fail_on_warn and warns:
        return 1
    if args.min_score is not None and worst < args.min_score:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
