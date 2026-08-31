# Runbook — SQLite → Supabase Postgres, to "app tested on the Supabase connection"

**Goal line:** the brasil-archives Flask app boots and passes a click-through
(`/`, `/archives/`, `/search`, `/healthz`, `/oai?verb=Identify`) with
`DATABASE_URL` pointed at the **Supabase session pooler**, seeded by the normal
script sequence. Prod cutover on cPanel is the step *after* this (§ "After the
goal line").

**Specs (authoritative, don't duplicate):**
[`docs/supabase-migration-spec.md`](../supabase-migration-spec.md) (backend
move; §9.1 prep, §9.2.1 privacy/D10, §10 decisions) +
[`docs/partner-schema-design.md`](../partner-schema-design.md) (per-source
`src_<slug>` schemas; §11 phased plan, §12 sub-decisions). All §10 / §12
decisions are locked.

**Working style:** branch `postgres-migration` off `main`. Commit + **push to
GitHub** at each ✅ milestone (GitHub is source of truth). Merge to `main` when
1a and 1b are both green. cPanel is not touched until "After the goal line".

**Local Postgres:** Docker is available (`postgres:16`). Use it for local
runs; CI uses its own `services: postgres`.

```bash
docker run -d --name ba-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16
# local DATABASE_URL:
#   postgresql+psycopg://postgres:postgres@localhost:5432/postgres
```

---

## Phase 0 — setup

- [ ] `git switch -c postgres-migration`
- [ ] `docker run … postgres:16` (above); confirm `psql`-less connect via
      `python -c "import psycopg"` after step 1a-1.
- [ ] Skim the two specs' decision tables so the rest is mechanical.

---

## Phase 1a — dialect-agnostic core + CI  ·  spec §9.1 (1–2, 6), §5

No behaviour change; SQLite stays the default. Branch only, zero prod impact.

- [ ] **1a-1** `requirements.txt` += `psycopg[binary]>=3.1,<4.0`. `pip install -r requirements.txt` locally.
- [ ] **1a-2** `app/config.py` — add `SQLALCHEMY_ENGINE_OPTIONS` **only when the
      URL starts with `postgresql`** (spec §4.2): `poolclass=NullPool`
      (gate on `DB_NULLPOOL` if you want local pooling), `pool_pre_ping=True`,
      `connect_args={"connect_timeout": 10, "options": "-c statement_timeout=15000"}`.
      Keep `TestingConfig` on `sqlite:///:memory:`.
- [ ] **1a-3** `migrations/env.py` — `include_schemas=True`,
      `version_table_schema="public"`, and when the bind is SQLite apply
      `schema_translate_map` for the symbolic schema `"source"` → `None`
      (spec §6.4 / partner-schema-design §7.2). Add a stub `include_object`
      that already skips a `src_*` / `"source"` schema (finished in 1b).
- [ ] **1a-4** Audit the 5 migrations — all use `op.batch_alter_table`. Confirm
      each batch block is only index create/drop (no `recreate='always'`, no
      column-copy semantics) → safe on PG as plain `ALTER TABLE` (spec §7.1).
      Fix only if the audit finds a real SQLite-ism.
- [ ] **1a-5** `.github/workflows/ci.yml` — **new file** (no `.github/` today).
      Two jobs:
      - `tests-sqlite`: `pip install -r requirements-dev.txt && pytest` (the
        current default suite).
      - `tests-postgres`: `services: postgres:16`,
        `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/test`,
        `FLASK_APP=wsgi.py flask db upgrade` then `pytest`.
      Trigger on push + PR.
- [ ] **1a-6** Local PG run: `DATABASE_URL=…localhost… flask db upgrade` →
      seed sequence (spec §7.2) → `pytest`. Fix dialect-difference failures —
      expect result-order-without-`ORDER BY`, `LIKE` case sensitivity, id-reuse
      assumptions, timestamp string asserts (spec §7.3). Keep the fixes
      backend-neutral so the SQLite suite stays green.
- [ ] **1a-7** Both CI jobs green. **Commit + push.** ✅ *Milestone: suite green on SQLite and Postgres.*

---

## Phase 1b — per-source `src_<slug>` schemas  ·  partner-schema-design §11

- [ ] **1b-1** `{"schema": "source"}` on `AggregatedRecord`, `HarvestRun`,
      `HarvestError`, `FederationCache`; schema-qualify their FKs
      (`public.upgrade_projects`, `source.harvest_runs`) — design §4.1.
- [ ] **1b-2** `app/services/sources.py` (new) — `source_schema(slug)`,
      `bind_source(slug)`, `ensure_source_schema(engine, slug)`,
      `drop_source_schema(engine, slug)`, `rebuild_source_views(engine)` —
      design §4.2, §6.
- [ ] **1b-3** `app/models/_views.py` (new) — read-only `AggregatedRecordView`
      / `HarvestRunView` / `HarvestErrorView` with a `source_slug` column,
      `info={"is_view": True}` — design §5.2.
- [ ] **1b-4** `migrations/env.py` — finish `include_object` (skip the `*_all`
      views + anything in `src_*` / `"source"`) — design §7.2.
- [ ] **1b-5** Swap read call-sites to the view models — design §5.3:
      `app/services/federated_search.py`, `app/blueprints/harvest/routes.py`,
      `app/blueprints/admin/routes.py`, `app/blueprints/main.py`,
      `scripts/reextract.py`. Write paths keep the base models + `bind_source()`.
- [ ] **1b-6** Fold `ensure_source_schema` + `rebuild_source_views` into
      `scripts/load_upgrade_projects.py` (add `--skip-schema-sync`) — design §6.4.
- [ ] **1b-7** `tests/conftest.py` — `schema_translate_map={"source": None}` on
      the test engine; call `rebuild_source_views(db.engine)` in the `app`
      fixture after `create_all` — design §8.1.
- [ ] **1b-8** Add the PG-only targeted tests from design §8.2
      (`ensure_source_schema` idempotent, 3rd-source view rebuild, `bind_source`
      write lands in `src_mipibu.*` and shows in `aggregated_records_all`,
      cross-schema FK to `public`).
- [ ] **1b-9** Both CI jobs green (the PG job's `load_upgrade_projects` now also
      stamps `src_mipibu` / `src_povos_indigenas_rn` + the views). **Commit + push.**
- [ ] **1b-10** Open PR `postgres-migration` → `main`, self-review, merge. ✅ *Milestone: dual-backend green, per-source schemas in.*

---

## Phase 2 — Supabase project + connect  ·  spec §9.2, §9.2.1

- [ ] **2-1** Decide: reuse the existing `brasil-archives` Supabase project
      (the one [[supabase-keepalive-deployed]] already keeps warm) or create
      fresh. Region = **match the cPanel datacenter** (check the host; likely
      `us-east-1`) — spec D3. Note this is unrelated to the Wasabi bucket's
      `us-west-1`.
- [ ] **2-2 — PRIVACY POSTURE (D10 / spec §9.2.1), do at creation:**
      - Data API **OFF** (Settings → API), or `public` removed from Exposed
        schemas. brasil-archives never uses PostgREST.
      - Verify: unauthenticated
        `curl "https://<ref>.supabase.co/rest/v1/dimension_scores?limit=1" -H "apikey: <anon>"`
        returns an error, **not rows**.
      - Treat `DATABASE_URL` as the sole access boundary — env only, never repo.
- [ ] **2-3** Copy the **session-mode pooler** string (Connect → Session
      pooler, **port 5432**), user `postgres.<ref>`, add `?sslmode=require`.
      Scheme `postgresql+psycopg://`. Run `select version();` — confirm the PG
      major (informational; the logical-dump backup is version-proof anyway).
- [ ] **2-4** Confirm the project is in the keep-alive config
      (`C:\DEV\supabase-keepalive\keepalive.config.json`) — it already should be.
- [ ] **2-5 — THE TEST.** Locally:
      ```bash
      DATABASE_URL="postgresql+psycopg://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require"
      FLASK_APP=wsgi.py flask db upgrade            # builds public + src_* + views
      python -m scripts.load_vocabularies
      python -m scripts.load_survey
      python -m scripts.seed_povos_archive
      python -m scripts.load_upgrade_projects       # also stamps src_* + views
      python -m scripts.load_calibration
      python -m scripts.load_calibration --path configs/calibration/pass3.yaml
      python -m scripts.harvest --project mipibu
      python -m scripts.harvest --project povos-indigenas-rn
      pytest -q                                     # or a subset against the live conn
      ./app.bat start                              # or: python wsgi.py  (port 9000)
      ```
      Click-through: `/`, `/archives/?q=terra`, `/search?q=aldeia`,
      `/healthz`, `/oai?verb=Identify`, `/admin/` (with `BRASIL_ARCHIVES_ADMIN=1`).
      In the Supabase SQL editor: `select count(*) from public.archives;`
      `select count(*) from src_mipibu.aggregated_records;`
- [ ] **2-6** ✅ **GOAL LINE: app runs and passes the click-through on the
      Supabase connection.** Commit any test-shakeout fixes + push.

---

## Parallel track — Wasabi backup on cPanel  (do early; independent of the above)

Code is done + verified ([`docs/wasabi-backup.md`](../wasabi-backup.md)).
`python` mode backs up the **current SQLite prod** too, so wiring this now
closes the [[prod-db-gets-reseeded]] window months before cutover.

- [ ] **W-1** cPanel venv: `pip install -r requirements-backup.txt`.
- [ ] **W-2** Append to `~/flask/brasil-archives/.env` (`chmod 600`): the
      `WASABI_*` block + `BRASIL_ARCHIVES_BACKUP_KEY` (from Proton Pass) +
      `BACKUP_PREFIX=pg/` + `BACKUP_MODE=python` (values in wasabi-backup.md §11).
- [ ] **W-3** `venv/bin/python -m scripts.backup_to_wasabi --selftest` then a
      real run; confirm the object in `--list`.
- [ ] **W-4** Weekly cron `0 4 * * 0 cd ~/flask/brasil-archives && venv/bin/python -m scripts.backup_to_wasabi >> ~/logs/backup.log 2>&1`.
- [ ] **W-5** Wasabi console: **versioning ON** + **lifecycle rule** (expire
      `pg/` after 90d, noncurrent 30d).
- [ ] **W-6** Write the restore-drill section into `docs/DEPLOY.md`
      (wasabi-backup.md §10), then actually run it once.
- [ ] **W-7** (optional) swap the `.env` key for a bucket-scoped no-delete
      Wasabi sub-user.

---

## After the goal line — prod cutover (cPanel)  ·  spec §9.3–9.5

Not part of "testing the connection"; listed so the path is visible.

- [ ] `github-pull` on cPanel (brings psycopg; `pip install` fires).
- [ ] Setup Python App → env: set `DATABASE_URL` to the pooler string. **Save
      the old SQLite value** for rollback.
- [ ] In the venv: `flask db upgrade` → the seed sequence (§2-5) →
      `pybabel compile -d app/translations` → restart Passenger.
- [ ] Verify live: `/healthz`, `/search?q=aldeia`, `/archives/?q=jornal`,
      zero score labels on the public list (the `PUBLIC_SCORES` gate), Supabase
      row counts.
- [ ] `mv instance/brasil_archives.db instance/brasil_archives.db.pre-pg-$(date +%F)`.
- [ ] Rollback path if needed: unset `DATABASE_URL` → restart (spec §9.5).

---

## Housekeeping folded in (do at the point noted)

- [ ] **At 2-6 / after cutover:** delete the `prod-db-gets-reseeded` memory
      (problem solved); add a note that prod is durable Postgres.
- [ ] **After cutover:** rewrite `docs/DEPLOY.md` DB section (spec §9.4);
      update `docs/handoff/2026-08-27-master.md` storage line; add the
      data-handling note (spec §9.2.1) to `LICENSING.md`.
- [ ] **Unrelated, still open (handoff 2026-08-31 §"Open items" #1):** revoke
      the two exposed GitHub PATs; decide the app-dashboard vault `GITHUB_PAT`
      fate. Not blocking this runbook.
- [ ] **After 1a merges:** `TODO.md §6` still lists the probe/harvest crons as
      open — they're live; tidy that when convenient.

---

## Done when

`postgres-migration` is merged to `main` and pushed, both CI jobs are green,
the Wasabi backup cron is live on cPanel, and the app has passed the §2-5
click-through against the Supabase session pooler. Prod cutover is then a
separate, low-risk session (spec §9.3).
