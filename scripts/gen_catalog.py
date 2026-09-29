#!/usr/bin/env python3
"""Regenerate the agent catalog in README.md from agent frontmatter.

Replaces everything between <!-- catalog:start --> and <!-- catalog:end -->.
Use --check to fail (exit 1) if README.md is out of date instead of writing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / ".claude" / "agents"
README = ROOT / "README.md"
START, END = "<!-- catalog:start -->", "<!-- catalog:end -->"

CATEGORY_TITLES = {
    "review": "Code review & auditing",
    "testing": "Testing",
    "debugging": "Debugging & diagnosis",
    "architecture": "Architecture & refactoring",
    "docs": "Documentation",
    "languages": "Language & framework specialists",
    "data": "Data & databases",
    "devops": "DevOps, cloud & operations",
    "git": "Git & pull-request workflow",
    "ai": "AI engineering & Claude Code",
    "compliance": "Compliance & regulated software",
    "product": "Product & requirements",
    "research": "Research",
}


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---", 2)[1])


def first_sentence(desc: str) -> str:
    desc = " ".join(desc.split())
    for sep in (". Use ", ". Not ", ". MUST"):
        if sep in desc:
            return desc.split(sep)[0] + "."
    return desc


def build() -> str:
    by_cat: dict[str, list[tuple[str, dict]]] = {}
    for f in sorted(AGENTS.rglob("*.md")):
        by_cat.setdefault(f.parent.name, []).append((f.relative_to(ROOT).as_posix(), frontmatter(f)))
    total = sum(len(v) for v in by_cat.values())
    order = [c for c in CATEGORY_TITLES if c in by_cat] + sorted(set(by_cat) - set(CATEGORY_TITLES))
    lines = [f"**{total} agents** in {len(by_cat)} categories.", ""]
    for cat in order:
        lines += [f"### {CATEGORY_TITLES.get(cat, cat.title())}", "",
                  "| Agent | What it does | Model | Access |", "| --- | --- | --- | --- |"]
        for rel, fm in sorted(by_cat[cat], key=lambda x: x[1]["name"]):
            tools = [t.strip() for t in fm.get("tools", "").split(",")] if isinstance(fm.get("tools"), str) else fm.get("tools", [])
            access = "read/write" if {"Write", "Edit"} & set(tools) else "read-only"
            if {"WebSearch", "WebFetch"} & set(tools):
                access += " + web"
            desc = first_sentence(fm["description"]).replace("|", "\\|")
            lines.append(f"| [`{fm['name']}`]({rel}) | {desc} | {fm.get('model', 'inherit')} | {access} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    readme = README.read_text(encoding="utf-8")
    if START not in readme or END not in readme:
        sys.exit(f"README.md must contain {START} and {END}")
    head, rest = readme.split(START, 1)
    _, tail = rest.split(END, 1)
    new = f"{head}{START}\n{build()}{END}{tail}"
    if "--check" in sys.argv:
        if new != readme:
            print("README.md catalog is out of date; run `make catalog`", file=sys.stderr)
            return 1
        return 0
    README.write_text(new, encoding="utf-8")
    print("README.md catalog updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
