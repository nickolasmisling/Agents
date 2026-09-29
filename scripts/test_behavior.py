#!/usr/bin/env python3
"""Behavioral tests: does each subagent actually do its job well?

Each case in tests/behavior/cases/*.yaml runs one agent as the main thread
(`claude -p --agent NAME`) against a scratch copy of a fixture that contains
deliberately seeded defects, then a separate judge call grades the agent's
report and file changes against a rubric.

Case format:

    agent: security-auditor
    fixture: sample-app            # directory under tests/fixtures/ (default: sample-app)
    setup: |                       # optional shell run in the scratch copy after `git init`
      bash ../../scripts/make_history.sh
    prompt: Audit the app for security vulnerabilities.
    read_only: true                # fail if the agent modifies any tracked/untracked file
    check: python -m pytest -q     # optional command that must exit 0 afterwards
    rubric:
      must:                        # every item must be met
        - Flags the SQL injection in app/orders.py
      should:                      # scored, not required
        - Suggests parameterized queries
      must_not:                    # any item met fails the case
        - Reports the parameterized query in app/users.py as injectable

Usage:
    python3 scripts/test_behavior.py [--only NAME ...] [--jobs N] [--keep]
                                     [--permission-mode auto] [--budget 3]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "tests" / "behavior" / "cases"
FIXTURES = ROOT / "tests" / "fixtures"
RESULTS_DIR = ROOT / "tests" / "behavior" / "results"

JUDGE_PROMPT = """You are a strict grader for an automated test of a Claude Code subagent.
You get the task the agent was given, its final report, and the git diff of any files it changed.
Grade ONLY against the rubric. An item is met only if the report or diff gives clear, specific
evidence (e.g. names the right file/function and the actual problem). Vague or generic mentions
do not count. Do not use tools.

Task given to agent `{agent}`:
<<<
{prompt}
>>>

Agent's final report:
<<<
{report}
>>>

Files changed by the agent (git status --porcelain), then diff (truncated):
<<<
{status}
---
{diff}
>>>

Rubric (JSON): {rubric}

