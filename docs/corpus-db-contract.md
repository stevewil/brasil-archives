# Corpus database contract — v1.1

> **⚠️ Storage layer superseded (2026-09-02, same day as v1.1).** The corpus
> system of record moved from an immutable **SQLite file** to **PostgreSQL**
> — SQLite retired everywhere, mipibu and povos included. A **v2** rewrite
> of this document is pending; until then read it together with
> `corpus-explorers/docs/POSTGRES.md` (the normative Postgres rules) and
> `corpus-explorers/docs/POSTGRES-PLAN.md` (the v2 delta table + transition
> sequence) — types, FTS via `tsvector`/`unaccent`, immutability via a
> read-only `corpus` schema + `corpus_meta.content_digest`, distribution via
> `pg_dump --schema=corpus`. **Everything below about the backbone's
> *shape* — the provenance model, `_original`/`_normalized`, anti-fabrication,
> vocab, the conformance levels and v1.1 relaxations — carries over
> unchanged.** Only the dialect and the file-based mechanics are obsolete.

**Status:** Specification. Documents what `mipibu` and `povos-indigenas-rn`
already prove; normative for partner corpus explorer #3 onward.
**Date:** 2026-09-02 (v1.1: 2026-09-02, same day — see §11)
**Companion:** [`archive-research-harness.md`](archive-research-harness.md)
(the pipeline this contract sits inside), [`federation-v1.md`](federation-v1.md)
(what a partner exposes over the wire).
**Implementation:** `corpus-explorers/packages/corpus-toolkit` — this contract
as executable DDL (`create_corpus_db`) and checks (`validate_corpus_db`).
`sqlite3` + stdlib only. Ships contract v1.1.

> **v1.1 note.** v1 was extracted from the two reference corpora but then
> resolved several mipibu/povos divergences *toward* povos. When the
> validator was built, neither corpus actually satisfied the resulting
> `MUST` set. v1.1 relaxes those rules to `SHOULD` so the validator passes
> both reference corpora clean (warnings only). The relaxed items are
> flagged **[v1.1: was MUST]** below. The intent of v1 is unchanged — a
> corpus that meets every `SHOULD` is the target; v1.1 just stops the
> validator from failing corpora that the contract was derived from.

---

## 1. Purpose

Every partner corpus explorer serves an **immutable, read-only SQLite
database** as its system of record. `mipibu/app/db.py` and
`povos-indigenas-rn/app/db.py` open it `mode=ro&immutable=1` with
`PRAGMA query_only=ON`; the app never writes it.

The two existing corpora were modelled independently and **converged on the
same backbone**. This document makes that backbone normative so that:

- the **research harness** can stamp a new corpus DB and validate one,
- the **Layer-2 scaffold generator** can rely on stable table/column
  conventions,
- the **Layer-3 `CorpusAdapter`** can serve OAI-PMH + federation JSON from
  any conforming corpus without special-casing,
- every derived fact in any corpus carries the **same provenance shape**.

The contract governs the **backbone** (provenance, vocab, audit, FTS,
naming, integrity). It does **not** dictate the entity tables — `cases` vs
`documents` vs `newspaper_issues` is per-corpus. It dictates how those tables
are *shaped* and *sourced*.

Conformance levels: **MUST** (validator fails without it), **SHOULD**
(validator warns), **MAY** (allowed, unchecked).

---

## 2. File, distribution, immutability

| rule | level | detail |
|---|---|---|
| One SQLite file per corpus | MUST | `partners/<slug>/data/<corpus-slug>.db` |
| SHA-256 sidecar | MUST for a distributed/frozen corpus | `<corpus-slug>.db.sha256`, 64 lowercase hex + newline. The corpus version surfaced by `/api/health` and OAI `Identify`. The validator **warns** if it is absent on a working DB and **fails** under `--frozen`. |
| Served read-only | MUST | app opens `mode=ro&immutable=1`, `PRAGMA query_only=ON` |
| No app-side writes ever | MUST | no ORM, no migrations in the explorer app; the DB is built elsewhere and frozen |
| Distribution | SHOULD | commit in-repo if < ~5 MB (povos: 0.8 MB); otherwise content-addressed via Wasabi with the sidecar as the pin (mipibu pattern, `scripts/sync-corpus.sh`) |
| `schema_version` table **or** `PRAGMA user_version` exists | MUST | see §7 |
| ...carrying a non-zero value | SHOULD **[v1.1: was MUST]** | povos ships an empty `schema_version` table; validator warns |
| `PRAGMA foreign_keys = ON` honoured at build time | MUST | FKs are declared and enforced during construction |

---

