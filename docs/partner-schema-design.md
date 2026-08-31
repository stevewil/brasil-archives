# Design: per-source Postgres schemas for partner-harvested data

**Status:** design. Companion to `docs/supabase-migration-spec.md` (read that
first). Written 2026-08-30.
**Decision made (Steve, 2026-08-30):** each partner source (mipibu, povos, and
every future source) gets its **own Postgres schema with an identical table
template**. This doc specifies how.

---

## 1. The decision and why

brasil-archives is a federation aggregator. New partner sources will be
onboarded over time. Rather than one shared `aggregated_records` table
partitioned by an `upgrade_project_id` column, **each source is a
self-contained schema** — an instance of one standard template:

```
public                       core catalog (authoritative, curated)
  archives, dimension_scores, dimension_lifts, facet_values, probe_results,
  upgrade_projects,                <- the registry of ALL sources
  periods, record_types, themes, institutional_types, + join tables,
  aggregated_records_all,          <- read-only UNION view (see §5)
  harvest_runs_all, harvest_errors_all,
  alembic_version

src_mipibu                   one source, standard template
  aggregated_records, harvest_runs, harvest_errors, federation_cache

src_povos_indigenas_rn       another source, same template
  aggregated_records, harvest_runs, harvest_errors, federation_cache

src_<future>                 ...stamped from the same template
```

**Onboarding a new source becomes a repeatable, isolated operation:** add a
`configs/upgrade_projects/<slug>.yaml`, run the loader, and a fresh `src_<slug>`
schema is stamped from the model definitions. **Removing a source is
`DROP SCHEMA src_<slug> CASCADE`** — everything brasil-archives harvested or
cached for that source is gone in one statement, nothing dangling.

**Accepted cost:** a change to the *template* (e.g. a new column on
`aggregated_records`) must fan out across every `src_*` schema via a loop in
one Alembic migration. See §7. This is the price of the isolation; it is
bounded and mechanical.

---

## 2. Which tables are per-source vs shared

| table | schema | rationale |
|---|---|---|
| `aggregated_records` | **per-source** (`src_<slug>`) | the harvested corpus — the thing you drop/reload/expose per partner |
| `harvest_runs` | **per-source** | a source's complete harvest history lives with its data; `DROP SCHEMA` takes it too |
| `harvest_errors` | **per-source** | FK to `harvest_runs`; same lifecycle |
| `federation_cache` | **per-source** | ephemeral (15-min TTL) per-partner API responses; kept in-schema for a clean "everything about this source" boundary |
| `upgrade_projects` | `public` | the **registry of all sources**, loaded from `configs/upgrade_projects/*.yaml`. Not per-source by definition. |
| `probe_results` | `public` | core scoring-adjacent; mostly targets `archives`. Rows that target an upgrade project are a minority — not worth splitting. |
| `dimension_lifts` | `public` | curated scoring artifact loaded from YAML |
| everything else | `public` | core catalog |

**Alternative considered — "corpus-only per-source"** (only `aggregated_records`
per schema; `harvest_runs`/`harvest_errors`/`federation_cache` shared in one
`harvest` schema): simpler (no view needed for run/error lists), but
`DROP SCHEMA src_<slug>` then leaves that source's harvest history behind. We
chose **full per-source** for the clean purge story. If the view machinery
(§5) proves heavy, this is the fallback — it's a localized change.

---

## 3. Schema naming

`src_` + slug with `-` → `_`:

| upgrade project slug | schema |
|---|---|
| `mipibu` | `src_mipibu` |
| `povos-indigenas-rn` | `src_povos_indigenas_rn` |

- `src_` prefix: groups them (`\dn src_*` / `SELECT … WHERE schema_name LIKE 'src\_%'`),
  cannot collide with `public` or Supabase-reserved schemas
  (`auth`, `storage`, `realtime`, `extensions`, `graphql*`, `vault`,
  `supabase_functions`, `pgbouncer`, …).
