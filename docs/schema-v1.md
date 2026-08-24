# Schema — v1

**Status:** Design sketch. Not yet implemented as SQL.
**Date:** 2026-08-24

## Purpose

Data model for `brasil-archives`, expressed as SQLAlchemy-friendly table definitions with commentary. The schema is designed to be **standards-aware from the start**: fields for Handle, VIAF, GeoNames, Wikidata, and OAI-PMH endpoints are first-class, not retrofitted.

The schema tracks **history** where change matters: scores, facet values, and probe results are versioned so we can see how they evolved. Static institutional facts are stored once.

Target platform: SQLite for development and initial deployment. Migrations via Alembic / Flask-Migrate. The schema is portable to PostgreSQL if we outgrow SQLite.

## Table map

Core tables:

- `archives` — one row per archive institution or collection
- `upgrade_projects` — one row per registered upgrade project (Mipibu, and future explorers)
- `dimension_scores` — one row per (archive, dimension, revision), historical
- `facet_values` — one row per (archive, facet, value), historical
- `probe_results` — one row per (archive, probe_run), historical
- `linked_explorers_view` — logical view joining upgrade_projects to archives (or a proper table if we outgrow the view)

Vocabulary tables:

- `periods`, `record_types`, `themes`, `institutional_types`, `licensing_postures`, `web_ops_health_values`, `external_preservation_values`, `growth_signal_values`, `roadmap_values`, `prior_use_values` — controlled vocabularies for facets

Join tables for multi-select facets:

- `archive_periods`, `archive_record_types`, `archive_themes`
- `upgrade_project_periods`, `upgrade_project_record_types`

Federation and aggregation:

- `federation_endpoints` — an upgrade project's OAI-PMH, IIIF Search, EAD export URLs
- `aggregated_records` — metadata harvested from upgrade projects via OAI-PMH (deferred to phase 2)
- `dimension_lifts` — how each upgrade project lifts each dimension against its source archive

## Core tables

### `archives`

One row per archive institution or collection.

```sql
CREATE TABLE archives (
    id                       INTEGER PRIMARY KEY,
    slug                     TEXT NOT NULL UNIQUE,      -- 'labim-ufrn', 'tjma', etc.
    name                     TEXT NOT NULL,
    name_pt                  TEXT,

    -- Standards-aware identifiers
    handle_prefix            TEXT,                       -- e.g., '123456789' for LABIM
    doi                      TEXT,
    ark_identifier           TEXT,
    viaf_id                  TEXT,                       -- for the institution
    isni_id                  TEXT,
    wikidata_qid             TEXT,                       -- e.g., 'Q...'
    geonames_primary_id      INTEGER,                    -- primary geographic entity

    -- Institutional info
    institutional_type_id    INTEGER NOT NULL,           -- FK to institutional_types
    home_country_code        TEXT NOT NULL DEFAULT 'BR',
    home_state_code          TEXT,                       -- 'RN', 'BA', 'PE', etc.
    home_city                TEXT,

    -- Access
    canonical_url            TEXT NOT NULL,              -- the archive's front door
    catalog_url              TEXT,                       -- specific catalog URL if different
    contact_email            TEXT,

    -- Standards conformance (populated as verified)
    oai_pmh_base_url         TEXT,
    ead_finding_aid_url      TEXT,
    iiif_manifest_root       TEXT,

    -- Descriptions
    description_en           TEXT,
    description_pt           TEXT,
    curatorial_rarity_notes  TEXT,                       -- free-text facet
    prior_use_note           TEXT,                       -- free-text facet
    stated_scope             TEXT,                       -- what the archive claims to hold

    -- Editorial state
    no_digital_content       BOOLEAN NOT NULL DEFAULT 0,  -- from the 30 no-content rows
    fair_use_eligible        BOOLEAN,                     -- nullable = not yet reviewed
    caveat_emptor            BOOLEAN NOT NULL DEFAULT 0,  -- fatal-flaw bucket

    -- Provenance
    survey_source            TEXT,                        -- 'nordeste-digital-archives-survey.md'
    survey_row               INTEGER,
    created_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (institutional_type_id) REFERENCES institutional_types(id)
);
```

