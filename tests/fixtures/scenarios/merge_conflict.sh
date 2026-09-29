#!/usr/bin/env bash
# Create app/filters.py on main, change filter_by_site one way on
# feature/site-filter (several sites) and another way on main (case-insensitive
# match), then start merging the feature branch into main. The merge stops
# with a conflict in app/filters.py and the repo is left mid-merge on main.
#
# Run with cwd = a git checkout of sample-app (branch main, clean tree).
set -euo pipefail

git rev-parse --verify -q HEAD >/dev/null || { echo "merge_conflict: not a git repo with a commit" >&2; exit 1; }
if git rev-parse -q --verify refs/heads/feature/site-filter >/dev/null; then
  echo "merge_conflict: branch feature/site-filter already exists, nothing to do" >&2
  exit 1
fi

base_ts=$(git log -1 --format=%ct)
n=0

commit_as() {  # commit_as "<name>" "<email>" "<message>"
  n=$((n + 1))
  local when="$((base_ts + n * 2700 + (n * 331) % 900)) +0000"
  GIT_AUTHOR_DATE="$when" GIT_COMMITTER_DATE="$when" \
    git -c user.name="$1" -c user.email="$2" -c commit.gpgsign=false commit -q -m "$3"
}

replace_in() {  # replace_in <file> <old> <new>  (old must occur exactly once)
  python3 - "$1" "$2" "$3" <<'PY'
import sys
path, old, new = sys.argv[1:4]
text = open(path, encoding="utf-8").read()
if text.count(old) != 1:
    sys.exit(f"replace_in: expected one match in {path}, found {text.count(old)}")
open(path, "w", encoding="utf-8").write(text.replace(old, new))
PY
}

SOFIA=("Sofia Herrera" "sofia.herrera@batchtrack.example")
TOMAS=("Tomas Mejia" "tomas.mejia@batchtrack.example")

git checkout -q main
mkdir -p app tests
[ -f app/__init__.py ] || : > app/__init__.py
[ -f tests/__init__.py ] || : > tests/__init__.py

# main: shared starting point ---------------------------------------------------
cat > app/filters.py <<'EOF'
"""Filters applied to batch listings before pagination."""


def filter_by_site(batches, site):
    """Batches produced at ``site``; all batches when no site is given."""
    if not site:
        return list(batches)
    return [batch for batch in batches if batch.get("site") == site]


def filter_by_status(batches, statuses):
    """Batches whose status is one of ``statuses``; all batches when empty."""
    if not statuses:
        return list(batches)
    wanted = set(statuses)
    return [batch for batch in batches if batch.get("status") in wanted]
EOF
cat > tests/test_filters.py <<'EOF'
from app.filters import filter_by_site, filter_by_status

BATCHES = [
    {"batch_no": "PX-2026-0101", "site": "BOG", "status": "released"},
    {"batch_no": "PX-2026-0102", "site": "BAQ", "status": "released"},
    {"batch_no": "PX-2026-0103", "site": "MDE", "status": "in_progress"},
    {"batch_no": "SG-2026-0104", "site": "bog", "status": "in_progress"},
    {"batch_no": "PX-2026-0105", "site": "CLO", "status": "rejected"},
    {"batch_no": "PX-2026-0106", "site": None, "status": "planned"},
]


def batch_nos(rows):
    return [row["batch_no"] for row in rows]


def test_no_site_returns_all_batches():
    assert batch_nos(filter_by_site(BATCHES, None)) == batch_nos(BATCHES)
    assert batch_nos(filter_by_site(BATCHES, "")) == batch_nos(BATCHES)


def test_single_site():
    assert batch_nos(filter_by_site(BATCHES, "BAQ")) == ["PX-2026-0102"]


def test_filter_by_status():
    assert batch_nos(filter_by_status(BATCHES, ["released"])) == ["PX-2026-0101", "PX-2026-0102"]
    assert batch_nos(filter_by_status(BATCHES, [])) == batch_nos(BATCHES)
