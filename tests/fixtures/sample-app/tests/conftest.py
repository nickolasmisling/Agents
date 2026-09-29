import pytest

from app import db, users

BATCHES = [
    ("PX-2026-0101", "Paracetamol 500mg", "BOG", "released", 1000.0, 985.0, "2026-03-02T08:00:00+00:00"),
    ("PX-2026-0102", "Paracetamol 500mg", "BOG", "released", 1000.0, 1012.0, "2026-03-05T08:00:00+00:00"),
    ("PX-2026-0103", "Ibuprofen 400mg", "BAQ", "in_progress", 800.0, None, "2026-03-09T08:00:00+00:00"),
    ("SG-2026-0104", "Omega-3 1000mg", "BAQ", "released", 1200.0, 1100.0, "2026-03-12T08:00:00+00:00"),
    ("PX-2026-0105", "Ibuprofen 400mg", "BOG", "rejected", 800.0, 640.0, "2026-03-15T08:00:00+00:00"),
]

MATERIALS = [
    (1, "API-PCM-2601", "Paracetamol", 520.0),
    (1, "EXC-MCC-2604", "Microcrystalline cellulose", 310.0),
    (2, "API-PCM-2601", "Paracetamol", 520.0),
    (3, "API-IBU-2602", "Ibuprofen", 330.0),
    (4, "OIL-OM3-2603", "Fish oil concentrate", 900.0),
    (4, "GEL-BOV-2605", "Bovine gelatin", 260.0),
    (5, "API-IBU-2602", "Ibuprofen", 330.0),
]


def _seed(conn):
    users.create_user(conn, "alice", "Alice#2026qa", role="qa")
    users.create_user(conn, "bob", "Bob#2026ops", role="operator")
    users.create_user(conn, "carol", "Carol#2026adm", role="admin")
    conn.executemany(
        "INSERT INTO batches (batch_no, product, site, status, planned_qty, actual_qty, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        BATCHES,
    )
    conn.executemany(
        "INSERT INTO materials (batch_id, lot_no, name, qty) VALUES (?, ?, ?, ?)", MATERIALS
    )
    conn.commit()


@pytest.fixture
def conn():
    connection = db.connect(":memory:")
    db.init_db(connection)
    _seed(connection)
    yield connection
    connection.close()


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "batchtrack.db")
    with db.session(path) as connection:
        db.init_db(connection)
        _seed(connection)
    return path
