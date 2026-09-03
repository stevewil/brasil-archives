# Spec: brasil-archives storage — SQLite → Supabase Postgres

> **SUPERSEDED 2026-09-01 — kept as design history.** The move to Postgres
> shipped, but **not to Supabase**: the Namecheap shared host only permits
> outbound `:443`, so the Supabase pooler is unreachable from it
> (`Connection refused` on both `:5432` and `:6543`). Prod runs on the
> **PostgreSQL 10.23 instance cPanel itself provides on `localhost`**.
> Everything Postgres-shaped in this spec (the per-source `src_<slug>`
> schema design, the seed-is-the-migration approach, the engine/pooling
> config, the CI job) is still accurate and shipped; only the *host* and
> the D10 Data-API privacy checklist (§9.2.1) do not apply — a
> `localhost`-only DB has no anon/REST surface. Outcome + current state:
> `docs/handoff/2026-09-01-supabase-cutover-in-progress.md`.

**Status:** proposal / design. Nothing built. Written 2026-08-30.
**Owner decision points:** §10.

---

## 1. TL;DR

Move brasil-archives's database from the local/cPanel **SQLite file** to a
**Supabase Postgres** project (the free-plan slot that just opened up). The
primary payoff is **durability** — the cPanel SQLite DB is not durable and
recovery is currently a manual re-seed runbook (`docs/DEPLOY.md`, the
`prod-db-gets-reseeded` memory note). Postgres on Supabase ends that.

Two things make this a **low-risk** migration:

1. **The code is already almost dialect-agnostic.** `DATABASE_URL` is honored
   (`app/config.py`), partial indexes already carry `postgresql_where`
   (`app/models/scoring.py`), there are no SQLite `PRAGMA`s or runtime `ALTER`s
   in app code, and JSON is stored as `TEXT` + `json.loads` (works unchanged on
   PG).
2. **There is no precious data to migrate.** Everything authoritative comes
   from git-tracked YAML/markdown via idempotent scripts
   (`scripts/load_*`), and the harvested records are re-derivable by re-running
   `scripts/harvest.py`. **The "migration" is: point at Postgres, `flask db
   upgrade`, run the existing seed sequence once.** No ETL, no `pg_dump`
   import.

Alongside the backend move, **put the auxiliary (harvested / federated) data
for partner projects like mipibu and povos into a dedicated Postgres schema**,
separate from the core catalog tables — see §6.

---

## 2. Why now / what it fixes

| today | after |
|---|---|
| cPanel SQLite DB silently reseeds on some redeploys; missing Pass 2/3 scores, harvest tables, etc. until someone re-runs the recovery runbook | durable managed Postgres; deploys never touch data |
| single-writer file; Passenger workers contend on the file lock | proper concurrent Postgres, connection pooling |
| backup = "hope the file is there" + the reseed scripts | Supabase daily backups + `pg_dump` cron + the reseed scripts as disaster-recovery |
| no way to let another tool query the harvested corpus | optional: expose the `harvest` schema via Supabase's Data API |
| federated + catalog search do a full table scan in Python (`fold()`), with a TODO to "move to FTS5 at ~10⁴ records" | opens the door to `unaccent` + `pg_trgm` / `tsvector` in SQL (Phase 2) |

Non-goals for the core migration (explicitly deferred — see §8):
- Rewriting search to use Postgres FTS.
- Converting `TEXT` JSON columns to `jsonb`.
- Moving naive `timestamp` columns to `timestamptz`.

---

## 3. Current state — what is / isn't SQLite-coupled

**Verified this session by reading the code.**

### Not coupled (works on Postgres as-is)
- `app/config.py` — `SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///…")`. The switch already exists.
- `app/models/scoring.py` — the two partial indexes (`idx_dimension_scores_active`, `idx_facet_values_active`) already declare **both** `sqlite_where` and `postgresql_where`.
- `migrations/versions/68facc4f886d_*` (initial schema) — partial indexes carry `postgresql_where` too.
- No `PRAGMA`, no `ATTACH`, no runtime `ALTER TABLE` in `app/`.
- JSON columns (`aggregated_records.extracted_json`, `.set_specs_json`,
  `federation_cache.response_json`) are `Text` + `json.loads()` at the service
  layer — portable.
