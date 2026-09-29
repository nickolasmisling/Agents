"""Client for the site LIMS (laboratory information management system) REST API."""

import json
import urllib.error
import urllib.parse
import urllib.request

from . import LIMS_API_TOKEN, LIMS_BASE_URL

MAX_ATTEMPTS = 3


def _request(method, path, payload=None):
    headers = {"Authorization": f"Bearer {LIMS_API_TOKEN}", "Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(LIMS_BASE_URL + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _send(method, path, payload=None):
    last_error = None
    for _ in range(MAX_ATTEMPTS):
        try:
            return _request(method, path, payload)
        except (urllib.error.URLError, ConnectionError) as exc:
            last_error = exc
    raise last_error


def get_sample_results(lot_no):
    """QC results recorded in LIMS for a material lot."""
    query = urllib.parse.urlencode({"lot": lot_no})
    try:
        data = _send("GET", f"/samples?{query}")
        return data.get("results", [])
    except Exception:
        pass


def submit_sample(batch_no, lot_no, tests):
    """Register a new QC sample in LIMS and return its sample id."""
    payload = {"batch": batch_no, "lot": lot_no, "tests": list(tests)}
    data = _send("POST", "/samples", payload)
    return data["sample_id"]


def is_lot_approved(lot_no):
    results = get_sample_results(lot_no)
    return bool(results) and all(r.get("status") == "pass" for r in results)
