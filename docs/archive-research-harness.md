# Archive Research Harness

**Status:** Specification / design. Nothing built yet.
**Date:** 2026-09-02
**Purpose:** Define the repeatable process — and the tooling it still needs —
for turning a row in the brasil-archives catalog into a public partner corpus
explorer the way `mipibu` and `povos-indigenas-rn` already are, with an AI
research agent doing the deep archival research at its centre.

> **Read alongside:** [`federation-v1.md`](federation-v1.md) (the contract a
> partner must speak), [`project-schema-design.md`](project-schema-design.md)
> (the `src_<slug>` schemas on the aggregator side),
> [`scenario-driven-federation-model.md`](scenario-driven-federation-model.md)
> (federation is an index, not a mirror; companion apps are monolithic),
> [`integrations/povos-indigenas-rn.md`](integrations/povos-indigenas-rn.md)
> and `povos-indigenas-rn/docs/INTEGRATION.md` (the hand-written version of
> what this harness automates).

---

## 1. What we are building and why

brasil-archives has surveyed ~80 Northeast-Brazil archives and scored 21 of
them. A handful are worth a **dedicated corpus explorer** — a small bilingual
read-only app that takes one archive's holdings, adds structured metadata /
description / full-text search, and federates back into brasil-archives as an
**upgrade project**. Two exist: `mipibu` (judicial records) and
`povos-indigenas-rn` (Indigenous-history evidence base).

Each was built once, by hand, in an ad-hoc environment. There is no reusable
tooling for the hard part — the archival research that produces the corpus.
This document specifies a **harness**: a defined pipeline plus the components
it needs, so building partner explorer #3, #4, #5 is a driven process rather
than a fresh invention each time.

### The operating model (decided in discussion, 2026-09-02)

> **Superseded in part, 2026-09-02 (same day):** the "independent monolith
> per partner, scaffold-a-repo-and-hand-off" model below was replaced by a
> **monorepo** — `corpus-explorers`, with `packages/corpus-toolkit`,
> `packages/explorer-core`, and `partners/<slug>/` instance directories.
> The forge now generates an instance *directory*, not a repo. See that
> repo's `docs/MONOREPO.md`. Everything else here still holds.

- brasil-archives is **both the aggregator and the forge**. It triages
  candidates, runs (or dispatches) the research agent, reviews the resulting
  corpus, then **scaffolds the partner instance and hands off**.
- After handoff the partner instance is worked independently in VS Code.
  brasil-archives does not manage its day-to-day; a fix to the shared
  `explorer-core` reaches every partner on its next deploy.
- Build-time exchange between the forge and a partner is **git + HTTP only** —
  never a shared database connection. Steady state is the periodic OAI-PMH
  harvest, exactly as today.
- The research agent's working data lives in **its own database in the
  partner's build environment**, not in the brasil-archives catalog DB (see
  §7).

### First worked example

`jornais-digitalizados` — BCZM/UFRN's open directory of ~53,000 digitized
newspaper page PDFs (`bczm.ufrn.br/jornais/`, structure `/<TITLE>/<YEAR>/`,
1862–1987, no OCR, no metadata). The survey calls it "the easiest technical
win in the whole survey" to *enumerate* and "pre-OCR and poor in metadata" to
*use* — so nearly all the work is research: OCR ~53k pages, reconstruct the
serial structure (title → year → issue → page), extract dates and mastheads,
pull named entities, build the search index. This is precisely the
"agent mines an archive over a period of time" case.

---

## 2. What we know — the anatomy of a partner corpus explorer

Verified by reading both repos (`c:\DEV\mipibu`, `c:\DEV\povos-indigenas-rn`)
at `main` on 2026-09-02. Three layers, decreasing reusability.

### 2.1 Layer 1 — the corpus database (bespoke research; ~80% of the effort)

Each app serves an **immutable, read-only SQLite file** with a per-corpus
schema. `mipibu/app/db.py` and `povos/app/db.py` both open it
`mode=ro&immutable=1` with `PRAGMA query_only=ON` — no code path can write it.

