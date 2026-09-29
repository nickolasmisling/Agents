# Architecture

batchtrack records manufacturing batches, the material lots dispensed into
them, electronic signatures and an audit trail. This page gives a short map of
the pieces and how data moves between them.

## Components

| Component | Path | Role |
| --- | --- | --- |
| API | `app/` | Python (standard library only). JSON API over SQLite, yield report, LIMS client, in-process cache. |
| Web UI | `web/` | React + TypeScript single-page app that talks to the API under `/api`. |
| ERP sync | `services/erp-sync/` | Java job that posts released batches to the ERP as goods receipts. |
| Inventory reconciliation | `services/inventory/` | Go CLI that compares lot quantities with warehouse stock exports. |
| Labels | `services/labels/` | .NET service that renders container labels for dispensed lots. |
| Checksums | `services/checksum/` | Rust library for label check digits and export checksums. |
| Migrations | `db/migrations/` | SQL migrations for the shared database. |
| Deployment | `Dockerfile`, `k8s/`, `infra/`, `scripts/` | Container image, Kubernetes manifests, Terraform and ops scripts. |

## Data model

Five tables hold the batch record:

- `batches`: one row per batch (`batch_no`, product, site, status, planned and actual quantity).
- `materials`: lots dispensed into a batch.
- `signatures`: electronic signatures on a batch, with their meaning and time.
- `users`: operators, QA reviewers and administrators.
- `audit_log`: old and new values for every change to a GxP record.

Batch status moves `planned` -> `in_progress` -> `quarantined` -> `released` or `rejected`.

## Request flow

```
browser -> web UI -> /api (app.api) -> SQLite
                                   \-> LIMS REST API (QC results per lot)
ERP sync  -> reads released batches -> ERP
labels    -> reads materials         -> label printer
```

The API process also runs a few scheduled background jobs in-process.

## Yield

Batch yield is `actual_qty / planned_qty * 100`. The site yield report
(`app/report.py`) groups released and rejected batches by site and product
and flags batches outside the 95-102 % window.

## Other data in the repository

- `data/batches.csv`: export of batch headers for the first half of 2026, used for yield analysis.
- `logs/app.log`: two hours of production API log from 2026-09-14.