Respond with ONLY a JSON object, no prose, no code fences:
{{"must": [{{"item": str, "met": bool, "evidence": str}}],
  "should": [{{"item": str, "met": bool}}],
  "must_not": [{{"item": str, "violated": bool, "evidence": str}}],
  "quality": int (1-5 overall usefulness of the report to an engineer),
  "notes": str (one or two sentences)}}"""


def claude_json(args: list[str], cwd: Path, timeout: int) -> dict:
    proc = subprocess.run(["claude", "-p", *args, "--output-format", "json"],
                          cwd=cwd, capture_output=True, text=True, timeout=timeout, env=dict(os.environ))
    out = proc.stdout
    start = out.find("{")
    try:
        return json.JSONDecoder().raw_decode(out[start:])[0] if start >= 0 else {"is_error": True, "result": proc.stderr}
    except json.JSONDecodeError:
        return {"is_error": True, "result": (out + proc.stderr)[-3000:]}


def parse_json_blob(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start = text.find("{")
    try:
        return json.JSONDecoder().raw_decode(text[start:])[0]
    except (json.JSONDecodeError, ValueError):
        return None


def sh(cmd: str, cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def run_case(path: Path, opts: argparse.Namespace) -> dict:
    case = yaml.safe_load(path.read_text(encoding="utf-8"))
    agent, prompt = case["agent"], case["prompt"]
    tmp = Path(tempfile.mkdtemp(prefix=f"beh-{agent}-"))
    work = tmp / "work"
    shutil.copytree(FIXTURES / case.get("fixture", "sample-app"), work)
    shutil.copytree(ROOT / ".claude" / "agents", work / ".claude" / "agents")
    git = "git -c user.email=fixture@example.com -c user.name=Fixture"
    sh(f"git init -q -b main && {git} add -A && {git} commit -qm 'fixture baseline'", work)
    if case.get("setup"):
        r = sh(case["setup"], work)
        if r.returncode:
            return {"case": path.stem, "agent": agent, "pass": False, "error": f"setup failed: {r.stderr[-800:]}"}
    sh(f"{git} add -A && {git} commit -qm 'setup' --allow-empty", work)
    # Keep the agent definitions out of the diff we grade.
    sh("git update-index --assume-unchanged $(git ls-files .claude) 2>/dev/null; true", work)

    res = claude_json([prompt, "--agent", agent, "--permission-mode", opts.permission_mode,
                       "--max-budget-usd", str(opts.budget)], work, opts.timeout)
    report = res.get("result") or ""
    status = sh("git status --porcelain -- . ':!.claude'", work).stdout
    diff = sh("git diff -- . ':!.claude'", work).stdout
    untracked = sh("git ls-files --others --exclude-standard -- . ':!.claude'", work).stdout.split()
    for f in untracked[:10]:
        p = work / f
        if p.is_file() and p.stat().st_size < 20000:
            diff += f"\n+++ new file {f}\n" + p.read_text(errors="replace")

    check_ok, check_out = True, ""
    if case.get("check"):
        r = sh(case["check"], work)
        check_ok, check_out = r.returncode == 0, (r.stdout + r.stderr)[-1500:]

    judge_prompt = JUDGE_PROMPT.format(agent=agent, prompt=prompt, report=report[:30000],
                                       status=status or "(no changes)", diff=diff[:30000] or "(none)",
                                       rubric=json.dumps(case.get("rubric", {})))
    verdict = None
    for _ in range(2):
        jr = claude_json([judge_prompt, "--max-turns", "1", "--model", opts.judge_model], tmp, opts.timeout)
        verdict = parse_json_blob(jr.get("result") or "")
        if verdict:
            break

    problems = []
    if res.get("is_error") or not report:
        problems.append(f"agent run errored: {str(res.get('result'))[:300]}")
    if case.get("read_only") and status.strip():
        problems.append(f"read-only agent modified files:\n{status}")
    if not check_ok:
        problems.append(f"post-check `{case['check']}` failed:\n{check_out}")
    if verdict is None:
        problems.append("judge returned unparseable output")
    else:
        problems += [f"missed MUST: {m['item']}" for m in verdict.get("must", []) if not m.get("met")]
        problems += [f"violated MUST_NOT: {m['item']} ({m.get('evidence', '')})"
                     for m in verdict.get("must_not", []) if m.get("violated")]

    result = {
        "case": path.stem, "agent": agent, "pass": not problems, "problems": problems,
        "quality": (verdict or {}).get("quality"),
        "should_met": sum(bool(s.get("met")) for s in (verdict or {}).get("should", [])),
        "should_total": len((verdict or {}).get("should", [])),
        "notes": (verdict or {}).get("notes"),
        "cost_usd": res.get("total_cost_usd"), "turns": res.get("num_turns"),
        "report": report, "changed": status, "workdir": str(work) if opts.keep else None,
    }
    if not opts.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="agent or case names to run")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--permission-mode", default="auto",
                    help="permission mode for the agent under test (default: auto)")
    ap.add_argument("--budget", type=float, default=3.0, help="max USD per agent run")
    ap.add_argument("--judge-model", default="sonnet")
    ap.add_argument("--timeout", type=int, default=1200)
    ap.add_argument("--keep", action="store_true", help="keep scratch directories for inspection")
    args = ap.parse_args()

    if not shutil.which("claude"):
        sys.exit("the `claude` CLI must be on PATH")
    paths = sorted(CASES_DIR.glob("*.yaml"))
    if args.only:
        paths = [p for p in paths if p.stem in args.only or yaml.safe_load(p.read_text())["agent"] in args.only]
    if not paths:
        sys.exit("no matching cases")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futs = {pool.submit(run_case, p, args): p for p in paths}
        for fut in cf.as_completed(futs):
            p = futs[fut]
            try:
                r = fut.result()
            except Exception as e:  # noqa: BLE001 - report and keep going
                r = {"case": p.stem, "agent": p.stem, "pass": False, "problems": [f"harness error: {e!r}"]}
            results.append(r)
            (RESULTS_DIR / f"{r['case']}.json").write_text(json.dumps(r, indent=2))
            mark = "PASS" if r["pass"] else "FAIL"
            extra = f"q={r.get('quality')} should={r.get('should_met')}/{r.get('should_total')} ${r.get('cost_usd') or 0:.2f}"
            print(f"{mark}  {r['case']:<32} {extra}")
            for prob in r.get("problems", []):
                print(f"      - {prob.splitlines()[0][:160]}")

    passed = sum(r["pass"] for r in results)
    cost = sum(r.get("cost_usd") or 0 for r in results)
    print(f"\n{passed}/{len(results)} behavior cases passed (${cost:.2f}); details in {RESULTS_DIR.relative_to(ROOT)}/")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
