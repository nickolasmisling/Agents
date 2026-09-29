#!/usr/bin/env python3
"""Static validator for Claude Code subagent definitions.

Claude Code is forgiving in ways that hide mistakes: a misspelled tool name is
silently dropped, an unknown frontmatter key is ignored, and an agent whose
`tools` field is omitted inherits *every* tool (including Write/Edit and all MCP
tools). This script turns those silent failures into errors, and enforces the
conventions in docs/STYLE_GUIDE.md.

Usage:
    python3 scripts/validate_agents.py [--strict] [--json] [PATH ...]

PATH defaults to .claude/agents. Exit status is 1 if any errors are found
(or any warnings, with --strict).
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / ".claude" / "agents"

# Tool names verified against Claude Code 2.1.x by listing the tools a probe
# agent actually received. Names outside this set are silently dropped by
# Claude Code, so we treat them as errors.
KNOWN_TOOLS = {
    "Read", "Write", "Edit", "Glob", "Grep", "Bash", "WebFetch", "WebSearch",
    "NotebookEdit", "Agent", "Skill", "ToolSearch", "SendMessage", "Monitor",
    "TaskCreate", "TaskGet", "TaskList", "TaskUpdate", "TaskStop",
    "AskUserQuestion", "EnterWorktree", "ExitWorktree", "EnterPlanMode",
    "ExitPlanMode", "CronCreate", "CronDelete", "CronList", "PushNotification",
    "Workflow", "ListMcpResourcesTool", "ReadMcpResourceTool", "LSP",
}
# Legacy names: accepted by some versions, but should not be used in new files.
DEPRECATED_TOOLS = {
    "Task": "renamed to Agent",
    "TodoWrite": "replaced by TaskCreate/TaskUpdate/TaskList",
    "MultiEdit": "removed; use Edit",
}
WRITE_TOOLS = {"Write", "Edit", "NotebookEdit"}

MODEL_ALIASES = {
    "inherit", "default", "best", "sonnet", "opus", "haiku", "fable",
    "opusplan", "sonnet[1m]", "opus[1m]",
}
MODEL_ID_RE = re.compile(r"^claude-[a-z0-9-]+(\[1m\])?$")

ENUMS = {
    "permissionMode": {"default", "acceptEdits", "auto", "plan", "dontAsk",
                       "bypassPermissions", "manual"},
    "effort": {"low", "medium", "high", "xhigh", "max"},
    "memory": {"user", "project", "local"},
    "isolation": {"worktree"},
    "color": {"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"},
}
KNOWN_KEYS = {
    "name", "description", "tools", "disallowedTools", "model", "color",
    "permissionMode", "maxTurns", "skills", "mcpServers", "hooks", "memory",
    "isolation", "effort", "omitClaudeMd", "background",
}

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
MCP_TOOL_RE = re.compile(r"^mcp__[A-Za-z0-9_-]+(__[A-Za-z0-9_*-]+)?$")
AGENT_SCOPED_RE = re.compile(r"^Agent\(([A-Za-z0-9_, -]+)\)$")
TRIGGER_RE = re.compile(
    r"\b(use (it |this )?(proactively|when|whenever|after|before|for|to)|"
    r"must be used|invoke (when|after|before|for))\b",
    re.IGNORECASE,
)
OUTPUT_HEADING_RE = re.compile(r"^#{2,3} .*\b(output|report|deliverable|return)", re.I | re.M)
ASK_USER_RE = re.compile(r"\b(ask (the )?user|ask for clarification|confirm with the user|wait for (the )?user)", re.I)
DATED_MODEL_RE = re.compile(r"-\d{8}$")

DESC_MIN, DESC_MAX = 80, 500
PROACTIVE_BUDGET = 10  # library-wide cap on "Use PROACTIVELY" descriptions
BODY_MIN_WORDS = 250
OVERLAP_WARN = 0.45  # Jaccard similarity of description keyword sets

STOPWORDS = set("""a an and or the of to for in on with by from as at is are be this that it its
use used using when whenever after before any all into your you their them should must can
code proactively agent subagent task tasks such e g eg i ie etc not no do does than then also
via per each only other more most""".split())


class Report:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, level: str, path: Path | str, msg: str) -> None:
        self.items.append({"level": level, "file": str(path), "message": msg})

    def errors(self) -> list[dict]:
        return [i for i in self.items if i["level"] == "error"]

    def warnings(self) -> list[dict]:
        return [i for i in self.items if i["level"] == "warning"]


def split_frontmatter(text: str) -> tuple[str | None, str]:
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---", 4)
    if end == -1:
        return None, text
    fm = text[4:end]
    rest = text[end + 4:]
    if rest.startswith("\n"):
        rest = rest[1:]
    return fm, rest


def as_list(value) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [t.strip() for t in re.split(r",(?![^()]*\))", value) if t.strip()]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return [v.strip() for v in value]
    return None


def check_tools(field: str, raw, path: Path, rep: Report) -> list[str]:
    tools = as_list(raw)
    if tools is None:
        rep.add("error", path, f"`{field}` must be a comma-separated string or a list of strings")
        return []
    seen = set()
    for t in tools:
        if t in seen:
            rep.add("warning", path, f"`{field}` lists {t!r} twice")
        seen.add(t)
        if t in KNOWN_TOOLS or MCP_TOOL_RE.match(t) or AGENT_SCOPED_RE.match(t):
            continue
        if t in DEPRECATED_TOOLS:
            rep.add("warning", path, f"`{field}`: {t!r} is deprecated ({DEPRECATED_TOOLS[t]})")
            continue
        rep.add("error", path, f"`{field}`: unknown tool {t!r} (Claude Code silently drops unknown tools)")
    return tools


def keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z][a-z0-9+#.-]{2,}", text.lower())
    return {w.strip(".-") for w in words if w not in STOPWORDS}


def validate_file(path: Path, rep: Report) -> dict | None:
    text = path.read_text(encoding="utf-8")
    if "\r\n" in text:
        rep.add("warning", path, "file uses CRLF line endings")
        text = text.replace("\r\n", "\n")
    fm_text, body = split_frontmatter(text)
    if fm_text is None:
        rep.add("error", path, "missing YAML frontmatter (file must start with '---' and close it with '---')")
        return None
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        rep.add("error", path, f"frontmatter is not valid YAML: {e}")
        return None
    if not isinstance(fm, dict):
        rep.add("error", path, "frontmatter must be a YAML mapping")
        return None

    for key in fm:
        if key not in KNOWN_KEYS:
            rep.add("error", path, f"unknown frontmatter key {key!r} (Claude Code ignores it; typo?)")

    name = fm.get("name")
    if not isinstance(name, str) or not name.strip():
        rep.add("error", path, "`name` is required and must be a non-empty string")
        name = None
    else:
        if not NAME_RE.match(name):
            rep.add("error", path, f"`name` {name!r} must be lowercase kebab-case")
        if name != path.stem:
            rep.add("error", path, f"`name` {name!r} does not match filename {path.stem!r}")

    desc = fm.get("description")
    if not isinstance(desc, str) or not desc.strip():
        rep.add("error", path, "`description` is required and must be a non-empty string")
        desc = ""
    else:
        desc = " ".join(desc.split())
        if len(desc) < DESC_MIN:
            rep.add("warning", path, f"`description` is short ({len(desc)} chars); say what it does AND when to use it")
        if len(desc) > DESC_MAX:
            rep.add("warning", path, f"`description` is long ({len(desc)} chars > {DESC_MAX}); move detail into the body")
        if re.search(r"must be used", desc, re.I) or "<example>" in desc:
            rep.add("warning", path, "`description` uses shouting or <example> transcripts; keep it a plain routing rule")
        if not TRIGGER_RE.search(desc):
            rep.add("warning", path, "`description` has no delegation trigger (e.g. 'Use when…', 'Use PROACTIVELY after…')")

    tools: list[str] = []
    if "tools" not in fm:
        rep.add("warning", path, "`tools` omitted: agent inherits ALL tools incl. Write/Edit/MCP; declare least privilege explicitly")
    else:
        tools = check_tools("tools", fm["tools"], path, rep)
    if "disallowedTools" in fm:
        denied = check_tools("disallowedTools", fm["disallowedTools"], path, rep)
        both = set(tools) & set(denied)
        if both:
            rep.add("error", path, f"tools listed in both `tools` and `disallowedTools`: {sorted(both)}")

    model = fm.get("model")
    if model is not None:
        if not isinstance(model, str) or not (model in MODEL_ALIASES or MODEL_ID_RE.match(model)):
            rep.add("error", path, f"`model` {model!r} is not a known alias or claude-* model id")
        elif DATED_MODEL_RE.search(model):
            rep.add("warning", path, f"`model` {model!r} is a dated id; prefer an alias (sonnet/opus/haiku/inherit)")

    for key, allowed in ENUMS.items():
        if key in fm and fm[key] not in allowed:
            rep.add("error", path, f"`{key}` {fm[key]!r} must be one of {sorted(allowed)}")
    if fm.get("permissionMode") == "bypassPermissions":
        rep.add("warning", path, "`permissionMode: bypassPermissions` is dangerous in a shared library")

    if "hooks" in fm:
        rep.add("warning", path, "`hooks` in agent frontmatter did not fire in our tests; don't rely on them for enforcement")
    if "Agent" in tools or any(AGENT_SCOPED_RE.match(t) for t in tools):
        rep.add("warning", path, "agent can spawn subagents (`Agent` tool); library agents should be leaves")
    if "maxTurns" in fm and not (isinstance(fm["maxTurns"], int) and fm["maxTurns"] > 0):
        rep.add("error", path, "`maxTurns` must be a positive integer")
    if "skills" in fm and as_list(fm["skills"]) is None:
        rep.add("error", path, "`skills` must be a list of strings")
    if "omitClaudeMd" in fm and not isinstance(fm["omitClaudeMd"], bool):
        rep.add("error", path, "`omitClaudeMd` must be a boolean")

    words = len(body.split())
    if words == 0:
        rep.add("error", path, "system prompt body is empty")
    elif words < BODY_MIN_WORDS:
        rep.add("warning", path, f"system prompt body is thin ({words} words < {BODY_MIN_WORDS})")
    if ASK_USER_RE.search(body):
        rep.add("warning", path, "body tells the agent to ask the user; subagents can't. Return NEEDS_CONTEXT or state an assumption")
    if words and not OUTPUT_HEADING_RE.search(body):
        rep.add("warning", path, "body has no '## Output…' section defining what to return to the parent")

    return {
        "name": name,
        "path": path,
        "category": path.parent.name if path.parent != DEFAULT_DIR else "",
        "description": desc,
        "tools": tools,
        "model": model,
        "color": fm.get("color"),
        "writes": bool(set(tools) & WRITE_TOOLS) if "tools" in fm else True,
        "body_words": words,
    }


def cross_checks(agents: list[dict], rep: Report) -> None:
    by_name: dict[str, list[Path]] = {}
    for a in agents:
        if a["name"]:
            by_name.setdefault(a["name"], []).append(a["path"])
    for name, paths in by_name.items():
        if len(paths) > 1:
            rep.add("error", paths[0], f"duplicate agent name {name!r} also in {[str(p) for p in paths[1:]]}")

    proactive = [a["name"] for a in agents if re.search(r"\bproactively\b", a["description"], re.I)]
    if len(proactive) > PROACTIVE_BUDGET:
        rep.add("warning", "(library)", f"{len(proactive)} agents say 'PROACTIVELY' (budget {PROACTIVE_BUDGET}): {', '.join(sorted(proactive))}")
    total_desc = sum(len(a["description"]) for a in agents)
    if total_desc > 40000:
        rep.add("warning", "(library)", f"descriptions total {total_desc} chars; they all load into the parent's context")

    kw = {a["name"]: keywords(a["description"]) for a in agents if a["name"]}
    for (n1, k1), (n2, k2) in itertools.combinations(kw.items(), 2):
        if not k1 or not k2:
            continue
        j = len(k1 & k2) / len(k1 | k2)
        if j >= OVERLAP_WARN:
            rep.add("warning", f"{n1} <-> {n2}", f"descriptions overlap (Jaccard {j:.2f}); they may compete for delegation")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", type=Path, default=[DEFAULT_DIR])
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args()

    files: list[Path] = []
    for p in args.paths:
        if p.is_dir():
            files.extend(sorted(p.rglob("*.md")))
        elif p.suffix == ".md":
            files.append(p)
    files = [f for f in files if f.name.lower() != "readme.md"]
    if not files:
        print(f"no agent files found under {[str(p) for p in args.paths]}", file=sys.stderr)
        return 1

    rep = Report()
    agents = [a for a in (validate_file(f, rep) for f in files) if a]
    cross_checks(agents, rep)

    errors, warnings = rep.errors(), rep.warnings()
    if args.json:
        print(json.dumps({"files": len(files), "errors": errors, "warnings": warnings}, indent=2))
    else:
        for item in rep.items:
            try:
                where = Path(item["file"]).relative_to(ROOT)
            except ValueError:
                where = item["file"]
            print(f"{item['level'].upper():7} {where}: {item['message']}")
        print(f"\n{len(files)} agent file(s): {len(errors)} error(s), {len(warnings)} warning(s)")
    failed = bool(errors) or (args.strict and bool(warnings))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