### `upgrade_projects`

One row per registered upgrade project.

```sql
CREATE TABLE upgrade_projects (
    id                       INTEGER PRIMARY KEY,
    slug                     TEXT NOT NULL UNIQUE,       -- 'mipibu'
    name                     TEXT NOT NULL,
    name_pt                  TEXT,

    -- Source
    source_archive_id        INTEGER NOT NULL,
    scope_description_en     TEXT NOT NULL,
    scope_description_pt     TEXT,
    approximate_document_count       INTEGER,
    approximate_page_equivalents     INTEGER,

    -- Delivery
    primary_url              TEXT NOT NULL,
    source_repo              TEXT,
    delivery_status          TEXT NOT NULL,              -- in-development|beta|stable|deprecated

    -- Federation contract (see docs/federation-v1.md)
    federation_contract_version    TEXT NOT NULL DEFAULT 'v1',
    oai_pmh_base_url               TEXT,
    iiif_search_endpoint           TEXT,
    ead_export_url                 TEXT,
    eac_cpf_export_url             TEXT,
    supported_metadata_formats     TEXT,                 -- comma-separated: oai_dc,ead
    supported_authorities          TEXT,                 -- comma-separated: viaf,geonames

    -- License and contact
    code_license             TEXT,
    data_license             TEXT,
    attribution_required     BOOLEAN NOT NULL DEFAULT 1,
    contact_email            TEXT,
    maintainer               TEXT,

    -- Provenance
    yaml_source              TEXT,                        -- path to registration YAML
    created_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (source_archive_id) REFERENCES archives(id)
);
```

### `dimension_scores` — historical

One row per (archive, dimension, revision). New score → new row, old row retained.

```sql
CREATE TABLE dimension_scores (
    id                       INTEGER PRIMARY KEY,
    archive_id               INTEGER NOT NULL,
    dimension                TEXT NOT NULL,              -- 'accessibility', 'provenance_curatorial', etc.
    score                    INTEGER NOT NULL,           -- 0-10
    justification_en         TEXT NOT NULL,
    justification_pt         TEXT,
    scored_by                TEXT,                        -- 'stevewil', 'agent', etc.
    scored_at                TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    superseded_at            TIMESTAMP,                   -- NULL = currently active
    superseded_by_id         INTEGER,                     -- FK to next revision

    FOREIGN KEY (archive_id) REFERENCES archives(id),
    FOREIGN KEY (superseded_by_id) REFERENCES dimension_scores(id),
    CHECK (score >= 0 AND score <= 10),
    CHECK (dimension IN (
        'accessibility',
        'provenance_curatorial',
        'corpus_completeness',
        'finding_aids',
        'pipeline_ingestion_readiness',
        'uniqueness_non_duplication',
        'scale',
        'linkage_potential'
    ))
);

CREATE INDEX idx_dimension_scores_active ON dimension_scores(archive_id, dimension)
    WHERE superseded_at IS NULL;
```

### `dimension_lifts`

For upgrade projects: how much each project lifts each dimension against its source archive.

```sql
CREATE TABLE dimension_lifts (
    id                       INTEGER PRIMARY KEY,
    upgrade_project_id       INTEGER NOT NULL,
    dimension                TEXT NOT NULL,
    source_archive_score     INTEGER NOT NULL,           -- what the source archive scored
    upgrade_score            INTEGER NOT NULL,           -- what the upgrade project achieves for its scope
    justification_en         TEXT NOT NULL,
    justification_pt         TEXT,
    recorded_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (upgrade_project_id) REFERENCES upgrade_projects(id),
    CHECK (source_archive_score >= 0 AND source_archive_score <= 10),
    CHECK (upgrade_score >= 0 AND upgrade_score <= 10)
);
```

### `probe_results` — historical

One row per probe run. Not overwritten; new probe → new row.

