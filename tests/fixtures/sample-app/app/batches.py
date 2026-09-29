"""Batch record queries and state changes."""

import re

from . import db, utils

BATCH_NO_RE = re.compile(r"^[A-Z]{2,4}-\d{4}-\d{3,5}$")


def normalize_batch_no(raw):
    """Upper-case and strip a batch number, e.g. ' px-2026-0101' -> 'PX-2026-0101'."""
    value = raw.strip().upper().replace(" ", "")
    if not BATCH_NO_RE.match(value):
        raise ValueError(f"invalid batch number: {raw!r}")
    return value


def create_batch(conn, batch_no, product, site, planned_qty, status="planned"):
    cur = conn.execute(
        "INSERT INTO batches (batch_no, product, site, status, planned_qty, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (normalize_batch_no(batch_no), product, site, status, planned_qty, utils.utc_now_iso()),
    )
    conn.commit()
    return cur.lastrowid


def get_batch(conn, batch_id):
    row = conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    return dict(row) if row else None


def list_batches(conn, product=None, site=None, status=None):
    """Return batches, newest first, optionally filtered by product, site and status."""
    clauses = []
    params = []
    if product:
        clauses.append(f"product = '{product}'")
    if site:
        clauses.append(f"site = '{site}'")
    if status:
        clauses.append("status = ?")
        params.append(status)
    sql = "SELECT * FROM batches"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC"
    return [dict(row) for row in conn.execute(sql, params)]


def batches_with_materials(conn, status="released"):
    """Batches in the given status, each with the list of material lots consumed."""
    result = []
    rows = conn.execute(
        "SELECT * FROM batches WHERE status = ? ORDER BY batch_no", (status,)
    ).fetchall()
    for row in rows:
        batch = dict(row)
        materials = conn.execute(
            "SELECT lot_no, name, qty FROM materials WHERE batch_id = ? ORDER BY id",
            (batch["id"],),
        ).fetchall()
        batch["materials"] = [dict(m) for m in materials]
        result.append(batch)
    return result


def paginate(items, page, page_size):
    """Return the 1-based ``page`` of ``items``."""
    if page < 1 or page_size < 1:
        raise ValueError("page and page_size must be positive")
    start = (page - 1) * page_size + 1
    end = page * page_size
    return items[start:end]


def release_batch(conn, batch_id, user_id):
    row = conn.execute("SELECT status FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if row is None:
        raise LookupError(f"batch {batch_id} not found")
    if row["status"] == "released":
        return False
    conn.execute("UPDATE batches SET status = 'released' WHERE id = ?", (batch_id,))
    db.write_audit(conn, "batches", batch_id, "update", row["status"], "released", user_id)
    conn.commit()
    return True


def set_actual_qty(db_path, batch_no, actual_qty, user_id):
    """Record the yielded quantity for a batch that has not been released yet."""
    conn = db.connect(db_path)
    row = conn.execute(
        "SELECT id, status, actual_qty FROM batches WHERE batch_no = ?",
        (normalize_batch_no(batch_no),),
    ).fetchone()
    if row is None:
        raise LookupError(f"batch {batch_no} not found")
    if row["status"] == "released":
        raise ValueError(f"batch {batch_no} is already released")
    conn.execute("UPDATE batches SET actual_qty = ? WHERE id = ?", (actual_qty, row["id"]))
    db.write_audit(conn, "batches", row["id"], "update", row["actual_qty"], actual_qty, user_id)
    conn.commit()
    conn.close()
    return row["id"]
