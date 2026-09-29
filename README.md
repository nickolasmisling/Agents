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
**61 agents** in 12 categories.

### Code review & auditing

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`accessibility-reviewer`](.claude/agents/review/accessibility-reviewer.md) | WCAG 2.2 AA accessibility (a11y) review of UI code (React, Vue, Angular, Svelte, HTML, Razor/Blazor): screen-reader and keyboard access, labels, contrast, focus, ARIA, target size; reports SC-cited fixes, never edits or claims conformance. | sonnet | read-only |
| [`api-contract-reviewer`](.claude/agents/review/api-contract-reviewer.md) | Reviews API contracts (REST handlers, OpenAPI, GraphQL, gRPC/protobuf, Kafka/Service Bus/MQTT event schemas, public library APIs) for breaking changes vs the base branch, versioning, naming/error-model/pagination consistency, HTTP semantics and idempotency. | sonnet | read-only |
| [`architecture-reviewer`](.claude/agents/review/architecture-reviewer.md) | Reviews structure of a change or code area: layering, dependency direction/cycles, module boundaries, coupling, leaky abstractions, pattern drift, testability, ADR fit. | opus | read-only |
| [`code-reviewer`](.claude/agents/review/code-reviewer.md) | Reviews the current change (uncommitted diff, else branch vs main) for correctness bugs: logic errors, off-by-one, null handling, broken error paths, resource leaks, API misuse, broken callers, CLAUDE.md violations. | sonnet | read-only |
| [`concurrency-reviewer`](.claude/agents/review/concurrency-reviewer.md) | Reviews code for race conditions, thread-safety, deadlocks, lost DB updates and async/goroutine leaks (threads, async/await, locks, channels, pools, jobs, timers, shared caches, transactions), each with a concrete interleaving. | opus | read-only |
| [`dependency-auditor`](.claude/agents/review/dependency-auditor.md) | Supply-chain audit of manifests and lockfiles with native tools (npm/pnpm/yarn audit, pip-audit, dotnet list package --vulnerable, govulncheck, cargo audit): known advisories, floating versions, deprecated, unused or duplicate packages, copyleft licenses. | haiku | read-only + web |
| [`finding-verifier`](.claude/agents/review/finding-verifier.md) | Dispatched with ONE reported finding (bug, vulnerability, scanner alert, failing-test claim, review comment) and its location to try to disprove it: traces data flow and mitigations, runs a throwaway repro, returns a JSON verdict. | opus | read-only |
| [`security-reviewer`](.claude/agents/review/security-reviewer.md) | Security review of changed code or named paths: injection, XSS, authz/IDOR, CSRF, SSRF, path traversal, deserialization, weak crypto, hardcoded secrets, insecure defaults. | opus | read-only |
| [`silent-failure-hunter`](.claude/agents/review/silent-failure-hunter.md) | Finds swallowed exceptions and silent failures in a diff or named paths: empty/catch-all catches, log-and-continue, errors as HTTP 200 or defaults, discarded Go errors, unhandled rejections, lost writes, unsafe retries, missing timeouts. | sonnet | read-only |
| [`spec-compliance-reviewer`](.claude/agents/review/spec-compliance-reviewer.md) | Checks an implementation (diff or named paths) against a supplied ticket, spec, plan, PRD or acceptance criteria, requirement by requirement with path:line evidence, plus scope creep and misreadings. | sonnet | read-only |

