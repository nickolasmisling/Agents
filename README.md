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
