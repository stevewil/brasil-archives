# brasil-archives — what this app is

**Written:** 2026-08-27, from a full read of `docs/` and the code. A working
narrative for someone new to the repo. For the authoritative design, follow
the links into `docs/`; where this file and a `docs/` file disagree, `docs/`
wins.

---

## One sentence

`brasil-archives` is a bilingual (PT/EN) Flask catalog of Brazilian digital
archives that **scores** each archive for "is it worth building a
Mipibu-style research pipeline against this?", and acts as the **federation
aggregator** for a small constellation of companion "corpus explorer" apps.

It is a *catalog and a routing layer*, never a content host. Documents live
at the source archive or in a companion app; `brasil-archives` describes,
scores, links out, and harvests metadata.

## Who it's for

Two audiences, one dataset:

1. **Internal** — a resource-constrained scholarly team deciding which of
   ~79 surveyed Northeast-Brazil archives to invest pipeline-building effort
   in. This is the live use today (the scoring UI, the harvest debugging
   views).
2. **Public (later)** — a read-only bilingual site where researchers filter
   and locate archives by score and facet. The admin/public split shipped
   2026-08-27 (UI-Polish Track 2): the public deployment leaves
   `BRASIL_ARCHIVES_ADMIN` unset, which 404s the scoring forms, facet
   editor, and `/harvest`, and swaps the detail page's score block for a
   read-only table.

**Domain frame:** national-period historian focus (roughly 1800–1900),
Northeast Brazil (the nine states AL BA CE MA PB PE PI RN SE), ecclesiastical
and judicial sources prominent. Explicitly **rejects age-as-value bias** — a
1960s archive is not automatically worth less than an 1860s one.

**Fundamental floor:** every archive shown on the eventual public site must
clear *fair use / uso justo for scholarly work* (`fair_use_eligible`).
Archives that can't are kept internally so they aren't re-researched, but
never surfaced publicly. Terminology is fixed: "uso justo", never "uso
legítimo".

## The ecosystem it sits in

Three repos (see `docs/handoff/2026-08-27-master.md`):

| Repo | Role |
|---|---|
| **brasil-archives** (this) | Catalog + scoring + federation aggregator |
| **mipibu** | São José de Mipibu judicial-records corpus explorer; the reference companion. Live, exposes OAI-PMH + a federation JSON API |
| **povos-indigenas-rn** | Indigenous history of RN corpus explorer; scaffolded, not yet federating |

Companion apps register with brasil-archives as **upgrade projects** and
speak a **federation contract** (`docs/federation-v1.md`): OAI-PMH for
metadata harvest, an optional lightweight JSON API (`/api/health`,
`/api/schema`, `/api/records`, `/api/records/<id>`) for live previews, and
optionally IIIF Content Search (not consumed yet).

Design stance (`docs/scenario-driven-federation-model.md`): federation is an
**index, not a mirror**; companion apps are deliberately **monolithic** — no
shared framework is extracted until three companion apps exist across two
material classes ("rule of three").

## The scoring model (the intellectual core)

Full spec: `docs/algorithm-v1.md`, `docs/adr-0001-two-axis-aggregation.md`.

**Eight scored dimensions**, each 0–10 with written anchor points and a
per-archive justification (EN + optional PT):

- **Pipeline axis** (cost to reach the material): `accessibility`,
  `finding_aids`, `pipeline_ingestion_readiness`, `scale`
- **Research axis** (value once reached): `provenance_curatorial`,
  `corpus_completeness`, `uniqueness_non_duplication`, `linkage_potential`

Three aggregations are shown, none stored:

- **Naive sum** 0–80 — legacy, unweighted, still sortable
- **Two axis totals** 0–40 each — an unweighted sum per axis
- **Quadrant label** at threshold 28/40 ("High pipeline / Low research" etc.,
  or `n.a.` if an axis has no scores)

