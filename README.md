# Claude Code subagent library

A tested library of custom [Claude Code subagents](https://code.claude.com/docs/en/sub-agents).
Each agent is task-shaped: it has a specific trigger, least-privilege tools, a step-by-step
procedure, and a fixed report format. No "senior Python expert" personas.

Every agent in this library is:

* **Validated statically.** `scripts/validate_agents.py` catches the mistakes Claude Code
  hides from you: misspelled tool names are silently dropped, unknown frontmatter keys are
  ignored, and an agent with no `tools` line inherits *every* tool.
* **Load-tested** against the real CLI (`scripts/test_loading.sh`).
* **Routing-tested.** Realistic requests go to the right agent (`tests/routing/cases.yaml`),
  both when Claude is asked to choose and when requests run for real.
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

The installer also writes `agent-routing.md` next to the agents directory and prints
one line to add to your CLAUDE.md. Do it: see [Using them](#using-them).

Or install as a Claude Code plugin:

```
/plugin marketplace add nickolasmisling/Agents
/plugin install agent-library@nickolasmisling-agents
```

Plugin agents are namespaced, so you invoke them as `agent-library:code-reviewer`.

Restart Claude Code after installing so it picks up the new agents.

## Using them

**Import the routing section into CLAUDE.md.** Good descriptions alone are not enough.
In live tests on 20 realistic requests, Claude delegated to the right agent only 8
times and did the rest itself. With the generated routing section in CLAUDE.md it
delegated correctly 20 times out of 20, and still answered trivial requests (a commit
message, a file lookup) itself ([details](docs/TEST_RESULTS.md#routing)):

```markdown
<!-- ~/.claude/CLAUDE.md, after ./install.sh -->
@~/.claude/agent-routing.md

<!-- or the project's CLAUDE.md, after ./install.sh --project . -->
@.claude/agent-routing.md
```

`install.sh` filters the routing file to the agents you installed. With the plugin
install, agents are named `agent-library:<name>`; importing `docs/ROUTING.md` should
still guide Claude, but that combination is untested.

A few agents are marked to be used **proactively**, meaning Claude should reach for
them without being asked:

* `code-reviewer`
* `security-reviewer`
* `test-runner`
* `debugger`
* `build-fixer`
* `change-verifier`
* `gxp-data-integrity-reviewer`

When a step matters, name the agent:

```
Use the migration-reviewer agent on db/migrations/002_add_site.sql
@"security-reviewer (agent)" check the login changes
```

To pin every agent to one model (for example, on a budget), set
`CLAUDE_CODE_SUBAGENT_MODEL=sonnet`.

### Optional: Microsoft Learn docs

`docs-researcher`, `dotnet-modernizer` and `powershell-scripter` can use the free
[Microsoft Learn MCP server](https://learn.microsoft.com/training/support/mcp) for
.NET, Azure, SQL Server and PowerShell docs. Without it, they fall back to web fetches.
Agents refer to MCP tools by full name, so register the server under exactly the name
`Microsoft_Learn`:

```bash
claude mcp add --transport http Microsoft_Learn https://learn.microsoft.com/api/mcp
```

If you register it under another name, the tool names won't match and Claude Code
silently drops them from these agents.

## Catalog

<!-- catalog:start -->
**61 agents** in 12 categories.

### Code review & auditing

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`accessibility-reviewer`](.claude/agents/review/accessibility-reviewer.md) | WCAG 2.2 AA accessibility (a11y) review of UI code (React, Vue, Angular, Svelte, HTML, Razor/Blazor): screen-reader and keyboard access, labels, contrast, focus, ARIA, target size; reports SC-cited fixes, never edits or claims conformance. | sonnet | read-only |
| [`api-contract-reviewer`](.claude/agents/review/api-contract-reviewer.md) | Reviews API contracts (REST handlers, OpenAPI, GraphQL, gRPC/protobuf, Kafka/Service Bus/MQTT event schemas, public library APIs) for breaking changes vs the base branch, versioning, naming/error-model/pagination consistency, HTTP semantics and idempotency. | sonnet | read-only |
| [`architecture-reviewer`](.claude/agents/review/architecture-reviewer.md) | Reviews structure of a change or code area: layering, dependency direction/cycles, module boundaries, coupling, leaky abstractions, pattern drift, testability, ADR fit. | opus | read-only |
| [`code-reviewer`](.claude/agents/review/code-reviewer.md) | Reviews the current change (uncommitted diff, else branch vs main) for correctness bugs: logic errors, off-by-one, null handling, broken error paths, resource leaks, API misuse, broken callers, CLAUDE.md violations. | sonnet | read-only |
| [`concurrency-reviewer`](.claude/agents/review/concurrency-reviewer.md) | Reviews code for race conditions, thread-safety, deadlocks, lost DB updates and async/goroutine leaks (threads, async/await, locks, channels, pools, jobs, timers, shared caches, transactions), each with a concrete interleaving. | opus | read-only |
| [`dependency-auditor`](.claude/agents/review/dependency-auditor.md) | Audits dependencies via manifests, lockfiles and native tools (npm/yarn audit, pip-audit, dotnet list package, govulncheck, cargo audit): vulnerable, outdated, deprecated, abandoned, unpinned, unused/duplicate packages, copyleft licenses. | sonnet | read-only + web |
| [`finding-verifier`](.claude/agents/review/finding-verifier.md) | Dispatched with ONE reported finding (bug, vulnerability, scanner alert, failing-test claim, review comment) and its location to try to disprove it: traces data flow and mitigations, runs a throwaway repro, returns a JSON verdict. | opus | read-only |
| [`security-reviewer`](.claude/agents/review/security-reviewer.md) | Security review of changed code or named paths: injection, XSS, authz/IDOR, CSRF, SSRF, path traversal, deserialization, weak crypto, hardcoded secrets, insecure defaults. | opus | read-only |
| [`silent-failure-hunter`](.claude/agents/review/silent-failure-hunter.md) | Finds swallowed exceptions and silent failures in a diff or named paths: empty/catch-all catches, log-and-continue, errors as HTTP 200 or defaults, discarded Go errors, unhandled rejections, lost writes, unsafe retries, missing timeouts. | sonnet | read-only |
| [`spec-compliance-reviewer`](.claude/agents/review/spec-compliance-reviewer.md) | Checks an implementation (diff or named paths) against a supplied ticket, spec, plan, PRD or acceptance criteria, requirement by requirement with path:line evidence, plus scope creep and misreadings. | sonnet | read-only |

### Testing

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`change-verifier`](.claude/agents/testing/change-verifier.md) | Independently proves a claimed fix or feature works by running it: rebuild, relevant tests, lint/typecheck, the CLI/function/endpoint, each acceptance criterion with evidence. | sonnet | read-only |
| [`e2e-test-writer`](.claude/agents/testing/e2e-test-writer.md) | Writes browser end-to-end tests (Playwright preferred; Cypress, Selenium or WebdriverIO only if the repo already uses them) for a login, checkout or form flow and its key error states, then runs them headless. | sonnet | read/write |
| [`flaky-test-investigator`](.claude/agents/testing/flaky-test-investigator.md) | Diagnoses intermittent (flaky) tests, incl. browser E2E: finds the nondeterminism (timing, order/shared state, randomness, clocks/time zones, unordered results, network, leaks, races, float) via repeated runs and makes the test deterministic. | sonnet | read/write |
| [`release-readiness-gate`](.claude/agents/testing/release-readiness-gate.md) | Go/no-go gate before tagging or deploying a release: re-runs tests on the release commit, then checks build, version bumps, CHANGELOG vs. commits since the last tag, migrations, config/secrets, flags, added TODOs, dependency audit, rollback and monitoring. | opus | read-only |
| [`test-gap-analyzer`](.claude/agents/testing/test-gap-analyzer.md) | Finds what is NOT tested in the current diff or named modules, ranked by risk: maps functions and branches to the tests that exercise them (grep, coverage tools) and flags weak tests (no assertions, self-mocking, can't-fail, snapshot-only, time/random). | sonnet | read-only |
| [`test-runner`](.claude/agents/testing/test-runner.md) | Runs the project's tests (detected runner, narrowest subset first) and returns a compact digest: command, exit code, pass/fail/skip counts, each failure's test id, first error line and file:line. | haiku | read-only |
| [`test-writer`](.claude/agents/testing/test-writer.md) | Writes unit, component and integration tests for named code or the current diff in the repo's existing framework and style: happy path, boundaries, error paths, regression and characterization tests; runs them and reports evidence and bugs found. | sonnet | read/write |

### Debugging & diagnosis

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`build-fixer`](.claude/agents/debugging/build-fixer.md) | Gets a failing build, compile, type-check, lint or dependency restore green with the smallest correct diff (tsc, eslint, mypy, ruff, dotnet, go, cargo, maven, gradle), fixing types, imports and call sites instead of suppressing errors. | sonnet | read/write |
| [`ci-failure-investigator`](.claude/agents/debugging/ci-failure-investigator.md) | Diagnoses a failed CI run (GitHub Actions, Azure Pipelines, GitLab CI, Jenkins): finds the failing step and first real error, compares with the last green run, classifies the cause (code, flaky, drift, outage, secrets, YAML, timeout) and routes the fix. | sonnet | read-only |
| [`debugger`](.claude/agents/debugging/debugger.md) | Root-causes and fixes bugs that fail every run: exceptions, stack traces, crashes, hangs, failing tests, wrong output. Reproduces (or builds a repro from a trace), proves the cause, fixes minimally, adds a regression test. | opus | read/write |
| [`git-bisector`](.claude/agents/debugging/git-bisector.md) | Finds the commit that introduced a regression with `git bisect run` from a good ref, a bad ref (default HEAD) and a check (builds one if none); returns the first bad commit, responsible hunk and bisect log. | sonnet | read-only |
| [`log-analyzer`](.claude/agents/debugging/log-analyzer.md) | Digests large logs, traces and exports (text, JSON lines, syslog, CI, Event Viewer CSV/.evtx): first failure, error clusters with counts, timeline around deploys/restarts, correlated ids, red herrings, likely root cause with line-cited evidence. | sonnet | read-only |
| [`performance-analyst`](.claude/agents/debugging/performance-analyst.md) | Finds and measures performance bottlenecks (slow endpoints, background jobs, tests, pages; memory growth; bundle size): N+1 queries, quadratic loops, sync I/O, sync-over-async, chatty calls, unbounded caches, re-renders. Unmeasured claims are labelled hypotheses. | sonnet | read-only |

### Architecture & refactoring

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`code-simplifier`](.claude/agents/architecture/code-simplifier.md) | Behavior-preserving refactoring of recently changed or named code: guard clauses, splitting long functions, removing duplication, dead code and needless abstraction, clearer names, simpler conditionals; tests before and after. | inherit | read/write |
| [`dependency-upgrader`](.claude/agents/architecture/dependency-upgrader.md) | Upgrades a library, framework, runtime or SDK across major (or runtime minor) versions (React 17->18, Django 3->5, Spring Boot 2->3, Python 3.8->3.12) per official migration guides, tests green per step. | sonnet | read/write + web |
| [`dotnet-modernizer`](.claude/agents/architecture/dotnet-modernizer.md) | Ports .NET Framework apps to modern .NET project by project: SDK-style csproj, MVC/Web API to ASP.NET Core, WCF to CoreWCF/gRPC, Web.config to appsettings, BinaryFormatter, Windows services, WinForms/WPF, EF6. | sonnet | read/write + web |
| [`legacy-code-analyst`](.claude/agents/architecture/legacy-code-analyst.md) | Extracts and documents business rules, data flows, dependencies, side effects of legacy code (stored procedures, VB6/VBA, Excel macros, WebForms, classic ASP, COBOL, batch/cron jobs, old Java/.NET) at path:line. | sonnet | read-only |
| [`manufacturing-integration-engineer`](.claude/agents/architecture/manufacturing-integration-engineer.md) | Designs and reviews ISA-95 Level 2-4 integrations: MES<->ERP/SAP (B2MML), OPC UA, MQTT/Sparkplug B, historians (PI), ISA-88 batch, LIMS, labels, serialization; checks buffering, idempotency, ordering, timestamps, reconciliation. | opus | read/write |

### Documentation

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`adr-writer`](.claude/agents/docs/adr-writer.md) | Records an architecture decision as an ADR in the repo's template or MADR: context, options with pros/cons, decision, consequences, status, date, links to code/PRs; numbered, index updated, unstated rationale kept as an open question. | sonnet | read/write |
| [`diagram-generator`](.claude/agents/docs/diagram-generator.md) | Generates Mermaid diagrams from the actual code: architecture, sequence (request/feature flow), ER (migrations/ORM models), state (status enums), class and CI pipeline diagrams, each node and edge traced to path:line and syntax-checked. | sonnet | read/write |
| [`docs-sync-editor`](.claude/agents/docs/docs-sync-editor.md) | Fixes docs that are out of date after a code change, with minimal edits: README, docs/*.md and docstrings citing renamed, removed or changed (defaults, types, methods) CLI flags, config keys, env vars, signatures, endpoints, setup steps or examples. | sonnet | read/write |
| [`technical-writer`](.claude/agents/docs/technical-writer.md) | Writes new docs: README, getting-started, how-to guides, runbooks, API usage guides, onboarding, troubleshooting, architecture overviews, doc comments; commands, flags, env vars and paths verified against the repo. | sonnet | read/write |

### Data & databases

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`data-analyst`](.claude/agents/data/data-analyst.md) | Answers questions from data files (CSV, TSV, Excel, JSON, Parquet) and database tables via read-only SQL: profiles first, flags quality issues, then computes the answer with reproducible pandas/DuckDB/SQL code, n per group and statistical caveats. | sonnet | read/write |
| [`database-architect`](.claude/agents/data/database-architect.md) | Designs new database schemas or major restructurings, or critiques an existing schema's design: keys, relationships, constraints, temporal/audit history, tenancy, partitioning, expand/contract migration. Returns DDL (not run), Mermaid ER diagram, rationale. | opus | read-only |
| [`migration-reviewer`](.claude/agents/data/migration-reviewer.md) | Reviews database schema migrations (raw SQL, EF Core, Alembic, Django, Flyway, Liquibase, Rails, Prisma, Knex) for production safety: drops/renames still used by code, locks/rewrites, running-app compatibility (expand/contract), ordering, rollback, idempotency, backfills. | sonnet | read-only |
| [`sql-query-tuner`](.claude/agents/data/sql-query-tuner.md) | Tunes slow SQL (SQL Server, PostgreSQL, MySQL/MariaDB, SQLite, Oracle): non-SARGable predicates, missing or redundant indexes, key lookups, bad estimates, parameter sniffing, OFFSET paging, blocking; proposes rewrites and index DDL with write cost, never runs them. | sonnet | read-only |

### DevOps, cloud & operations

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`bash-scripter`](.claude/agents/devops/bash-scripter.md) | Writes, reviews and hardens shell scripts (bash, sh/POSIX, zsh): strict mode and its pitfalls, quoting, safe rm, temp-file cleanup, argument parsing, exit codes, idempotency, GNU/BSD portability; runs shellcheck, shfmt, bash -n. | sonnet | read/write |
| [`ci-pipeline-engineer`](.claude/agents/devops/ci-pipeline-engineer.md) | Writes and fixes CI/CD pipeline YAML for GitHub Actions, Azure Pipelines and GitLab CI: build/test/deploy stages, reusable workflows and templates, caching, matrix builds, environments with approvals, OIDC instead of stored cloud secrets, SHA-pinned actions, least-privilege tokens. | sonnet | read/write |
| [`container-engineer`](.claude/agents/devops/container-engineer.md) | Writes and optimizes Dockerfiles, .dockerignore and docker-compose files: multi-stage builds, pinned slim/distroless bases, layer caching, non-root USER, BuildKit secrets, HEALTHCHECK, size reduction. | sonnet | read/write |
| [`iac-reviewer`](.claude/agents/devops/iac-reviewer.md) | Reviews infrastructure-as-code and deployment config (Terraform/OpenTofu, Bicep/ARM, CloudFormation/CDK, Pulumi, Kubernetes/Helm, Docker/compose) for public exposure, broad IAM/RBAC, secrets, encryption, pinning and pod security. | sonnet | read-only |
| [`observability-engineer`](.claude/agents/devops/observability-engineer.md) | Adds or improves observability in application code: structured JSON logs with trace ids and no secrets/PII, RED/USE metrics with bounded cardinality, OpenTelemetry tracing across async and queues, health/readiness endpoints, SLO burn-rate alerts. | sonnet | read/write |
| [`powershell-scripter`](.claude/agents/devops/powershell-scripter.md) | Writes, reviews and fixes PowerShell scripts and modules (.ps1/.psm1/.psd1) for Windows PowerShell 5.1 or PowerShell 7: -WhatIf/-Confirm support, strict error handling, approved verbs, parameter validation, no hardcoded credentials; runs PSScriptAnalyzer and Pester. | sonnet | read/write |

### Git & pull-request workflow

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`changelog-writer`](.claude/agents/git/changelog-writer.md) | Updates CHANGELOG.md's Unreleased section from commits/PRs since the last tag: end-user entries in Added/Changed/Deprecated/Removed/Fixed/Security, noise dropped, BREAKING changes flagged with migration notes, PR/SHA refs cited. Also drafts release notes (returned, unpublished). | sonnet | read/write |
| [`git-historian`](.claude/agents/git/git-historian.md) | Answers why code is the way it is from version control: when and why a line, function or file changed, which commit, PR or ticket (INC-, JIRA-, #123) introduced it, and who knows it, via git log -L, pickaxe, blame past renames and PR lookups. | sonnet | read-only |
| [`merge-conflict-resolver`](.claude/agents/git/merge-conflict-resolver.md) | Resolves git merge, rebase, cherry-pick, revert and stash-pop conflicts by combining the intent of both sides instead of picking one: reads base/ours/theirs and each side's commits, fixes semantic conflicts, builds, tests and stages. | opus | read/write |
| [`pr-description-writer`](.claude/agents/git/pr-description-writer.md) | Drafts a pull request (or merge request) title and description from the branch diff (base...HEAD), mirroring the repo's PR template if present: summary, grouped changes, risk and rollout, testing evidence, linked issues. | sonnet | read-only |

### AI engineering & Claude Code

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`claude-api-reviewer`](.claude/agents/ai/claude-api-reviewer.md) | Reviews code calling the Claude API, Anthropic SDKs or Agent SDK (incl. Bedrock/Vertex/Foundry) against current docs: model ids, tool_use loops, stop_reason, thinking, caching, history edits, 429/529 retries, keys, cost. | sonnet | read-only + web |
| [`claude-md-curator`](.claude/agents/ai/claude-md-curator.md) | Creates or maintains CLAUDE.md files (root, nested) and .claude/rules: runs every build/test/lint command they list, records non-obvious conventions, architecture pointers and gotchas, prunes stale, generic or derivable lines, proposes hooks for must-always rules. | sonnet | read/write |
| [`llm-eval-designer`](.claude/agents/ai/llm-eval-designer.md) | Designs and builds evals for LLM features (eval suite, golden dataset, LLM-as-judge, promptfoo): error analysis of real outputs, failure-mode taxonomy, code graders before calibrated judges, CI regression gate. | opus | read/write |
| [`mcp-server-builder`](.claude/agents/ai/mcp-server-builder.md) | Builds, extends or fixes Model Context Protocol (MCP) servers (TypeScript/Python): tool descriptions and schemas, resources, prompts, stdio/Streamable HTTP, auth, tool errors, output limits; tests with MCP Inspector. | sonnet | read/write + web |
| [`prompt-engineer`](.claude/agents/ai/prompt-engineer.md) | Writes and improves prompts for LLM features in application code: system prompts, tool descriptions, few-shot examples, JSON/structured-output schemas, RAG and classification/extraction prompts. | opus | read/write |
| [`subagent-auditor`](.claude/agents/ai/subagent-auditor.md) | Audits subagent definitions (.claude/agents, ~/.claude/agents): frontmatter, name clashes, missing/over-broad/stale tools, dated models, vague or overlapping descriptions, bodies that ask the user or lack an output contract; proposes routing prompts. | sonnet | read-only |
| [`subagent-author`](.claude/agents/ai/subagent-author.md) | Creates or improves Claude Code subagent files (.claude/agents/**/*.md, ~/.claude/agents) and drafts trigger and near-miss routing prompts. | opus | read/write + web |

