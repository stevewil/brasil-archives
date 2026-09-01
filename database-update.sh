#!/usr/bin/env bash
# Refresh the local dev database with a fresh snapshot of cPanel production.
#
#   ./database-update.sh
#
# Starts the local Docker Postgres if it isn't up, then pulls a fresh
# pg_dump of prod over SSH into the local `app` database. Read-only on
# production. Run it whenever your local copy feels stale.
#
# Needs: Docker, and the `brasil-cpanel` SSH host (see docs/dev-postgres.md).
# After it runs, point .env at the copy (one-time):
#   DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/app

set -euo pipefail
cd "$(dirname "$0")"

CONTAINER="${CONTAINER:-ba-pg10}"

if ! command -v docker >/dev/null 2>&1; then
    echo "!! Docker not found — install Docker Desktop and retry." >&2
    exit 1
fi

echo "==> Starting local Postgres (docker compose up -d db) ..."
docker compose up -d db

echo "==> Waiting for it to accept connections ..."
for i in $(seq 1 30); do
    if docker exec "$CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
        echo "    ready."
        break
    fi
    sleep 1
    if [ "$i" -eq 30 ]; then
        echo "!! '$CONTAINER' never became ready. Check: docker compose logs db" >&2
        exit 1
    fi
done

echo
exec scripts/dev/refresh-local-db.sh