The 4-4 axis partition lives in **code** (`app/services/scoring.py` `AXES`)
with an **import-time assertion** that every dimension is in exactly one
axis. Changing the partition is a code-review event, not a config edit.

**Facets** (12, not scored — filterable/annotative): time period, record
type, themes (all multi-select vocab), institutional type, licensing
posture, stated roadmap, `scholarly_access_practical`
(`well-supported` / `usable-with-effort` / `only-via-federation` /
`not-yet-assessed`), plus free-text rarity notes and prior-use notes, plus
four probe-updated health/growth signals (probe not built yet).

Anything requiring a value judgment tied to a researcher's frame (which
record types matter, which themes are significant, how old is "old") is a
**facet**, not a score. Anything requiring predicting the future
(institutional durability, growth) became a facet fed by a periodic probe.

**Scoring status:** the algorithm is designed and a 6-archive calibration
set (`configs/calibration/pass2.yaml`) was scored on paper, but the live DB
has **zero `DimensionScore` / `FacetValue` rows** — detail pages currently
render mostly `—` placeholders. Scoring the survey is future work.

## Standards posture

`docs/standards.md` — the project deliberately does not invent exchange
formats. It adopts ISAD(G) / ISDIAH / ISAAR(CPF) for description, Dublin
Core / EAD / EAG / EAC-CPF for encoding, **OAI-PMH** for harvest, IIIF
Content Search for federated search, and records Handle / DOI / ARK / VIAF /
GeoNames / Wikidata / ISNI identifiers as first-class columns. Phased
adoption: Phase 1 = standards-aware schema; later phases = standards-native
input, then output, then LOD. No MARC (library standard, not archival). No
bespoke REST API.

## The code

Flask app factory + SQLAlchemy 2.0 + Flask-Migrate (Alembic) + Flask-Babel +
Flask-WTF. SQLite for dev and initial deploy; portable to Postgres.

