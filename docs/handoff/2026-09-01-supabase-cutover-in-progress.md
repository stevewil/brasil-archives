# Handoff — 2026-09-01 · Supabase cutover IN PROGRESS (blocked on cPanel 500s)

**Status:** Phases 1a + 1b merged to `main` and CI-green. Supabase project
fully migrated + seeded + verified. **cPanel cutover started but every page
500s** — `/healthz` connects to Postgres fine, real queries fail. Debugging
was interrupted here.

**Resume at:** § "Pick up here — the 500".

---

## What's done

### Code — merged to `main`
- **PR #1** (`90ebd71`) — phases 1a (Postgres-ready core + CI) and 1b
  (per-source `src_<slug>` schemas). `main` CI green (`tests-sqlite` +
  `tests-postgres`).
- `00a03dc` — gitignore `.claude/settings.local.json`.
- `.claude/settings.local.json` (gitignored) — permission rules so Claude can
  `git push` / `gh pr merge` without prompting.
- Local dev + tests still default to SQLite (`DATABASE_URL` unset). Local
  `.venv` has `psycopg[binary]` 3.3.5 + `cryptography` installed.

### Supabase project — READY (this is the prod target)
- **Ref:** `mwdjvwdpvdpscoxrzcwf` · **PostgreSQL 17.6** · region **us-west-2**
- **Session-pooler URL** (in local `.env` password comment + cPanel `.env`
  line 6):
  ```
  postgresql+psycopg://postgres.mwdjvwdpvdpscoxrzcwf:<PW>@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require
  ```
  PW = `mWtCeXd2gGeJg928ZCHxmw87rBqZ0pZf0hEZe2ESd1UWsebRgBjNfThbvgSmckU9`
  (alphanumeric — no URL-encoding). **→ Proton Pass.**
- **Publishable key** (for the Data-API-off check): `sb_publishable_tsfQcxF_ur63e4WxfUCrVg_ProzieHz`
- **Data API: OFF + verified.** `curl .../rest/v1/dimension_scores` with the
  valid publishable key → `PGRST002 "Could not query the database for the
  schema cache"` on every attempt. `public` is unreachable over REST. (D10 ✓)
- **Migrated + seeded from a local machine** (2026-09-01), so the cutover
  needs **no re-seed** on cPanel:
  - `flask db upgrade` → head `62af3c38c093`
  - `load_vocabularies` / `load_survey` / `seed_povos_archive` /
    `load_upgrade_projects` / `load_calibration` ×2
  - harvest: `mipibu` (oai_dc **508** + oai_ead **508**),
    `povos-indigenas-rn` (**145**) → **1161** total in `src_mipibu` (1016) +
    `src_povos_indigenas_rn` (145)
  - Counts verified: `public.archives`=80, `dimension_scores` active=168,
    `upgrade_projects`=2, `facet_values` active=47, `aggregated_records_all`
    view=1161. **Matches the SQLite prod exactly.**
  - **Local app against Supabase → every page 200** (`/`, `/archives/`,
    `/search?q=terra`, `/search?q=Potiguara`, `/oai` Identify + ListRecords).
    So the code + data + connection are all good *from a workstation*.

### cPanel — cutover STARTED, not complete
- `./github-pull` ran → new code is live (`/healthz` now returns a
  `"database"` field).
- `~/flask/brasil-archives/.env` edited:
  - line 6: the correct Supabase URL **with the real password** (verified)
  - all `DATABASE_URL=sqlite...` lines commented (via
    `sed -i 's/^DATABASE_URL=sqlite/# DATABASE_URL=sqlite/' .env`)
  - `grep -c '^DATABASE_URL=' .env` → 1
  - **`.env.pre-supabase-2026-09-01` backup exists.**
- `touch tmp/restart.txt` → restarted.
- **`curl .../healthz` → `{"database":"postgresql",...}`** — Passenger is
  connecting to Postgres.
- **BUT `/`, `/archives/`, `/search`, `/oai` all return HTTP 500.**
- The old SQLite file is **still in place** (`instance/brasil_archives.db` —
  NOT renamed). Rollback is still trivial.

---

## Pick up here — the 500

`/healthz` works because it only reads `db.engine.dialect.name` (no query).
Every real page 500s → the **connection or every query fails**. It works from
a local machine against the *same* pooler URL, so the difference is the cPanel
environment / network path.

### Diagnostic that was interrupted

Run on cPanel (venv active, in `~/flask/brasil-archives`) — the earlier
attempt used a bare `python -c` with **no `load_dotenv()`**, so it silently
fell back to SQLite (`no such table: public.archives` — a red herring). Do it
**with** dotenv:

```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
from app import create_app
app = create_app()
with app.app_context():
    from app.extensions import db
    from sqlalchemy import text
    print('archives:', db.session.execute(text('select count(*) from public.archives')).scalar())
" 2>&1 | tail -25
```

Also grab the Passenger error log: cPanel → Setup Python App → the app's
error log, or `tail -80 ~/flask/brasil-archives/stderr.log` /
`~/logs/*brasil*`.

### Leading hypothesis — the `options` connect_arg