| | mipibu | povos |
|---|---|---|
| file | `data/sao-jose-mipibu-audit.db` (~7 MB) | `data/povos_rn.db` (~0.8 MB) |
| distribution | content-addressed, synced via Wasabi (`scripts/sync-corpus.sh`, `<db>.sha256` sidecar) | committed in-repo (fine at its scale) |
| entity tables | `cases` (508), `digital_files` (508), `repository_items` (57), `archival_collections` (21), `archival_units` (18) | `documents` (40), `communities` (17), `ethnic_groups` (10), `indigenous_passages` (37), `academic_works` (29), `portal_essays` (9), `document_collections` (3) |
| source of the data | metadata **audit of a DSpace repository** (LABIM/UFRN) — hierarchical crawl of `/handle/`, rule-derived normalized fields; *"no information was read from the digitized documents"* (methodology page) | **assembled from digital catalogs** — Projeto Resgate / Biblioteca Nacional (AHU consultas), CRL Digital Collections, UFRN — plus secondary literature and an ethnic-group index |

**The convergent schema contract.** The two corpora were modelled
independently and *landed on the same backbone*. This is the most important
finding in this document — it is the corpus-DB contract, waiting to be
written down:

| element | mipibu | povos | role |
|---|---|---|---|
| `controlled_terms` | 49 rows | 23 rows | bilingual vocab: `term_code, vocabulary, label_pt, label_en, definition_pt/en, is_placeholder` |
| `source_assertions` | **1058 rows** | 20 rows | every derived fact + its evidence (see below) |
| `audit_events` | 9 rows | 6 rows | the crawl/build log: `event_type, target_url, target_table, outcome, detail, occurred_at` |
| `repositories` | 1 | 3 | the source institution(s): `name_original, short_code, domain, base_url, software, rights_statement_original` |
| `fts_<kind>` | `fts_case_metadata`, `fts_transcription` | `fts_documents`, `fts_passages`, `fts_essays` | SQLite FTS5, one per searchable kind |
| `schema_version` / `migrations` | present | present | corpus schema versioning |
| `external_identifiers` | 508 | (via assertions) | Handle / DOI / catalog URLs |
| `_original` vs `_normalized` columns | pervasive | pervasive | verbatim-from-source vs rule-derived, never mixed |

**`source_assertions` is the research-integrity backbone.** povos's columns:

```
subject_table, subject_id, subject_column   -- which fact
asserted_value                              -- the value
evidence_type, evidence_url, evidence_file,
  evidence_page, evidence_quote_original    -- the evidence
method                                      -- e.g. "keyword_ocr_search_and_manual_context_review"
confidence                                  -- 0.0-1.0
verification_status                         -- e.g. "human_reviewed"
asserted_at
```

Both corpora also encode explicit **anti-fabrication rules**: povos's OAI
layer emits coordinates *only* when both lat and lon are non-NULL, never
invents a date, and surfaces trust flags through `dc:description`
(`[verification: …]`, `[confidence: …]`, `[placeholder: …]`). mipibu marks
undescribed records `not_stated_in_repository` rather than guessing a type.

### 2.2 Layer 2 — the explorer app (structural pattern; ~90% identical shape)

Flask factory, **no ORM, no migrations** (the corpus is external and
immutable). ~4–5k LOC each. Near-identical module layout:

| module | responsibility | varies per corpus? |
|---|---|---|
| `app/__init__.py` | factory, security headers, error handlers, template helpers | no (boilerplate) |
| `app/config.py` | env-driven config, `DATABASE_PATH`, `DEFAULT_LANG=pt`, `PER_PAGE_*` | no |
| `app/db.py` | read-only immutable SQLite access (`query_all/query_one/scalar`) | **no — copy verbatim** |
| `app/queries.py` | all SQL | **yes — entirely** |
| `app/presenters.py` | row → bilingual dict shaping | yes |
| `app/i18n.py` | `t()` string table + label helpers | mostly no (shared keys) + per-corpus additions |
| `app/params.py` | query-param validation, year bounds | light |
| `app/views/main.py` | browse + detail routes per entity kind | yes (route per kind) |
| `app/views/api.py` + `federation.py` | the 4 federation JSON endpoints | **mostly no** (see 2.3) |
| `app/oai/` | OAI-PMH provider package | **mostly no** (see 2.3) |
| `app/templates/` | `base.html`, per-kind `list`/`detail`, `methodology.html`, `api_docs.html`, `error.html` | yes (per-kind templates) |
| deploy | `passenger_wsgi.py`, `app.bat`, `Dockerfile`, `github-pull`, `monitoring/`, `app-monitor.ps1` | **no — copy verbatim** |
| tests | `tests/` + CI (`pytest` + a legacy `qa_test.py` sweep in povos) | shape yes, harness no |

