#!/usr/bin/env bash
# Install agents from this repo into a Claude Code agents directory.
#
#   ./install.sh                     copy all agents to ~/.claude/agents
#   ./install.sh --link              symlink instead (updates with `git pull`)
#   ./install.sh --project DIR       install into DIR/.claude/agents instead
#   ./install.sh --category review   only one category (repeatable)
#   ./install.sh --only a,b,c        only the named agents
#   ./install.sh --dry-run           show what would happen
#   ./install.sh --uninstall         remove agents that came from this repo
set -euo pipefail

src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.claude/agents"
dest="$HOME/.claude/agents"
mode=copy dry=0 uninstall=0 force=0
categories=() only=""

usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while (($#)); do
  case "$1" in
    --link) mode=link ;;
    --project) dest="$(cd "${2:?--project needs a directory}" && pwd)/.claude/agents"; shift ;;
    --category) categories+=("${2:?--category needs a name}"); shift ;;
    --only) only="${2:?--only needs a list}"; shift ;;
    --dry-run) dry=1 ;;
    --force) force=1 ;;
    --uninstall) uninstall=1 ;;
    -h|--help) usage 0 ;;
    *) echo "unknown option: $1" >&2; usage 1 ;;
  esac
  shift
done

run() { if ((dry)); then echo "would: $*"; else "$@"; fi; }

mapfile -t files < <(find "$src" -name '*.md' -type f | sort)
selected=()
for f in "${files[@]}"; do
  name="$(basename "$f" .md)"
  cat="$(basename "$(dirname "$f")")"
  if ((${#categories[@]})) && [[ ! " ${categories[*]} " == *" $cat "* ]]; then continue; fi
  if [[ -n "$only" ]] && [[ ! ",$only," == *",$name,"* ]]; then continue; fi
  selected+=("$f")
done
((${#selected[@]})) || { echo "no agents matched" >&2; exit 1; }

run mkdir -p "$dest"
installed=0 skipped=0
for f in "${selected[@]}"; do
  target="$dest/$(basename "$f")"
  if ((uninstall)); then
    if [[ -L "$target" && "$(readlink "$target")" == "$f" ]] || { [[ -f "$target" ]] && cmp -s "$f" "$target"; }; then
      run rm -f "$target"; installed=$((installed + 1))
    fi
    continue
  fi
  if [[ -e "$target" || -L "$target" ]] && ((!force)) && ! cmp -s "$f" "$target"; then
    echo "skip (exists and differs, use --force): $target" >&2; skipped=$((skipped + 1)); continue
  fi
  if [[ $mode == link ]]; then run ln -sfn "$f" "$target"; else run cp "$f" "$target"; fi
  installed=$((installed + 1))
done

verb=$([[ $uninstall == 1 ]] && echo removed || echo installed)
msg="$verb $installed agent(s) in $dest"
((skipped)) && msg+=" ($skipped skipped)"
echo "$msg"