- `func.current_timestamp()` server defaults — portable.
- `CheckConstraint("… IN ('a','b',…)")` value lists — portable.

### Needs attention
| item | where | action |
|---|---|---|
| No Postgres driver installed | `requirements.txt` | add `psycopg[binary]` (psycopg 3) |
| No PG engine options (pooling, pre-ping, SSL) | `app/config.py` / `app/extensions.py` | add `SQLALCHEMY_ENGINE_OPTIONS` when the URL is Postgres — §5.2 |
| Alembic `env.py` is stock | `migrations/env.py` | add `include_schemas=True` + the SQLite `schema_translate_map` — §6.4 |
| The 5 existing migrations use `batch_alter_table` | `migrations/versions/*` | audit for `recreate='always'` / SQLite-only ops; plain `batch_alter_table` is a no-op wrapper on PG and is fine — §7.1 |
| `federated_search.search()` and `archives/routes.py::_text_matches` load **all** candidate rows and filter in Python via `fold()` | `app/services/federated_search.py:190+`, `app/blueprints/archives/routes.py` | works unchanged on PG (just a full scan). Phase 2 replaces it with SQL — §8.2 |
| Tests run on `sqlite:///:memory:` (`TestingConfig`) | `app/config.py`, `tests/conftest.py` | keep SQLite as the fast default; add a Postgres CI job — §7.3 |

---

## 4. Target architecture

```
                     ┌────────────────────────────────────────┐
  cPanel (Passenger) │  Flask app  ──psycopg3──►  Supabase     │
  brasil-archives    │  DATABASE_URL = session-pooler URL      │
                     │  NullPool (Supavisor does the pooling)  │
                     └────────────────────────────────────────┘
                                        │
                     Supabase Postgres project (free slot)
                     ├── schema  public   →  core catalog (see §6)
                     │     archives, dimension_scores, dimension_lifts,
                     │     facet_values, probe_results, upgrade_projects,
                     │     periods, record_types, themes, institutional_types,
                     │     + join tables, + alembic_version
                     └── schema  harvest  →  auxiliary / partner-derived data
                           aggregated_records, harvest_runs, harvest_errors,
                           federation_cache
```

- **Local dev + CI unit tests:** unchanged default — `DATABASE_URL` unset →
  SQLite. The `harvest` schema collapses into the single SQLite file via
  `schema_translate_map` (§6.4).
- **cPanel prod:** `DATABASE_URL` = Supabase **session-mode pooler** string.

### 4.1 Connection (the cPanel-specific gotchas)

- **IPv4.** Supabase's *direct* connection (`db.<ref>.supabase.co:5432`) is
  **IPv6-only** unless you buy the IPv4 add-on. cPanel shared hosting is
  IPv4-only. → **Use the Supavisor pooler host**
  (`aws-0-<region>.pooler.supabase.com`), which is IPv4.
- **Session mode, not transaction mode.** Use the pooler's **port 5432**
  (session mode) — it behaves like a real connection (prepared statements,
  `SET`, transactions all work), which is what SQLAlchemy + a long-lived
  Passenger process want. Port 6543 (transaction mode) is for
  serverless/lambda and breaks prepared statements — **do not use it here.**
- **Username** on the pooler is `postgres.<project-ref>`, not `postgres`.
- **TLS required** — `?sslmode=require` in the URL.
- Driver URL scheme: `postgresql+psycopg://` (psycopg 3).

```
DATABASE_URL=postgresql+psycopg://postgres.<ref>:<db-password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

### 4.2 SQLAlchemy engine options (Postgres only)

Passenger prefork + a socket-based pool = fork-safety hazards. Simplest robust
answer for a low-traffic catalog site: **don't pool in the app; let Supavisor
pool.**

```python
# app/config.py — applied only when the URL is Postgres
import sqlalchemy.pool
SQLALCHEMY_ENGINE_OPTIONS = {
    "poolclass": sqlalchemy.pool.NullPool,  # Supavisor is the pool
    "pool_pre_ping": True,
    "connect_args": {"connect_timeout": 10, "options": "-c statement_timeout=15000"},
}
```

Local dev against a real Postgres can keep normal pooling — gate the
`NullPool` on an env flag (`DB_NULLPOOL=1`, set on cPanel) if you want that
flexibility.

---

## 5. What actually changes in the repo (core migration)

1. **`requirements.txt`** — `+ psycopg[binary]>=3.1,<4.0`.
2. **`app/config.py`** — a helper that returns `SQLALCHEMY_ENGINE_OPTIONS`
   when `SQLALCHEMY_DATABASE_URI` starts with `postgresql`; `BaseConfig` picks
   it up. Keep `TestingConfig` on `sqlite:///:memory:`.
