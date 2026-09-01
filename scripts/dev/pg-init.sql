-- Runs once, on first boot of the docker-compose `db` service (empty volume).
-- Postgres' entrypoint has already created the default `postgres` database
-- and role; this just adds the extra DBs the workflows expect.
--   app          — run the app locally against Postgres
--   app_test     — the pytest target (TEST_DATABASE_URL); fixtures drop/recreate
--   migrate_check — a throwaway DB for "migrations + seed apply cleanly"
CREATE DATABASE app;
CREATE DATABASE app_test;
CREATE DATABASE migrate_check;