`app/config.py::_engine_options()` sets, for Postgres:
```python
connect_args={"connect_timeout": 10,
              "options": "-c search_path=public -c statement_timeout=15000"}
```
Supabase's **Supavisor session pooler** has historically rejected the
`options` startup packet (multiple `-c` flags). It worked from the
workstation, but cPanel's psycopg/network may negotiate the startup packet
differently. **Test this first** on cPanel:

```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
import os
from sqlalchemy import create_engine, text
url = os.environ['DATABASE_URL']
for label, ca in [('no-options', {'connect_timeout': 10}),
                  ('with-options', {'connect_timeout': 10, 'options': '-c search_path=public -c statement_timeout=15000'})]:
    try:
        e = create_engine(url, connect_args=ca)
        with e.connect() as c:
            print(label, '->', c.execute(text('select count(*) from archives')).scalar())
    except Exception as ex:
        print(label, 'FAILED:', repr(ex)[:300])
"
```

- **If `no-options` works and `with-options` fails** → confirmed. Fix in
  `_engine_options`: drop `options` entirely (Supabase's default
  `search_path` is `\"$user\", public, extensions` — `public` already
  resolves; move `statement_timeout` to a `SET` via a `connect` event or an
  `execution_options` if wanted). Commit → push → `github-pull` on cPanel →
  restart.
- **If both fail** → it's not the options. Look at: the error log traceback;
  whether `search_path` is somehow empty through the pooler (unqualified
  `archives` unresolvable); NullPool exhausting the free-tier session-pooler
  connection cap under Passenger (would be intermittent, not every-request);
  TLS/`sslmode` negotiation; `statement_timeout` too low for a cross-region
  query.
- **If both work** → the standalone connection is fine and the bug is app-side
  (the `engine_connect` schema-translate listener in `app/services/sources.py`,
  the view models, or the `_storage_info()` / `reset_source` teardown). Get the
  real traceback from the diagnostic above.

### Other suspects (lower probability)
- `create_app()` on cPanel → `ProductionConfig` (`BRASIL_ARCHIVES_CONFIG=production`
  in `.env`); the workstation test used `"development"`. Both inherit the same
  `_engine_options`, but rule it out.
- `passenger_wsgi.py` import order — must `load_dotenv()` **before** importing
  `app` (else `BaseConfig.SQLALCHEMY_ENGINE_OPTIONS` captures the SQLite
  branch). `/healthz` says postgresql, so the URI is right, but double-check
  the engine *options* aren't the SQLite `schema_translate_map` variant.

---

## After the 500 is fixed

1. `curl .../healthz` → `postgresql`; `curl .../` → 200 with 80 / 2 / 1161;
   `/search?q=terra`, `/archives/?q=jornal`, `/oai?verb=Identify` → 200.
2. Confirm public list hides scores (`BRASIL_ARCHIVES_PUBLIC_SCORES` unset).
3. `mv instance/brasil_archives.db instance/brasil_archives.db.pre-pg-2026-09-01`
4. **Keep-alive:** make sure `mwdjvwdpvdpscoxrzcwf` is the project in
   `C:\DEV\supabase-keepalive\keepalive.config.json` (it may reference a
   different/placeholder `brasil-archives` project). Active site traffic also
   keeps it warm now, but belt-and-suspenders. [[supabase-keepalive-deployed]]
5. **Wasabi backup** — wire the cron on cPanel now that prod is Postgres:
   `docs/wasabi-backup.md` §5 (path A) + §9. `pip install -r requirements-backup.txt`
   in the venv; append `WASABI_*` + `BRASIL_ARCHIVES_BACKUP_KEY` +
   `BACKUP_MODE=python` to `~/flask/brasil-archives/.env`; cron `0 4 * * 0`.
6. Docs/cleanup: rewrite `docs/DEPLOY.md` DB section; update
   `docs/handoff/2026-08-27-master.md` storage line; add the data-handling
   note to `LICENSING.md` (spec §9.4); **delete the `prod-db-gets-reseeded`
   memory** (problem solved). Add a `pg_dump`-free weekly backup note.
7. Update `docs/handoff/2026-08-31-postgres-migration-runbook.md` — check off
   Phase 1b-10 (merged) and Phase 2 (done + cutover).

---

## Key facts for resume

| | |
|---|---|
| cPanel | `fromuagq@premium32`, app `~/flask/brasil-archives`, venv `~/virtualenv/flask/brasil-archives/3.13/`, config via `.env` file, deploy via `./github-pull`, startup `passenger_wsgi.py`, restart `touch tmp/restart.txt` |
| Supabase | ref `mwdjvwdpvdpscoxrzcwf`, PG 17.6, us-west-2, session pooler :5432, Data API OFF |
| Rollback | in cPanel `.env`: un-comment the sqlite `DATABASE_URL` line, comment line 6, `touch tmp/restart.txt`. Old SQLite file untouched at `instance/brasil_archives.db`. |
| Local test cmd | `DATABASE_URL="postgresql+psycopg://postgres.mwdjvwdpvdpscoxrzcwf:<PW>@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require" .venv/Scripts/python.exe -m pytest` etc. |
| Docker PG for local dual-backend testing | `docker run -d --name ba-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16` then `TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/test` |
