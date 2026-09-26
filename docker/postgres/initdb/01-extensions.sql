-- Runs once, on an empty data volume only.
-- This directory is mounted over the postgis image's own /docker-entrypoint-initdb.d,
-- so its postgis bootstrap script does not run; create what the app needs here.
-- Migrations use geometry columns and uuid_generate_v4() but create neither extension.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
