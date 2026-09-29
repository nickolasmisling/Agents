#!/usr/bin/env bash
# Build history on top of HEAD in which the LIMS client gains a de-duplication
# step for sample results. The reason lives only in one commit message; later
# commits rename and reformat the code and touch unrelated files.
#
# Run with cwd = a git checkout of sample-app (branch main, clean tree).
set -euo pipefail

git rev-parse --verify -q HEAD >/dev/null || { echo "historian_history: not a git repo with a commit" >&2; exit 1; }
if [ -f tests/test_lims_dedup.py ]; then
  echo "historian_history: tests/test_lims_dedup.py already exists, nothing to do" >&2
  exit 1
fi

base_ts=$(git log -1 --format=%ct)
n=0

commit_as() {  # commit_as "<name>" "<email>" "<message>"
  n=$((n + 1))
  local when="$((base_ts + n * 5400 + (n * 613) % 2400)) +0000"
  GIT_AUTHOR_DATE="$when" GIT_COMMITTER_DATE="$when" \
    git -c user.name="$1" -c user.email="$2" -c commit.gpgsign=false commit -q -m "$3"
}

append_to() {  # append_to <file>  (block on stdin, separated by two blank lines)
  local block
  block=$(cat)
  python3 - "$1" "$block" <<'PY'
import os, sys
path, block = sys.argv[1:3]
text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
text = text.rstrip("\n")
text = (text + "\n\n\n" if text else "") + block.strip("\n") + "\n"
os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
open(path, "w", encoding="utf-8").write(text)
PY
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

MARTA=("Marta Salazar" "marta.salazar@batchtrack.example")
ANDREA=("Andrea Castillo" "andrea.castillo@batchtrack.example")
JULIAN=("Julian Rojas" "julian.rojas@batchtrack.example")

mkdir -p app tests docs/runbooks
[ -f app/__init__.py ] || : > app/__init__.py
[ -f tests/__init__.py ] || : > tests/__init__.py

if [ -f app/lims_client.py ]; then
  target=app/lims_client.py
  module=app.lims_client
else
  target=app/lims_dedup.py
  module=app.lims_dedup
  printf '"""Helpers for sample results returned by the site LIMS."""\n' > "$target"
fi

# 1 ---------------------------------------------------------------------------
cat > docs/lims.md <<'EOF'
# LIMS integration

batchtrack reads QC results for material lots from the site LIMS over its
REST API (`/api/v2`). Calls go through the plant API gateway and use a
personal access token issued to the `batchtrack` service account.

| Call | Used for |
| --- | --- |
| `GET /samples?lot=<lot_no>` | QC results for a lot, one row per test. |
| `POST /samples` | Register a QC sample for a batch. |

A lot counts as approved when every result for it has status `pass`.

After INC-4388 the gateway idle timeout was raised to 120 s, because large
result sets for multi-test lots were cut off at 30 s.
EOF
git add docs/lims.md
commit_as "${MARTA[@]}" "Add LIMS integration notes"

# 2 ---------------------------------------------------------------------------
if [ "$target" = app/lims_client.py ] && [ "$(grep -c '^    results = get_sample_results(lot_no)$' "$target" || true)" = 1 ]; then
  replace_in "$target" '    results = get_sample_results(lot_no)
' '    results = get_lot_results(lot_no)
'
fi
if [ "$target" = app/lims_client.py ]; then
  append_to "$target" <<'EOF'
def latest_results_by_lot(results):
    """Keep one result per (lot_no, test): the most recently reviewed row."""
    latest = {}
    for result in results:
        key = (result.get("lot_no"), result.get("test"))
        seen = latest.get(key)
        if seen is None or (result.get("reviewed_at") or "") >= (seen.get("reviewed_at") or ""):
            latest[key] = result
    return list(latest.values())


def get_lot_results(lot_no):
    """QC results for a lot, with re-reviewed results collapsed to their latest row."""
    return latest_results_by_lot(get_sample_results(lot_no) or [])
EOF
else
  append_to "$target" <<'EOF'
def latest_results_by_lot(results):
    """Keep one result per (lot_no, test): the most recently reviewed row."""
    latest = {}
    for result in results:
        key = (result.get("lot_no"), result.get("test"))
        seen = latest.get(key)
        if seen is None or (result.get("reviewed_at") or "") >= (seen.get("reviewed_at") or ""):
            latest[key] = result
    return list(latest.values())
EOF
fi
git add "$target"
commit_as "${ANDREA[@]}" "Collapse duplicate LIMS results per lot and test

Since the LIMS upgrade to 7.2, GET /samples returns a result twice once
QC has re-reviewed it: the original row and the amended row carry the
same lot_no and test, in no stable order. is_lot_approved() picked up
the stale \"fail\" row, and the release dashboard kept lot OIL-OM3-2603
on hold for two days although QC had passed it (INC-4521).

The vendor confirmed the defect on their side (Samplify support case
SUP-88213) and plans the fix for LIMS 7.3. Until the site runs 7.3 we
keep only the most recently reviewed row per (lot_no, test). Remove
this once the upgrade is done.

Refs: INC-4521"

# 3 ---------------------------------------------------------------------------
cat > tests/test_lims_dedup.py <<EOF
from ${module} import latest_results_by_lot

ORIGINAL = {"lot_no": "OIL-OM3-2603", "test": "peroxide", "status": "fail", "reviewed_at": "2026-05-04T09:12:00Z"}
AMENDED = {"lot_no": "OIL-OM3-2603", "test": "peroxide", "status": "pass", "reviewed_at": "2026-05-04T15:40:00Z"}
ASSAY = {"lot_no": "OIL-OM3-2603", "test": "assay", "status": "pass", "reviewed_at": "2026-05-03T11:00:00Z"}


def by_test(results):
    return sorted(results, key=lambda r: r["test"])


def test_latest_review_wins_in_either_order():
    assert by_test(latest_results_by_lot([ORIGINAL, AMENDED, ASSAY])) == [ASSAY, AMENDED]
    assert by_test(latest_results_by_lot([AMENDED, ORIGINAL, ASSAY])) == [ASSAY, AMENDED]


def test_distinct_tests_are_kept():
    assert len(latest_results_by_lot([ASSAY, AMENDED])) == 2


def test_empty():
    assert latest_results_by_lot([]) == []
EOF
git add tests/test_lims_dedup.py
commit_as "${ANDREA[@]}" "Add tests for LIMS result collapsing"

# 4 ---------------------------------------------------------------------------
cat > docs/runbooks/lims-outage.md <<'EOF'
# Runbook: LIMS unavailable

Symptoms: lots stay "not approved" on the release dashboard, API log shows
`batchtrack.lims` errors or slow responses above 2 s.

1. Check the gateway status page and the LIMS service health endpoint.
2. If the gateway returns 504, see INC-4388 for the timeout settings.
3. Do not release batches manually while LIMS is down; QA decides on a
   paper fallback per the site SOP.
4. When LIMS is back, reload the dashboard. Results are fetched on demand;
   nothing needs to be replayed.
EOF
git add docs/runbooks/lims-outage.md
commit_as "${MARTA[@]}" "Add runbook for LIMS outages"

# 5 ---------------------------------------------------------------------------
replace_in "$target" 'def latest_results_by_lot(results):
    """Keep one result per (lot_no, test): the most recently reviewed row."""
    latest = {}
    for result in results:
        key = (result.get("lot_no"), result.get("test"))
        seen = latest.get(key)
        if seen is None or (result.get("reviewed_at") or "") >= (seen.get("reviewed_at") or ""):
            latest[key] = result
    return list(latest.values())' 'def unique_results(results):
    """One result per (lot_no, test)."""
    ordered = sorted(results, key=lambda r: r.get("reviewed_at") or "")
    return list({(r.get("lot_no"), r.get("test")): r for r in ordered}.values())'
if grep -q 'return latest_results_by_lot(get_sample_results(lot_no) or \[\])' "$target"; then
  replace_in "$target" '    """QC results for a lot, with re-reviewed results collapsed to their latest row."""
    return latest_results_by_lot(get_sample_results(lot_no) or [])' '    """QC results for a lot."""
    return unique_results(get_sample_results(lot_no) or [])'
fi
python3 - tests/test_lims_dedup.py <<'PY'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read().replace("latest_results_by_lot", "unique_results")
open(path, "w", encoding="utf-8").write(text)
PY
git add "$target" tests/test_lims_dedup.py
commit_as "${JULIAN[@]}" "Rename LIMS result helpers

Shorter names and a simpler implementation. No behaviour change."

# 6 ---------------------------------------------------------------------------
replace_in docs/lims.md 'personal access token issued to the `batchtrack` service account.' \
  'token issued to the `batchtrack` service account (rotated every 90 days).'
git add docs/lims.md
commit_as "${JULIAN[@]}" "Note token rotation in LIMS docs"

# 7 ---------------------------------------------------------------------------
editorconfig=.editorconfig
[ -e "$editorconfig" ] && editorconfig=docs/.editorconfig
cat > "$editorconfig" <<'EOF'
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

[*.py]
indent_style = space
indent_size = 4

[*.{md,yml,yaml,json}]
indent_style = space
indent_size = 2
EOF
git add "$editorconfig"
commit_as "${MARTA[@]}" "Add editorconfig"

echo "historian_history: $n commits on $(git rev-parse --abbrev-ref HEAD); de-duplication helper unique_results() in $target"
