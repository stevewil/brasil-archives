# Handoff — 2026-09-01 · Postgres cutover DONE (cPanel-local, not Supabase)

**Status: prod is LIVE on Postgres, data verified.** Not Supabase — the
Namecheap shared box only allows outbound `:443`, so the Supabase pooler
is permanently unreachable (see History). Prod runs the **PostgreSQL
10.23 instance cPanel itself provides** on localhost (`fromuagq_brasil-archives`
db). Verified 2026-09-01 ~18:05 UTC directly against the DB:

| | Postgres | target |
|---|---|---|
| archives | 80 | 80 |
| dimension_scores (active) | 168 | 168 |
| upgrade_projects | 2 | 2 |
| facet_values (active) | 47 | 47 |
| aggregated_records_all | 1161 | 1161 |
| schemas | `public, src_mipibu, src_povos_indigenas_rn` | ✓ |
| `*_all` views | all 3 present | ✓ |

Live site: `/healthz` → `database_connected: true`, `/` renders "Archives
cataloged", `/archives/` shows 51, `/search?q=terra` → 8 results, `/oai`
Identify + ListRecords OK.

### What went wrong first (fixed — commit `de44665`)

`flask db upgrade` (Flask CLI, auto-loads `.env`) built the Postgres
schema, but `python -m scripts.load_* / harvest` **did not load `.env`**,
so with `DATABASE_URL` only in the file (not exported) they silently ran
against the SQLite fallback — leaving Postgres with an empty schema while
the site served "No archives". This is almost certainly the real cause of
the historical `prod-db-gets-reseeded` incident too. Fix: `scripts/__init__.py`
now `load_dotenv()` on import. After `./github-pull`, the reseed was
re-run and landed in Postgres correctly (508+508+145 harvested, all
loaders `insert N`).

## Resume here — decommission Supabase + SQLite, wire the backup

1. **Cut ties with SQLite**: on cPanel,
   `mv instance/brasil_archives.db instance/brasil_archives.db.pre-pg-2026-09-01`.
   It still holds the pre-cutover copy (80/168/2/1161) — keep it as a
   belt-and-suspenders snapshot, just get it out of the fallback path.
2. **Cut ties with Supabase** (Steve decided 2026-09-01: **delete** the
   project, not pause):
   - Delete the `mwdjvwdpvdpscoxrzcwf` project in the Supabase dashboard.
     Its DB password is already in public git history (`b3f9b69`) — once
     deleted that's fully moot.
   - Remove the `brasil-archives` entry from
     `C:\DEV\supabase-keepalive\keepalive.config.json` (leave the *other*
     kept-warm project alone). See [[supabase-keepalive-deployed]].
   - Sweep docs that still describe Supabase as the live-DB plan and mark
     them superseded: `docs/supabase-migration-spec.md`,
     `docs/partner-schema-design.md` (mechanism doc stays accurate — it's
     Postgres-generic, just correct the "Supabase" framing),
     `docs/handoff/2026-08-31-postgres-migration-runbook.md` (check off
     Phase 2, note the host pivot), `docs/DEPLOY.md` DB section (describe
     cPanel-local Postgres, not Supabase pooler URLs).
3. **Fix the backup before trusting it** — `scripts/backup_to_wasabi.py`
   `python_dump()` only reads the `_target_schema(engine)` schema
   (`public` on Postgres). The harvested records live in
   `src_mipibu` / `src_povos_indigenas_rn`, which it currently **misses
   entirely**. Either switch `.env` to `BACKUP_MODE=pgdump` (pg_dump 10 on
   the box matches this PG 10.23 server, so `--schema=public` still isn't
   enough on its own — check `pg_dump`'s schema flags support multiple
   `--schema` args or drop to no `--schema` filter for a full-DB dump) or
   extend `python_dump`/`python_restore` to loop every registered
   `src_<slug>` schema. Then wire the cron (`0 4 * * 0`) and test one
   restore.
4. **Rotate the remaining secrets** (see [[secrets-in-handoff-docs]]):
   Wasabi key pair (leaked ID), and — good hygiene, not leaked —
   the cPanel PG password + `SECRET_KEY`. After each, update BOTH the
   cPanel `.env` and the local repo `.env`, plus Proton Pass.
