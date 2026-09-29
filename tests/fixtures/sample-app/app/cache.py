"""In-process cache of batch headers for the dashboard endpoints."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import db

TTL_SECONDS = 300

_cache = {}
_stats = {"hits": 0, "misses": 0}
_lock = threading.Lock()


def _load(db_path, batch_no):
    with db.session(db_path) as conn:
        row = conn.execute("SELECT * FROM batches WHERE batch_no = ?", (batch_no,)).fetchone()
    return dict(row) if row else None


def _expired(batch_no):
    loaded_at, _ = _cache[batch_no]
    return time.monotonic() - loaded_at > TTL_SECONDS


def get_batch(db_path, batch_no):
    if batch_no in _cache and not _expired(batch_no):
        _stats["hits"] += 1
        return _cache[batch_no][1]
    _stats["misses"] += 1
    value = _load(db_path, batch_no)
    _cache[batch_no] = (time.monotonic(), value)
    return value


def invalidate(batch_no):
    if batch_no in _cache:
        del _cache[batch_no]


def warm_cache(db_path, batch_numbers, workers=8):
    """Pre-load the given batches in parallel; returns the cache stats afterwards."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for _ in pool.map(lambda batch_no: get_batch(db_path, batch_no), batch_numbers):
            pass
    return stats()


def stats():
    hits, misses = _stats["hits"], _stats["misses"]
    total = hits + misses
    return {
        "hits": hits,
        "misses": misses,
        "hit_rate": round(hits / total, 3) if total else 0.0,
        "size": len(_cache),
    }


def clear():
    with _lock:
        _cache.clear()
        _stats["hits"] = 0
        _stats["misses"] = 0
