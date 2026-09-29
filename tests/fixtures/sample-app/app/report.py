"""Yield statistics and the periodic site yield report."""

LOW_YIELD_PCT = 95.0
HIGH_YIELD_PCT = 102.0


def yield_pct(planned_qty, actual_qty):
    """Actual output as a percentage of the planned quantity."""
    return round(actual_qty / planned_qty * 100.0, 2)


def collect_warnings(rows, warnings=[]):
    for row in rows:
        if row.get("actual_qty") is None:
            warnings.append(f"{row['batch_no']}: actual quantity not recorded")
        elif row["actual_qty"] < 0:
            warnings.append(f"{row['batch_no']}: negative actual quantity")
    return warnings


def site_summary(rows, low=LOW_YIELD_PCT, high=HIGH_YIELD_PCT, include_open=False):
    summary = {}
    for row in rows:
        site = row.get("site") or "UNKNOWN"
        if site not in summary:
            summary[site] = {"batches": 0, "released": 0, "rejected": 0, "missing_qty": [],
                             "low_yield": [], "high_yield": [], "products": {}}
        entry = summary[site]
        entry["batches"] += 1
        if row["status"] == "released":
            entry["released"] += 1
        elif row["status"] == "rejected":
            entry["rejected"] += 1
        else:
            if not include_open:
                continue
        if row.get("actual_qty") is None:
            entry["missing_qty"].append(row["batch_no"])
        else:
            pct = yield_pct(row["planned_qty"], row["actual_qty"])
            product = row.get("product") or "UNKNOWN"
            if product not in entry["products"]:
                entry["products"][product] = {"count": 0, "total": 0.0, "min": None, "max": None}
            stats = entry["products"][product]
            stats["count"] += 1
            stats["total"] += pct
            if stats["min"] is None or pct < stats["min"]:
                stats["min"] = pct
            if stats["max"] is None or pct > stats["max"]:
                stats["max"] = pct
            if pct < low:
                if row["status"] == "released":
                    entry["low_yield"].append({"batch_no": row["batch_no"], "pct": pct, "flag": "released"})
                else:
                    if row["status"] == "rejected":
                        entry["low_yield"].append({"batch_no": row["batch_no"], "pct": pct, "flag": "rejected"})
                    else:
                        entry["low_yield"].append({"batch_no": row["batch_no"], "pct": pct, "flag": "open"})
            elif pct > high:
                if row["status"] == "released":
                    entry["high_yield"].append({"batch_no": row["batch_no"], "pct": pct, "flag": "released"})
                else:
                    entry["high_yield"].append({"batch_no": row["batch_no"], "pct": pct, "flag": row["status"]})
    for site, entry in summary.items():
        for product, stats in entry["products"].items():
            if stats["count"]:
                stats["avg"] = round(stats["total"] / stats["count"], 2)
                if stats["avg"] < low:
                    stats["trend"] = "below"
                elif stats["avg"] > high:
                    stats["trend"] = "above"
                else:
                    stats["trend"] = "within"
            else:
                stats["avg"] = None
                stats["trend"] = "n/a"
        if entry["batches"]:
            entry["release_rate"] = round(entry["released"] / entry["batches"] * 100.0, 1)
        else:
            entry["release_rate"] = 0.0
    return summary


def _percentile(values, pct):
    ordered = sorted(values)
    if not ordered:
        return None
    k = (len(ordered) - 1) * pct / 100.0
    lower = int(k)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (k - lower)


def format_report(summary):
    lines = []
    for site in sorted(summary):
        entry = summary[site]
        lines.append(f"Site {site}: {entry['batches']} batches, {entry['release_rate']}% released")
        for product, stats in sorted(entry["products"].items()):
            lines.append(f"  {product}: avg {stats['avg']}% (min {stats['min']}%, max {stats['max']}%)")
        for item in entry["low_yield"] + entry["high_yield"]:
            lines.append(f"  ! {item['batch_no']} {item['pct']}% [{item['flag']}]")
        if entry["missing_qty"]:
            lines.append(f"  missing actual qty: {', '.join(entry['missing_qty'])}")
    return "\n".join(lines)


def build_report(conn, since=None):
    sql = "SELECT batch_no, product, site, status, planned_qty, actual_qty FROM batches"
    params = ()
    if since:
        sql += " WHERE created_at >= ?"
        params = (since,)
    rows = [dict(row) for row in conn.execute(sql, params)]
    summary = site_summary(rows)
    return {"summary": summary, "warnings": collect_warnings(rows), "text": format_report(summary)}
