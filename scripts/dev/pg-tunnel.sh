#!/usr/bin/env bash
# Forward the cPanel-local production Postgres to localhost:5433 over SSH.
#
#   scripts/dev/pg-tunnel.sh          # runs in the foreground; Ctrl-C to stop
#
# Needs a `brasil-cpanel` Host entry in ~/.ssh/config (see docs/dev-postgres.md).
# Local port 5433 is deliberate — it stays clear of the Docker PG 10 on 5432.
#
# READ-ONLY WORK ONLY. This points at real production data. NEVER set
# TEST_DATABASE_URL to this tunnel — the pytest fixtures run db.drop_all().
# For running the app or the suite on Postgres, use `docker compose up -d db`.

set -euo pipefail

LOCAL_PORT="${1:-5433}"
echo "Tunnel: localhost:${LOCAL_PORT} -> cPanel localhost:5432 (prod Postgres)"
echo "Connect with:"
echo "  psql 'postgresql://fromuagq_brasil-archives-user:PW@localhost:${LOCAL_PORT}/fromuagq_brasil-archives?sslmode=disable'"
echo "Ctrl-C to close."
exec ssh -N -L "${LOCAL_PORT}:localhost:5432" brasil-cpanel