### Compliance & regulated software

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`change-control-impact-assessor`](.claude/agents/compliance/change-control-impact-assessor.md) | Drafts a GxP change-control impact assessment (DRAFT, never approves) for a PR, branch or release of a validated system: class, GxP impact, affected URS, regression/revalidation scope, migration, rollback, evidence. | opus | read-only |
| [`csv-validation-author`](.claude/agents/compliance/csv-validation-author.md) | Drafts GxP computer system validation (CSV/CSA, GAMP 5) documents: system description, GAMP category, intended use, GxP impact, risk assessment, DRAFT URS, trace matrix, IQ/OQ/PQ or CSA protocols, never executed. | opus | read/write |
| [`gxp-data-integrity-reviewer`](.claude/agents/compliance/gxp-data-integrity-reviewer.md) | Reviews data integrity of GxP-regulated code (pharma, biotech, medical device, labs, QA) touching regulated records, audit trails, e-signatures, timestamps, user identity/roles or record edits/deletes; maps findings to ALCOA+ and 21 CFR Part 11 / EU Annex 11. | opus | read-only |

### Product & requirements

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`i18n-engineer`](.claude/agents/product/i18n-engineer.md) | Internationalizes apps: extracts hardcoded UI strings to i18next, react-intl/FormatJS, gettext/Babel, .resx/IStringLocalizer or Angular i18n; locale-aware dates, time zones, numbers, currency; ICU plurals, RTL; drafts es/pt-BR translations for review. | sonnet | read/write |
| [`requirements-analyst`](.claude/agents/product/requirements-analyst.md) | Turns a vague request, ticket, email or meeting note into testable, code-grounded requirements for new or changed features: user stories or URS "shall" items with IDs, Given/When/Then acceptance criteria, NFRs, edge cases, open questions. | sonnet | read/write |