```
app/
  __init__.py          create_app(): wires extensions, registers vocab_label
                       + get_locale Jinja globals, mounts 3 blueprints,
                       adds /healthz
  config.py            Base/Development/Testing/Production configs.
                       resolve_config() REFUSES to return ProductionConfig
                       if SECRET_KEY is unset or "dev-secret-change-me".
  extensions.py        db, migrate, babel, csrf singletons
  i18n.py              resolve_label() (pure, unit-tested) + vocab_label()
                       Jinja wrapper — picks label_pt/label_en by locale,
                       falls back EN → "".

  models/
    archive.py           Archive — one institution/collection. Standards-
                         aware ID columns, editorial flags (no_digital_content,
                         fair_use_eligible, caveat_emptor), survey provenance.
    upgrade_project.py   UpgradeProject — a registered companion app.
                         source_archive_id NOT NULL (every companion points
                         at an archives row). Federation endpoint columns.
    scoring.py           DimensionScore, DimensionLift, FacetValue — all
                         history-bearing (superseded_at / superseded_by_id;
                         new value = new row, old row retained).
    probe.py             ProbeResult — quarterly health probe (table only,
                         no probe runner yet).
    vocabularies.py      Period, RecordType, Theme, InstitutionalType —
                         controlled vocab as tables (label_en, label_pt,
                         sort_order), editable without migrations.
    joins.py             archive_periods / _record_types / _themes and the
                         upgrade_project_* equivalents.
    federation_cache.py  FederationCache — 15-min TTL cache of companion
                         JSON responses.
    aggregated_record.py / harvest_run.py / harvest_error.py
                         Phase 3 harvest store (below).

  services/
    scoring.py           active_scores / naive_sum / axis_scores /
                         quadrant_label + the AXES partition (guarded at
                         import). Write helpers record_score / set_facet_value
                         / set_archive_tags do the supersede-and-insert dance;
                         blueprint stays thin.
    federation.py        Phase 2 JSON federation client. urllib, 8s timeout,
                         cache-first, serves STALE cache on upstream failure,
                         raises FederationUnavailable only when there's no
                         cache at all. Never breaks a page render.
    oai_client.py        Phase 3 read-only OAI-PMH 2.0 client. Identify +
                         ListRecords with transparent resumption-token
                         paging. 30s timeout. noRecordsMatch → empty
                         iterator (not an error); protocol/HTTP errors raise.
    oai_extractors/      Registry {oai_dc, oai_ead} → pure Element→dict
                         functions returning {"canonical": {...}, "raw": {...}}.
                         New metadata format = new extractor, no migration.
    harvest.py           run_harvest(): one HarvestRun row per invocation,
                         per-record upsert keyed by
                         (project, oai_identifier, prefix) with SHA-256 of
                         raw XML as the change oracle. Per-record failures
                         → HarvestError rows, run continues; HTTP/protocol
                         failure → run marked 'failed'. dry_run supported.
    static_harvest.py    Fallback: fetch a single static OAI-DC XML dump for
                         companions that can't run a live endpoint.

  blueprints/
    main.py              /  (landing: stat tiles, featured archives,
                        browse-by-state chips, live partner federation
                        preview), /healthz
    archives/            /archives/ (filter by state/type/content, sort by
                         name/pipeline/research/naive-sum, NULLs last),
                         /archives/<slug> (detail: score cards, axis card,
                         facets, live federation preview per companion),
                         /archives/<slug>/score  (POST, history-aware),
                         /archives/<slug>/facets (GET/POST, facets + tags)
    harvest/             /harvest/ (run list + rollups),
                         /harvest/runs/<id>, /harvest/records/<id>.
                         Read-only debugging surface; writes are CLI-only.

  templates/  base.html + index + archives/{list,detail,facets} +
              harvest/{index,run_detail,record_detail}. All user-facing
              strings wrapped in {{ _() }}; catalogs in app/translations/
              (pt fully translated, en is the anchor; .mo git-ignored,
              compiled at deploy). Hand-authored CSS with design tokens in
              static/style.css. No CSS framework.

scripts/
  load_vocabularies.py     configs/vocabularies/*.yaml → vocab tables
  load_survey.py           docs/nordeste-digital-archives-survey.md → archives
                           (Table 1 = 50 pipeline-viable, Table 2 = 29
                           no-content; slug like ...-t1r8 = table 1 row 8)
  load_upgrade_projects.py  configs/upgrade_projects/*.yaml → upgrade_projects
                            (idempotent upsert by slug)
  load_calibration.py       configs/calibration/pass2.yaml (paper scores)
  harvest.py                CLI: --list / --project <slug> [--format oai_ead]
                            [--since] [--dry-run]. Exit 0=ok 1=partial 2=failed
  dev/session_state.sh      bootstrap digest for a new agent session

migrations/versions/  3 revisions: initial schema → federation_cache +
                      json_api_base_url → aggregated_records + harvest_runs
                      + harvest_errors
```

### Request-time data flow, archive detail page

1. Load `Archive` by slug (404 if missing), eager-load vocab relations.
2. `svc.active_scores` / `score_history` per dimension → score cards + forms.
3. `svc.axis_scores` + `quadrant_label` → the two-axis profile card.
4. For each `UpgradeProject` whose `source_archive_id` matches: call
   `federation._fetch` → cache-first `GET /api/health` on the companion.
   Any failure becomes an "unavailable" panel; a live hit shows record
   count + corpus version + a deep link into the companion's browse UI.

### The harvest pipeline (Phase 3 Track 2 — "data pipe only")

`scripts/harvest.py --project mipibu [--format oai_ead]` →
`services/harvest.run_harvest` → `oai_client.iterate_records` (resumption
paging) → per record: parse header, run the format extractor, SHA-256 the
raw `<record>` XML, upsert into `aggregated_records`. It **changes no
scores and adds no public UI** — it stockpiles record-level data for a
future rescoring pass. mipibu yields 508 records for `oai_dc` and 508 for
`oai_ead` (1016 total).

