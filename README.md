# Claude Code subagent library

A tested library of custom [Claude Code subagents](https://code.claude.com/docs/en/sub-agents).
Each agent is task-shaped: it has a specific trigger, least-privilege tools, a step-by-step
procedure, and a fixed report format. No "senior Python expert" personas.

Every agent in this library is:

* **Validated statically.** `scripts/validate_agents.py` catches the mistakes Claude Code
  hides from you: misspelled tool names are silently dropped, unknown frontmatter keys are
  ignored, and an agent with no `tools` line inherits *every* tool.
* **Load-tested** against the real CLI (`scripts/test_loading.sh`).
* **Routing-tested.** Realistic requests go to the right agent (`tests/routing/cases.yaml`).
* **Behavior-tested.** Each agent runs against a deliberately broken sample app
  (`tests/fixtures/sample-app`), and a separate grader call scores its report against a
  rubric (`tests/behavior/cases/`).

## Install

```bash
git clone https://github.com/nickolasmisling/Agents.git && cd Agents

./install.sh                      # copy every agent to ~/.claude/agents (all projects)
./install.sh --link               # symlink instead, so `git pull` updates them
./install.sh --project ../my-app  # install into one project's .claude/agents
./install.sh --category review --category testing   # just some categories
./install.sh --only code-reviewer,debugger          # just some agents
./install.sh --uninstall          # remove what this repo installed
```

Or install as a Claude Code plugin:

```
/plugin marketplace add nickolasmisling/Agents
/plugin install agent-library@nickolasmisling-agents
```

Plugin agents are namespaced, so you invoke them as `agent-library:code-reviewer`.

Restart Claude Code after installing so it picks up the new agents.

## Using them

Claude delegates on its own when a request matches an agent's description. A few agents
are marked to be used **proactively**, meaning Claude should reach for them without being
asked:

* `code-reviewer`
* `security-reviewer`
* `test-runner`
* `debugger`
* `build-fixer`
* `change-verifier`
* `gxp-data-integrity-reviewer`

Automatic delegation is probabilistic. When a step matters, name the agent:

```
Use the migration-reviewer agent on db/migrations/002_add_site.sql
@"security-reviewer (agent)" check the login changes
```

To pin every agent to one model (for example, on a budget), set
`CLAUDE_CODE_SUBAGENT_MODEL=sonnet`.

## Catalog

<!-- catalog:start -->
**34 agents** in 7 categories.

### Code review & auditing

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`accessibility-reviewer`](.claude/agents/review/accessibility-reviewer.md) | WCAG 2.2 AA accessibility review of UI code (React/JSX/TSX, Vue, Angular, Svelte, HTML, Razor/Blazor): alt text, keyboard access, form labels, color contrast, focus and modal handling, ARIA misuse, live regions, target size. | sonnet | read-only |
| [`api-contract-reviewer`](.claude/agents/review/api-contract-reviewer.md) | Reviews API contracts (REST handlers, OpenAPI, GraphQL, gRPC/protobuf, Kafka/Service Bus/MQTT event schemas, public library signatures) for breaking changes vs the base branch, versioning, naming/error-model/pagination consistency, HTTP semantics and idempotency. | sonnet | read-only |
| [`architecture-reviewer`](.claude/agents/review/architecture-reviewer.md) | Reviews the structure of a change or codebase area: layering violations, dependency direction and cycles, module/service boundaries, coupling, leaking abstractions, pattern drift, testability seams, fit with documented architecture/ADRs. | opus | read-only |
| [`code-reviewer`](.claude/agents/review/code-reviewer.md) | Reviews the current change (uncommitted diff, else branch vs main) for correctness bugs: logic errors, off-by-one, null handling, broken error paths, resource leaks, API misuse, caller regressions, CLAUDE.md violations. | sonnet | read-only |
| [`concurrency-reviewer`](.claude/agents/review/concurrency-reviewer.md) | Reviews concurrent code for races, deadlocks, lost updates and leaks, each shown as a concrete interleaving: threads, async/await, locks, goroutines/channels, thread pools, background jobs, timers, shared caches, DB transactions and isolation. | opus | read-only |
| [`dependency-auditor`](.claude/agents/review/dependency-auditor.md) | Supply-chain audit of manifests and lockfiles with native tools (npm/pnpm/yarn audit, pip-audit, dotnet list package --vulnerable, govulncheck, cargo audit): known advisories, floating versions, deprecated, unused or duplicate packages, copyleft licenses. | haiku | read-only + web |
| [`finding-verifier`](.claude/agents/review/finding-verifier.md) | Dispatched with ONE reported finding (bug, vulnerability, failing-test claim, review comment) and its location to try to disprove it: traces callers, data flow and mitigations, runs a throwaway repro, returns a JSON verdict. | opus | read-only |
| [`security-reviewer`](.claude/agents/review/security-reviewer.md) | Security review of changed code (git diff HEAD) or named paths: injection, XSS, authz/IDOR, CSRF, SSRF, path traversal, unsafe deserialization, weak crypto, hardcoded secrets, insecure defaults. | opus | read-only |
| [`silent-failure-hunter`](.claude/agents/review/silent-failure-hunter.md) | Hunts error handling that hides failures in the diff or named paths: empty or catch-all catches, log-and-continue, errors returned as HTTP 200, discarded Go errors, unhandled promise rejections, retries without backoff, missing timeouts, parse-failure defaults. | sonnet | read-only |
| [`spec-compliance-reviewer`](.claude/agents/review/spec-compliance-reviewer.md) | Checks an implementation (current diff or named paths) against a supplied spec, ticket, plan, PRD or acceptance criteria, requirement by requirement: MET / PARTIAL / MISSING / DEVIATES with path:line evidence, plus scope creep and misread requirements. | sonnet | read-only |

