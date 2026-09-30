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
import re
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
do not count. Judge substance, not wording: if your own evidence shows an item is met, mark it
met; if it shows the item is missed, say exactly what is missing. Do not use tools.

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


GITCONFIG = Path(tempfile.gettempdir()) / "agent-behavior-tests.gitconfig"


def sh(cmd: str, cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess:
    # Setup/check commands can reference $FIXTURES (tests/fixtures) and $REPO_ROOT.
    # The fallback git identity comes from a config file, not GIT_AUTHOR_* variables, so
    # scenario scripts' own `git -c user.name=...` authors still take precedence.
    if not GITCONFIG.exists():
        GITCONFIG.write_text("[user]\n\tname = Fixture\n\temail = fixture@example.com\n"
                             "[init]\n\tdefaultBranch = main\n[advice]\n\tdetachedHead = false\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_"))}
    env.update(FIXTURES=str(FIXTURES), REPO_ROOT=str(ROOT), PYTHONDONTWRITEBYTECODE="1",
               GIT_CONFIG_GLOBAL=str(GITCONFIG))
    return subprocess.run(cmd, shell=True, executable="/bin/bash", cwd=cwd, capture_output=True,
                          text=True, timeout=timeout, env=env)


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


GENERATED = re.compile(
    r"(^|/)(package-lock\.json|npm-shrinkwrap\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|uv\.lock|"
    r"Pipfile\.lock|Cargo\.lock|go\.sum|packages\.lock\.json|composer\.lock|Gemfile\.lock)$"
    r"|(^|/)(dist|build|out|bin|obj|target|coverage|test-results|playwright-report|blob-report|"
    r"\.next|\.nuxt|\.venv|venv|\.ruff_cache|\.mypy_cache)/"
    r"|\.(min\.js|map|pyc|zip|png|jpg|jpeg|gif|ico|pdf|db|sqlite)$")
DIFF_BUDGET = 90_000


def render_diff(touched: list[str], before: Path, after: Path) -> str:
    """Unified diff of what the agent changed, with source files first.

    Lockfiles, build output, caches, binaries and gitignored files are listed by name
    only, so they can't push the agent's real changes out of the grader's view.
    """
    ignored = set(subprocess.run(["git", "check-ignore", "--no-index", "--stdin"], cwd=after, input="\n".join(touched),
                                 capture_output=True, text=True).stdout.split())
    listed = [f for f in touched if GENERATED.search(f) or f in ignored]
    source = [f for f in touched if f not in listed]
    out = ""
    for f in source:
        old = before / f if (before / f).exists() else Path("/dev/null")
        new = after / f if (after / f).exists() else Path("/dev/null")
        out += subprocess.run(["diff", "-u", "--label", f"a/{f}", "--label", f"b/{f}", str(old), str(new)],
                              capture_output=True, text=True, errors="replace").stdout
    if len(out) > DIFF_BUDGET:
        out = out[:DIFF_BUDGET] + f"\n[... diff truncated at {DIFF_BUDGET} chars ...]\n"
    if listed:
        out += "\n[generated, lock, build or ignored files changed; content omitted]\n" + "\n".join(listed[:200])
    return out


CASE_KEYS = {"agent", "fixture", "setup", "keep_setup_uncommitted", "prompt", "read_only", "check", "rubric"}


def lint_cases(paths: list[Path]) -> list[str]:
    """Structural checks on case files; returns a list of problems."""
    agents = {p.stem for p in (ROOT / ".claude" / "agents").rglob("*.md")}
    problems = []
    for p in paths:
        try:
            c = yaml.safe_load(p.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            problems.append(f"{p.name}: invalid YAML: {e}")
            continue
        if not isinstance(c, dict):
            problems.append(f"{p.name}: not a mapping")
            continue
        for k in set(c) - CASE_KEYS:
            problems.append(f"{p.name}: unknown key {k!r}")
        if c.get("agent") not in agents:
            problems.append(f"{p.name}: agent {c.get('agent')!r} is not defined in .claude/agents")
        if not isinstance(c.get("prompt"), str) or not c["prompt"].strip():
            problems.append(f"{p.name}: prompt must be a non-empty string")
        if not (FIXTURES / c.get("fixture", "sample-app")).is_dir():
            problems.append(f"{p.name}: fixture {c.get('fixture')!r} not found")
        for k in ("read_only", "keep_setup_uncommitted"):
            if k in c and not isinstance(c[k], bool):
                problems.append(f"{p.name}: {k} must be true/false")
        for k in ("setup", "check"):
            if k in c and not isinstance(c[k], str):
                problems.append(f"{p.name}: {k} must be a string")
        rubric = c.get("rubric") or {}
        if not rubric.get("must"):
            problems.append(f"{p.name}: rubric.must is empty")
        for k in ("must", "should", "must_not"):
            for i, item in enumerate(rubric.get(k) or []):
                if not isinstance(item, str):
                    problems.append(f"{p.name}: rubric.{k}[{i}] is a {type(item).__name__}, not a string (quote it)")
    missing = agents - {yaml.safe_load(p.read_text())["agent"] for p in paths if p.exists()}
    for a in sorted(missing):
        problems.append(f"no behavior case for agent {a!r}")
    return problems


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
    diff = render_diff(touched, snapshot, work)

    check_ok, check_out = True, ""
    if case.get("check"):
        r = sh(case["check"], work)
        check_ok, check_out = r.returncode == 0, (r.stdout + r.stderr)[-1500:]

    judge_prompt = JUDGE_PROMPT.format(agent=agent, prompt=prompt, report=report[:120000],
                                       status=status or "(no changes)", diff=diff or "(none)",
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
    ap.add_argument("--lint", action="store_true", help="only validate case files (no model calls)")
    args = ap.parse_args()

    paths = sorted(CASES_DIR.glob("*.yaml"))
    if args.lint:
        problems = lint_cases(paths)
        for prob in problems:
            print(f"ERROR  {prob}")
        print(f"{len(paths)} case file(s): {len(problems)} problem(s)")
        return 1 if problems else 0
    if not shutil.which("claude"):
        sys.exit("the `claude` CLI must be on PATH")
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