## Running it locally

```bash
py -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
# .env: FLASK_APP=wsgi.py, a real SECRET_KEY, FLASK_RUN_PORT=9000,
#       leave DATABASE_URL unset (defaults to an absolute instance/ path)

export FLASK_APP=wsgi.py
.venv/Scripts/python -m flask db upgrade
.venv/Scripts/python -m scripts.load_vocabularies
.venv/Scripts/python -m scripts.load_survey
.venv/Scripts/python -m scripts.load_upgrade_projects
.venv/Scripts/python -m scripts.load_calibration                     # Pass 2 anchor scores
.venv/Scripts/python -m scripts.harvest --project mipibu              # optional
.venv/Scripts/python -m scripts.harvest --project mipibu --format oai_ead

.venv/Scripts/python -m flask run          # http://127.0.0.1:9000
.venv/Scripts/python -m pytest             # 144 passed, 5 skipped (opt-in live)
```

Local dev port is **9000** (workstation convention: one port per app —
mipibu 5050, povos 5051, etc.). `instance/` and `.env` are git-ignored.

**Deploy** (`docs/DEPLOY.md`): GitHub is the source of truth; cPanel
*pulls*, never receives a push. `git pull` → `flask db upgrade` (if schema
changed) → `touch tmp/restart.txt` → `curl .../healthz`.

## Current state (2026-08-27)

- **Phase 3 shipped**: schema, survey load, Phase 2 JSON federation +
  15-min cache, Phase 3 OAI-PMH harvest into `aggregated_records`, live
  federation preview on archive detail, locale-aware vocab labels.
- **DB after a full local load**: 79 archives, 1 upgrade project (mipibu),
  1016 aggregated records, 2 harvest runs.
- **Not built yet**: any real `DimensionScore` data in prod; the quarterly
  health probe; IIIF Content Search fanout; cron-scheduled harvest; povos
  federating.
- **UI polish**: all 5 tracks landed (Track 1 PT translation catalog,
  Track 2 admin split, Track 3 home redesign, Track 4 vocab labels,
  Track 5 metadata/favicon/CSS). See `docs/UI-POLISH-PICKUP.md`. Track 1
  and Track 3 not yet pulled to cPanel; Track 1's deploy needs a
  `pybabel compile -d app/translations` step (`.mo` files are git-ignored).

## Conventions worth knowing

- **History tables never destructively update.** New score/facet value →
  new row; the old row gets `superseded_at` + `superseded_by_id`.
- **Composite scores are computed, never persisted.** The dimensions are
  authoritative; the aggregation is a display choice.
- **Modeling decisions live in code, config lives in YAML.** The axis
  partition is code (and asserted); vocabularies and companion
  registrations are YAML loaded by idempotent scripts.
- **Federation failure is normal and must never break a render.**
- **Bilingual from the start** — every user-facing model has a `_pt`
  column; retrofitting later was considered too expensive.
- **Code: MIT/Apache. Derived data: CC-BY-SA.** (Finalized before public
  release.)

## Key docs

| Topic | File |
|---|---|
| Ecosystem overview, standing constraints | `docs/handoff/2026-08-27-master.md` |
| Scoring algorithm | `docs/algorithm-v1.md` |
| Two-axis aggregation rationale | `docs/adr-0001-two-axis-aggregation.md` |
| Federation protocol (what companions expose) | `docs/federation-v1.md` |
| Federation design rationale (index-not-mirror) | `docs/scenario-driven-federation-model.md` |
| Data model | `docs/schema-v1.md` |
| Harvest pipeline | `docs/harvest-design.md` |
| Standards conformance plan | `docs/standards.md` |
| Deploy | `docs/DEPLOY.md` |
| Remaining UI work | `docs/UI-POLISH-PICKUP.md` |
| Adding povos as an upgrade project | `docs/integrations/povos-indigenas-rn.md` |