### Research

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`docs-researcher`](.claude/agents/research/docs-researcher.md) | Answers how-to, config and API-deprecation questions on a library, framework, SDK, CLI or cloud service from official docs, with citations and a version-matched example. | sonnet | read-only + web |
| [`feature-tracer`](.claude/agents/research/feature-tracer.md) | Explains how an existing feature works end to end: entry point (route, CLI command, UI event, job, message handler) through validation, services and domain logic to data stores, side effects and response at path:line, with config flags, error paths and tests. | sonnet | read-only |
| [`library-evaluator`](.claude/agents/research/library-evaluator.md) | Compares candidate libraries, frameworks or services ('X vs Y', 'what should we use for…', 'alternative to <lib>') and recommends one with a cited table: stack fit, maintenance, license, security history, transitive deps, platform (Windows, air-gapped), exit cost. | sonnet | read-only + web |
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
make test             # free: static validation, case lint, CLI load test (project + plugin)
make test-routing     # ~$6: does Claude pick the right agent for 68 realistic requests?
make test-routing-live ARGS="--claude-md docs/ROUTING.md"   # runs requests for real
make test-behavior    # ~$14: run every agent on the seeded fixture and grade it
python3 scripts/test_behavior.py --only code-reviewer debugger   # a subset
```

Results and the defects testing caught are in [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md).
Behavior tests run each agent with `--agent <name>` in a scratch copy of the fixture,
with Bash pre-approved in that copy (`--allowedTools Bash`); run them in a container or
VM. The fixture's answer key lives in `tests/fixtures/answer-key/`, outside the
directory the agents can see.

## Contributing an agent

1. Read [docs/STYLE_GUIDE.md](docs/STYLE_GUIDE.md), or ask the `subagent-author` agent to
   draft one.
2. Add `.claude/agents/<category>/<name>.md`.
3. Add a routing case and a behavior case.
4. Run `make test` and `make catalog`, and optionally
   `python3 scripts/test_behavior.py --only <name>`.

## License

Public domain ([Unlicense](LICENSE)).
