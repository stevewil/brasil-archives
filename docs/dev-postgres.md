# Local development against Postgres

The default test/dev loop is SQLite (`.venv/bin/pytest`, `flask run`).
Production is the **PostgreSQL 10.23** instance the cPanel host provides on
its own `localhost` — the Supabase pooler is unreachable from that box
(outbound `:443` only). Two ways to work against a matching Postgres from
a workstation, for different jobs.

## 1. Docker PG 10 — for running the app and the test suite

A throwaway local Postgres, same major as prod. Safe to drop/recreate.

```bash
docker compose up -d db      # postgres:10; creates app / app_test / migrate_check
docker compose down          # stop (add -v to wipe the volume)
```

Run the suite against it:

```bash
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/app_test .venv/bin/pytest
```

Run the app against it — with a **snapshot of real production data**:

```bash
scripts/dev/refresh-local-db.sh          # pg_dump prod over SSH -> local `app` db
# then in .env:
#   DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/app
.venv/bin/flask run
```

`refresh-local-db.sh` is read-only on prod (`pg_dump` only). It drops and
recreates the local `app` database and loads a point-in-time copy —
schema, all data, every schema including `src_<slug>`, and the
`alembic_version` stamp (so `flask db upgrade` is a no-op against the
copy). It's a **snapshot, not a live link** — re-run the script whenever
you want fresher data. Needs the SSH setup in §2.

Or start from an empty schema instead of a prod copy:

```bash
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/app
.venv/bin/flask db upgrade && .venv/bin/python -m scripts.load_vocabularies   # + the rest
```

CI's `tests-postgres` job runs the full suite on `postgres:10` on every push.

## 2. SSH tunnel — for inspecting real production data

For `psql`, a GUI (DBeaver/pgAdmin), or `pg_dump` against the actual prod
database. **Read-only work only** — see the warning at the bottom.

### One-time setup

1. A dedicated key already exists at `~/.ssh/brasil_cpanel_ed25519`
   (regenerate with `ssh-keygen -t ed25519 -f ~/.ssh/brasil_cpanel_ed25519`).
   Add its `.pub` to **cPanel → SSH Access → Manage SSH Keys → Import Key**,
   then **Authorize** it.
2. In cPanel → SSH Access, read the real **host** and **port** (Namecheap
   shared is typically `serverNNN.web-hosting.com` on `21098` — confirm,
   don't assume). Put them in `~/.ssh/config`:

   ```
   Host brasil-cpanel
       HostName serverNNN.web-hosting.com
       User fromuagq
       Port 21098
       IdentityFile ~/.ssh/brasil_cpanel_ed25519
       IdentitiesOnly yes
   ```
3. Test the shell: `ssh brasil-cpanel` should log in without a password.

### Opening the tunnel

```bash
scripts/dev/pg-tunnel.sh        # localhost:5433 -> cPanel Postgres; Ctrl-C to close
```

Then, in another shell:

```bash
psql 'postgresql://fromuagq_brasil-archives-user:PW@localhost:5433/fromuagq_brasil-archives?sslmode=disable'
```

`sslmode=disable` is correct — the cPanel side is a plaintext localhost
connection; SSH provides the encryption. Local port **5433** stays clear
of the Docker PG on 5432.

### Refreshing local Docker with real prod data

`scripts/dev/refresh-local-db.sh` (see §1) does the whole dump-over-SSH →
restore-into-`app` in one command. Nothing in it can write to prod.

## ⚠️ Never point the test suite at the tunnel

`tests/conftest.py` runs `drop_source_views()` + `db.drop_all()` in the
`app` fixture. If `TEST_DATABASE_URL` (or a stray `DATABASE_URL` picked up
by a script) resolves through the tunnel, **it drops every table in
production**. Keep the tunnel connection string out of `.env` entirely —
use it ad hoc with `psql` / a GUI / `pg_dump`, never through the app or
pytest. For anything that writes or runs migrations, use the Docker PG 10.
