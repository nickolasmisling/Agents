#!/usr/bin/env python3
"""Behavioral tests: does each subagent actually do its job well?

Each case in tests/behavior/cases/*.yaml runs one agent as the main thread
(`claude -p --agent NAME`) against a scratch copy of a fixture that contains
deliberately seeded defects, then a separate judge call grades the agent's
report and file changes against a rubric.

Case format:

    agent: security-auditor
    fixture: sample-app            # directory under tests/fixtures/ (default: sample-app)
    setup: |                       # optional shell run in the scratch copy after `git init`;
      bash "$FIXTURES/scenarios/regression_history.sh"   # $FIXTURES and $REPO_ROOT are set
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
                                     [--permission-mode acceptEdits] [--budget 3]

The agent under test runs with Bash pre-approved inside a throwaway copy of the
fixture. Run this in a container or VM if you don't trust the agents.
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

Files the agent created, modified or deleted, then the unified diff of its changes (truncated):
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
    # Setup/check commands can reference $FIXTURES (tests/fixtures) and $REPO_ROOT.
    env = dict(os.environ, FIXTURES=str(FIXTURES), REPO_ROOT=str(ROOT),
               PYTHONDONTWRITEBYTECODE="1", GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.com",
               GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.com")
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)


def fingerprint(root: Path) -> dict[str, str]:
    """Content hash of every file outside .git, to detect any change an agent makes."""
    import hashlib
    skip = {".git", "__pycache__", ".pytest_cache", "node_modules"}
    out = {}
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if p.is_file() and not (set(rel.parts) & skip) and rel.parts[:2] != (".claude", "settings.local.json"):
            out[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


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
    if not case.get("keep_setup_uncommitted"):
        # Most cases grade a clean tree; cases that test "review my uncommitted diff"
        # or "resolve this in-progress merge" set keep_setup_uncommitted: true.
        sh(f"{git} add -A && {git} commit -qm 'setup' --allow-empty", work)
    before = fingerprint(work)
    snapshot = tmp / "before"
    shutil.copytree(work, snapshot, ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__"))

    # Headless runs can't answer permission prompts; pre-approve the tools an agent may
    # legitimately need inside this throwaway copy. The agent's own `tools` list still
    # limits what it can actually call.
    res = claude_json([prompt, "--agent", agent, "--permission-mode", opts.permission_mode,
                       "--allowedTools", *opts.allow, "--max-budget-usd", str(opts.budget)],
                      work, opts.timeout)
    report = res.get("result") or ""
    after = fingerprint(work)
    touched = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    status = "\n".join(touched)  # files the agent created, modified or deleted
    diff = ""
    for f in touched[:25]:
        old = snapshot / f if (snapshot / f).exists() else Path("/dev/null")
        new = work / f if (work / f).exists() else Path("/dev/null")
        diff += subprocess.run(["diff", "-u", "--label", f"a/{f}", "--label", f"b/{f}", str(old), str(new)],
                               capture_output=True, text=True, errors="replace").stdout

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
    ap.add_argument("--permission-mode", default="acceptEdits",
                    help="permission mode for the agent under test (default: acceptEdits)")
    ap.add_argument("--allow", nargs="*", default=["Bash", "WebFetch", "WebSearch"],
                    help="tools pre-approved for the agent under test (default: Bash WebFetch WebSearch)")
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
