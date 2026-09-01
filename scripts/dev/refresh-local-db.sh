#!/usr/bin/env bash
# Refresh the local Docker Postgres with a fresh copy of the cPanel
# production database, over SSH.
#
#   docker compose up -d db          # start the container if needed
#   scripts/dev/refresh-local-db.sh
#
# Then point .env at the copy:
#   DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/app
#
# Read-only on production — pg_dump only reads. The dump (schema + data +
# the alembic_version stamp, all schemas incl. src_<slug>) is streamed
# over the `brasil-cpanel` SSH connection and loaded into the local `app`
# database, which is dropped and recreated first. Nothing here can touch
# prod. Needs the SSH setup from docs/dev-postgres.md.

set -euo pipefail

SSH_HOST="${SSH_HOST:-brasil-cpanel}"
REMOTE_DIR="${REMOTE_DIR:-flask/brasil-archives}"
CONTAINER="${CONTAINER:-ba-pg10}"
DB="${DB:-app}"

if ! docker exec "$CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
    echo "!! container '$CONTAINER' not ready — run: docker compose up -d db" >&2
    exit 1
fi

echo "==> Dumping production over SSH (read-only) ..."
tmp=$(mktemp -t brasil-prod.XXXXXX.sql.gz)
trap 'rm -f "$tmp"' EXIT
ssh "$SSH_HOST" "cd ~/$REMOTE_DIR && \
  URL=\$(grep '^DATABASE_URL=' .env | sed 's/^DATABASE_URL=//; s#postgresql+psycopg://#postgresql://#; s/[?].*\$//') && \
  PGSSLMODE=disable pg_dump --no-owner --no-privileges \"\$URL\" | gzip" > "$tmp"
echo "    $(du -h "$tmp" | cut -f1) dumped"

echo "==> Recreating local '$DB' ..."
docker exec "$CONTAINER" psql -U postgres -q -tc \
  "select pg_terminate_backend(pid) from pg_stat_activity where datname='$DB' and pid<>pg_backend_pid()" >/dev/null || true
docker exec "$CONTAINER" psql -U postgres -q \
  -c "DROP DATABASE IF EXISTS $DB;" -c "CREATE DATABASE $DB;"

echo "==> Restoring ..."
gunzip -c "$tmp" | docker exec -i "$CONTAINER" psql -U postgres -q -o /dev/null -v ON_ERROR_STOP=1 -d "$DB"

echo "==> Verify:"
for q in \
  "select 'archives                = '||count(*) from archives" \
  "select 'dimension_scores (act.) = '||count(*) from dimension_scores where superseded_at is null" \
  "select 'upgrade_projects        = '||count(*) from upgrade_projects" \
  "select 'aggregated_records_all  = '||count(*) from aggregated_records_all" \
  "select 'alembic head            = '||version_num from alembic_version"
do
  docker exec "$CONTAINER" psql -U postgres -d "$DB" -tAc "$q"
done

echo
echo "==> Ready. In .env:"
echo "    DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/$DB"
