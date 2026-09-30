# Test results

Measured with Claude Code 2.1.284 in a Linux container, September 2026. Each
section says what was run so it can be reproduced (`make test`,
`make test-routing`, `make test-behavior`).

## Summary

| Check | Result |
| --- | --- |
| Static validation (`validate_agents.py --strict`) | 61 agents, 0 errors, 0 warnings |
| Case lint (`test_behavior.py --lint`) | 62 cases, 0 problems |
| Load: project agents / plugin (`test_loading.sh`) | 61/61 and 61/61 registered |
| Routing, select mode (68 requests) | 68/68 correct |
| Routing, live mode, agents only | 8/20 delegated correctly |
| Routing, live mode, with `agent-routing.md` in CLAUDE.md | **20/20**, and 5/5 near-misses not over-delegated |
| Behavior (62 graded cases) | all 62 passed on the current agents (details below) |

## Routing

**Select mode** asks the main agent which subagent it would delegate a request to,
without doing the work. All 68 cases pass, including sibling near-misses (flaky test
vs debugger, bisect vs history, container-engineer vs iac-reviewer, docs-sync-editor
vs technical-writer, dotnet-modernizer vs dependency-upgrader).

**Live mode** runs the request for real in a copy of the fixture and reads which
agents actually ran (`subagent_stats.by_type`). This is the number that matters in
daily use, and it shows that good descriptions alone are not enough:

| Same 20 requests | Delegated to the right agent | Done by the main agent itself |
| --- | --- | --- |
| Agents installed, no routing section | 8 | 12 |
| Agents + `docs/ROUTING.md` in CLAUDE.md | 20 | 0 |

With the routing section, the five near-miss requests still behaved correctly: a
commit message, a file lookup and a Claude API question were answered directly, the
Claude Code question went to the built-in `claude-code-guide`, and the new-system
plan went to the built-in `Plan`. Importing the file with `@.claude/agent-routing.md`
instead of pasting it gave the same result (3/3 on requests that failed without it).
`install.sh` writes this file, filtered to the agents you install.

Wrong picks were never the problem: in every miss, the main agent simply did the work
itself.

## Behavior

Each case runs one agent (`claude -p --agent <name>`) on a scratch copy of
`tests/fixtures/sample-app`, a small polyglot app with about 150 seeded defects and
false-positive traps. A separate grader call scores the agent's final report and
file changes against a rubric of must, should and must-not items. Read-only agents
fail on any file change. Many cases also run a shell `check` (tests pass, conflict
markers gone, database unchanged, git history intact). Every case was written by one
agent and independently checked by another, which replayed the setup, confirmed each
rubric fact against the code and mutation-tested the checks.

Final full run: 53/62. The nine failures were real agent defects or noise, fixed
as follows, after which all nine cases pass (requirements-analyst twice in a row):

| Agent | What went wrong | Fix |
| --- | --- | --- |
| bash-scripter | A "sandbox" run of the script under review reached the real `curl`, because the script re-exported `PATH` past the stubs | No end-to-end runs without network isolation; PATH stubs declared unsafe for scripts that set PATH or call absolute paths |
| dependency-auditor | Added CVE aliases from memory to rows where `npm audit` printed only GHSA ids | Ids only as printed; aliases only from a fetched, cited OSV record |
| docs-researcher | Answered without checking the project's declared runtime range | Mandatory, cited first step; answer must hold across the range |
| log-analyzer | Called warnings red herrings from totals | Before/after split counts required |
| powershell-scripter | Fixed the script but never said the old one exited 0 on failure | Report caller-visible changes as before -> after (now a style-guide rule) |
| claude-md-curator | Report said a stale command was removed; it was still in the file | Grep the final file for everything reported removed |
| requirements-analyst | Wrote unanswered business decisions as firm requirements; the first fix over-corrected and deferred everything | Three tiers: stated facts firm (with negative ACs), low-impact interpretations flagged, only open decisions TBD; added Edit |
| iac-reviewer | Grader marked an item missed while its own note said it was met | Grader prompt now judges substance, not wording |
| flaky-test-investigator | Run cut off by an API session limit | Re-run passed |

Earlier rounds found and fixed, among others: test-writer pinning a crash
(`pytest.raises(ZeroDivisionError)`) as expected behavior; e2e-test-writer breaking
the repo's existing `npm test`; code-simplifier giving no baseline; dotnet-modernizer
creating an options class without wiring `IOptions<T>`; database-architect burying
its ER diagram under 39k characters of DDL; subagent-auditor flagging an in-budget
description as MEDIUM.

### Model choice

Three agents started on `haiku` and moved to `sonnet` after failing their cases:
changelog-writer (summarized commit messages and missed a behavior-changing diff),
pr-description-writer (dropped required evidence labels, inconsistently between
runs) and dependency-auditor (invented a release date, miscounted major versions,
rated a dev-only advisory CRITICAL against its own rule). On `sonnet` each passed
repeatedly and was no more expensive per run, because it needed fewer turns.
test-runner stays on `haiku`.

### Harness problems found by testing the tests

* Setup scripts ran under `/bin/sh` (dash), which rejects `set -o pipefail`.
* The grader saw only the first 30k characters of long reports and diffs; lockfiles
  and build output could hide the agent's real changes. Generated and ignored files
  are now listed by name only.
* `GIT_AUTHOR_*` variables in the runner overrode scenario scripts' per-commit
  authors (which "who wrote this?" cases depend on).
* Live routing counted "no delegation" as a failure even when that was the expected
  outcome.

## Caveats

* Grading is done by an LLM against written rubrics; most cases passed on a single
  run. Treat a single failure as a signal to look, not proof of a regression.
* The container had no dotnet, pwsh, terraform or shellcheck, so dotnet-modernizer,
  powershell-scripter and iac-reviewer were graded on their output, not on a build or
  analyzer run.
* Frontmatter `hooks` never fired in our tests, so no agent relies on them.
* Costs per behavior case ranged from about $0.04 (test-runner) to $1.20
  (llm-eval-designer); a full behavior run cost about $14.
