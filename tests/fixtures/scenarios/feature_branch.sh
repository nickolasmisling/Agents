#!/usr/bin/env bash
# Create feature/export-csv with four commits that add a CSV export of batch
# listings (app/export.py + tests), leave it checked out, and stage (without
# committing) a small bug fix in app/export.py together with a test for it.
#
# Run with cwd = a git checkout of sample-app (branch main, clean tree).
set -euo pipefail

git rev-parse --verify -q HEAD >/dev/null || { echo "feature_branch: not a git repo with a commit" >&2; exit 1; }
if git rev-parse -q --verify refs/heads/feature/export-csv >/dev/null; then
  echo "feature_branch: branch feature/export-csv already exists, nothing to do" >&2
  exit 1
fi

base_ts=$(git log -1 --format=%ct)
n=0

commit_as() {  # commit_as "<name>" "<email>" "<message>"
  n=$((n + 1))
  local when="$((base_ts + n * 3000 + (n * 457) % 1100)) +0000"
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

VALENTINA=("Valentina Rios" "valentina.rios@batchtrack.example")

git checkout -q -b feature/export-csv
mkdir -p app tests
[ -f app/__init__.py ] || : > app/__init__.py
[ -f tests/__init__.py ] || : > tests/__init__.py

# 1 ---------------------------------------------------------------------------
cat > app/export.py <<'EOF'
"""CSV export of batch listings."""

import csv

DEFAULT_COLUMNS = ["batch_no", "product", "site", "status", "planned_qty", "actual_qty"]


def export_batches_csv(rows, fh, columns=None):
    """Write ``rows`` (dicts or sqlite3.Row) to ``fh`` as CSV; returns the number of data rows."""
    columns = list(columns or DEFAULT_COLUMNS)
    writer = csv.writer(fh)
    writer.writerow(columns)
    count = 0
    for row in rows:
        writer.writerow([row[column] for column in columns])
        count += 1
    return count
EOF
git add app/export.py app/__init__.py tests/__init__.py
commit_as "${VALENTINA[@]}" "Add CSV export for batch listings"

# 2 ---------------------------------------------------------------------------
cat > tests/test_export.py <<'EOF'
import csv
import io

from app.export import DEFAULT_COLUMNS, export_batches_csv

ROWS = [
    {"batch_no": "PX-2026-0101", "product": "Paracetamol 500mg", "site": "BOG", "status": "released",
     "planned_qty": 1000.0, "actual_qty": 985.0},
    {"batch_no": "SG-2026-0104", "product": "Omega-3 1000mg", "site": "BAQ", "status": "released",
     "planned_qty": 1200.0, "actual_qty": 1100.0},
]


def read_back(text):
    return list(csv.reader(io.StringIO(text)))


def test_header_and_rows():
    buf = io.StringIO()
    assert export_batches_csv(ROWS, buf) == 2
    lines = read_back(buf.getvalue())
    assert lines[0] == DEFAULT_COLUMNS
    assert [line[0] for line in lines[1:]] == ["PX-2026-0101", "SG-2026-0104"]


def test_selected_columns():
    buf = io.StringIO()
    export_batches_csv(ROWS, buf, columns=["batch_no", "site"])
    assert read_back(buf.getvalue()) == [["batch_no", "site"], ["PX-2026-0101", "BOG"], ["SG-2026-0104", "BAQ"]]
EOF
git add tests/test_export.py
commit_as "${VALENTINA[@]}" "Add tests for batch CSV export"

# 3 ---------------------------------------------------------------------------
cat >> app/export.py <<'EOF'


def export_from_db(conn, fh, status=None):
    """Export batches from the database, optionally only one status, ordered by batch number."""
    sql = "SELECT batch_no, product, site, status, planned_qty, actual_qty FROM batches"
    params = ()
    if status:
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY batch_no"
    return export_batches_csv(conn.execute(sql, params), fh)
EOF
replace_in tests/test_export.py 'import csv
import io

from app.export import DEFAULT_COLUMNS, export_batches_csv' 'import csv
import io
import sqlite3

from app.export import DEFAULT_COLUMNS, export_batches_csv, export_from_db'
cat >> tests/test_export.py <<'EOF'


def test_export_from_db_filters_by_status():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE batches (batch_no TEXT, product TEXT, site TEXT, status TEXT, planned_qty REAL, actual_qty REAL)"
    )
    conn.executemany("INSERT INTO batches VALUES (?, ?, ?, ?, ?, ?)", [
        ("PX-2026-0102", "Paracetamol 500mg", "BOG", "released", 1000.0, 1012.0),
        ("PX-2026-0101", "Paracetamol 500mg", "BOG", "released", 1000.0, 985.0),
        ("PX-2026-0105", "Ibuprofen 400mg", "BOG", "rejected", 800.0, 640.0),
    ])
    buf = io.StringIO()
    assert export_from_db(conn, buf, status="released") == 2
    assert [line[0] for line in read_back(buf.getvalue())[1:]] == ["PX-2026-0101", "PX-2026-0102"]
EOF
git add app/export.py tests/test_export.py
commit_as "${VALENTINA[@]}" "Export batches straight from the database"

# 4 ---------------------------------------------------------------------------
replace_in app/export.py 'DEFAULT_COLUMNS = ["batch_no", "product", "site", "status", "planned_qty", "actual_qty"]
' 'DEFAULT_COLUMNS = ["batch_no", "product", "site", "status", "planned_qty", "actual_qty"]
QTY_COLUMNS = {"planned_qty", "actual_qty"}


def _cell(column, value):
    if column in QTY_COLUMNS:
        return f"{float(value):.1f}"
    return value
'
replace_in app/export.py '        writer.writerow([row[column] for column in columns])' \
  '        writer.writerow([_cell(column, row[column]) for column in columns])'
cat >> tests/test_export.py <<'EOF'


def test_quantities_have_one_decimal():
    rows = [dict(ROWS[0], planned_qty=1000, actual_qty=985.04)]
    buf = io.StringIO()
    export_batches_csv(rows, buf)
    assert read_back(buf.getvalue())[1][4:] == ["1000.0", "985.0"]
EOF
git add app/export.py tests/test_export.py
commit_as "${VALENTINA[@]}" "Format quantities with one decimal in CSV export"

# staged, not committed: fix for batches without a quantity ------------------------
replace_in app/export.py 'def _cell(column, value):
    if column in QTY_COLUMNS:' 'def _cell(column, value):
    if value is None:
        return ""
    if column in QTY_COLUMNS:'
cat >> tests/test_export.py <<'EOF'


def test_missing_actual_quantity_is_left_empty():
    rows = [dict(ROWS[0], status="in_progress", actual_qty=None)]
    buf = io.StringIO()
    assert export_batches_csv(rows, buf) == 1
    assert read_back(buf.getvalue())[1][3:] == ["in_progress", "1000.0", ""]
EOF
git add app/export.py tests/test_export.py

echo "feature_branch: on $(git rev-parse --abbrev-ref HEAD), $(git rev-list --count main..HEAD) commits ahead of main; staged: $(git diff --cached --name-only | tr '\n' ' ' | sed 's/ $//')"