3. **`app/models/*`** — the four auxiliary models get
   `__table_args__ = {"schema": "harvest"}` (merged with their existing
   tuples → `(*constraints, {"schema": "harvest"})`). See §6.3.
4. **`migrations/env.py`** — `include_schemas=True`; apply
   `schema_translate_map={"harvest": None}` when the dialect is SQLite; set
   `version_table_schema="public"`.
5. **New migration** — `CREATE SCHEMA IF NOT EXISTS harvest` (Postgres only,
   guarded on `op.get_bind().dialect.name`), then move the four tables into it
   (`ALTER TABLE … SET SCHEMA harvest` on PG; a no-op on SQLite via the
   translate map). Or fold this into a squashed baseline (§7.1).
6. **`tests/conftest.py`** — the test engine gets
   `execution_options(schema_translate_map={"harvest": None})` so
   `harvest.*` tables resolve to the single in-memory SQLite DB.
7. **`docs/DEPLOY.md`** — rewrite the DB section (§9.3).
8. **CI** — add a Postgres job (§7.3).

Everything else — models, queries, services, blueprints, `app/text.py`,
scripts — is untouched by the core migration.

---

## 6. Auxiliary partner data — per-source schemas

> **DECIDED 2026-08-30 (Steve):** each partner source gets its **own Postgres
> schema with an identical table template** (`src_mipibu`,
> `src_povos_indigenas_rn`, `src_<future>` …). This overrides the original
> recommendation below (which argued for one shared `harvest` schema). The
> full mechanical design — model retargeting via `schema_translate_map`, the
> `ensure_source_schema` stamper, the cross-source `*_all` views, the Alembic
> fan-out pattern, dual-backend testing — is in
> **`docs/project-schema-design.md`**. Decisions D1/D7 are resolved there.
> §6.2–6.4 below are retained only as the analysis of the alternative.

### 6.1 Recommendation (SUPERSEDED — see the box above)

~~Put the *derived* partner data in a dedicated `harvest` schema. Do NOT make
per-partner tables.~~ **Superseded: per-source schemas, one template each.**
The reasoning below is kept for the record.

- Core catalog stays in `public`: `archives`, `dimension_scores`,
  `dimension_lifts`, `facet_values`, `probe_results`, the four vocabulary
  tables, join tables, and **`upgrade_projects`** (it is curated registration
  config loaded from `configs/upgrade_projects/*.yaml` — a sibling of the
  vocabularies, not derived data).
- `harvest` schema holds only what is **100% reconstructable by re-running a
  harvest / re-hitting a partner API**:
  `aggregated_records`, `harvest_runs`, `harvest_errors`, `federation_cache`.
- Cross-schema foreign keys (`harvest.aggregated_records.upgrade_project_id →
  public.upgrade_projects.id`) are normal Postgres and stay as-is.

### 6.2 Why a schema, and why not per-partner tables

**Why separate at all:**
- **Durability tiering, encoded in the schema.** `pg_dump --schema=public` is
  the real backup; `harvest` can be excluded from backups and `TRUNCATE`d +
  re-harvested freely (e.g. after an extractor change — today that's
  `scripts/reextract.py`). "Ours vs theirs" becomes a hard boundary.
- **Selective API exposure.** If you ever want another tool (or a public
  read-API) over the harvested corpus, add **only** `harvest` to Supabase →
  Settings → API → *Exposed schemas*. `public` — with the scored judgments —
  stays private. This lines up exactly with the existing public-scores gate
  philosophy (`app/visibility.py`).
- **Permissions.** A future read-only DB role can be `GRANT USAGE ON SCHEMA
  harvest` and nothing else.

**Why NOT `mipibu` / `povos` schemas (or `aux_mipibu_*` tables):**
- The schema is *identical* per partner (OAI Dublin Core). Duplicating it N
  times means every search becomes a UNION across N schemas, facet counts
  need cross-schema aggregation, and the SQLAlchemy models must be
  parameterized by schema or copy-pasted.
