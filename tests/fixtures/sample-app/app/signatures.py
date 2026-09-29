"""Electronic signatures on batch records."""

import json

from . import db


def sign_batch(conn, batch_id, user_id, signed_at, meaning=None):
    """Attach a signature by ``user_id`` to the batch record."""
    batch = conn.execute("SELECT id FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if batch is None:
        raise LookupError(f"batch {batch_id} not found")
    cur = conn.execute(
        "INSERT INTO signatures (batch_id, user_id, meaning, signed_at) VALUES (?, ?, ?, ?)",
        (batch_id, user_id, meaning, signed_at),
    )
    db.write_audit(
        conn,
        "signatures",
        cur.lastrowid,
        "insert",
        None,
        json.dumps({"batch_id": batch_id, "meaning": meaning, "signed_at": signed_at}),
        user_id,
    )
    conn.commit()
    return cur.lastrowid


def update_signature(conn, signature_id, meaning=None, signed_at=None):
    """Correct the meaning or timestamp of an existing signature."""
    fields = []
    params = []
    if meaning is not None:
        fields.append("meaning = ?")
        params.append(meaning)
    if signed_at is not None:
        fields.append("signed_at = ?")
        params.append(signed_at)
    if not fields:
        return False
    params.append(signature_id)
    conn.execute(f"UPDATE signatures SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    return True


def delete_signature(conn, signature_id):
    conn.execute("DELETE FROM signatures WHERE id = ?", (signature_id,))
    conn.commit()


def signatures_for_batch(conn, batch_id):
    rows = conn.execute(
        "SELECT s.id, s.user_id, u.username, s.meaning, s.signed_at "
        "FROM signatures s JOIN users u ON u.id = s.user_id "
        "WHERE s.batch_id = ? ORDER BY s.signed_at, s.id",
        (batch_id,),
    )
    return [dict(row) for row in rows]
