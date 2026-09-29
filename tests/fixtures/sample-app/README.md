# batchtrack

batchtrack keeps electronic batch records for a solid-dose and softgel
manufacturing site: batches and their planned/actual quantities, the material
lots dispensed into each batch, electronic signatures, and an audit log. It
exposes a small JSON API and produces a periodic yield report per site.

## Layout

| Path | Contents |
| --- | --- |
| `app/` | Python package: schema and DB helpers, batch/user/signature logic, LIMS client, yield report, JSON API |
| `tests/` | pytest suite for the Python package |

Other components of the repository live in their own top-level directories.

## Requirements

- Python 3.10 or newer (the package uses only the standard library)
- pytest for the test suite

## Running the tests

```sh
pip install -r requirements.txt
python -m pytest -q
```

## Running the API locally

```sh
export BATCHTRACK_DB=./batchtrack.db
python -m app.api
```

The server listens on `http://127.0.0.1:8080`. Useful endpoints:

- `GET /batches?site=BOG&status=released&page=1&page_size=25`
- `GET /batches/<id>`
- `POST /batches` with `{"batchNo": "PX-2026-0101", "product": "...", "site": "BOG", "plannedQty": 1000}`
- `GET /batches/<id>/signatures`, `POST /batches/<id>/signatures`

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `BATCHTRACK_DB` | `batchtrack.db` | SQLite database file |
| `BATCHTRACK_LIMS_URL` | internal LIMS URL | Base URL of the LIMS REST API |
