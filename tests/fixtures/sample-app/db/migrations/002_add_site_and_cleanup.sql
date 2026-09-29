-- 002_add_site_and_cleanup.sql
-- Introduce a sites reference table and move batches from the free-text
-- site column to a site_id foreign key.

BEGIN;

CREATE TABLE sites (
    id       SERIAL PRIMARY KEY,
    code     TEXT NOT NULL UNIQUE,
    name     TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC'
);

INSERT INTO sites (code, name, timezone) VALUES
    ('BOG', 'Bogota plant', 'America/Bogota'),
    ('BAQ', 'Barranquilla plant', 'America/Bogota'),
    ('MIA', 'Miami softgel plant', 'America/New_York');

ALTER TABLE batches
    ADD COLUMN site_id INTEGER NOT NULL REFERENCES sites (id);

UPDATE batches AS b
   SET site_id = s.id
  FROM sites AS s
 WHERE s.code = b.site;

ALTER TABLE batches DROP COLUMN site;

CREATE INDEX idx_batches_site_id ON batches (site_id);

COMMIT;