### Testing

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`change-verifier`](.claude/agents/testing/change-verifier.md) | Skeptically verifies a claimed fix or feature works before it is called done: rebuild, relevant tests re-run after the last edit, lint/typecheck, direct exercise (CLI, script, curl), each acceptance criterion checked with evidence. | sonnet | read-only |
| [`e2e-test-writer`](.claude/agents/testing/e2e-test-writer.md) | Writes browser end-to-end tests (Playwright preferred; Cypress, Selenium or WebdriverIO only if the repo already uses them) for a critical user journey and its key error states, with role/label/test-id locators, auto-waiting assertions and isolated data, then runs them headless. | sonnet | read/write |
| [`flaky-test-investigator`](.claude/agents/testing/flaky-test-investigator.md) | Diagnoses intermittent (flaky) tests: reproduces with repeated, shuffled, isolated and time-shifted runs, finds the nondeterminism (timing, order/shared state, unseeded randomness, clock/time zone, unordered results, network, leaks, parallel races, float) and makes the test deterministic, with before/after pass rates. | sonnet | read/write |
| [`release-readiness-gate`](.claude/agents/testing/release-readiness-gate.md) | Go/no-go gate before tagging, cutting a release or deploying: re-runs tests on the release commit, checks build, version bumps, CHANGELOG vs. commits since the last tag, migrations, config/env vars, feature flags, added TODOs, dependency audit, rollback plan and monitoring. | opus | read-only |
| [`test-gap-analyzer`](.claude/agents/testing/test-gap-analyzer.md) | Finds what is NOT tested in the current diff or named modules, ranked by risk: maps functions and branches to the tests that exercise them (grep, coverage tools) and flags weak tests (no assertions, mocking the unit under test, can't-fail, snapshot-only, time/random-dependent). | sonnet | read-only |
| [`test-runner`](.claude/agents/testing/test-runner.md) | Runs the project's tests (detected runner, narrowest relevant subset first) and returns a compact digest: command, exit code, pass/fail/skip counts, and each failure's test id, first error line and file:line. | haiku | read-only |
| [`test-writer`](.claude/agents/testing/test-writer.md) | Writes unit and integration tests for named code or the current diff in the repo's existing framework and style: happy path, boundaries, error paths, regression tests for known bugs; runs them and reports evidence and any bugs found. | sonnet | read/write |

### Debugging & diagnosis

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`build-fixer`](.claude/agents/debugging/build-fixer.md) | Gets a failing build, compile, type-check, lint or dependency restore green with the smallest correct diff (tsc, eslint, mypy, ruff, dotnet, go, cargo, maven, gradle), fixing types, imports and call sites instead of suppressing errors. | sonnet | read/write |
| [`ci-failure-investigator`](.claude/agents/debugging/ci-failure-investigator.md) | Investigates a failed CI/CD run (GitHub Actions, Azure Pipelines, GitLab CI, Jenkins): pulls the logs, finds the failing step and first real error, compares with the last green run, and classifies the cause (code, flaky test, toolchain drift, registry outage, secrets, YAML, timeout). | sonnet | read-only |
| [`debugger`](.claude/agents/debugging/debugger.md) | Root-causes runtime errors, exceptions, crashes, consistently failing tests and wrong output: reproduces the failure, tests hypotheses with cheap experiments, fixes the root cause minimally, adds a regression test and re-runs. | opus | read/write |
| [`git-bisector`](.claude/agents/debugging/git-bisector.md) | Finds the commit that introduced a regression with `git bisect run`: takes a good ref (tag, commit, last release), a bad ref (default HEAD) and a failing test or command (builds one if none), and returns the first bad commit, the responsible diff hunk and the bisect log. | sonnet | read-only |
| [`log-analyzer`](.claude/agents/debugging/log-analyzer.md) | Digests large logs, traces and exports (plain text, JSON lines, syslog, CI logs, Windows events): time range, first failure, normalized error clusters with counts, timeline around deploys/restarts, correlated trace ids, red herrings, likely root cause with line-cited evidence. | sonnet | read-only |
| [`performance-analyst`](.claude/agents/debugging/performance-analyst.md) | Finds and quantifies performance bottlenecks (slow endpoints, jobs, tests, pages; memory growth; bundle size) by profiling and benchmarking, labelling anything unmeasured a hypothesis: N+1 queries, quadratic loops, sync I/O, sync-over-async, chatty calls, unbounded caches, re-renders. | sonnet | read-only |