```sql
CREATE TABLE probe_results (
    id                       INTEGER PRIMARY KEY,
    archive_id               INTEGER,                     -- one of archive_id or upgrade_project_id
    upgrade_project_id       INTEGER,                     -- must be non-null
    probed_at                TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Web ops signals
    canonical_url            TEXT NOT NULL,
    https_valid              BOOLEAN,
    cert_expires_at          DATE,
    canonical_http_status    INTEGER,
    interior_url_sample      TEXT,                        -- JSON list of sample URLs
    interior_http_statuses   TEXT,                        -- JSON list of statuses

    -- OAI-PMH signal (for upgrade projects)
    oai_pmh_identify_ok      BOOLEAN,
    oai_pmh_earliest_datestamp   DATE,
    oai_pmh_record_count     INTEGER,

    -- IIIF signal (for upgrade projects)
    iiif_search_endpoint_ok  BOOLEAN,

    -- External preservation signal
    wayback_home_count       INTEGER,
    wayback_interior_hit_ratio     REAL,                  -- 0.0 to 1.0

    -- Growth signal
    directory_url_count_now  INTEGER,
    directory_url_count_12m_ago    INTEGER,
    directory_url_count_24m_ago    INTEGER,

    -- Prior use signal
    citation_count_crossref  INTEGER,
    citation_count_semantic_scholar    INTEGER,

    -- Computed facet values (denormalized for query speed)
    web_ops_health           TEXT,                        -- computed from above
    external_preservation    TEXT,
    growth_signal            TEXT,
    prior_use_signal         TEXT,

    -- Probe metadata
    probe_version            TEXT NOT NULL,
    probe_notes              TEXT,

    FOREIGN KEY (archive_id) REFERENCES archives(id),
    FOREIGN KEY (upgrade_project_id) REFERENCES upgrade_projects(id),
    CHECK ((archive_id IS NOT NULL) OR (upgrade_project_id IS NOT NULL))
);

CREATE INDEX idx_probe_results_archive_time ON probe_results(archive_id, probed_at DESC);
CREATE INDEX idx_probe_results_upgrade_time ON probe_results(upgrade_project_id, probed_at DESC);
```

### `facet_values` — historical

Single-select facets that aren't derived from probes go here. Multi-select facets use dedicated join tables (see below).

```sql
CREATE TABLE facet_values (
    id                       INTEGER PRIMARY KEY,
    archive_id               INTEGER NOT NULL,
    facet                    TEXT NOT NULL,              -- 'licensing_posture', 'stated_roadmap', etc.
    value                    TEXT NOT NULL,
    note                     TEXT,
    set_by                   TEXT,
    set_at                   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    superseded_at            TIMESTAMP,
    superseded_by_id         INTEGER,

    FOREIGN KEY (archive_id) REFERENCES archives(id),
    FOREIGN KEY (superseded_by_id) REFERENCES facet_values(id)
);

CREATE INDEX idx_facet_values_active ON facet_values(archive_id, facet)
    WHERE superseded_at IS NULL;
```

## Vocabulary tables

Controlled vocabularies stored as tables so they can be edited without schema migrations. Populated by `scripts/load_vocabularies.py` from YAML files in `configs/vocabularies/`.

```sql
CREATE TABLE periods (
    id                       INTEGER PRIMARY KEY,
    slug                     TEXT NOT NULL UNIQUE,       -- 'second-reign-imperio-1840-1889'
    label_en                 TEXT NOT NULL,
    label_pt                 TEXT NOT NULL,
    sort_order               INTEGER NOT NULL,
    start_year               INTEGER,
    end_year                 INTEGER
);

CREATE TABLE record_types (
    id                       INTEGER PRIMARY KEY,
    slug                     TEXT NOT NULL UNIQUE,
    label_en                 TEXT NOT NULL,
    label_pt                 TEXT NOT NULL,
    category                 TEXT NOT NULL,              -- 'judicial', 'ecclesiastical', etc.
    sort_order               INTEGER NOT NULL
);

CREATE TABLE themes (
    id                       INTEGER PRIMARY KEY,
    slug                     TEXT NOT NULL UNIQUE,
    label_en                 TEXT NOT NULL,
    label_pt                 TEXT NOT NULL,
    category                 TEXT NOT NULL,              -- 'population', 'economy', etc.
    sort_order               INTEGER NOT NULL,
    provisional              BOOLEAN NOT NULL DEFAULT 1   -- flag from algorithm design
);

CREATE TABLE institutional_types (
    id                       INTEGER PRIMARY KEY,
    slug                     TEXT NOT NULL UNIQUE,
    label_en                 TEXT NOT NULL,
    label_pt                 TEXT NOT NULL,
    sort_order               INTEGER NOT NULL
);
```

