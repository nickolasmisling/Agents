-- 001_init.sql
-- Initial schema for the batchtrack records database (PostgreSQL 15).

BEGIN;

CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL
);

CREATE TABLE batches (
    id          BIGSERIAL PRIMARY KEY,
    batch_no    TEXT NOT NULL UNIQUE,
    product     TEXT,
    site        TEXT,
    status      TEXT NOT NULL DEFAULT 'planned',
    planned_qty NUMERIC(14, 3),
    actual_qty  NUMERIC(14, 3),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE materials (
    id       BIGSERIAL PRIMARY KEY,
    batch_id BIGINT NOT NULL REFERENCES batches (id),
    lot_no   TEXT NOT NULL,
    name     TEXT NOT NULL,
    qty      NUMERIC(14, 3)
);

CREATE TABLE signatures (
    id        BIGSERIAL PRIMARY KEY,
    batch_id  BIGINT NOT NULL REFERENCES batches (id),
    user_id   BIGINT NOT NULL REFERENCES users (id),
    meaning   TEXT,
    signed_at TIMESTAMPTZ
);

CREATE TABLE audit_log (
    id         BIGSERIAL PRIMARY KEY,
    table_name TEXT NOT NULL,
    record_id  BIGINT NOT NULL,
    action     TEXT NOT NULL,
    old_value  TEXT,
    new_value  TEXT,
    user_id    BIGINT REFERENCES users (id),
    at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_batches_status ON batches (status);
CREATE INDEX idx_materials_batch ON materials (batch_id);
CREATE INDEX idx_signatures_batch ON signatures (batch_id);
CREATE INDEX idx_audit_log_record ON audit_log (table_name, record_id);

COMMIT;