### Architecture & refactoring

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`code-simplifier`](.claude/agents/architecture/code-simplifier.md) | Behavior-preserving cleanup of recently changed or named code: guard clauses for deep nesting, splitting long functions, removing duplication, dead code and needless abstraction, clearer names, simpler conditionals; tests run before and after. | inherit | read/write |
| [`dependency-upgrader`](.claude/agents/architecture/dependency-upgrader.md) | Upgrades a library, framework, runtime or SDK across major versions (React 17->18, Django 3->5, Spring Boot 2->3, Node 16->22, Python 3.8->3.12, Angular, EF Core) from official migration guides, with codemods, lockfile, CI and docs updated and tests green per step. | sonnet | read/write + web |
| [`legacy-code-analyst`](.claude/agents/architecture/legacy-code-analyst.md) | Extracts business rules from legacy or undocumented code (stored procedures, VB6/VBA, WebForms, classic ASP, COBOL, Excel macros, batch/cron jobs, old Java/.NET): rules catalog with path:line, data flows, hidden dependencies, side effects, error behavior, dead paths, fact vs inference. | sonnet | read-only |
| [`manufacturing-integration-engineer`](.claude/agents/architecture/manufacturing-integration-engineer.md) | Designs and reviews ISA-95 Level 2-4 integrations: MES<->ERP/SAP (B2MML), OPC UA, MQTT/Sparkplug B, historians (PI), ISA-88 batch, LIMS, label printing, serialization; checks buffering, idempotency, ordering, timestamps, reconciliation. | opus | read/write |

