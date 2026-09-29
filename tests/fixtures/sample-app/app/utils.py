"""Small helpers shared across the app."""

import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone

_BATCH_NO = re.compile(r"^[A-Z]{2,4}-\d{4}-\d{3,5}$")


def utc_now_iso():
    """Current UTC time as an ISO-8601 string with second precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_batch_no(text):
    """Normalise a batch number typed by an operator, e.g. ' px-2026-0101 '."""
    cleaned = text.strip().upper().replace(" ", "")
    if not _BATCH_NO.match(cleaned):
        raise ValueError(f"invalid batch number: {text!r}")
    return cleaned


def to_float(value, default=None):
    """Parse a quantity coming from a form or JSON body."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