### Testing

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`change-verifier`](.claude/agents/testing/change-verifier.md) | Independently proves a claimed fix or feature works by running it: rebuild, relevant tests, lint/typecheck, the CLI/function/endpoint, each acceptance criterion with evidence. | sonnet | read-only |
| [`e2e-test-writer`](.claude/agents/testing/e2e-test-writer.md) | Writes browser end-to-end tests (Playwright preferred; Cypress, Selenium or WebdriverIO only if the repo already uses them) for a login, checkout or form flow and its key error states, then runs them headless. | sonnet | read/write |
| [`flaky-test-investigator`](.claude/agents/testing/flaky-test-investigator.md) | Diagnoses intermittent (flaky) tests: reproduces with repeated, shuffled, isolated and time-shifted runs, finds the nondeterminism (timing, order/shared state, unseeded randomness, clock/time zone, unordered results, network, leaks, parallel races, float) and makes the test deterministic, with before/after pass rates. | sonnet | read/write |
| [`release-readiness-gate`](.claude/agents/testing/release-readiness-gate.md) | Go/no-go gate before tagging or deploying a release: re-runs tests on the release commit, then checks build, version bumps, CHANGELOG vs. commits since the last tag, migrations, config/secrets, flags, added TODOs, dependency audit, rollback and monitoring. | opus | read-only |
| [`test-gap-analyzer`](.claude/agents/testing/test-gap-analyzer.md) | Finds what is NOT tested in the current diff or named modules, ranked by risk: maps functions and branches to the tests that exercise them (grep, coverage tools) and flags weak tests (no assertions, self-mocking, can't-fail, snapshot-only, time/random). | sonnet | read-only |
| [`test-runner`](.claude/agents/testing/test-runner.md) | Runs the project's tests (detected runner, narrowest subset first) and returns a compact digest: command, exit code, pass/fail/skip counts, each failure's test id, first error line and file:line. | haiku | read-only |
| [`test-writer`](.claude/agents/testing/test-writer.md) | Writes unit, component and integration tests for named code or the current diff in the repo's existing framework and style: happy path, boundaries, error paths, regression and characterization tests; runs them and reports evidence and bugs found. | sonnet | read/write |

### Debugging & diagnosis

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`build-fixer`](.claude/agents/debugging/build-fixer.md) | Gets a failing build, compile, type-check, lint or dependency restore green with the smallest correct diff (tsc, eslint, mypy, ruff, dotnet, go, cargo, maven, gradle), fixing types, imports and call sites instead of suppressing errors. | sonnet | read/write |
| [`ci-failure-investigator`](.claude/agents/debugging/ci-failure-investigator.md) | Investigates a failed CI/CD run (GitHub Actions, Azure Pipelines, GitLab CI, Jenkins): pulls the logs, finds the failing step and first real error, compares with the last green run, and classifies the cause (code, flaky test, toolchain drift, registry outage, secrets, YAML, timeout). | sonnet | read-only |
| [`debugger`](.claude/agents/debugging/debugger.md) | Root-causes and fixes bugs that fail on every run: exceptions, stack traces, crashes, hangs, failing tests, wrong output. Reproduces (or builds a repro from a trace), proves the cause, fixes minimally, adds a regression test. | opus | read/write |
| [`git-bisector`](.claude/agents/debugging/git-bisector.md) | Finds the commit that introduced a regression with `git bisect run` from a good ref, a bad ref (default HEAD) and a check (builds one if none); returns the first bad commit, responsible hunk and bisect log. | sonnet | read-only |
| [`log-analyzer`](.claude/agents/debugging/log-analyzer.md) | Digests large logs, traces and exports (plain text, JSON lines, syslog, CI logs, Windows events): time range, first failure, normalized error clusters with counts, timeline around deploys/restarts, correlated trace ids, red herrings, likely root cause with line-cited evidence. | sonnet | read-only |
| [`performance-analyst`](.claude/agents/debugging/performance-analyst.md) | Finds and quantifies performance bottlenecks (slow endpoints, jobs, tests, pages; memory growth; bundle size) by profiling and benchmarking, labelling anything unmeasured a hypothesis: N+1 queries, quadratic loops, sync I/O, sync-over-async, chatty calls, unbounded caches, re-renders. | sonnet | read-only |