- Deterministic, computed at runtime — never stored:
  ```python
  def source_schema(slug: str) -> str:
      return "src_" + slug.replace("-", "_")
  ```
- Postgres identifier limit is 63 bytes — fine for any realistic slug.

---

## 4. SQLAlchemy: one model, retargeted per source

### 4.1 Symbolic schema on the write models

The four per-source models declare a **placeholder** schema `"source"` — never
a real Postgres schema, always translated at runtime:

```python
# app/models/aggregated_record.py
class AggregatedRecord(db.Model):
    __tablename__ = "aggregated_records"
    __table_args__ = (
        UniqueConstraint("upgrade_project_id", "oai_identifier", "metadata_prefix",
                         name="uq_aggregated_records_identity"),
        Index("ix_aggregated_records_project_datestamp", "upgrade_project_id", "datestamp"),
        Index("ix_aggregated_records_sha", "raw_xml_sha256"),
        {"schema": "source"},                          # <- placeholder
    )
    ...
    upgrade_project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("public.upgrade_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    harvest_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source.harvest_runs.id", ondelete="RESTRICT"),   # within-source
        nullable=False,
    )
```

`HarvestRun`, `HarvestError`, `FederationCache` get `{"schema": "source"}` the
same way. Within-source FKs use `source.<table>`; FKs to the registry use
`public.upgrade_projects`.

### 4.2 Resolving `"source"` at runtime — `schema_translate_map`

SQLAlchemy's [schema translation](https://docs.sqlalchemy.org/en/20/core/connections.html#translation-of-schema-names)
rewrites `source.aggregated_records` → `src_mipibu.aggregated_records` on a
per-connection basis.