Every app also publishes a **`methodology.html`** page: how the corpus was
bounded, what the numbers mean, where they should not be trusted. Currently
hand-written; it is really the research agent's report, rendered.

### 2.3 Layer 3 — the federation surface (near-identical; re-implemented 3×)

**The four JSON endpoints** (`federation-v1.md`): `GET /api/health`,
`/api/schema`, `/api/records`, `/api/records/<id>`. `Content-Type:
application/json; charset=utf-8`, `Access-Control-Allow-Origin: *`, every
label carries `label_pt` + `label_en`, `?lang=` selects single-language
fields. `corpus_version` = SHA-256 of the corpus DB (mipibu: sidecar file;
povos: computed lazily). Record identifier scheme
`<prefix>:<kind>:<id>`.

**The OAI-PMH provider** (`app/oai/`): envelope, six verbs, every error code,
stateless base64url resumption tokens, `oai_dc` (required), `oai_ead`
(mipibu only — it is a real fonds; povos skipped it, being composite), a set
hierarchy (`<prefix>:<kind>`, then sub-sets by type / period / decade).
mipibu ~1900 LOC, povos ~1900 LOC, **written from scratch both times** —
plus brasil-archives has a *third* provider (`app/oai/`, its own catalog).

**N=3 parallel implementations. The rule of three is satisfied.** povos's
`HANDOFF-2026-08-26.md` §"Package extraction plan" already sketches the
target: a portable `oai_pmh` package (envelope, errors, resumption,
serializers that take **dicts**) + a `CorpusAdapter` interface
(`iter_records(kind, set_spec, from_, until, limit, offset)`,
`count_records(...)`, `get_record(identifier)`) where all SQL lives.

### 2.4 The aggregator side (already built)

When a partner is registered: `configs/upgrade_projects/<slug>.yaml` +
`scripts/load_upgrade_projects.py` upsert → a `src_<slug>` Postgres schema is
stamped from one template (`aggregated_records`, `harvest_runs`,
`harvest_errors`, `federation_cache`); `public.*_all` UNION views span all
sources; `scripts/harvest.py` pulls the partner's `oai_dc` into
`src_<slug>.aggregated_records`; the archive detail page shows a live
federation preview from `/api/health`. Removing a partner is
`DROP SCHEMA src_<slug> CASCADE`.

**Prerequisite that bit us with povos:** `upgrade_projects.source_archive_id`
is `NOT NULL`. Every partner needs a row in `archives`. For catalog archives
(like `jornais-digitalizados`) the row already exists — no bootstrap needed.
For composite sources (like povos) a seed script adds one.

---

## 3. What we know — the three corpus-construction modes

The single biggest variable, and the survey already tells us which archives
fall where:

| mode | what it is | example | agent tractability |
|---|---|---|---|
| **A — metadata audit** | crawl a structured repository (DSpace / AtoM / OAI-PMH), capture its metadata verbatim, derive normalized fields by rule, do **not** read the scanned documents | mipibu (LABIM DSpace); Jornais de Sergipe (DSpace, sequential handles, OAI-PMH); APEPI | **high** — enumeration + extraction + normalization is squarely agent work |
| **B — assembly from catalogs + literature** | pull records from one or more digital catalogs, cross-reference secondary sources, model entities (people, groups, places), track every inclusion decision as an assertion | povos (Projeto Resgate + CRL + UFRN + literature) | **medium–high** — the crawl is easy; the scholarly inclusion/confidence calls need human gates |
| **C — OCR-first** | enumerate a pile of page images / PDFs with little or no metadata, OCR them, reconstruct structure from the OCR + filenames, then index | `jornais-digitalizados` (~53k page PDFs, no OCR); Museu de História do Piauí; Nupem | **medium** — enumeration trivial, OCR is a long batch job, structure reconstruction is the hard modelling |

A complete harness must handle all three. `jornais-digitalizados` exercises
**C**, which neither existing partner does — a deliberate choice for the
first harness build.

---

## 4. What we are missing — the gap list

Everything the harness needs that does not exist yet. Grouped by pipeline
phase (§5 lays out the phases).

