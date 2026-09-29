#!/usr/bin/env python3
"""Generate sample-app/data/batches.csv deterministically.

Usage: python3 gen_batches_csv.py [output_path]

The seeded data-quality issues are listed in answer-key/data-and-history.md
(DATA-01 .. DATA-06). Running this script twice produces byte-identical output.
"""

import csv
import itertools
import os
import random
import sys
from datetime import date, timedelta

SEED = 20260301
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "..", "sample-app", "data", "batches.csv")

COLUMNS = ["batch_no", "product", "site", "planned_qty", "actual_qty",
           "start_date", "end_date", "status", "operator"]

# product -> (batch prefix, planned quantities, base yield %)
PRODUCTS = {
    "Paracetamol 500mg": ("PX", [1000, 1500], 98.8),
    "Ibuprofen 400mg": ("PX", [800, 1200], 98.2),
    "Loratadine 10mg": ("PX", [500, 600], 99.1),
    "Omega-3 1000mg": ("SG", [1200, 1400], 97.4),
    "Vitamin D3 1000IU": ("SG", [900, 1000], 97.9),
}

SITES = {
    "BOG": (0.2, ["jgomez", "lmartinez", "aperez"]),
    "BAQ": (0.0, ["dcastro", "mhernandez", "rsuarez"]),
    "CLO": (-8.0, ["pvargas", "ngarcia", "ctorres"]),   # DATA-04: systematically lower yield
    "MDE": (-0.3, ["jramirez", "sortiz", "emoreno"]),
}

N_UNIQUE = 145
FIRST_DAY = date(2026, 1, 5)
LAST_DAY = date(2026, 6, 26)


def build_unique(rng):
    combos = list(itertools.product(SITES, PRODUCTS)) * 7
    combos += rng.sample(list(itertools.product(SITES, PRODUCTS)), N_UNIQUE - len(combos))
    rng.shuffle(combos)
    span = (LAST_DAY - FIRST_DAY).days
    days = sorted(rng.randint(0, span) for _ in range(N_UNIQUE))
    rows = []
    for seq, ((site, product), offset) in enumerate(zip(combos, days), start=201):
        prefix, planned_choices, base_yield = PRODUCTS[product]
        site_shift, operators = SITES[site]
        planned = rng.choice(planned_choices)
        pct = rng.gauss(base_yield + site_shift, 1.1)
        start = FIRST_DAY + timedelta(days=offset)
        end = start + timedelta(days=rng.randint(1, 3))
        rows.append({
            "batch_no": f"{prefix}-2026-{seq:04d}",
            "product": product,
            "site": site,
            "planned_qty": f"{planned:.1f}",
            "actual_qty": f"{planned * pct / 100.0:.1f}",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "status": "released",
            "operator": rng.choice(operators),
        })
    return rows


def set_statuses(rows, rng):
    # Most recent batches are still open or waiting for QC disposition.
    for row in rows[-7:]:
        row["status"] = "in_progress"
        row["actual_qty"] = ""
        row["end_date"] = ""
    for row in rows[-11:-7]:
        row["status"] = "quarantined"
    # A handful of rejections spread over the period and the sites.
    rejected_idx = [14, 37, 61, 88, 103, 120]
    for i in rejected_idx:
        row = rows[i]
        row["status"] = "rejected"
        planned = float(row["planned_qty"])
        row["actual_qty"] = f"{planned * rng.uniform(0.86, 0.93):.1f}"
    return rejected_idx


def seed_issues(rows, rng):
    log = {}
    released = [i for i, r in enumerate(rows) if r["status"] == "released"]

    # DATA-02: released batches with no actual quantity recorded.
    missing = [9, 33, 58, 76, 97, 115]
    for i in missing:
        assert rows[i]["status"] == "released"
        rows[i]["actual_qty"] = ""
    log["missing_actual"] = [rows[i]["batch_no"] for i in missing]

    # DATA-03: decimal slip, actual quantity ~10x planned (one at CLO, one at BAQ).
    outliers = []
    for site in ("CLO", "BAQ"):
        i = next(i for i in released[40:] if rows[i]["site"] == site and i not in missing)
        planned = float(rows[i]["planned_qty"])
        rows[i]["actual_qty"] = f"{float(rows[i]['actual_qty']) * 10:.1f}"
        outliers.append((rows[i]["batch_no"], site, planned, rows[i]["actual_qty"]))
    log["outliers"] = outliers

    # DATA-05: non-ISO dates in a handful of rows.
    date_fmt = [
        (21, "start_date", "{m:02d}/{d:02d}/{y}"),
        (46, "end_date", "{d:02d}/{m:02d}/{y}"),
        (67, "start_date", "{y}/{m:02d}/{d:02d}"),
        (82, "end_date", "{d:02d}-{mon}-{y}"),
        (109, "start_date", "{y}-{m}-{d}"),
        (126, "start_date", "{y}{m:02d}{d:02d}"),
    ]
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    changed = []
    for i, col, fmt in date_fmt:
        # Keep day > 12 so that every rewritten date has exactly one reading.
        while not rows[i][col] or date.fromisoformat(rows[i][col]).day <= 12:
            i += 1
        d = date.fromisoformat(rows[i][col])
        rows[i][col] = fmt.format(y=d.year, m=d.month, d=d.day, mon=months[d.month - 1])
        changed.append((rows[i]["batch_no"], col, rows[i][col], d.isoformat()))
    log["dates"] = changed

    # DATA-06: casing / whitespace variants of one product name.
    variants = ["omega-3 1000mg", "OMEGA-3 1000MG", "Omega-3  1000mg",
                " Omega-3 1000mg", "Omega-3 1000mg ", "Omega-3 1000 mg", "omega-3 1000mg"]
    omega = [i for i, r in enumerate(rows) if r["product"] == "Omega-3 1000mg"]
    picks = sorted(rng.sample(omega, len(variants)))
    for i, name in zip(picks, variants):
        rows[i]["product"] = name
    log["product_variants"] = [(rows[i]["batch_no"], repr(rows[i]["product"])) for i in picks]
    return log


def add_duplicates(rows, rng):
    # DATA-01: exact duplicate rows (double-exported records).
    sources = [5, 30, 52, 90, 131]
    out = list(rows)
    dupes = []
    for n, src in enumerate(sorted(sources, reverse=True)):
        row = dict(rows[src])
        pos = src + 1 if n % 2 == 0 else min(len(out), src + rng.randint(3, 9))
        out.insert(pos, row)
        dupes.append(row["batch_no"])
    return out, sorted(dupes)


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    rng = random.Random(SEED)
    rows = build_unique(rng)
    rejected = [rows[i]["batch_no"] for i in set_statuses(rows, rng)]
    log = seed_issues(rows, rng)
    rows, dupes = add_duplicates(rows, rng)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {os.path.normpath(out_path)}")
    print("duplicates:", dupes)
    print("rejected:", rejected)
    for key, value in log.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