## 3. The provenance backbone (MUST)

### 3.1 `source_assertions` — every derived fact, with its evidence

This table is **near-identical** in both corpora today. It is the contract.

```sql
CREATE TABLE source_assertions (
    assertion_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_table       TEXT NOT NULL,          -- entity table the fact is about
    subject_id          INTEGER NOT NULL,       -- row PK in that table
    subject_column      TEXT,                   -- the column, NULL = the row's existence itself
    asserted_value      TEXT,                   -- the value claimed (as text)
    evidence_type       TEXT NOT NULL,
    evidence_url        TEXT,
    evidence_file       TEXT,                   -- path/name within the source, if applicable
    evidence_page       INTEGER,
    evidence_quote_original TEXT,               -- verbatim supporting snippet
    method              TEXT,                   -- how the value was derived
    confidence          REAL,                   -- 0.0-1.0, NULL = not scored
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    asserted_at         TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
    CHECK (verification_status IN
        ('unverified','machine_extracted','human_reviewed','confirmed','disputed'))
);
```

- **`evidence_type`** — controlled. Recommended v1 set (union of what both
  corpora conceptually cover): `repository_metadata`, `http_header`,
  `file_inspection`, `page_image`, `ocr_text`,
  `archival_catalog_description`, `external_source`, `derivation` (a value
  computed by rule from other asserted values). Both reference corpora ship
  a 5-value CHECK subset; a corpus MAY narrow or extend the set by editing
  the CHECK (pass `evidence_types` in the manifest). The validator does
  **not** pin the CHECK contents **[v1.1: was "MUST match"]** — it only
  requires the column and the `confidence` + `verification_status` CHECKs.
- **`method`** — free text but conventional: `html_parse`, `oai_pmh`,
  `dspace_rest`, `curl_head`, `pdfinfo`, `pdftotext`, `ai_vision_ocr`,
  `regex_keyword_search`, `rule`, `manual`, `manual_context_review`.
- **`verification_status`** — the same five-value ladder is used here **and**
  on entity rows (§5.3). `machine_extracted` = an agent produced it with no
  human check; `human_reviewed` = a person looked; `confirmed` = a person
  cross-checked against the source; `disputed` = flagged wrong, kept for the
  record.

**Coverage rule (SHOULD — validator warns) [v1.1: was MUST]:** every
**non-verbatim** column value in an entity table — i.e. every `*_normalized`,
every classification, every date parsed into `year_start`/`year_end`, every
asserted link, every inclusion decision — has at least one `source_assertions`
row. Verbatim `*_original` columns copied straight from a single source
record MAY share one row-level assertion (`subject_column` NULL) citing that
record. The validator samples this check by default and runs it in full at
freeze; it is `MUST` **at freeze** for a corpus that will publish scores or
research claims.

### 3.2 `audit_events` — the build/crawl log

