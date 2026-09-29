import time

import pytest

from app import batches, db


def test_normalize_batch_no_uppercases_and_strips():
    assert batches.normalize_batch_no("  px-2026-0101 ") == "PX-2026-0101"


def test_normalize_batch_no_rejects_garbage():
    with pytest.raises(ValueError):
        batches.normalize_batch_no("batch 7")


def test_create_and_get_batch(conn):
    batch_id = batches.create_batch(conn, "px-2026-0200", "Paracetamol 500mg", "BOG", 1000.0)
    batch = batches.get_batch(conn, batch_id)
    assert batch["batch_no"] == "PX-2026-0200"
    assert batch["status"] == "planned"
    assert batch["created_at"]


def test_list_batches_filters_by_site(conn):
    rows = batches.list_batches(conn, site="BAQ")
    assert {r["batch_no"] for r in rows} == {"PX-2026-0103", "SG-2026-0104"}


def test_list_batches_filters_by_product_and_status(conn):
    rows = batches.list_batches(conn, product="Paracetamol 500mg", status="released")
    assert [r["batch_no"] for r in rows] == ["PX-2026-0102", "PX-2026-0101"]


def test_batches_with_materials_attaches_lots(conn):
    released = batches.batches_with_materials(conn)
    assert [b["batch_no"] for b in released] == ["PX-2026-0101", "PX-2026-0102", "SG-2026-0104"]
    assert [m["lot_no"] for m in released[0]["materials"]] == ["API-PCM-2601", "EXC-MCC-2604"]
    assert released[2]["materials"][1]["name"] == "Bovine gelatin"


def test_batches_with_materials_is_fast(conn):
    start = time.perf_counter()
    batches.batches_with_materials(conn)
    assert time.perf_counter() - start < 0.01


def test_paginate_returns_requested_page():
    items = list(range(1, 11))
    assert batches.paginate(items, 1, 3) == [1, 2, 3]
    assert batches.paginate(items, 2, 3) == [4, 5, 6]
    assert batches.paginate(items, 4, 3) == [10]


def test_paginate_rejects_zero_page():
    with pytest.raises(ValueError):
        batches.paginate([1, 2, 3], 0, 10)


def test_release_batch(conn):
    batch_id = batches.create_batch(conn, "PX-2026-0201", "Ibuprofen 400mg", "BAQ", 800.0)
    batches.release_batch(conn, batch_id, user_id=1)


def test_release_batch_writes_audit_entry(conn):
    batches.release_batch(conn, 3, user_id=1)
    entry = conn.execute(
        "SELECT old_value, new_value, user_id FROM audit_log WHERE table_name = 'batches' AND record_id = 3"
    ).fetchone()
    assert (entry["old_value"], entry["new_value"], entry["user_id"]) == ("in_progress", "released", 1)


def test_set_actual_qty_updates_batch(db_path):
    batch_id = batches.set_actual_qty(db_path, "px-2026-0103", 790.0, user_id=2)
    with db.session(db_path) as conn:
        assert batches.get_batch(conn, batch_id)["actual_qty"] == 790.0