- **Postgres, writing/reading one source's data** (harvest, reextract,
  federation cache): set the map for the operation.
  ```python
  from app.services.sources import source_schema

  def bind_source(slug: str):
      """Point db.session's connection at one source's schema."""
      db.session.connection(execution_options={
          "schema_translate_map": {"source": source_schema(slug)}
      })
  ```
  `harvest.run_harvest(project_slug=…)` is already one-source-per-call — it
  calls `bind_source(slug)` once at the top, before it touches `HarvestRun` /
  `AggregatedRecord`. `app/services/federation.py` calls it per operation
  (it's always scoped to one `UpgradeProject`).
  *Constraint:* the map is connection-wide, so **do not mix two sources'
  writes in one transaction.** Nothing in the codebase does this today.

- **SQLite (local dev + tests):** map `"source"` → `None` **globally**, in the
  engine's execution options, so every per-source table collapses into the one
  SQLite file, disambiguated by `upgrade_project_id` exactly as today.
  ```python
  # factory, after db.init_app(app), when dialect == "sqlite"
  db.engine.update_execution_options(schema_translate_map={"source": None})
  ```

### 4.3 Cross-source reads

Search, the harvest-runs list, and the admin dashboard need **all sources at
once**. They do NOT use the write models. They query read-only view models
(§5).

---

## 5. Cross-source read layer — `*_all` views

### 5.1 The views

Three views in `public`, regenerated whenever the source list changes (§6.3):

| view | Postgres definition | SQLite definition |
|---|---|---|
| `public.aggregated_records_all` | `SELECT ar.*, 'mipibu' AS source_slug FROM src_mipibu.aggregated_records ar UNION ALL SELECT ar.*, 'povos_indigenas_rn' … ` | `SELECT ar.*, up.slug AS source_slug FROM aggregated_records ar JOIN upgrade_projects up ON up.id = ar.upgrade_project_id` |
| `public.harvest_runs_all` | UNION ALL over `src_*.harvest_runs` + `source_slug` | JOIN over the single `harvest_runs` |
| `public.harvest_errors_all` | UNION ALL over `src_*.harvest_errors` + `source_slug` | JOIN over the single `harvest_errors` |

Zero sources registered → the PG view is a typed empty stub
(`SELECT …, NULL::text AS source_slug WHERE false`) so dependent queries never
break on a fresh DB.

### 5.2 Read-only view models

```python
# app/models/_views.py  (new)
class AggregatedRecordView(db.Model):
    __tablename__ = "aggregated_records_all"     # resolves to public.* on PG, bare on SQLite
    __table_args__ = {"info": {"is_view": True}}
    # all columns of AggregatedRecord, mapped read-only, PLUS:
    source_slug: Mapped[str] = mapped_column(String)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)   # views need a PK for the ORM
```

- Alembic must **not** try to create/drop these (`is_view` flag +
  `include_object` hook in `env.py` skips them).
- `db.create_all()` in tests must not create them either — the fixture calls
  the view generator instead (§8).

### 5.3 Call-site changes (read paths only)

| file | today | after |
|---|---|---|
| `app/services/federated_search.py` | `select(AggregatedRecord).where(metadata_prefix == "oai_dc")` | `select(AggregatedRecordView).where(metadata_prefix == "oai_dc")`; `hit.project_slug` comes from `source_slug` instead of the `upgrade_project` relationship (or keep the relationship — `upgrade_project_id` is in the view) |
| `app/blueprints/harvest/routes.py` | `select(HarvestRun)…`, the `AggregatedRecord × UpgradeProject` rollup | `HarvestRunView`, and the rollup groups `aggregated_records_all` by `source_slug, metadata_prefix` |
| `app/blueprints/admin/routes.py` | `_recent_harvest_runs()`, `_recent_harvest_errors()` | `HarvestRunView` / `HarvestErrorView` ordered by `started_at` / `id` |
| `app/blueprints/main.py` | `_aggregated_record_count()` | `select(func.count()).select_from(AggregatedRecordView)` |
| `scripts/reextract.py` (all-sources mode) | iterate `AggregatedRecord` | iterate per source with `bind_source(slug)`, or read via the view and write per source |

Write paths (`harvest.py` service, `federation.py`, `reextract` single-source)
keep the base models + `bind_source()`.

---

## 6. Stamping a source schema from the model template

### 6.1 `ensure_source_schema(engine, slug)`

Builds `src_<slug>` and its four tables **from the model metadata** so the
template can never drift from the models.

```python
# app/services/sources.py  (new)
from sqlalchemy import MetaData, text
from app.models import AggregatedRecord, HarvestRun, HarvestError, FederationCache

_PER_SOURCE = (AggregatedRecord, HarvestRun, HarvestError, FederationCache)

def ensure_source_schema(engine, slug: str) -> None:
    if engine.dialect.name != "postgresql":
        return                      # sqlite: translate map collapses it, nothing to do
    schema = source_schema(slug)
    md = MetaData(schema=schema)
    for model in _PER_SOURCE:
        model.__table__.to_metadata(
            md, schema=schema,
            referred_schema_fn=lambda tbl, to_schema, fk, refl:
                None if fk.target_fullname.startswith("public.")   # keep FKs to public.*
                else schema,                                       # retarget within-source FKs
        )
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        md.create_all(conn, checkfirst=True)
```

### 6.2 `drop_source_schema(engine, slug)` — for de-registering a source

`DROP SCHEMA IF EXISTS "src_<slug>" CASCADE`. Guarded, PG-only, never called
automatically — an operator action (a `--drop <slug>` flag on the loader, or
manual).

### 6.3 View regeneration — `rebuild_source_views(engine)`

Reads the registered slugs from `public.upgrade_projects`, emits
`CREATE OR REPLACE VIEW public.<name>_all AS <UNION ALL …>` for the three
views (PG) or the JOIN form (SQLite). Idempotent. Called after any change to
the source list.

### 6.4 Wiring into the existing loader

Fold both into `scripts/load_upgrade_projects.py` so onboarding stays one
command:

```
python -m scripts.load_upgrade_projects
  → upsert public.upgrade_projects rows        (existing behavior)
  → for each slug: ensure_source_schema(...)   (new, PG only)
  → rebuild_source_views(...)                  (new)
```

Add `--skip-schema-sync` for the rare case you want the row without the
schema. `github-pull` already prints a reminder to run the loader when
`configs/` changes.

---

## 7. Alembic

### 7.1 What Alembic manages

- **`public`** — core catalog + `upgrade_projects` + `alembic_version`.
  Normal migrations.
- **`src_*` schemas** — **not individually versioned.** They are all
  instances of the model template, (re)built by `ensure_source_schema` from
  the *current* model definitions. A fresh install always gets the current
  shape.

### 7.2 `migrations/env.py` changes

```python
context.configure(
    connection=connection,
    target_metadata=get_metadata(),
    include_schemas=True,
    version_table_schema="public",
    include_object=_skip_views_and_source_schema,   # see below
    **conf_args,
)
```

- `include_object` skips (a) the `*_all` views, (b) anything in a `src_*`
  schema and the placeholder `"source"` schema — autogenerate must never try
  to diff those.
- On SQLite, set `connection.execution_options(schema_translate_map={"source": None})`
  before `context.configure` and guard any `CREATE SCHEMA` in migrations with
  `op.get_bind().dialect.name == "postgresql"`.

### 7.3 Changing the per-source template (the ongoing tax)

When a per-source table needs a column/index change, one migration fans out:

```python
def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        op.add_column("aggregated_records", sa.Column("new_col", sa.Text()))  # sqlite: single table
        return
    schemas = [r[0] for r in bind.execute(sa.text(
        "select schema_name from information_schema.schemata where schema_name like 'src\\_%'"
    ))]
    for s in schemas:
        op.add_column("aggregated_records", sa.Column("new_col", sa.Text()), schema=s)
```

**AND** update the model (so `ensure_source_schema` builds the new shape for
future sources / fresh installs). The migration covers existing deployments;
the model covers new ones. Keep them in the same commit.

---

## 8. Testing

### 8.1 SQLite unit suite (the fast default — 317 tests)

- Engine gets `schema_translate_map={"source": None}` → all per-source tables
  are the single shared tables. Behavior is **identical to today**
  (`upgrade_project_id` disambiguates).
- `tests/conftest.py` `app` fixture: after `db.create_all()`, call
  `rebuild_source_views(db.engine)` so `aggregated_records_all` etc. exist
  (the JOIN form).
- Existing tests mostly unaffected. Search/harvest-blueprint tests that
  assert on results now hit the view — verify the `source_slug` column
  doesn't break any assertion.

### 8.2 Postgres CI job (fidelity)

New GitHub Actions job, `services: postgres:16`:
```
flask db upgrade
python -m scripts.load_vocabularies && … && python -m scripts.load_upgrade_projects
# ^ this now also stamps src_mipibu, src_povos_indigenas_rn + the views
pytest
```
Plus targeted tests:
- `ensure_source_schema` is idempotent; creates 4 tables in `src_<slug>`.
- Registering a 3rd source rebuilds the UNION views to include it.
- `drop_source_schema` + `rebuild_source_views` cleanly removes a source.
- A harvest run with `bind_source("mipibu")` writes into
  `src_mipibu.aggregated_records` and is visible via
  `aggregated_records_all` with `source_slug='mipibu'`.
- Cross-source FK: `src_mipibu.aggregated_records.upgrade_project_id`
  references `public.upgrade_projects`.

---

## 9. Supabase-specific notes

- **Per-source API exposure (bonus).** Any `src_*` schema can be added
  individually to Settings → API → *Exposed schemas* to give that partner a
  read-only PostgREST endpoint over only their own aggregated data. `public`
  (with the scored judgments) stays private. Not doing this now — noting the
  capability.
- **RLS:** the app connects as the project's `postgres` role (bypasses RLS).
  Only relevant if a `src_*` schema is API-exposed later — then add
  `anon`-facing RLS or withhold grants.
- **Schema count:** dozens of custom schemas is fine on Supabase. No concern
  at the scale of "one per partner source."
- **Backups:** `pg_dump` (no `--schema`) captures every `src_*` automatically.
  `pg_dump --schema=public` is still the "core only, sources re-harvestable"
  fast backup from the migration spec §9.4.
- **`search_path`:** set `options=-c search_path=public` in `connect_args` so
  unqualified names resolve to `public`; qualified/translated names from the
  models are unaffected.

---

## 10. Downsides — stated plainly

1. **Template changes fan out** (§7.3). Every per-source table alteration is a
   loop-over-schemas migration + a model change, in one commit. This is the
   main ongoing cost.
2. **The `_all` views must stay in sync** with the source list. Mitigated by
   folding `rebuild_source_views` into `load_upgrade_projects` and the
   `github-pull` reminder — but if the loader isn't run after adding a source,
   that source is invisible to search until it is.
3. **More moving parts** than a single `upgrade_project_id`-partitioned table:
   `bind_source()`, `ensure_source_schema`, the view generator, view models,
   the Alembic `include_object` hook.
4. **No cross-source transaction** for writes (the translate map is
   connection-wide). Not a limitation any current code hits.
5. **`Phase 2` search work** (`unaccent`/`pg_trgm` from the migration spec
   §8.2) now lands on the `_all` views / per-source tables — the folded
   column + GIN index must be added to the **template**, so it fans out too.

If (1) or (2) become painful, the fallback is **corpus-only per-source**
(§2) — `aggregated_records` per schema, operational tables shared — which
removes the run/error views and most of the fan-out surface.

---

## 11. Revised phased plan (supersedes migration-spec §6 mechanics)

### Phase 1a — core migration (unchanged from migration-spec §9.1)
psycopg dep, PG engine options, `env.py` baseline, PG CI job, `public`-only
tables green on both backends.

### Phase 1b — per-source schemas
1. Add `{"schema": "source"}` to the 4 models; schema-qualify their FKs.
2. `app/services/sources.py` — `source_schema`, `bind_source`,
   `ensure_source_schema`, `drop_source_schema`, `rebuild_source_views`.
3. `app/models/_views.py` — the 3 read-only view models.
4. `env.py` — `include_object` hook; SQLite translate map.
5. Fold schema-sync + view-rebuild into `scripts/load_upgrade_projects.py`.
6. Swap read call-sites (§5.3) to the view models.
7. `conftest.py` — translate map + `rebuild_source_views` in the fixture.
8. Dual-backend tests (§8). Get green.

### Phase 2 — cutover (migration-spec §9.2–9.4)
Create the Supabase project; on cPanel: `flask db upgrade` →
`load_vocabularies` → `load_survey` → `seed_povos_archive` →
`load_upgrade_projects` *(now also stamps `src_*` + views)* →
`load_calibration` ×2 → `harvest --project mipibu` → `harvest --project
povos-indigenas-rn` → `reextract`. Verify `src_mipibu.aggregated_records` and
`aggregated_records_all`. Update `docs/DEPLOY.md`.

### Phase 3 — deferred (migration-spec §8)
`jsonb`; SQL search via `unaccent`/`pg_trgm` **added to the per-source
template**; `timestamptz`.

---

## 12. Open sub-decisions

| # | question | recommendation |
|---|---|---|
| **P1** | full per-source (all 4 tables) vs corpus-only per-source | **full** — clean `DROP SCHEMA` purge; matches the stated goal. Fall back to corpus-only if fan-out/view upkeep hurts. |
| **P2** | schema name: `src_<slug>` vs bare `<slug>` | **`src_<slug>`** — groupable, collision-proof. |
| **P3** | fold schema-sync into `load_upgrade_projects` vs a separate `scripts/sync_sources.py` | **fold in** (one command to onboard) + keep a thin standalone entrypoint for re-running just the sync. |
| **P4** | keep the `upgrade_project` ORM relationship on the view models, or use `source_slug` only | keep both — `upgrade_project_id` is in the view; `source_slug` is the cheap path. |
| **P5** | de-register flow (`--drop <slug>`) now or later | later — manual `DROP SCHEMA` is fine until a source is actually retired. |