```sql
CREATE TABLE audit_events (
    event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type   TEXT NOT NULL,   -- enumeration | http_fetch | http_head | download
                                  --   | ocr | sample_inspection | keyword_search
                                  --   | manual_review | load | integrity_check
    target_url   TEXT,
    target_table TEXT,
    http_status  TEXT,
    outcome      TEXT NOT NULL,   -- ok | blocked_robots | http_error | parse_error
                                  --   | skipped | not_found
    detail       TEXT,
    occurred_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**MUST** record: the start and end of every enumeration pass, every
robots/ToS check, every batch of fetches (one row per batch is fine), every
freeze/integrity-check. This table is a primary input to the generated
methodology report.

`http_status` is **SHOULD [v1.1: was MUST]** — povos omits the column; keep
it for any corpus doing its own fetching.

### 3.3 `repositories` — the source institution(s)

```sql
CREATE TABLE repositories (
    repository_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name_original   TEXT NOT NULL,
    short_code      TEXT NOT NULL UNIQUE,       -- BN_RESGATE | CRL | LABIM | BCZM ...
    domain          TEXT NOT NULL,
    base_url        TEXT NOT NULL,
    software        TEXT,                       -- DSpace 6 | AtoM | Apache autoindex | IIIF ...
    custodian_of_originals_original TEXT,
    rights_statement_original       TEXT,       -- verbatim rights text from the source
    robots_notes    TEXT,                       -- what robots.txt / ToS said, and when checked
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

One row per distinct source (composite corpora like povos have several).

- `rights_statement_original` **MUST** be non-NULL for every row — the
  validator fails otherwise. It is the fair-use gate's core evidence
  (`archive-research-harness.md` §4.11).
- `robots_notes` and `custodian_of_originals_original` are **SHOULD**
  **[v1.1: was MUST]** — povos omits both columns. Strongly recommended for
  any corpus built by crawling; the fair-use determination is weaker without
  `robots_notes`.

### 3.4 `external_identifiers` — SHOULD

Present in mipibu (508 rows); povos folds these into `source_assertions`.
Recommended when a corpus carries stable external IDs (Handle, DOI, VIAF,
GeoNames, Wikidata, catalog IDs):

```sql
CREATE TABLE external_identifiers (
    external_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_table   TEXT NOT NULL,
    subject_id      INTEGER NOT NULL,
    id_scheme       TEXT NOT NULL,   -- hdl | doi | viaf | wikidata | geonames | familysearch | local_catalogue
    id_value        TEXT NOT NULL,
    id_url          TEXT,
    confidence      REAL,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (subject_table, subject_id, id_scheme, id_value),
    CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0))
);
```

---

## 4. Controlled vocabulary (MUST)

```sql
CREATE TABLE controlled_terms (
    term_code       TEXT PRIMARY KEY,           -- stable slug, snake_case
    vocabulary      TEXT NOT NULL,              -- which vocab this term belongs to
    label_pt        TEXT,
    label_en        TEXT,
    definition_pt   TEXT,
    definition_en   TEXT,
    match_pattern   TEXT,                       -- optional regex applied to the *_original string
    is_placeholder  INTEGER NOT NULL DEFAULT 0, -- 1 for "other_unresolved" / "not_stated_in_source"
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (is_placeholder IN (0,1))
);
```

- **Required columns (validator, MUST):** `term_code`, `vocabulary`,
  `label_pt`, `label_en`.
- Bilingual **`definition_pt` / `definition_en`** are **SHOULD**
  **[v1.1: was implied MUST]** — mipibu ships a single `definition` and no
  `definition_*`; that is tolerated but deprecated. `match_pattern` is `MAY`.
- `is_placeholder` column: **SHOULD [v1.1: was MUST]** — povos folds
  placeholder handling into per-table `is_placeholder` flags instead.
- A `*_normalized` column that the **manifest marks `controlled`** MUST FK
  `controlled_terms(term_code)` (`ON DELETE SET NULL ON UPDATE CASCADE`) —
  the validator fails otherwise. A free-text `*_normalized` column (e.g.
  `name_normalized`, `text_normalized`) is allowed and **not** required to
  FK **[v1.1: was "every classification column MUST FK"]**.
- Every vocabulary **SHOULD [v1.1: was MUST]** carry an explicit placeholder
  term (`is_placeholder = 1`) for "the source did not say" — never guess a
  value to avoid a NULL. `create_corpus_db` stamps one per declared
  vocabulary. mipibu uses `not_stated_in_repository`.
- Both `label_pt` and `label_en` **SHOULD** be non-empty for every
  non-placeholder term.

---

## 5. Entity-table conventions

The tables themselves are per-corpus. Their **shape** is contracted.

### 5.1 Naming (MUST)

| convention | rule |
|---|---|
| Primary key | `<singular_kind>_id INTEGER PRIMARY KEY AUTOINCREMENT` (`case_id`, `document_id`, `issue_id`) |
| Verbatim from source | suffix `_original` — copied character-for-character, **never** cleaned, including misspellings and empty-as-empty |
| Derived by rule/agent | suffix `_normalized` — and it has a `source_assertions` row |
| Timestamps | `created_at`, `updated_at` (`updated_at` only where the build mutates rows), `TEXT NOT NULL DEFAULT (datetime('now'))` |
| Foreign keys | declared, `ON DELETE CASCADE` for owned children, `ON DELETE SET NULL` for optional links, `ON UPDATE CASCADE` |
| Booleans | `INTEGER NOT NULL DEFAULT 0` + `CHECK (col IN (0,1))` |
| Dates | store `date_original TEXT` verbatim **and** parsed `year_start INTEGER` / `year_end INTEGER` (nullable); a `CHECK` bounding the year range is SHOULD |

### 5.2 In-scope flag (MUST for primary kinds)

Every **primary** entity kind — a top-level, record-bearing kind that is
federated (the manifest's `primary: true`) — has an explicit "is this really
part of the corpus" mechanism: mipibu's `is_case`, povos's
`inclusion_status IN ('included','flagged_unverified','excluded')` +
`inclusion_note`. The contract requires **one of**:

- `inclusion_status TEXT NOT NULL DEFAULT 'included' CHECK (… IN ('included','flagged_unverified','excluded'))` + `inclusion_note TEXT`, **or**
- a documented boolean equivalent (a `NOT NULL` 0/1 column whose name reads
  as an in-scope flag — `is_*`, `*_flag` — with a `CHECK (col IN (0,1))`).

**[v1.1]** v1 said *every* top-level entity table; in practice mipibu and
povos each carry the mechanism only on their one primary kind (`cases`,
`documents`). The validator: with a manifest, fails a `primary` kind that
lacks it; manifest-free, fails only if **no** entity table has one.
Secondary/child kinds (persons, places, pages) don't need it.

Rows that are `excluded` / not-in-scope are **kept** (so the decision isn't
re-litigated) and filtered out of the public views, OAI, and federation JSON.

### 5.3 Confidence & verification on rows (SHOULD)

Entity rows whose *existence* or *classification* is an agent judgement carry
`confidence REAL` (0.0–1.0) and
`verification_status TEXT NOT NULL DEFAULT 'unverified'` using the same
five-value ladder as §3.1.

### 5.4 Anti-fabrication (MUST)

- A value that is not in a source and not derivable by a stated rule is
  **NULL**, not a guess.
- Geographic coordinates emitted **only** when both lat and lon are known
  from a source; never geocoded silently (povos rule).
- Dates never invented; "undated" is a valid state.
- Any AI-vision / OCR transcription of manuscript or degraded material
  carries a risk-note column (povos `paleography_risk_note`) and an
  `extraction_method` that names it.
- Trust signals propagate outward: the OAI `oai_dc` layer surfaces
  `verification_status` / `confidence` / placeholder state in
  `dc:description` prefixes (`[verification: …]`, `[confidence: …]`,
  `[placeholder: …]`) so a harvester inherits the caveat.

---

## 6. Full-text search (MUST where the app offers search)

One FTS5 virtual table per searchable entity kind, named **`fts_<kind>`**.

```sql
CREATE VIRTUAL TABLE fts_<kind> USING fts5(
    <col>, <col>, ...,
    tokenize = 'unicode61 remove_diacritics 2'      -- MUST: accent-insensitive PT search
);
```

- `tokenize = 'unicode61 remove_diacritics 2'` is **required** — Portuguese
  search must be accent- and case-insensitive. Both corpora use exactly this.
- External-content (`content=`, `content_rowid=`) or contentless or
  standalone are all allowed; the generator picks based on table size.
- The FTS tables are populated by the **freeze step**, not maintained live.

---

## 7. Schema versioning (MUST)

Carry **one** of:

```sql
CREATE TABLE schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT NOT NULL
);
```

...or `PRAGMA user_version`. The table (or the pragma) **MUST** exist;
carrying a non-zero value is **SHOULD [v1.1]** (povos ships the table empty —
validator warns). `create_corpus_db` writes a row from the manifest's
`schema_version`.

A `migrations` table (`migration_id`, `name` UNIQUE, `applied_at`, `notes`)
is SHOULD — it records the build-tool migrations that produced this corpus,
distinct from the schema version. `create_corpus_db` stamps the first row.

The **corpus schema version** (this file's contract version + the corpus's
own entity-schema revision) is reported by `/api/schema` and is separate from
the **corpus content version** (the `.sha256`).

---

## 8. What Layer 3 needs from a conforming corpus

The shared `CorpusAdapter` (`archive-research-harness.md` C10) implements
`iter_records`, `count_records`, `get_record` over these guarantees:

| adapter need | contract guarantee |
|---|---|
| stable record identity | `<kind>_id` integer PKs, never reused |
| record kinds | the entity-kinds manifest lists them; each maps to one table |
| datestamp per record | `updated_at` (fallback `created_at`, fallback a corpus floor date) |
| selective-harvest sets | derivable from `*_normalized` FK columns + `year_start` decade |
| bilingual labels | `controlled_terms.label_pt` / `label_en`; entity `*_original` is source-language (usually PT) |
| rights for `dc:rights` | `repositories.rights_statement_original` + the partner's own data licence |
| provenance for `dc:source` | `external_identifiers` and/or `source_assertions.evidence_url` |
| trust flags | `verification_status`, `confidence`, `is_placeholder` |
| in-scope filter | §5.2 flag |

A corpus that satisfies this contract can be federated with **no
adapter-specific code** beyond the manifest.

---

## 9. Validator (`validate_corpus_db`)

`corpus-explorers/packages/corpus-toolkit`. Run before the forge will
scaffold an app. **Fails** on any MUST violation, **warns** on SHOULD.
Two modes: **manifest-free** (structural only) and **with a manifest**
(adds the per-corpus shape rules). `--frozen` upgrades the sidecar check to
a failure; `--strict` treats warnings as failures.

Both reference corpora (`sao-jose-mipibu-audit.db`, `povos_rn.db`) pass
manifest-free with warnings only.

### FAIL (MUST)

| id | check |
|---|---|
| `C1.sidecar` | (under `--frozen`) `.sha256` exists, 64-hex, matches the file |
| `C2.table` | `source_assertions`, `audit_events`, `repositories`, `controlled_terms`, `schema_version` exist |
| `C2.column` | each of those carries its required columns (§3, §4) |
| `C2.check` | `source_assertions` has the `confidence` 0..1 and `verification_status` ladder CHECKs |
| `C7.fts` | every `fts_*` table uses `tokenize = '… remove_diacritics 2'` |
| `C8.inscope` | (manifest) every `primary` kind has the §5.2 mechanism; (manifest-free) at least one entity table does |
| `C9.fk` | (manifest) every `controlled` `*_normalized` column FKs `controlled_terms` |
| `C9.rights` | `repositories.rights_statement_original` non-NULL for every row |
| `C10.geo` | no `latitude`/`longitude` (or `lat`/`lon`) row with exactly one of the pair set |
| `C11.integrity` | opens read-only; `PRAGMA integrity_check` = `ok` |
| `C12.fk_check` | `PRAGMA foreign_key_check` returns no rows |
| `C6.coverage` | **at freeze only** — every `controlled` `*_normalized` value has a `source_assertions` row |

### WARN (SHOULD)

`C1.sidecar` absent on a working DB · recommended backbone tables/columns
missing (`external_identifiers`, `migrations`, `audit_events.http_status`,
`repositories.robots_notes`/`custodian_of_originals_original`,
`controlled_terms.is_placeholder`/`definition_pt`/`definition_en`) ·
`C3.version` no schema-version value · `C5.placeholder` a vocabulary with no
`is_placeholder = 1` term · `C.labels` non-placeholder term missing
`label_en` · `C9.rights` NULL `robots_notes` · `C6.coverage` sampled
`*_normalized` value with no assertion (outside freeze) · `C.extids`
Handle/DOI-looking `*_original` strings but no `external_identifiers` table.

---

## 10. Divergences resolved

| point | mipibu | povos | contract v1 |
|---|---|---|---|
| `controlled_terms` definition | single `definition` | `definition_pt` + `definition_en` | **bilingual** (`_pt`/`_en`); keep mipibu's `match_pattern` |
| external IDs | `external_identifiers` table | folded into assertions | table is **SHOULD**; assertions always allowed |
| in-scope flag | `is_case` boolean | `inclusion_status` enum + note | **enum + note** preferred; boolean allowed if documented |
| `audit_events.http_status` | present | absent | **present** (nullable) |
| `repositories.robots_notes` / `custodian_of_originals_original` | present | absent | **present** (the fair-use gate needs them) |
| assertion `evidence_type` set | 5 values | 5 values (same) | **union of 8** (§3.1) |
| corpus DB distribution | Wasabi + sidecar | in-repo | size-based (§2) |

---

## 11. Change log

- **2026-09-02** — v1. Extracted from the live schemas of
  `sao-jose-mipibu-audit.db` and `povos_rn.db` at `main`, plus the
  harness spec of the same day.
- **2026-09-02** — v1.1. Building `corpus-toolkit` showed that neither
  reference corpus satisfied v1's `MUST` set (v1 had resolved divergences
  toward povos, but the DDL of both was already frozen). Relaxed to
  `SHOULD` — flagged **[v1.1: was MUST]** inline:
  - `audit_events.http_status` (povos omits the column)
  - `repositories.robots_notes` + `custodian_of_originals_original` (povos
    omits both); `rights_statement_original` stays a hard MUST
  - `controlled_terms.is_placeholder` column + placeholder-per-vocabulary
    (povos has neither); bilingual `definition_pt/_en` (mipibu has neither)
  - `source_assertions.evidence_type` CHECK contents no longer pinned (both
    ship a 5-value subset of the 8-value union)
  - coverage rule → SHOULD outside freeze, MUST at freeze
  - `*_normalized` → `controlled_terms` FK required only for columns the
    manifest marks `controlled` (mipibu has many free-text `_normalized`)
  - in-scope mechanism → required on `primary` kinds, not every table
  - non-zero `schema_version` value → SHOULD (povos ships an empty table)
  - `.sha256` sidecar → MUST for a frozen/distributed corpus; warn on a
    working DB, fail under `--frozen` (povos has no sidecar in-repo)

  Also: added the manifest-v0 format and `create_corpus_db`; the toolkit
  now lives in the new `corpus-explorers` monorepo (see that repo's
  `docs/MONOREPO.md`), not a `brasil-archives` sibling.