### Architecture & refactoring

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`code-simplifier`](.claude/agents/architecture/code-simplifier.md) | Behavior-preserving cleanup of recently changed or named code: guard clauses for deep nesting, splitting long functions, removing duplication, dead code and needless abstraction, clearer names, simpler conditionals; tests run before and after. | inherit | read/write |
| [`dependency-upgrader`](.claude/agents/architecture/dependency-upgrader.md) | Upgrades a library, framework, runtime or SDK across major versions (React 17->18, Django 3->5, Spring Boot 2->3, Node 16->22, Python 3.8->3.12, Angular, EF Core) from official migration guides, with codemods, lockfile, CI and docs updated and tests green per step. | sonnet | read/write + web |
| [`dotnet-modernizer`](.claude/agents/architecture/dotnet-modernizer.md) | Ports .NET Framework apps to modern .NET one project at a time with the build kept green: SDK-style csproj, PackageReference, multi-targeting, ASP.NET MVC/Web API to ASP.NET Core (YARP, System.Web adapters), WCF to CoreWCF/gRPC, Web.config to appsettings, BinaryFormatter, Windows services, EF6. | sonnet | read/write + web |
| [`legacy-code-analyst`](.claude/agents/architecture/legacy-code-analyst.md) | Extracts and documents business rules in legacy code (stored procedures, VB6/VBA, Excel macros, WebForms, classic ASP, COBOL, batch/cron jobs, old Java/.NET): rules, data flows, hidden dependencies, side effects at path:line. | sonnet | read-only |
| [`manufacturing-integration-engineer`](.claude/agents/architecture/manufacturing-integration-engineer.md) | Designs and reviews ISA-95 Level 2-4 integrations: MES<->ERP/SAP (B2MML), OPC UA, MQTT/Sparkplug B, historians (PI), ISA-88 batch, LIMS, label printing, serialization; checks buffering, idempotency, ordering, timestamps, reconciliation. | opus | read/write |