5. Update `LICENSING.md` (spec §9.4) with the data-handling note — the
   privacy posture is simpler now (no Data API / PostgREST layer to
   misconfigure; the DB is `localhost`-only, never network-exposed).
6. Delete the now-resolved [[prod-db-gets-reseeded]] memory once the
   Wasabi backup is verified working — the root cause (scripts not
   loading `.env`) is fixed in `de44665`.

## Local dev access to the prod DB — WORKING

SSH set up 2026-09-01: key `~/.ssh/brasil_cpanel_ed25519`, `brasil-cpanel`
in `~/.ssh/config` (`premium32.web-hosting.com:21098`), pubkey authorized.
Tunnel verified: `scripts/dev/pg-tunnel.sh` → `localhost:5433` → a real
`psycopg` query returned the right counts. (First attempt failed on a
stale background `ssh` holding 5433 — kill `ssh` and retry if it closes
unexpectedly.) Guide: `docs/dev-postgres.md`. Reminder: tunnel = psql/GUI
only, never `TEST_DATABASE_URL`.

---

## History — the Supabase attempt (superseded)

Kept for the record; none of this is the current plan.

**Blocker discovered:** the Namecheap shared box (`fromuagq@premium32`)
permits **only outbound TCP :443**. Confirmed by socket test: the
Supabase pooler was REFUSED on both `:5432` (session) and `:6543`
(transaction) — CSF `TCP_OUT` allowlist, `Connection refused` (active
reject, not a timeout). Direct Postgres to Supabase from this host is not
possible, full stop — no `.env` or code change fixes it.

`supabase-py` (PostgREST over :443) was considered and rejected: it would
require turning the Data API back on (undoing the D10 privacy decision
that keeps the non-public scored judgments out of `public`'s REST
surface), and the app's per-source-schema/ORM/migration code doesn't map
onto PostgREST's query model — a rewrite, not a fix. See
[[public-scores-and-admin-gates]], [[licensing-2026-08-29]].

The pooler-safe connect fix (below) is still correct and still shipped —
it's dialect-generic, not Supabase-specific, and is exactly what made the
cPanel-local Postgres path work cleanly.

## UPDATE 2026-09-01 (later) — pooler-safe connect landed, awaiting cPanel run

Studied `stevewil/media-pipeline-agent`'s Supabase usage. Two transferable
fixes shipped in `5441194` (pushed to `main`, CI pending):

- **`_engine_options`**: dropped the psycopg `options` startup packet
  (Supavisor drops all but the first `-c` — verified: `statement_timeout`
  never took). Added **`prepare_threshold: None`** (psycopg3 prepared-stmt
  collisions across pooled backends — mpa sets this on every connect).
- **`connect` event listener** in `app/config.py` issues `SET search_path` +
  `SET statement_timeout` per connection instead. No-op on SQLite.
- **`/healthz` now runs `SELECT 1`** → 503 + `database_error` when the DB
  can't answer (was a misleading 200 — that's why the 500 was a surprise).
- **`BRASIL_ARCHIVES_DB_CHECK=1`** (opt-in) fail-fast in `create_app()`.

Verified from a workstation against the Supabase pooler: all pages 200,
`search_path='public, extensions'`, `statement_timeout=15s`. Full suite
356 passed.

**Next on cPanel:**
1. `./github-pull` (pulls `5441194` + `scripts/pg_diagnose.py`).
2. Add `BRASIL_ARCHIVES_DB_CHECK=1` to `~/flask/brasil-archives/.env`.
3. `touch tmp/restart.txt`; `curl -s .../healthz` — now a real check.
   - 200 `"database_connected": true` → cutover likely done, verify pages.
   - 503 / still 500 → `source` the venv, run `python -m scripts.pg_diagnose`,
     paste output. `[1] FAILED` = outbound 5432 firewalled (open a ticket
     or move to the `:6543` transaction pooler — already `prepare_threshold`-
     safe and NullPool). `[3]/[4] FAILED` = app-side, grab the traceback.

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
| Local Postgres (matches prod major) | `docker compose up -d db` (PG 10) then `TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/app_test pytest`. CI (`postgres:10`) + full suite verified green on PG 10.21. |
