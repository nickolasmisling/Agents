#!/usr/bin/env bash
# Load test: confirm Claude Code itself registers every agent defined in this repo,
# both as project agents (.claude/agents) and when the repo is loaded as a plugin.
#
# The static validator checks our files; this checks the real CLI agrees. It
# relies on `claude --agent <unknown>` printing the list of available agents,
# so it makes no model calls and costs nothing.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command -v claude >/dev/null || { echo "the claude CLI must be on PATH" >&2; exit 2; }

expected="$(grep -rhoP '^name:\s*\K[a-z0-9-]+' "$root/.claude/agents" --include='*.md' | sort -u)"
count="$(grep -c . <<<"$expected")"

# Prints the agent names Claude Code reports as available, one per line.
# Arguments are extra CLI flags; runs in the directory given by $cwd.
loaded_agents() {
  local out
  out="$(cd "$cwd" && claude -p "$@" --agent __no_such_agent__ "x" 2>&1 || true)"
  [[ "$out" == *"Available agents: "* ]] || { echo "unexpected CLI output: $out" >&2; return 1; }
  tr ',' '\n' <<<"${out#*Available agents: }" | sed 's/^ *//;s/ *$//' | sort -u
}

check() {
  local label="$1" prefix="$2" missing
  shift 2
  missing="$(comm -23 <(sed "s/^/$prefix/" <<<"$expected") <(loaded_agents "$@"))"
  if [[ -n "$missing" ]]; then
    echo "FAIL ($label): $(grep -c . <<<"$missing") of $count agents not registered:" >&2
    sed 's/^/  - /' <<<"$missing" >&2
    return 1
  fi
  echo "OK ($label): all $count agents registered"
}

status=0
cwd="$root" check "project agents" "" || status=1

scratch="$(mktemp -d)"
trap 'rm -rf -- "$scratch"' EXIT
plugin="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$root/.claude-plugin/plugin.json")"
cwd="$scratch" check "plugin $plugin" "$plugin:" --plugin-dir "$root" || status=1

echo "Claude Code $(claude --version | cut -d' ' -f1)"
exit "$status"
