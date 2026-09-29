#!/usr/bin/env bash
# Build a 10-commit history on top of HEAD that touches app/report.py and
# related files. Commit 1 is tagged v1.3.0 and adds tests/test_report_regression.py;
# a later commit breaks compute_batch_yield, so the test fails at the final HEAD.
#
# Run with cwd = a git checkout of sample-app (branch main, clean tree).
set -euo pipefail

git rev-parse --verify -q HEAD >/dev/null || { echo "regression_history: not a git repo with a commit" >&2; exit 1; }
if git rev-parse -q --verify refs/tags/v1.3.0 >/dev/null; then
  echo "regression_history: tag v1.3.0 already exists, nothing to do" >&2
  exit 1
fi

base_ts=$(git log -1 --format=%ct)
n=0

commit_as() {  # commit_as "<name>" "<email>" "<message>"
  n=$((n + 1))
  local when="$((base_ts + n * 1800 + (n * 419) % 1200)) +0000"
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

LAURA=("Laura Mendez" "laura.mendez@batchtrack.example")
DIEGO=("Diego Ruiz" "diego.ruiz@batchtrack.example")
CAMILA=("Camila Ortega" "camila.ortega@batchtrack.example")
ANDRES=("Andres Pardo" "andres.pardo@batchtrack.example")

mkdir -p app tests docs
[ -f app/__init__.py ] || : > app/__init__.py
[ -f tests/__init__.py ] || : > tests/__init__.py
[ -f app/report.py ] || printf '"""Yield statistics and the periodic site yield report."""\n' > app/report.py

# 1 ---------------------------------------------------------------------------
append_to app/report.py <<'EOF'
def compute_batch_yield(actual, planned):
    """Yield of one batch in percent: actual output over the planned (theoretical) quantity.

    Returns None when a quantity is missing or the planned quantity is not positive,
    so callers can show "n/a" instead of failing on an incomplete batch record.
    """
    if actual is None or planned is None or planned <= 0:
        return None
    return round(actual / planned * 100.0, 1)
EOF
cat > tests/test_report_regression.py <<'EOF'
from app.report import compute_batch_yield


def test_yield_is_actual_over_planned():
    assert compute_batch_yield(985.0, 1000.0) == 98.5


def test_yield_can_exceed_100_percent():
    assert compute_batch_yield(1012.0, 1000.0) == 101.2


def test_low_yield_batch():
    assert compute_batch_yield(640.0, 800.0) == 80.0


def test_missing_actual_quantity_gives_none():
    assert compute_batch_yield(None, 1000.0) is None


def test_zero_planned_quantity_gives_none():
    assert compute_batch_yield(500.0, 0) is None
EOF
git add app/report.py tests/test_report_regression.py app/__init__.py tests/__init__.py
commit_as "${LAURA[@]}" "Add compute_batch_yield for single-batch yield

The site report only deals in averages per site and product. The
batch release form needs a per-batch figure that copes with a missing
actual quantity, so add a small helper and pin its behaviour with
tests."
git -c user.name="${LAURA[0]}" -c user.email="${LAURA[1]}" tag -a v1.3.0 -m "batchtrack 1.3.0"

# 2 ---------------------------------------------------------------------------
append_to app/report.py <<'EOF'
def yield_by_batch(rows):
    """Map batch_no -> yield % for the given batch rows (None when it cannot be computed)."""
    return {row["batch_no"]: compute_batch_yield(row.get("actual_qty"), row.get("planned_qty")) for row in rows}
EOF
git add app/report.py
commit_as "${LAURA[@]}" "Add yield_by_batch helper for the yield export"

# 3 ---------------------------------------------------------------------------
cat > docs/yield.md <<'EOF'
# Yield definitions

| Term | Definition |
| --- | --- |
| Planned quantity | Theoretical output of the batch from the master batch record. |
| Actual quantity | Output counted at the end of packaging. |
| Batch yield | `actual / planned * 100`, one decimal (`app.report.compute_batch_yield`). |
| Site yield | Average batch yield per site and product in the periodic report (`app.report.site_summary`). |

A batch without an actual quantity has no yield yet; it is shown as `n/a`.
EOF
git add docs/yield.md
commit_as "${CAMILA[@]}" "Document batch and site yield definitions"

# 4 ---------------------------------------------------------------------------
cat > app/yield_export.py <<'EOF'
"""CSV export of per-batch yields for the monthly QA review."""

import csv

from .report import yield_by_batch

HEADER = ["batch_no", "product", "planned_qty", "actual_qty", "yield_pct"]


def write_yield_csv(rows, fh):
    """Write one line per batch to ``fh``; returns the number of batches written."""
    yields = yield_by_batch(rows)
    writer = csv.writer(fh)
    writer.writerow(HEADER)
    for row in rows:
        pct = yields[row["batch_no"]]
        writer.writerow([
            row["batch_no"],
            row.get("product") or "",
            row.get("planned_qty"),
            row.get("actual_qty"),
            "" if pct is None else f"{pct:.1f}",
        ])
    return len(rows)
EOF
git add app/yield_export.py
commit_as "${CAMILA[@]}" "Add CSV export of batch yields for QA review"

# 5 ---------------------------------------------------------------------------
append_to app/report.py <<'EOF'
def yield_outliers(rows, low=90.0, high=105.0):
    """Batches whose yield falls outside [low, high], as (batch_no, pct) sorted by batch number."""
    flagged = []
    for batch_no, pct in sorted(yield_by_batch(rows).items()):
        if pct is not None and not low <= pct <= high:
            flagged.append((batch_no, pct))
    return flagged
EOF
git add app/report.py
commit_as "${ANDRES[@]}" "Flag batches with yield outside 90-105 %"

# 6 ---------------------------------------------------------------------------
replace_in app/report.py 'def compute_batch_yield(actual, planned):
    """Yield of one batch in percent: actual output over the planned (theoretical) quantity.

    Returns None when a quantity is missing or the planned quantity is not positive,
    so callers can show "n/a" instead of failing on an incomplete batch record.
    """
    if actual is None or planned is None or planned <= 0:
        return None
    return round(actual / planned * 100.0, 1)' 'def _valid_qty(value):
    """A quantity usable in yield maths: a non-negative number, else None."""
    if value is None or value == "":
        return None
    try:
        qty = float(value)
    except (TypeError, ValueError):
        return None
    return qty if qty >= 0 else None


def compute_batch_yield(planned, actual):
    """Yield of one batch in percent: actual output over the planned (theoretical) quantity.

    Quantities may be numbers or numeric strings. Returns None when a quantity is
    missing or invalid, or the planned quantity is zero.
    """
    planned, actual = _valid_qty(planned), _valid_qty(actual)
    if actual is None or not planned:
        return None
    return round(actual / planned * 100.0, 1)'
git add app/report.py
commit_as "${DIEGO[@]}" "Share quantity parsing between yield helpers

Quantities from the release form arrive as strings (\"985.0\") and the
CSV import can carry negative corrections. Parse them in one place
with _valid_qty() instead of trusting the caller."

# 7 ---------------------------------------------------------------------------
replace_in app/yield_export.py 'HEADER = ["batch_no", "product", "planned_qty", "actual_qty", "yield_pct"]' \
  'HEADER = ["batch_no", "product", "site", "planned_qty", "actual_qty", "yield_pct"]'
replace_in app/yield_export.py '            row.get("product") or "",
' '            row.get("product") or "",
            row.get("site") or "",
'
git add app/yield_export.py
commit_as "${CAMILA[@]}" "Include site in the yield export"

# 8 ---------------------------------------------------------------------------
cat > tests/test_yield_export.py <<'EOF'
import io

from app.yield_export import HEADER, write_yield_csv

ROWS = [
    {"batch_no": "PX-2026-0101", "product": "Paracetamol 500mg", "site": "BOG",
     "planned_qty": 1000.0, "actual_qty": 1000.0},
    {"batch_no": "PX-2026-0103", "product": "Ibuprofen 400mg", "site": "BAQ",
     "planned_qty": 800.0, "actual_qty": None},
]


def export(rows):
    buf = io.StringIO()
    count = write_yield_csv(rows, buf)
    return count, buf.getvalue().splitlines()


def test_header_and_one_line_per_batch():
    count, lines = export(ROWS)
    assert count == 2
    assert lines[0] == ",".join(HEADER)
    assert len(lines) == 3


def test_yield_column():
    _, lines = export(ROWS)
    assert lines[1].endswith(",100.0")
    assert lines[2].endswith(",")
EOF
git add tests/test_yield_export.py
commit_as "${ANDRES[@]}" "Add tests for the yield CSV export"

# 9 ---------------------------------------------------------------------------
replace_in app/report.py 'def yield_by_batch(rows):
    """Map batch_no -> yield % for the given batch rows (None when it cannot be computed)."""
    return {row["batch_no"]: compute_batch_yield(row.get("actual_qty"), row.get("planned_qty")) for row in rows}' 'def yield_by_batch(rows):
    """Map batch_no -> yield % for the given batch rows (None when it cannot be computed).

    Draft rows without a batch number are skipped.
    """
    return {
        row["batch_no"]: compute_batch_yield(row.get("actual_qty"), row.get("planned_qty"))
        for row in rows
        if row.get("batch_no")
    }'
replace_in app/yield_export.py '    for row in rows:
        pct = yields[row["batch_no"]]' '    rows = [row for row in rows if row.get("batch_no")]
    for row in rows:
        pct = yields[row["batch_no"]]'
git add app/report.py app/yield_export.py
commit_as "${LAURA[@]}" "Skip draft rows without a batch number in yield helpers"

# 10 --------------------------------------------------------------------------
cat >> docs/yield.md <<'EOF'

Batch yield is rounded to one decimal; the site report keeps two decimals
because it averages many batches. Batches outside 90-105 % are listed by
`app.report.yield_outliers` for QA follow-up.
EOF
git add docs/yield.md
commit_as "${CAMILA[@]}" "Explain yield rounding and the outlier window"

echo "regression_history: $(git rev-list --count v1.3.0..HEAD) commits after v1.3.0 on $(git rev-parse --abbrev-ref HEAD); tests/test_report_regression.py passes at v1.3.0 and fails at HEAD"