- Adding a partner today is a **config row** (`configs/upgrade_projects/<slug>.yaml`
  + `scripts/load_upgrade_projects.py`). Per-partner tables make it a
  **migration**.
- The partner identity is already a **column** (`upgrade_project_id`) with an
  FK and indexes — that is the correct relational model for "same shape,
  different source".
- If genuine *physical* per-partner separation is ever needed (drop one
  partner's data instantly, isolate I/O), the right tool is **Postgres
  declarative partitioning**: `aggregated_records PARTITION BY LIST
  (upgrade_project_id)`, one partition per partner. Transparent to
  SQLAlchemy; `DROP TABLE aggregated_records_povos` purges a partner in O(1).
  Not needed at ~10³–10⁴ records — noted as a future option, not part of this
  spec.

### 6.3 SQLAlchemy model change (example)

```python
# app/models/aggregated_record.py
class AggregatedRecord(db.Model):
    __tablename__ = "aggregated_records"
    __table_args__ = (
        UniqueConstraint("upgrade_project_id", "oai_identifier", "metadata_prefix",
                         name="uq_aggregated_records_identity"),
        Index("ix_aggregated_records_project_datestamp", "upgrade_project_id", "datestamp"),
        Index("ix_aggregated_records_sha", "raw_xml_sha256"),
        {"schema": "harvest"},          # <-- added
    )
    ...
    upgrade_project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("public.upgrade_projects.id", ondelete="CASCADE"),  # <-- schema-qualified
        nullable=False,
    )
    harvest_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("harvest.harvest_runs.id", ondelete="RESTRICT"),    # <-- schema-qualified
        nullable=False,
    )
```

Do the same for `HarvestRun`, `HarvestError`, `FederationCache`. FK targets in
`public` get a `public.` prefix; FK targets within `harvest` get `harvest.`.

### 6.4 Making it work on SQLite too (tests, local dev)

SQLite has no schemas. Use SQLAlchemy's `schema_translate_map` to erase the
`harvest` namespace when the dialect is SQLite:

- **App runtime:** in `app/extensions.py` / the factory, after `db.init_app`,
  if `db.engine.dialect.name == "sqlite"`, wrap the engine with
  `execution_options(schema_translate_map={"harvest": None})`. (Flask-SQLAlchemy
  3.x: set it via `SQLALCHEMY_ENGINE_OPTIONS["execution_options"]`.)
- **Alembic (`migrations/env.py`):** in `run_migrations_online`, when the bind
  is SQLite, pass the same `schema_translate_map` to
  `connection.execution_options(...)` before `context.configure`. Guard the
  `CREATE SCHEMA` / `SET SCHEMA` statements with
  `if op.get_bind().dialect.name == "postgresql":`.
- **Tests:** `tests/conftest.py` `app` fixture already builds the engine via
  the factory, so if the factory applies the map, tests inherit it. Add one
  assertion test that a `harvest.*` model round-trips on both backends.

Net effect: on Postgres the tables live in `harvest`; on SQLite they live in
the one file with their bare names. Same models, same query code.

### 6.5 Fallback if `schema_translate_map` + Alembic proves too fiddly

Use a **table-name prefix** instead: `harvest_aggregated_records`,
`harvest_harvest_runs` (or `aux_*`). Identical on SQLite and PG, zero schema
machinery, still gives `pg_dump -t 'harvest_*'` selectivity and grep-able
grouping. Loses: schema-level API exposure and `GRANT ON SCHEMA`. Promotable
to a real schema later via a rename migration. **Decision D1 in §10.**

---

## 7. Migration mechanics

### 7.1 Alembic strategy

Two viable paths:

**(a) Fix the existing 5 migrations (recommended).**
- Audit each `migrations/versions/*.py` for SQLite-only constructs. The known
  usage is `op.batch_alter_table(...)` — on Postgres this just emits plain
  `ALTER TABLE`, so it is safe *unless* a step uses `recreate='always'` or
  relies on the table-copy semantics. Grep confirms only index creates/drops
  inside batch blocks → safe.
- Add the schema handling to `env.py` (§6.4).
- Add one new migration: create `harvest` schema + `SET SCHEMA` the four
  tables.
- `flask db upgrade` then runs clean against a fresh Postgres DB.

**(b) Squash to a Postgres baseline.**
- `alembic revision --autogenerate` against an empty Postgres from the current
  models → one `0001_baseline` migration (with the `harvest` schema built in).
- Archive the old chain (or delete it — there's no production migration
  history worth preserving since data is reseeded).
- Cleaner going forward; more up-front work; loses the SQLite migration
  history unless you keep a parallel branch.

**Decision D2 in §10.** Default: (a).

### 7.2 "The reseed IS the migration"

Because all authoritative data is script-generated, the cutover data step is
just the existing recovery runbook (`docs/DEPLOY.md` line 11-14), run once
against Postgres:

```bash
FLASK_APP=wsgi.py flask db upgrade                 # creates public + harvest schemas & tables
python -m scripts.load_vocabularies
python -m scripts.load_survey
python -m scripts.seed_povos_archive
python -m scripts.load_upgrade_projects            # mipibu + povos
python -m scripts.load_calibration                 # Pass 2
python -m scripts.load_calibration --path configs/calibration/pass3.yaml   # Pass 3
python -m scripts.harvest --project mipibu         # oai_dc + oai_ead
python -m scripts.harvest --project povos
python -m scripts.reextract                        # if any extractor changed since last harvest
```

Then `pybabel compile -d app/translations` and restart. No `pg_dump` import,
no data ETL.

If there is any hand-entered admin data in the *current* cPanel SQLite that
is NOT reproducible from `configs/` + scripts (there should not be, per the
project's "config lives in YAML" convention), export it first:
`sqlite3 instance/brasil_archives.db .dump > pre-pg-dump.sql` and reconcile
manually.

### 7.3 Testing

- **Unit suite stays on SQLite** (`sqlite:///:memory:`) — fast, no external
  service, 317 tests. The `schema_translate_map` keeps `harvest.*` working.
- **New CI job — full suite on Postgres.** GitHub Actions `services: postgres:10`
  (pinned to the production major — see the 2026-09-01 cutover handoff),
  `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/test`,
  `flask db upgrade` then `pytest`. Runs on every push (it's ~1 min).
- **Likely dialect-difference failures to expect and fix:**
  - Tests that assert result **order without an explicit `ORDER BY`** (SQLite
    often returns insertion order; Postgres does not).
  - `LIKE` case-sensitivity — catalog + federated search fold in Python so
    probably safe, but any raw `LIKE` in a test needs `ILIKE` or `unaccent`.
  - Autoincrement starting value — both start at 1, but a test that inserts,
    deletes, re-inserts and expects a specific id will differ.
  - `func.current_timestamp()` string format assertions.
  - Integer division / `NULLS FIRST|LAST` default ordering.
- Add `pytest -m pg` or a `--pg` flag that points the `app` fixture at
  `$DATABASE_URL` for local Postgres runs.

---

## 8. Deferred — Postgres-native improvements (Phase 2+, separate work)

Keep these **out** of the cutover to bound its risk.

### 8.1 `jsonb`
`aggregated_records.extracted_json` / `.set_specs_json`,
`federation_cache.response_json` → `jsonb`. Enables `->`/`->>`/`@>` and GIN
indexes, and lets `federated_search` filter inside the JSON in SQL instead of
`json.loads`-ing every row. Migration: `ALTER COLUMN … TYPE jsonb USING
…::jsonb`. Ripples to every read site (`app/services/federated_search.py`,
`app/services/federation.py`, `app/blueprints/harvest/routes.py`,
`app/services/probe.py`). Medium effort.

### 8.2 Search into SQL
Today `federated_search.search()` (`app/services/federated_search.py`) and the
catalog `_text_matches` (`app/blueprints/archives/routes.py`) fetch all
candidate rows and filter with `app/text.py::fold()` in Python — the code
comments already flag "move to FTS5 at ~10⁴ records." On Postgres:
- **Option A (parity, low risk):** a stored `folded` text column (generated or
  trigger-maintained) mirroring `fold()`, `WHERE folded LIKE '%needle%'` with a
  `pg_trgm` GIN index.
- **Option B (better UX):** `unaccent()` + `to_tsvector('simple', unaccent(…))`
  generated column + GIN, real ranked FTS. Behavior change (stemming, ranking)
  — needs a test-parity pass.
Recommend A first. Requires the `pg_trgm` and/or `unaccent` extensions
(`CREATE EXTENSION` — available on Supabase).

### 8.3 `timestamptz`
Naive `DateTime` columns + `scoring._utcnow()` work fine on PG as `timestamp`.
Moving to `timestamptz` is better hygiene but touches every model and the
`_utcnow()` helper. Low urgency.

### 8.4 Native ENUMs / domains
The `CheckConstraint("dimension IN (…)")` lists could become PG `ENUM` types.
No functional gain; skip.

---

## 9. Cutover runbook (cPanel)

### 9.1 Prep (no prod impact — do on a branch, merge when green)
1. Add `psycopg[binary]` to `requirements.txt`.
2. Add the PG `SQLALCHEMY_ENGINE_OPTIONS` to `app/config.py`.
3. Move the 4 auxiliary models to `{"schema": "harvest"}`; schema-qualify their
   FKs.
4. Teach `migrations/env.py` the schema + `schema_translate_map`; add the
   `harvest`-schema migration.
5. `tests/conftest.py` — translate map for the test engine.
6. Add the Postgres CI job. Get **both** SQLite and Postgres suites green.
7. Merge.

### 9.2 Create the Supabase project
1. Supabase → new project in the free slot. **Region: match the cPanel
   datacenter** (decision D3 — likely `us-east-1` or `us-west-1`; confirm the
   cPanel host's location). Nano compute is fine.
2. Copy the **session-mode pooler** connection string (Connect → Session
   pooler) and the DB password.
3. Add this project to the keep-alive tool's config
   (`C:\DEV\supabase-keepalive\keepalive.config.json`) so it never pauses —
   see `docs/supabase-keepalive.md`. (Active site traffic also keeps it warm,
   but belt-and-suspenders.)

### 9.2.1 Privacy posture — lock this down at project creation

Moving off SQLite is the first time the data can be protected **at the storage
layer** rather than by "nobody reads the file." But Postgres does not make
anything private on its own, and Supabase's defaults are *more* exposed than a
cPanel SQLite file. Three config choices turn the migration into a privacy
gain instead of a privacy regression — do them when the project is created,
before any real data is loaded.

**Why this matters here:** the scored judgments (`dimension_scores`,
`dimension_lifts`, `facet_values`, the axis totals / quadrant) are
deliberately **not published** (`LICENSING.md` — non-public, unlicensed; the
`BRASIL_ARCHIVES_PUBLIC_SCORES` gate in `app/visibility.py`). Today that data
still sits in a world-readable file and only the app's refusal to render it
keeps it back. After cutover it should be unreachable without the app's own
credentials.

1. **Turn the Data API OFF (or remove `public` from Exposed schemas).**
   Supabase exposes the `public` schema through PostgREST with the `anon` key
   **by default**. brasil-archives does not use the Data API at all — the Flask
   app connects straight through the session pooler. Supabase → Settings → API
   → either disable the Data API entirely, or set *Exposed schemas* to empty /
   remove `public`. **Verify** in §9.3: an unauthenticated
   `curl https://<ref>.supabase.co/rest/v1/dimension_scores?apikey=<anon>`
   must return a 404 / "schema must be one of" error, not rows.
   *If this step is skipped, the migration leaks the scored judgments that
   were previously only file-readable.*

2. **App connects as a dedicated role, not `postgres`, if practical.** The
   pooler user is `postgres.<ref>` (effectively superuser — bypasses RLS and
   every GRANT). For a low-traffic single-app deployment this is acceptable
   (the connection string is the secret boundary), but if a restricted role is
   cheap to maintain, create `brasil_app` with `GRANT`s only on the schemas it
   needs and point `DATABASE_URL` at that. Either way: **`DATABASE_URL` is a
   secret** — it is the whole access-control boundary for `public`. It lives
   only in cPanel's *Setup Python App → Environment variables*, never in the
   repo, never in a handoff doc, never pasted in a screenshot.

3. **Per-source schemas are the API-exposure unit (future).** If a partner is
   ever given a read-only endpoint over their own harvested corpus, expose
   **only** their `src_<slug>` schema — never `public`. A read-only analytics
   consumer gets a role with `GRANT USAGE ON SCHEMA src_<slug>` and nothing
   else. This mirrors the existing public-scores gate philosophy: "ours, with
   the judgments" stays private; "what we harvested from them" can be shared.
   Not doing this now — noting that the boundary exists and which side each
   schema is on (see §12 "Schema ownership at a glance").

**Also inherited for free (no config needed):** TLS in transit
(`sslmode=require` — the SQLite file traveled in the clear in every backup);
`pg_dump --schema=public` backups carry only the sensitive core (§9.4);
network/IP allow-lists are available on the Supabase project if ever wanted.

**New trust boundary to record:** liability-sensitive scoring data now lives
with Supabase (AWS underneath) rather than in a file we hold. Their
encryption-at-rest and access controls beat cPanel shared hosting, but this is
a processor relationship that did not exist before — add a line to
`LICENSING.md` / a data-handling note (§9.4).

### 9.3 Flip cPanel
1. `github-pull` (brings the psycopg dep; `pip install` runs because
   `requirements.txt` changed).
2. In **Setup Python App → Environment variables**: set
   `DATABASE_URL` to the pooler string (`…?sslmode=require`). **Save the old
   SQLite value** in a scratch note for rollback. Optionally set
   `DB_NULLPOOL=1`.
3. In the venv:
   ```bash
   FLASK_APP=wsgi.py flask db upgrade          # creates public + harvest, all tables
   # then the seed sequence from §7.2
   pybabel compile -d app/translations
   ```
4. Restart Passenger. Verify:
   ```bash
   curl -s https://brasil-archives.from-bottom-to.top/healthz
   curl -s 'https://brasil-archives.from-bottom-to.top/search?q=aldeia' | grep -c 'search-hit'
   curl -s 'https://brasil-archives.from-bottom-to.top/archives/?q=jornal' | head -c 200
   ```
   In the Supabase SQL editor:
   ```sql
   select count(*) from public.archives;
   select count(*) from harvest.aggregated_records;
   select relname, n_live_tup from pg_stat_user_tables order by 1;
   ```
   **Privacy check (§9.2.1 step 1):** confirm the scored judgments are NOT
   reachable over the Data API —
   ```bash
   curl -s "https://<ref>.supabase.co/rest/v1/dimension_scores?select=id&limit=1" \
        -H "apikey: <anon-key>"
   ```
   must return an error (`"The schema must be one of the following"` / 404),
   not a JSON array of rows.
5. Rename the old SQLite file: `mv instance/brasil_archives.db instance/brasil_archives.db.pre-pg-$(date +%F)`. Keep it a few weeks.

### 9.4 Docs / cleanup
- `docs/DEPLOY.md`: `DATABASE_URL` is now the Supabase pooler string;
  `flask db upgrade` on every deploy that ships a migration; **the reseed
  sequence is now disaster-recovery only — deploys do not touch data.**
- Delete the `prod-db-gets-reseeded` memory note (problem solved); add a note
  that prod is Supabase Postgres, durable.
- `docs/handoff/2026-08-27-master.md` standing-constraints: update the storage
  line.
- **Privacy / data-handling note** (§9.2.1): record in `LICENSING.md` (or a
  new `docs/data-handling.md`) that the non-public scored judgments now live
  in a Supabase-hosted Postgres (AWS), that `public` is withheld from the Data
  API, and that `DATABASE_URL` is the sole access-control boundary. Confirm the
  Data API check from §9.3 is still green as part of any future Supabase
  dashboard change.
- Add the encrypted **Wasabi off-site backup** — weekly logical dump of the
  core tables (`scripts/backup_to_wasabi.py`, `python` mode — cPanel has only
  `pg_dump 10`), client-side AES-GCM, to a dedicated `brasil-archives` bucket,
  retention via a Wasabi lifecycle rule (~12 weeks). BUILT + verified
  2026-08-31; can run against SQLite prod *before* cutover too. Full design:
  **[`wasabi-backup.md`](wasabi-backup.md)** (resolves D8). Supabase free's own
  daily backup (1-day retention, no PITR) is the thin first layer.

### 9.5 Rollback
Unset `DATABASE_URL` (or restore the saved SQLite value) → restart. If the
SQLite file was renamed, rename it back first, or re-run the seed sequence
against SQLite. Because both backends are "run the seed scripts," rollback is
safe and fast. Keep the SQLite fallback path working until you're confident.

---

## 10. Open decisions

| # | decision | recommendation |
|---|---|---|
| **D1** | Auxiliary data isolation | **RESOLVED 2026-08-30: per-source schemas** (`src_<slug>`), one identical table template each. Full design + sub-decisions P1–P5 in `docs/project-schema-design.md`. |
| **D2** | Alembic: fix the existing 5 migrations vs squash to a PG baseline | **Fix the 5** (they're nearly PG-ready). Squash later if desired. |
| **D3** | Supabase region | Match the cPanel datacenter (confirm host location; probably `us-east-1`). |
| **D4** | Keep SQLite for local dev + unit tests | **Yes** — fast tests, no infra. Add a PG CI job for fidelity. |
| **D5** | App-side pooling on cPanel | **`NullPool`**, let Supavisor pool — sidesteps Passenger fork-safety. |
| **D6** | Phase 2 (jsonb, SQL search) timing | **Defer.** Ship the durable backend first; do search/`jsonb` as separate PRs. |
| **D7** | `upgrade_projects` schema | **`public`** — it's curated config loaded from `configs/`, not derived data. |
| **D8** | Free-tier backup strategy | **RESOLVED + BUILT 2026-08-31:** `scripts/backup_to_wasabi.py` — weekly **Python logical dump** of the core tables (cPanel `pg_dump` is only `10.23`), client-side AES-256-GCM, to the `brasil-archives` Wasabi bucket (us-west-1); retention = Wasabi lifecycle rule (~12 weeks); seed scripts remain the re-derivation fallback. Verified end-to-end against the live bucket. Runs on cPanel via the venv + a weekly cron. Full design → `docs/wasabi-backup.md`. |
| **D9** | Do we also move `media-pipeline-agent`'s DB or leave it? | Out of scope — that's a separate app on its own Supabase project. |
| **D10** | Data privacy posture on Supabase | **RESOLVED 2026-08-31:** Data API OFF / `public` not exposed (the scored judgments must not be reachable with the anon key — Supabase exposes `public` by default); `DATABASE_URL` is the sole access boundary and stays secret; `src_<slug>` is the only unit ever exposed to a partner, never `public`. Full checklist in §9.2.1. |

---

## 11. Effort estimate

| phase | scope | rough size |
|---|---|---|
| Prep (§9.1) | deps, config, schema split, env.py, conftest, CI, get both suites green | **M** (1 focused session) |
| Cutover (§9.2–9.4) | create project, flip env, seed, verify, docs | **S** (½ session + soak) |
| Phase 2 — `jsonb` | column type change + read-site updates | **M** |
| Phase 2 — SQL search | folded column + `pg_trgm` GIN, swap the Python scan | **M** |

---

## 12. Appendix — reference

### Connection string shapes
```
# cPanel prod (IPv4, session pooler, TLS)
postgresql+psycopg://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require

# local dev against a local Postgres
postgresql+psycopg://brasil:brasil@localhost:5432/brasil_archives

# unchanged default (no DATABASE_URL set)
sqlite:///<instance>/brasil_archives.db
```

### Schema ownership at a glance
| schema | tables | recoverable how |
|---|---|---|
| `public` | archives, dimension_scores, dimension_lifts, facet_values, probe_results, upgrade_projects, periods, record_types, themes, institutional_types, archive_periods, archive_record_types, archive_themes, upgrade_project_periods, upgrade_project_record_types, alembic_version | `load_vocabularies` + `load_survey` + `seed_povos_archive` + `load_upgrade_projects` + `load_calibration` ×2 + `probe.py` |
| `harvest` | aggregated_records, harvest_runs, harvest_errors, federation_cache | `scripts/harvest.py` (re-harvest) + `reextract.py` |

### Supabase reserved schemas (do not collide)
`auth`, `storage`, `realtime`, `extensions`, `graphql`, `graphql_public`,
`pgbouncer`, `vault`, `supabase_functions`, `supabase_migrations`,
`_analytics`, `pgsodium*`. `public` and custom names like `harvest` are yours.

### Files this spec touches (core migration only)
`requirements.txt`, `app/config.py`, `app/extensions.py` (or factory),
`app/models/aggregated_record.py`, `app/models/harvest_run.py`,
`app/models/harvest_error.py`, `app/models/federation_cache.py`,
`migrations/env.py`, `migrations/versions/<new>.py`, `tests/conftest.py`,
`docs/DEPLOY.md`, `.github/workflows/*` (new PG job).
