#!/usr/bin/env python3
"""Routing tests: does Claude pick the right subagent for a realistic request?

A subagent is only useful if the main agent delegates to it. Delegation is
driven entirely by each agent's `description`, so this suite checks that the
descriptions are specific enough to win the requests they should, and don't
steal requests meant for another agent.

Cases live in tests/routing/cases.yaml:

    - prompt: "I just changed the checkout flow, can you look it over before I push?"
      expect: [code-reviewer]          # any of these counts as a pass
      forbid: [security-auditor]       # optional: picking one of these is a fail
      select_only: true                # optional: premise not true of the fixture; skip in live mode

Modes:
  select (default)  Ask Claude which agent it would delegate to, without doing
                    the work. Cheap; tests description discrimination across
                    the whole roster at once.
  live              Run the request for real (in a scratch copy of
                    tests/fixtures/sample-app) and read the agents actually
                    spawned from `subagent_stats.by_type` in the JSON result.

Usage:
    python3 scripts/test_routing.py [--mode select|live] [--only NAME ...]
                                    [--jobs N] [--model MODEL] [--json OUT]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "tests" / "routing" / "cases.yaml"
FIXTURE = ROOT / "tests" / "fixtures" / "sample-app"
# Agents that ship with Claude Code; cases may expect or forbid them.
BUILTINS = {"Explore", "Plan", "general-purpose", "claude-code-guide", "statusline-setup", "claude"}

SELECT_PROMPT = """You are being evaluated on subagent routing. Do NOT perform the task and do NOT call any tools.
Read the user request below and decide which ONE subagent type from your Agent tool's list you would delegate it to.
If you would genuinely not delegate at all, answer NONE.
Reply with ONLY the subagent type name on a single line, nothing else.

User request:
<<<
{prompt}
>>>"""


def run_claude(args: list[str], cwd: Path, timeout: int) -> dict:
    env = dict(os.environ)
    proc = subprocess.run(
        ["claude", "-p", *args, "--output-format", "json"],
        cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env,
    )
    out = proc.stdout.strip()
    # The CLI may print trailing notices after the JSON document.
    start = out.find("{")
    try:
        return json.JSONDecoder().raw_decode(out[start:])[0] if start >= 0 else {}
    except json.JSONDecodeError:
        return {"is_error": True, "result": out[-2000:] + proc.stderr[-2000:]}


def agent_names() -> set[str]:
    names = set()
    for f in (ROOT / ".claude" / "agents").rglob("*.md"):
        m = re.search(r"^name:\s*([\w-]+)\s*$", f.read_text(encoding="utf-8"), re.M)
        if m:
            names.add(m.group(1))
    return names


def run_case(case: dict, mode: str, model: str | None, timeout: int, claude_md: Path | None = None) -> dict:
    extra = ["--model", model] if model else []
    if mode == "select":
        res = run_claude([SELECT_PROMPT.format(prompt=case["prompt"]), "--max-turns", "1", *extra], ROOT, timeout)
        raw = (res.get("result") or "").strip()
        picked = [raw.splitlines()[-1].strip().strip("`*'\" .")] if raw else []
    else:
        with tempfile.TemporaryDirectory(prefix="route-") as tmp:
            work = Path(tmp) / "sample-app"
            shutil.copytree(FIXTURE, work)
            shutil.copytree(ROOT / ".claude" / "agents", work / ".claude" / "agents")
            if claude_md:
                shutil.copy(claude_md, work / "CLAUDE.md")
            subprocess.run(["git", "init", "-q"], cwd=work)
            subprocess.run(["git", "add", "-A"], cwd=work)
            subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "fixture"], cwd=work)
            # Pre-approve Bash as a user normally would, so the main agent's choice between
            # doing the work itself and delegating isn't skewed by blocked commands.
            res = run_claude([case["prompt"], "--permission-mode", "acceptEdits", "--allowedTools", "Bash",
                              *extra], work, timeout)
        picked = sorted((res.get("subagent_stats") or {}).get("by_type", {}).keys())
        raw = (res.get("result") or "")[:300]

    expect, forbid = set(case["expect"]), set(case.get("forbid", []))
    ok = bool(set(picked) & expect) and not (set(picked) & forbid)
    return {"prompt": case["prompt"], "expect": sorted(expect), "picked": picked,
            "pass": ok, "raw": raw, "cost_usd": res.get("total_cost_usd", 0)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["select", "live"], default="select")
    ap.add_argument("--only", nargs="*", help="only cases whose expected agents include these names")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--model", help="model for the routing (main) agent")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--json", type=Path, help="write full results here")
    ap.add_argument("--claude-md", type=Path, help="live mode: CLAUDE.md to place in the scratch repo "
                    "(e.g. docs/ROUTING.md, to measure its effect on delegation)")
    args = ap.parse_args()

    if not shutil.which("claude"):
        sys.exit("the `claude` CLI must be on PATH")
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    known = agent_names()
    unknown = {n for c in cases for n in c["expect"] + c.get("forbid", [])} - known - BUILTINS - {"NONE"}
    if unknown:
        sys.exit(f"cases reference unknown agents: {sorted(unknown)}")
    if args.only:
        cases = [c for c in cases if set(c["expect"]) & set(args.only)]
    if args.mode == "live":
        # Cases whose premise isn't true of the plain fixture (e.g. "review my diff") only
        # make sense in select mode.
        cases = [c for c in cases if not c.get("select_only")]
    untested = known - {n for c in cases for n in c["expect"]}
    if untested and not args.only:
        print(f"note: no routing case targets: {', '.join(sorted(untested))}\n")

    results = []
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futs = {pool.submit(run_case, c, args.mode, args.model, args.timeout, args.claude_md): c for c in cases}
        for fut in cf.as_completed(futs):
            try:
                r = fut.result()
            except Exception as e:  # noqa: BLE001 - report and keep going
                c = futs[fut]
                r = {"prompt": c["prompt"], "expect": c["expect"], "picked": [], "pass": False, "raw": repr(e), "cost_usd": 0}
            results.append(r)
            mark = "PASS" if r["pass"] else "FAIL"
            print(f"{mark}  expect={','.join(r['expect'])}  picked={','.join(r['picked']) or '-'}  :: {r['prompt'][:70]}")

    passed = sum(r["pass"] for r in results)
    cost = sum(r["cost_usd"] or 0 for r in results)
    print(f"\n{passed}/{len(results)} routing cases passed ({args.mode} mode, ${cost:.2f})")
    if args.json:
        args.json.write_text(json.dumps(sorted(results, key=lambda r: r["expect"]), indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
