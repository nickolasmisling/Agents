#!/usr/bin/env bash
# Load test: confirm Claude Code itself registers every agent defined in this repo.
#
# The static validator checks our files; this checks the real CLI agrees. It
# relies on `claude --agent <unknown>` printing the list of available agents,
# so it makes no model calls and costs nothing.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

command -v claude >/dev/null || { echo "the claude CLI must be on PATH" >&2; exit 2; }

available="$(claude -p --agent __no_such_agent__ "x" 2>&1 || true)"
available="${available#*Available agents: }"
loaded="$(tr ',' '\n' <<<"$available" | sed 's/^ *//;s/ *$//' | sort -u)"

expected="$(grep -rhoP '^name:\s*\K[a-z0-9-]+' .claude/agents --include='*.md' | sort -u)"

missing="$(comm -23 <(echo "$expected") <(echo "$loaded"))"
count="$(echo "$expected" | grep -c . || true)"

if [[ -n "$missing" ]]; then
  echo "FAIL: $(echo "$missing" | grep -c .) of $count agents were not registered by Claude Code:" >&2
  echo "$missing" | sed 's/^/  - /' >&2
  exit 1
fi
echo "OK: all $count agents registered by Claude Code $(claude --version | cut -d' ' -f1)"