### Documentation

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`adr-writer`](.claude/agents/docs/adr-writer.md) | Records an architecture decision as an ADR (MADR or the repo's template): context, options with pros/cons, decision, consequences, status, date, links to code/PRs; numbered in the ADR folder, index updated. Unstated rationale becomes an open question. | sonnet | read/write |
| [`diagram-generator`](.claude/agents/docs/diagram-generator.md) | Generates Mermaid diagrams from the actual code: architecture, sequence (request/feature flow), ER (migrations/ORM models), state (status enums), class and CI pipeline diagrams, each node and edge traced to path:line and syntax-checked. | sonnet | read/write |
| [`docs-sync-editor`](.claude/agents/docs/docs-sync-editor.md) | Fixes documentation that drifted after a code change, with minimal line edits: README, docs/*.md and docstrings that still cite renamed or removed CLI flags, config keys, env vars, function signatures, endpoints, setup steps or examples. | sonnet | read/write |
| [`technical-writer`](.claude/agents/docs/technical-writer.md) | Writes NEW documentation: README, getting-started, how-to guides, runbooks, API usage guides, onboarding and troubleshooting pages, architecture overviews, with every command, flag, env var and path verified against the repo. | sonnet | read/write |

### Data & databases

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`data-analyst`](.claude/agents/data/data-analyst.md) | Answers questions from data files (CSV, TSV, Excel, JSON, Parquet) and databases via read-only SQL: profiles first (rows, types, nulls, duplicates, ranges, dates), flags data quality issues, then computes the answer with reproducible pandas/DuckDB/SQL code, group comparisons and statistical caveats. | sonnet | read/write |
| [`database-architect`](.claude/agents/data/database-architect.md) | Designs new database schemas or major restructurings from access patterns and invariants: entities, keys, normalization, constraints, temporal/audit history, soft delete, multi-tenancy, partitioning/retention, indexes, expand/contract migration. Returns DDL (not run), Mermaid ER diagram, rationale. | opus | read-only |
| [`migration-reviewer`](.claude/agents/data/migration-reviewer.md) | Reviews database schema migrations (raw SQL, EF Core, Alembic, Django, Flyway, Liquibase, Rails, Prisma, Knex) for production safety: data loss, drops/renames still used by code, locks and table rewrites, compatibility with the running app (expand/contract), rollback, idempotency, backfills. | sonnet | read-only |
| [`sql-query-tuner`](.claude/agents/data/sql-query-tuner.md) | Tunes slow SQL (SQL Server, PostgreSQL, MySQL/MariaDB, SQLite, Oracle) from the query, schema and actual plan: non-SARGable predicates, missing or redundant indexes, key lookups, bad estimates, parameter sniffing, OFFSET paging, blocking; proposes rewrites and index DDL with write cost, never runs them. | sonnet | read-only |

### DevOps, cloud & operations

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`bash-scripter`](.claude/agents/devops/bash-scripter.md) | Writes, reviews and hardens shell scripts (bash, sh/POSIX, zsh): strict mode and its pitfalls, quoting, safe rm and temp-file cleanup, argument parsing, exit codes, idempotency, GNU vs macOS/BSD portability; runs shellcheck, shfmt and bash -n. | sonnet | read/write |
| [`ci-pipeline-engineer`](.claude/agents/devops/ci-pipeline-engineer.md) | Writes and fixes CI/CD pipeline YAML for GitHub Actions, Azure Pipelines and GitLab CI: build/test/deploy stages, reusable workflows and templates, caching, matrix builds, environments with approvals, OIDC instead of stored cloud secrets, SHA-pinned actions, least-privilege tokens. | sonnet | read/write |
| [`container-engineer`](.claude/agents/devops/container-engineer.md) | Writes and optimizes Dockerfiles, .dockerignore and docker-compose files: multi-stage builds, pinned slim/distroless base images, layer caching, non-root USER, BuildKit secrets, HEALTHCHECK, PID 1 signals, measured size reduction. | sonnet | read/write |
| [`iac-reviewer`](.claude/agents/devops/iac-reviewer.md) | Reviews infrastructure-as-code and deployment config (Terraform/OpenTofu, Bicep/ARM, CloudFormation/CDK, Pulumi, Kubernetes/Helm/Kustomize, Dockerfiles, compose) for public exposure, broad IAM/RBAC, secrets, encryption, pinning, securityContext, limits and probes. | sonnet | read-only |
| [`observability-engineer`](.claude/agents/devops/observability-engineer.md) | Adds or improves observability in application code: structured JSON logs with trace ids and no secrets/PII, RED/USE metrics with bounded cardinality, OpenTelemetry tracing with propagation across async and queues, health/readiness endpoints, symptom-based SLO burn-rate alerts. | sonnet | read/write |
| [`powershell-scripter`](.claude/agents/devops/powershell-scripter.md) | Writes, reviews and fixes PowerShell scripts and modules (.ps1/.psm1/.psd1) for Windows PowerShell 5.1 or PowerShell 7: -WhatIf/-Confirm support, strict error handling, approved verbs, parameter validation, no hardcoded credentials; runs PSScriptAnalyzer and Pester. | sonnet | read/write |

### Git & pull-request workflow

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`changelog-writer`](.claude/agents/git/changelog-writer.md) | Updates CHANGELOG.md's Unreleased section from commits and PRs since the last tag: end-user entries under Added/Changed/Deprecated/Removed/Fixed/Security, refactor/test/chore/CI noise dropped, BREAKING changes flagged with migration notes, PR numbers/SHAs cited. | haiku | read/write |
| [`git-historian`](.claude/agents/git/git-historian.md) | Answers why code is the way it is from version control: when and why a line, function or file changed, which commit, PR or ticket (INC-, JIRA-, #123) introduced it, and who knows it, via git log -L, pickaxe, blame past renames and PR lookups. | sonnet | read-only |
| [`merge-conflict-resolver`](.claude/agents/git/merge-conflict-resolver.md) | Resolves git merge, rebase, cherry-pick and stash-pop conflicts by combining the intent of both sides instead of picking one: reads base/ours/theirs and each side's commits, fixes semantic conflicts outside the markers, then builds, tests and stages. | opus | read/write |
| [`pr-description-writer`](.claude/agents/git/pr-description-writer.md) | Drafts a pull request (or merge request) title and description from the branch diff (base...HEAD), mirroring the repo's PR template if present: summary, grouped changes, risk and rollout, testing evidence, linked issues. | haiku | read-only |

### AI engineering & Claude Code

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`claude-api-reviewer`](.claude/agents/ai/claude-api-reviewer.md) | Reviews code calling the Claude API, Anthropic SDKs or Claude Agent SDK (incl. Bedrock/Vertex) against current docs: model ids, max_tokens, prompt caching, tool_use loops, streaming, stop_reason, retries on 429/529, timeouts, thinking, API keys, cost. | sonnet | read-only + web |
| [`claude-md-curator`](.claude/agents/ai/claude-md-curator.md) | Creates or maintains CLAUDE.md files (root and nested) for Claude Code: runs every build/test/lint/format command it lists, records non-obvious conventions, architecture pointers and gotchas, prunes stale, generic or derivable lines, and proposes hooks for must-always rules. | sonnet | read/write |
| [`llm-eval-designer`](.claude/agents/ai/llm-eval-designer.md) | Designs and builds evals for LLM features: error analysis of real outputs, failure-mode taxonomy, golden dataset (10-50 cases incl. edge and adversarial, expected properties), code assertions before binary LLM-as-judge rubrics calibrated on human labels, metrics and a CI regression gate. | opus | read/write |
| [`mcp-server-builder`](.claude/agents/ai/mcp-server-builder.md) | Builds or extends Model Context Protocol (MCP) servers in TypeScript or Python (mcp/FastMCP): tools with precise names, descriptions and JSON schemas, resources, prompts, stdio or Streamable HTTP transport, auth; tests with MCP Inspector and registers via `claude mcp add`. | sonnet | read/write + web |
| [`prompt-engineer`](.claude/agents/ai/prompt-engineer.md) | Writes and improves prompts for LLM features in application code: system prompts, tool descriptions, few-shot examples, JSON/structured-output schemas, RAG and classification/extraction prompts. | opus | read/write |
| [`subagent-auditor`](.claude/agents/ai/subagent-auditor.md) | Audits Claude Code subagent definitions (.claude/agents, ~/.claude/agents) for broken frontmatter, name/filename or duplicate-name clashes, missing, over-broad or stale tools, dated model ids, and vague, bloated or overlapping descriptions that misroute delegation. | sonnet | read-only |
| [`subagent-author`](.claude/agents/ai/subagent-author.md) | Creates or improves Claude Code subagents (.claude/agents/**/*.md, ~/.claude/agents): routing-rule description, least-privilege tools, model alias, procedural body with guardrails and output contract, plus trigger and near-miss test prompts. | opus | read/write + web |