### 4.1 No canonical corpus-DB schema contract

mipibu and povos converged on a backbone (§2.1) but each hand-rolled it.
**Status: backbone + manifest + validator DONE 2026-09-02 (SQLite);
reworking for Postgres.** [`corpus-db-contract.md`](corpus-db-contract.md)
v1.1 + `corpus-explorers/packages/corpus-toolkit` shipped the backbone DDL,
**manifest v0** (JSON; covers 4.5), and a MUST/SHOULD validator that both
reference corpora pass. Building it forced the v1 → v1.1 relax (contract §11).

Then the storage layer flipped to **Postgres** — SQLite retired everywhere.
The contract needs a **v2** rewrite and the toolkit a `psycopg` rework
(`create_corpus_schema` / `validate_corpus_schema` / `freeze_corpus` /
`load_sqlite`). Backbone shapes + manifest carry over unchanged. Rules:
`corpus-explorers/docs/POSTGRES.md`; transition sequence:
`corpus-explorers/docs/POSTGRES-PLAN.md`.

Remaining on this line: contract v2 + toolkit rework; then manifest v0 → v1
(page/segment/OCR-run modelling),
driven by `jornais-digitalizados`.

### 4.2 No corpus-build tooling at all

The mipibu and povos corpora were built ad hoc (pplx sandboxes; nothing
checked in). **Needed — a `corpus_build` toolkit** (its home is an open
question, §8):

- **Crawl framework** — resumable, checkpointed, rate-limit-polite,
  robots-aware, writes an `audit_events` row per fetch. Must survive being
  stopped and restarted over days.
- **Source adapters** (see 4.4).
- **Extraction pipeline** — HTML/XML/PDF/OCR → candidate records; every
  derived field emits a `source_assertions` row with evidence + method +
  confidence.