### Documentation

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`adr-writer`](.claude/agents/docs/adr-writer.md) | Records an architecture decision as an ADR (MADR or the repo's template): context, options with pros/cons, decision, consequences, status, date, links to code/PRs; numbered in the ADR folder, index updated. Unstated rationale becomes an open question. | sonnet | read/write |
| [`docs-sync-editor`](.claude/agents/docs/docs-sync-editor.md) | Fixes documentation that drifted after a code change, with minimal line edits: README, docs/*.md and docstrings that still cite renamed or removed CLI flags, config keys, env vars, function signatures, endpoints, setup steps or examples. | sonnet | read/write |
| [`technical-writer`](.claude/agents/docs/technical-writer.md) | Writes NEW documentation: README, getting-started, how-to guides, runbooks, API usage guides, onboarding and troubleshooting pages, architecture overviews, with every command, flag, env var and path verified against the repo. | sonnet | read/write |

### Data & databases

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`data-analyst`](.claude/agents/data/data-analyst.md) | Answers questions from data files (CSV, TSV, Excel, JSON, Parquet) and databases via read-only SQL: profiles first (rows, types, nulls, duplicates, ranges, dates), flags data quality issues, then computes the answer with reproducible pandas/DuckDB/SQL code, group comparisons and statistical caveats. | sonnet | read/write |

### Git & pull-request workflow

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`changelog-writer`](.claude/agents/git/changelog-writer.md) | Updates CHANGELOG.md's Unreleased section from commits and PRs since the last tag: end-user entries under Added/Changed/Deprecated/Removed/Fixed/Security, refactor/test/chore/CI noise dropped, BREAKING changes flagged with migration notes, PR numbers/SHAs cited. | haiku | read/write |
| [`git-historian`](.claude/agents/git/git-historian.md) | Answers why code is the way it is from version control: when and why a line, function or file changed, which commit, PR or ticket (INC-, JIRA-, #123) introduced it, and who knows it, via git log -L, pickaxe, blame past renames and PR lookups. | sonnet | read-only |
| [`pr-description-writer`](.claude/agents/git/pr-description-writer.md) | Drafts a pull request (or merge request) title and description from the branch diff (base...HEAD), mirroring the repo's PR template if present: summary, grouped changes, risk and rollout, testing evidence, linked issues. | haiku | read-only |
<!-- catalog:end -->

## What's deliberately not here

* **Language personas** (python-pro, csharp-expert, react-specialist). The main model
  already knows these languages. In practice these agents rarely trigger and add little.
* **Duplicates of built-in agents.** Claude Code already ships `Explore` for finding code
  and `Plan` for implementation plans.
* **A commit-message writer.** The job takes a handful of tool calls, which isn't worth the
  overhead of a subagent.

## Testing

```bash
make test             # free: static validation + CLI load test
make test-routing     # ~$1-3: does Claude pick the right agent for 60+ realistic requests?
make test-behavior    # ~$30-60: run every agent on the seeded fixture and grade it
python3 scripts/test_behavior.py --only code-reviewer debugger   # a subset
```

Behavior tests run each agent with `--agent <name>` in a scratch copy of the fixture,
with Bash pre-approved in that copy (`--allowedTools Bash`). The fixture's answer key lives
in `tests/fixtures/answer-key/`, outside the directory the agents can see.

## Contributing an agent

1. Read [docs/STYLE_GUIDE.md](docs/STYLE_GUIDE.md), or ask the `subagent-author` agent to
   draft one.
2. Add `.claude/agents/<category>/<name>.md`.
3. Add a routing case and a behavior case.
4. Run `make test` and `make catalog`, and optionally
   `python3 scripts/test_behavior.py --only <name>`.

## License

Public domain ([Unlicense](LICENSE)).