### Compliance & regulated software

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`change-control-impact-assessor`](.claude/agents/compliance/change-control-impact-assessor.md) | Drafts a change-control impact assessment for a code change (PR, branch, release range) to a validated/GxP system: plain summary, proposed minor/major class, GxP impact, affected URS and functions, regression and revalidation scope, data migration, rollback, training/SOP, evidence. | opus | read-only |
| [`csv-validation-author`](.claude/agents/compliance/csv-validation-author.md) | Drafts GxP validation deliverables (CSV/CSA, GAMP 5) from code and docs: system description and category, intended use and GxP impact, risk assessment, DRAFT URS, traceability matrix, IQ/OQ/PQ or CSA test protocols, never executed. | opus | read/write |
| [`gxp-data-integrity-reviewer`](.claude/agents/compliance/gxp-data-integrity-reviewer.md) | Reviews code in GxP-regulated systems (pharma, biotech, medical device, labs, QA) touching regulated records, audit trails, e-signatures, timestamps, user identity/roles or record edits/deletes; maps findings to ALCOA+ and 21 CFR Part 11 / EU Annex 11. | opus | read-only |

### Product & requirements

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`i18n-engineer`](.claude/agents/product/i18n-engineer.md) | Internationalizes apps: extracts hardcoded UI strings into the repo's i18n framework (i18next, react-intl/FormatJS, gettext/Babel, .resx/IStringLocalizer, Angular i18n), fixes locale formatting of dates, time zones, numbers and currency, ICU plurals, RTL and text expansion, and drafts es/pt-BR translations for review. | sonnet | read/write |
| [`requirements-analyst`](.claude/agents/product/requirements-analyst.md) | Turns a vague request, ticket, email or meeting note into testable requirements grounded in code: problem, actors, user stories or URS "shall" items with IDs, Given/When/Then acceptance criteria, NFRs, edge cases, out-of-scope, assumptions, dependencies, open questions. | sonnet | read/write |

### Research

| Agent | What it does | Model | Access |
| --- | --- | --- | --- |
| [`docs-researcher`](.claude/agents/research/docs-researcher.md) | Answers how-to, API, config and deprecation questions about a known library, framework, SDK, CLI or cloud service from current official docs for the pinned version, with cited URLs and a version-matched example. | sonnet | read-only + web |
| [`feature-tracer`](.claude/agents/research/feature-tracer.md) | Explains how an existing feature works end to end: entry point (route, CLI command, UI event, job, message handler) through validation, services and domain logic to data stores, side effects and response at path:line, with config flags, error paths and tests. | sonnet | read-only |
| [`library-evaluator`](.claude/agents/research/library-evaluator.md) | Compares candidate libraries, frameworks or services for a need and recommends one: stack fit, ergonomics, maintenance health, adoption, license, security history, size, transitive deps, platform (Windows, air-gapped), exit cost, cited from registries, GitHub and docs. | sonnet | read-only + web |
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