- **Normalization helpers** — date parsing (with "uncertain" as a
  first-class outcome), name/place folding, controlled-term assignment,
  dedup-candidate grouping (mipibu's `duplicate_group_key` pattern).
- **OCR pipeline** for mode C — batch OCR, per-page confidence, layout →
  issue/page reconstruction, masthead/date extraction from page 1.
- **FTS builder** — populate `fts_<kind>` from the normalized tables.
- **Freeze step** — snapshot the build DB → immutable SQLite + `.sha256`,
  emit the methodology report.

### 4.3 No long-running research-agent runner

The "mine an archive over a period of time" capability. **Needed:**

- A **job model** — `build_jobs` (in the build DB): phase, status,
  checkpoint cursor, started/updated, agent notes. Resumable.
- A **worker** that runs outside a request cycle. cPanel **cannot** host
  this (no persistent workers, process caps) — it runs on the dev box or a
  cloud runner; the admin UI reads status.
- The **agent loop itself** — plan → fetch batch → extract → assert →
  checkpoint → self-check against the contract → repeat; escalate to a human
  gate on ambiguity, licence uncertainty, or a confidence-threshold breach.
- **Budget / etiquette guards** — max request rate per host, total-bytes
  ceiling, stop-on-403/robots-change.

### 4.4 No source-adapter abstraction

Each archive publishes differently. The survey already classifies them
(`enumerable-by-pattern`, `individually-addressable`, `disallow_by_robots`,
`full-scans-no-ocr`, DSpace / AtoM / Apache-listing / IIIF). **Needed:** a
`SourceAdapter` interface — `discover()`, `enumerate()`, `fetch(ref)`,
`native_metadata(ref)` — with concrete adapters for at least: OAI-PMH,
DSpace REST, AtoM, IIIF Presentation, plain Apache directory listing,
generic paginated HTML. Discovery (Phase 1) picks the adapter.

### 4.5 No Layer-2 scaffold generator

**Needed:**

- The **entity-kinds manifest** format — per kind: name, source table, PK,
  title field(s), date field(s), FTS table, list columns, detail sections,
  public URL pattern, which OAI sets it produces. This single file drives
  `queries.py`, `presenters.py`, `views/main.py`, the templates, and the
  OAI set registry.
- A **cookiecutter-style generator** that stamps a standalone partner repo
  from the manifest + the corpus DB + the shared deploy boilerplate. Output
  is a monolith, not a framework consumer (keeps the design stance).

### 4.6 No shared Layer-3 library

Designed in povos's handoff, never built. **Needed:** extract
`oai_pmh` + `federation_json` + `CorpusAdapter` from the three existing
implementations, keeping only what is identical. This is the one place a
*shared dependency* is justified (N=3, purely mechanical). Partners pin a
version; a bump propagates protocol fixes without re-templating.

### 4.7 No repo-cutting automation

**Needed:** from inside brasil-archives — create `c:\DEV\<slug>\`, `git
init`, scaffold, create the **public GitHub repo** (MIT `LICENSE`,
`.githooks`, CI workflow, `README`), first commit, register the cPanel
Passenger app, first deploy, smoke-test `/healthz` + `/api/health` + `/oai`.

### 4.8 No admin / forge control plane

The read-only `/admin/` dashboard (2026-08-29) is the seed. **Needed**,
behind the existing `ADMIN_UI_ENABLED` gate (never on the public host):

- **Candidate triage** view — every catalog archive scored for buildability
  (§5 Phase 0).
- **Build monitor** — live job status, `audit_events` tail, assertion
  counts, confidence histogram, cost so far.
- **Corpus review** — browse the built corpus, spot-check assertions,
  approve / reject / send-back, edit the methodology draft.
- **Freeze & handoff** trigger — one action that freezes the corpus, cuts
  the repo, files the `upgrade_projects` YAML PR, flips the
  `partner_builds` row to `handed_off`.

### 4.9 No template-drift mechanism

After partner #3, improvements to Layer 2 must reach #1 and #2. **Needed:** a
`partner sync` command — re-run the generator against a partner's manifest,
produce a reviewable diff, let the developer apply selectively. (Layer 3
drift is handled by the shared-lib version bump, 4.6.)

### 4.10 No methodology-report generator

Both partners have a hand-written `methodology.html`. **Needed:** the freeze
step emits a structured methodology document from `audit_events` +
`source_assertions` + the manifest (corpus bounds, source list, counts,
coverage gaps, confidence distribution, known caveats) that the partner app
renders.

### 4.11 Undefined policy / loop-closure questions

- **"Done" criteria for a corpus** — what freeze thresholds
  (coverage %, min confidence, human-review quota)?
- **Fair-use gate** — every partner must clear the fundamental floor. The
  agent's discovery phase must surface the rights situation; the forge must
  refuse to cut a repo without a recorded `fair_use_eligible` determination.
  (Survey already flags e.g. "Exclude Tribuna do Norte — copyright.")
- **Scoring feedback** — a live partner *lifts* its source archive's
  dimension scores. Registration should draft the `lifts:` block in the
  YAML, not leave it `{}` for a later manual Pass.
- **Candidate list** — which of the ~80 archives are actually harvestable?
  A triage pass is Phase 0 and doesn't exist yet.

---

## 5. The harness pipeline (target state)

```
        brasil-archives (the forge)                    partner build env
        ───────────────────────────                    ────────────────
Phase 0  Candidate triage        ─┐
         (admin: score each        │  known: the survey + catalog
          catalog archive for      │  missing: the triage view + score
          buildability)           ─┘

Phase 1  Discovery (agent)        ─┐  known: survey classifies platforms
         probe platform, endpoints │  missing: SourceAdapter.discover(),
         rights, scale, samples    │           rights extraction
         → discovery report       ─┘

Phase 2  Scoping & modelling      ─┐  known: the convergent schema backbone
         (agent + HUMAN GATE)      │  missing: entity-kinds manifest format,
         corpus bounds +           │           corpus-db-contract.md,
         entity-kinds manifest +   │           create_corpus_db
         corpus schema            ─┘

Phase 3  Mining ──────────────────────────────────►  long-running agent
         (dispatched by the forge,                    known: nothing
          runs in the build env)                      missing: crawl framework,
         crawl → extract → assert                              adapters, OCR,
         → normalize → FTS → checkpoint                        job runner,
         → build DB (its own database)                         assertion capture

Phase 4  Review & freeze          ◄──────────────────  build DB
         (admin: browse corpus,                        known: source_assertions
          spot-check assertions,                              model
          approve; edit methodology)                   missing: review UI,
         → immutable SQLite + .sha256                          freeze step,
         → methodology report                                  methodology gen

Phase 5  Forge                    ─┐  known: federation-v1, deploy boilerplate,
         scaffold Layer 2 from     │         load_upgrade_projects, src_<slug>
         manifest + Layer 3 lib;   │  missing: scaffold generator, Layer-3 lib,
         git init + GitHub repo +  │           repo-cutting automation
         MIT + CI; first deploy;   │
         write upgrade_project YAML │
         + draft lifts; archives    │
         row (already exists)      ─┘

Phase 6  Handoff ─────────────────────────────────►  developer opens in VS Code
         partner_builds row →                        works to public-view state
         'handed_off'                                 known: this is how mipibu/
         steady state = OAI harvest                          povos are worked

Phase 7  Drift sync (ongoing)     ◄─────────────────  partner repo
         partner sync → reviewable diff               missing: the sync command
```

---

## 6. Component inventory — known vs to build

| # | component | status | notes |
|---|---|---|---|
| C1 | Federation contract v1 | **known / stable** | `federation-v1.md` |
| C2 | Aggregator ingest (`src_<slug>`, harvest, views, preview) | **known / shipped** | `project-schema-design.md` |
| C3 | `load_upgrade_projects` + YAML registration | **known / shipped** | idempotent upsert |
| C4 | Deploy boilerplate (`passenger_wsgi`, `app.bat`, `Dockerfile`, `github-pull`, `monitoring/`) | **known — copy verbatim** | identical across mipibu/povos |
| C5 | Explorer app module skeleton (`__init__`, `config`, `db`) | **known — copy verbatim** | |
| C6 | Convergent corpus-DB backbone | **DONE** — contract v1.1 + `corpus-toolkit` (`create_corpus_db` / `validate_corpus_db` / `write_sidecar`) | 4.1; both reference corpora validate clean |
| C7 | `source_assertions` evidence model | **documented** — contract §3.1 | povos schema was the reference |
| C8 | Entity-kinds manifest | **v0 DONE** — `corpus-toolkit/docs/manifest-v0.md` (JSON) | grows to v1 with `jornais-digitalizados`; still drives C9 |
| C9 | Layer-2 scaffold generator | **to build** | 4.5 |
| C10 | Shared `oai_pmh` + `federation_json` + `CorpusAdapter` lib | **to build** | 4.6 — N=3, the one shared dependency |
| C11 | `SourceAdapter` interface + platform adapters | **to build** | 4.4 |
| C12 | Crawl framework (resumable, polite, audited) | **to build** | 4.2 |
| C13 | Extraction + normalization + assertion-capture pipeline | **to build** | 4.2 |
| C14 | OCR pipeline (mode C) | **to build** | 4.2 — needed for `jornais-digitalizados` |
| C15 | Long-running job model + worker | **to build** | 4.3 — not on cPanel |
| C16 | Research-agent loop | **to build** | 4.3 |
| C17 | Freeze step + methodology-report generator | **to build** | 4.2 / 4.10 |
| C18 | Repo-cutting automation | **to build** | 4.7 |
| C19 | Forge admin control plane | **to build** | 4.8 — extends `/admin/` |
| C20 | `partner sync` drift command | **to build** | 4.9 |
| C21 | `partner_builds` tracking table | **to build** | §7 |
| C22 | Candidate triage / buildability score | **to build** | 4.11 Phase 0 |
| C23 | Freeze criteria + fair-use gate + lift drafting | **policy — undecided** | 4.11 |

---

## 7. Data & database architecture

Three stores, each with a clear owner:

| store | holds | lifecycle | lives in |
|---|---|---|---|
| **`build` schema** | raw fetches, candidate records, `source_assertions`, `audit_events`, crawl checkpoints, dedup candidates, OCR text — large, volatile, corpus-specific | rebuilt freely; **local Docker PG / cloud runner only**, never cPanel | one Postgres **database per corpus** in the dedicated corpus cluster (`corpus-explorers/docs/POSTGRES-PLAN.md`). **Not** brasil-archives' catalog DB. |
| **`corpus` schema** | the curated, frozen system of record the partner app serves | immutable between freezes; versioned by `corpus_meta.content_digest` | same database, `corpus` schema; ships to cPanel-local Postgres 10 via `pg_dump -Fc --schema=corpus`; Wasabi holds the digest-pinned artifact |
| **`src_<slug>` schema** | brasil-archives' harvested index copy | refreshed by the harvest cron | brasil-archives Postgres — **already exists** |

**Why the build workspace is not a schema in the catalog DB:**

1. The catalog DB's just-won durability property — small, durable, weekly
   encrypted off-site backup. A months-long OCR job (tens of GB of page
   text) does not belong in that backup.
2. Per-corpus DDL (newspaper issues ≠ judicial cases ≠ thematic evidence)
   does not belong in the catalog's Alembic history, which only serves
   `public` + the uniform `src_<slug>` template.
3. "Hand off and forget" means the partner owns **all** its data — build
   workspace and frozen corpus alike.

**What the catalog DB does gain — one small table:** `partner_builds` in
`public` (or an admin schema). Metadata *about* builds, never build data:

```
partner_builds
  archive_slug        FK -> archives.slug        -- the catalog seed
  status              triage | discovery | modelling | mining
                       | review | forged | handed_off | abandoned
  phase_detail        text
  repo_url            text  null
  build_env_ref       text  null                  -- where the worker runs
  corpus_sha256       text  null                  -- set at freeze
  fair_use_determination  text  null              -- required before 'forged'
  last_agent_run_at   timestamptz null
  created_at, updated_at
```

This is the forge control plane's state, and it's tiny and durable — it
belongs with the catalog.

---

## 8. Open questions / decisions needed

1. ~~**Where does `corpus_build` live?**~~ **Resolved 2026-09-02:** the new
   `corpus-explorers` monorepo. `packages/corpus-toolkit` (DB build/validate)
   exists now; `packages/corpus-build` (crawl/extract/OCR) is the next
   package there. Every partner instance uses the same package — no
   copy-at-handoff.
2. **Does the forge admin ship in the deployed app or stay a local-only dev
   tool?** The long-running worker can't run on cPanel regardless. Option:
   the deployed `/admin/` shows read-only status; the *actions* (start
   build, freeze, cut repo) are a local CLI/TUI that shares the code.
3. **Corpus "done" criteria** — coverage %, minimum confidence, human-review
   quota per confidence band. Needs a policy doc.
4. **Manifest scope** — does one manifest also carry the scoring `lifts:`
   draft and the fair-use determination, or are those separate artifacts?
5. **Mode C structure reconstruction** — how much issue/date/masthead
   modelling is agent-automatic vs a human modelling gate for newspapers.
6. **Build `jornais-digitalizados` first, or the harness first?** (see §9).

---

## 9. Recommended sequencing

**Build `jornais-digitalizados` mostly by hand, with the harness as the
explicit goal.** Rationale: generalizing a generator from N=2 partner repos
would lock in guesses; doing a third by hand — deliberately reusing the
mipibu/povos patterns and writing down every seam — is how we learn what
C6–C22 actually need to be. Concretely:

1. **Done 2026-09-02:** [`corpus-db-contract.md`](corpus-db-contract.md)
   (C6/C7) — pure documentation of what mipibu + povos already prove.
   Next on this line: implement `create_corpus_db` + `validate_corpus_db`.
2. **Phase 0 pass:** triage the ~80 catalog archives for buildability;
   confirm `jornais-digitalizados` is the right first target and capture
   why (C22, done as a one-off).
3. **jornais build, by hand but instrumented:** stand up a build workspace
   DB on the schema contract; write the BCZM Apache-listing adapter (C11,
   one adapter); build the crawl + OCR + assertion pipeline for *this
   corpus* (C12–C14), keeping notes on what's corpus-specific vs general;
   freeze; hand-write the manifest (C8) and methodology (C17/C10).
4. **Scaffold jornais by copy-paste** from mipibu (C4/C5), adapt Layer 2 for
   the serial shape, copy an `app/oai/` and adapt.
5. **Extract, only now:** the Layer-3 shared lib (C10) from the three OAI
   implementations; the scaffold generator (C9) from the manifest that
   jornais forced us to define; the `partner_builds` table (C21) and the
   admin views (C19) from the process we just ran manually.
6. Partner #4 is the first one built *through* the harness.

This keeps "research first" honest — steps 1–3 are almost entirely archival
research and its tooling — while ensuring the harness, when we build it, is
generalized from three real corpora instead of two.

---

## 10. Change log

- **2026-09-02** — initial specification, from a teardown of `mipibu` and
  `povos-indigenas-rn` at `main` and the operating-model discussion of the
  same day.
