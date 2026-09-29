# Subagent style guide

Every agent in this library follows these conventions. `scripts/validate_agents.py`
enforces the mechanical parts; reviewers enforce the rest.

## Why these rules exist

A subagent is a fresh Claude instance with **no memory of the parent conversation**.
It sees only its system prompt (the file body), the delegation message the parent
writes, CLAUDE.md files, and a git status snapshot. The parent decides whether to
delegate by reading **only the `description`**. Almost every rule below follows from
those two facts.

## File layout

```
.claude/agents/<category>/<name>.md
```

* `name` is lowercase kebab-case and **must equal the filename** (without `.md`).
* Categories are directories; Claude Code loads agents from subdirectories.
* Frontmatter key order: `name`, `description`, `tools`, `model`, `color`, then any
  optional keys (`effort`, `maxTurns`, `memory`, ...).

## The description (the routing contract)

The description is the only thing the parent reads when choosing an agent. Write it
as a routing rule, not a job title.

**Formula** (1–3 sentences, roughly 150–500 characters):

```
<What it does, with the concrete nouns users actually say>. Use PROACTIVELY <trigger>
| Use when <trigger>. <Boundary: Not for X — use <other-agent>.>
```

* Lead with the concrete task and the words a user would type ("flaky test",
  "Dockerfile", "merge conflict", "21 CFR Part 11"), not abstractions.
* Say **when**: `Use PROACTIVELY after …` for agents the parent should reach for
  without being asked (reviewers, test runners, verifiers); `Use when …` for
  on-demand specialists.
* Add a **boundary clause** whenever a neighbouring agent could plausibly claim the
  same request. Name the neighbour. This is what keeps routing accurate as the
  library grows.
* No marketing ("world-class", "expert-level"), no model names, no dates.

Good:

> Diagnoses intermittently failing (flaky) tests: finds the nondeterminism source
> (timing, ordering, shared state, randomness, network, time zones) and makes the test
> deterministic. Use when a test passes and fails without code changes or fails only in
> CI. Not for consistently failing tests — use test-fixer.

Bad:

> Expert testing agent that helps with all kinds of test problems.

## Tools: least privilege, always explicit

Omitting `tools` gives the agent **every** tool, including Write, Edit, and all MCP
tools. Unknown tool names are **silently dropped**. So: always list tools, and let the
validator catch typos.

| Tier | Tools | Used by |
| --- | --- | --- |
| Analyst (read-only) | `Read, Grep, Glob, Bash` | reviewers, auditors, explainers, planners |
| Researcher | `Read, Grep, Glob, WebSearch, WebFetch` (+ `Bash` if it inspects the repo) | research, library evaluation |
| Builder | `Read, Write, Edit, Grep, Glob, Bash` | writers, fixers, implementers |
| Builder + web | Builder + `WebSearch, WebFetch` | migrations, API integrations |

* Analysts keep `Bash` for `git diff`, `git log`, linters and test runs, and their
  body **must** say they never modify files. The behavioral test suite fails any
  read-only agent that changes the working tree.
* Do not give `Agent` to library agents; nesting multiplies cost and hides work.
* MCP tools (`mcp__server__tool`) are allowed only as optional extras; the agent
  must still work when that server is not connected.

## Model

| Model | When |
| --- | --- |
| `opus` | Deep reasoning where a miss is expensive: security, architecture, debugging, concurrency, migrations, merge conflicts, compliance, prompt engineering. |
| `sonnet` | The default for everything else. |
| `haiku` | Short, mechanical, high-frequency tasks: commit messages, changelogs. |

Users can override all agents at once with `CLAUDE_CODE_SUBAGENT_MODEL`.

## Colours by category

`review` red · `testing` green · `debugging` orange · `docs` cyan · `architecture` purple ·
`languages` blue · `data` yellow · `devops` pink · `git` cyan · `ai` purple ·
`compliance` red · `product` yellow · `research` green

## The body (system prompt)

Target 400–1200 words. Structure:

```markdown
You are a <role>. <One or two sentences on the standard you hold: what "good" looks
like and what you refuse to do.>

## When invoked
1. Establish scope. <How to find what to work on with no context: the delegation
   message first, else `git diff`/`git status`, else ask the parent via the report.>
2. <Domain steps, in order.>
...

## <Checklist | Principles | Heuristics>
<The domain knowledge: specific, checkable items. Not "check for bugs".>

## Guardrails
- <What this agent must never do: e.g. never edit files; never run destructive
  commands; never invent APIs, CVEs, or citations; stop and report when blocked.>

## Output
<The exact shape of the final message. It goes to the PARENT agent, not the human:
dense, structured, no preamble, file:line references, prioritized, and an explicit
note of anything not checked.>
```

### Rules for the body

1. **Assume zero context.** Tell the agent how to discover scope itself, and to state
   its assumptions in the report when the delegation message is vague.
2. **Detect before acting.** Find the project's own tooling (package.json scripts,
   Makefile, pyproject, CI config) before running commands; never assume `npm test`.
3. **Evidence or silence.** Every finding cites `path:line` and a concrete failure
   scenario (input → wrong result). Speculation is labelled as such or dropped.
   Calibrate severity; do not pad the list.
4. **Verify before reporting.** Re-read the code behind each finding; run the test,
   linter, or reproduction when one is available.
5. **Builders make minimal diffs.** Match surrounding style, touch nothing unrelated,
   run the relevant tests afterwards, and never commit/push unless the delegation
   message asks.
6. **Say what you didn't do.** The report ends with what was out of scope, skipped, or
   unverified, so the parent does not over-trust it.
7. **No filler.** No "Great question", no restating the task, no generic advice that
   would apply to any codebase.

## Testing an agent

Every agent needs:

1. A **routing case** in `tests/routing/cases.yaml`: a realistic request that should
   go to it (and, where relevant, a near-miss that should not).
2. A **behavior case** in `tests/behavior/cases/<name>.yaml`: a task against the
   fixture with a rubric of must/should/must_not items drawn from
   `tests/fixtures/answer-key/`.

Run `make test` (static + load) locally; `make test-routing` and `make test-behavior`
spend API credits.