## Join tables for multi-select facets

```sql
CREATE TABLE archive_periods (
    archive_id               INTEGER NOT NULL,
    period_id                INTEGER NOT NULL,
    PRIMARY KEY (archive_id, period_id),
    FOREIGN KEY (archive_id) REFERENCES archives(id),
    FOREIGN KEY (period_id) REFERENCES periods(id)
);

CREATE TABLE archive_record_types (
    archive_id               INTEGER NOT NULL,
    record_type_id           INTEGER NOT NULL,
    PRIMARY KEY (archive_id, record_type_id),
    FOREIGN KEY (archive_id) REFERENCES archives(id),
    FOREIGN KEY (record_type_id) REFERENCES record_types(id)
);

CREATE TABLE archive_themes (
    archive_id               INTEGER NOT NULL,
    theme_id                 INTEGER NOT NULL,
    PRIMARY KEY (archive_id, theme_id),
    FOREIGN KEY (archive_id) REFERENCES archives(id),
    FOREIGN KEY (theme_id) REFERENCES themes(id)
);

-- Same shape for upgrade_project_periods, upgrade_project_record_types
```

## Federation and aggregation (deferred to Phase 2)

Two tables reserved but not implemented in Phase 1. Design placeholder so the schema is forward-compatible.

```sql
-- Deferred: harvested metadata records from upgrade projects
CREATE TABLE aggregated_records (
    id                       INTEGER PRIMARY KEY,
    upgrade_project_id       INTEGER NOT NULL,
    external_identifier      TEXT NOT NULL,              -- OAI identifier
    metadata_format          TEXT NOT NULL,              -- 'oai_dc', 'ead', etc.
    metadata_xml             TEXT NOT NULL,              -- raw XML preserved
    parsed_title             TEXT,
    parsed_date              TEXT,
    harvested_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (upgrade_project_id) REFERENCES upgrade_projects(id),
    UNIQUE (upgrade_project_id, external_identifier)
);
```

## Design notes

**Why history matters.** Scores and facets change over time — either because we refine our judgment, or because the archive itself changes (grows, degrades, closes). A federation that discards its own past decisions cannot support scholarship on how the archival landscape evolves. Storing historical rows costs almost nothing in SQLite and makes the project's own decision-making auditable.

**Why probes are also historical.** Similarly, probe results form a time series. Growth signal is literally a diff between probes. The `directory_url_count_12m_ago` field is computed at probe time from prior probe rows.

**Why controlled vocabularies are tables.** Periods, record types, themes, institutional types — these vocabularies will refine as we tag more archives. Storing them as tables (populated from YAML) makes them editable without schema migrations. New period or theme = new row.

**Why the schema is bilingual from the start.** Adding a `_pt` column is cheap; retrofitting one after 50 archives are populated is not. Bilingual PT/EN was a stated project goal from the beginning.

**What the schema deliberately does not include.**

- No `composite_score` field. Composite is computed at query time from `dimension_scores`; it never lives in the archive row. This is deliberate — the composite is not authoritative; the dimensions are.
- No user accounts. Deferred until public phase.
- No annotations, comments, or ratings. Deferred until public phase.
- No content storage. The federation is a catalog, not a delivery system.

## Migration path from survey

Loading `nordeste-digital-archives-survey.md` populates:

- `archives` rows (one per pipeline-viable and no-content row, with `no_digital_content=1` for the 30 no-content rows)
- No `dimension_scores` (scoring happens in Pass 2)
- No `facet_values` yet — facets populated during scoring or as separately extracted
- No `probe_results` (probe runs after schema is live)

## Change log

- **2026-08-24** — Initial design sketch. Not yet implemented in SQL or SQLAlchemy.