EOF
git add app/filters.py tests/test_filters.py app/__init__.py tests/__init__.py
commit_as "${SOFIA[@]}" "Add site and status filters for batch listings"

# feature/site-filter: several sites -------------------------------------------
git checkout -q -b feature/site-filter
replace_in app/filters.py 'def filter_by_site(batches, site):
    """Batches produced at ``site``; all batches when no site is given."""
    if not site:
        return list(batches)
    return [batch for batch in batches if batch.get("site") == site]' 'def filter_by_site(batches, site):
    """Batches produced at any of the given sites; all batches when no site is given.

    ``site`` is one site code, a comma-separated list such as "BOG,BAQ", or a list of codes.
    """
    if not site:
        return list(batches)
    if isinstance(site, str):
        site = site.split(",")
    wanted = {code.strip() for code in site if code and code.strip()}
    return [batch for batch in batches if batch.get("site") in wanted]'
git add app/filters.py
commit_as "${TOMAS[@]}" "Accept several sites in filter_by_site

Planners at BAQ also schedule CLO batches and want one listing for
both sites (?site=BAQ,CLO)."
cat >> tests/test_filters.py <<'EOF'


def test_several_sites_as_comma_separated_string():
    assert batch_nos(filter_by_site(BATCHES, "BAQ,CLO")) == ["PX-2026-0102", "PX-2026-0105"]
    assert batch_nos(filter_by_site(BATCHES, " BAQ , MDE ")) == ["PX-2026-0102", "PX-2026-0103"]


def test_several_sites_as_list():
    assert batch_nos(filter_by_site(BATCHES, ["MDE", "BAQ"])) == ["PX-2026-0102", "PX-2026-0103"]
EOF
git add tests/test_filters.py
commit_as "${TOMAS[@]}" "Test multi-site filtering"

# main: case-insensitive match ---------------------------------------------------
git checkout -q main
replace_in app/filters.py 'def filter_by_site(batches, site):
    """Batches produced at ``site``; all batches when no site is given."""
    if not site:
        return list(batches)
    return [batch for batch in batches if batch.get("site") == site]' 'def filter_by_site(batches, site):
    """Batches produced at ``site``, ignoring case and surrounding spaces; all batches when no site is given."""
    if not site:
        return list(batches)
    wanted = site.strip().upper()
    return [batch for batch in batches if (batch.get("site") or "").strip().upper() == wanted]'
replace_in tests/test_filters.py '    assert batch_nos(filter_by_site(BATCHES, "")) == batch_nos(BATCHES)
' '    assert batch_nos(filter_by_site(BATCHES, "")) == batch_nos(BATCHES)


def test_site_match_ignores_case_and_spaces():
    assert batch_nos(filter_by_site(BATCHES, "bog")) == ["PX-2026-0101", "SG-2026-0104"]
    assert batch_nos(filter_by_site(BATCHES, " Bog ")) == ["PX-2026-0101", "SG-2026-0104"]
    assert batch_nos(filter_by_site(BATCHES, "baq")) == ["PX-2026-0102"]
'
git add app/filters.py tests/test_filters.py
commit_as "${SOFIA[@]}" "Match site codes case-insensitively

Batches imported from the old spreadsheet have lower-case site codes
(\"bog\"), and the web UI sends whatever the user typed. Both were
missing from filtered listings."

# start the merge; it is expected to stop on a conflict --------------------------
if git -c user.name="${SOFIA[0]}" -c user.email="${SOFIA[1]}" merge --no-edit feature/site-filter >/dev/null 2>&1; then
  echo "merge_conflict: merge unexpectedly succeeded" >&2
  exit 1
fi
conflicts=$(git diff --name-only --diff-filter=U | tr '\n' ' ')
[ -n "$conflicts" ] || { echo "merge_conflict: merge failed without conflicts" >&2; exit 1; }
echo "merge_conflict: on main mid-merge of feature/site-filter; conflicted: ${conflicts% }"
