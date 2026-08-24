# Federation contract — v1

**Status:** Design specification. Not yet implemented.
**Date:** 2026-08-24

## Purpose

This document specifies how upgrade projects federate with `brasil-archives`. It does **not** define a bespoke `brasil-archives` API. Instead, it specifies which existing archival standards an upgrade project must speak in order to be first-class in the federation, and how `brasil-archives` consumes them.

The federation contract is a **conformance profile**, not a new protocol. If your upgrade project speaks OAI-PMH and (optionally) IIIF Content Search API, it can register with `brasil-archives` and participate in cross-corpus search, coverage-gap analysis, and metadata harvest.

## What an upgrade project is

An **upgrade project** is a research or curation project that takes a source archive (or defined subset of a source archive) and produces a derived resource with substantially higher scoring on one or more `brasil-archives` scoring dimensions.

The canonical first example is the [Mipibu Corpus Explorer](https://mipibu.pplx.app), which takes the São José de Mipibu judicial holdings from LABIM/UFRN and lifts them from Provenance 5 → 8 and Finding Aids 6 → 9 by adding structured metadata, per-case titles, defendant identification, and full-text search.

An upgrade project is:

- **Derived** — it always cites a source archive
- **Scoped** — it declares which subset of the source it covers (record types, date range, geography, or fonds/collection subset)
- **Documented** — it has a written description and a delivery URL
- **Cited** — it preserves provenance back to the source archive

An upgrade project **is not**:

- The source archive itself
- A finding aid without derivative content
- A pure aggregator of already-published material with no added description or transcription

## Registration

An upgrade project registers with `brasil-archives` by contributing a YAML file to `configs/upgrade_projects/<slug>.yaml` in the `brasil-archives` repository. Registration is a pull request; review is by `brasil-archives` maintainers.

Example registration (Mipibu):

```yaml
# configs/upgrade_projects/mipibu.yaml
slug: mipibu
name: Mipibu Corpus Explorer
name_pt: Explorador do Corpus de Mipibu

source_archive_slug: labim-ufrn
scope:
  description_en: >
    Judicial records from the First Registry of São José de Mipibu,
    criminal proceedings 1872-1926 and probate/wills 1855-1926.
  description_pt: >
    Registros judiciais do Primeiro Cartório de São José de Mipibu,
    processos crime 1872-1926 e inventários e testamentos 1855-1926.
  period_tags:
    - second-reign-imperio-1840-1889
    - old-republic-1889-1930
  record_types:
    - processos-crime
    - inventarios-e-testamentos
    - autos-de-tutela-e-curatela
  geography:
    - name: São José de Mipibu
      geonames_id: 3450362
  approximate_size:
    document_count: 508
    page_equivalents: 10000

delivery:
  primary_url: https://mipibu.pplx.app
  source_repo: https://github.com/stevewil/mipibu
  status: stable   # in-development | beta | stable | deprecated

federation:
  oai_pmh_base_url: https://mipibu.pplx.app/oai       # required for harvest
  iiif_search_endpoint: null                          # optional, when available
  ead_export_url: null
  eac_cpf_export_url: null
  supported_metadata_formats:
    - oai_dc     # Dublin Core, required by OAI-PMH
    - ead
  supported_authorities:
    - viaf
    - geonames

lifts:
  provenance_curatorial:
    source_archive_score: 5
    upgrade_score: 8
    justification_en: >
      Introduces item-level titles, defendant identification, transcribed
      openings, and ISAD(G)-shaped metadata; still short of full transcription.
    justification_pt: >
      Introduz títulos por item, identificação de réus, transcrição de aberturas,
      e metadados no padrão ISAD(G); ainda aquém da transcrição integral.
  finding_aids:
    source_archive_score: 6
    upgrade_score: 9
    justification_en: >
      Adds full-text metadata search, faceted browse by year/comarca/parties,
      downloadable CSV of the case index.
    justification_pt: >
      Acrescenta busca em texto integral dos metadados, navegação facetada por
      ano/comarca/partes, exportação CSV do índice de processos.
  linkage_potential:
    source_archive_score: 8
    upgrade_score: 8
    justification_en: >
      Preserves and structures existing name and place linkages from the
      source; no additional authority reconciliation yet.

license:
  code: MIT     # to be confirmed at Mipibu's own open-source decision
  data: CC-BY-SA-4.0
  attribution_required: true

contact:
  email: stevewil@example
  maintainer: stevewil
```

The YAML file is authoritative. On merge, `scripts/load_upgrade_projects.py` upserts it into the `brasil-archives` database. Fields that change frequently (health, coverage counts) are refreshed by federation calls rather than by YAML edits.

## The federation surface

### Required: OAI-PMH

Every registered upgrade project SHOULD expose an OAI-PMH endpoint. `brasil-archives` uses OAI-PMH for two purposes:

1. **Metadata harvest** — periodic harvest of the project's own metadata records into `brasil-archives`'s aggregation store. Enables coverage-gap analysis and non-search use cases.
2. **Health and staleness signal** — a project whose OAI-PMH endpoint has been silent for months is likely stalled; feeds into the Growth Signal facet.

Minimum OAI-PMH conformance for federation:

- Verb `Identify` returns a valid response including `earliestDatestamp` and `repositoryName`.
- Verb `ListMetadataFormats` includes at least `oai_dc` (Dublin Core; required by the OAI-PMH spec).
- Verb `ListRecords` with `metadataPrefix=oai_dc` returns valid records for the project's holdings.
- Resumption tokens work correctly for paginating through the full corpus.

Additional metadata formats are welcome. If the project can serve EAD, `ead` should also be advertised; `brasil-archives` will harvest richer descriptions where available.

**Reference implementation** — for Python/Flask projects, the [pyoai](https://pypi.org/project/pyoai/) library provides an OAI-PMH server abstraction. Mipibu's retrofit will use it and its implementation can be a reference for other projects.

### Optional but recommended: IIIF Content Search API

Projects that hold digital objects and want to participate in cross-corpus federated search SHOULD implement the [IIIF Content Search API 2.0](https://iiif.io/api/search/2.0/).

`brasil-archives` uses IIIF Content Search to federate queries across registered upgrade projects. A search from `brasil-archives` fans out to every project that advertises a Content Search endpoint, aggregates results with source-project attribution, and renders them with links back to the originating project.

Minimum IIIF Content Search conformance:

- Content Search 2.0 service description advertised in the project's IIIF service
- `q` parameter supported
- Response returns valid `AnnotationCollection` with `Annotation` items pointing back to the project's canvases and manifests
- Response includes the required Content Search 2.0 context

The Content Search API is content-focused, not metadata-focused. For metadata-driven queries (which records match a set of facets), we use OAI-PMH's `ListRecords` with a `set` parameter.

### Optional: Static exports

Projects that cannot maintain a live server (e.g., completed research projects with a static output) can register a **static export**:

- `ead_export_url` — pointer to a downloadable EAD XML file describing the project's holdings
- `eac_cpf_export_url` — pointer to authority records
- `oai_dc_export_url` — pointer to a downloadable OAI-DC XML dump

`brasil-archives` fetches these at harvest time. This mode does not support live search but does support catalog-level federation and coverage analysis.

## What `brasil-archives` does with the federated data

Once an upgrade project is registered and its endpoints are healthy, `brasil-archives`:

1. **Displays the upgrade project on the source archive's page** — with scope, status, delivery URL, and lifted-dimension breakdown.
2. **Harvests metadata via OAI-PMH** — populates an `aggregated_records` store used for coverage analysis and offline discovery. Preserves source-project provenance separately from source-archive provenance.
3. **Federates search via IIIF Content Search** — a search entered on `brasil-archives` fans out to all registered projects with a Content Search endpoint and aggregates results.
4. **Computes coverage-gap analysis** — for each (period, place, record-type) triple, reports which are covered by at least one upgrade project and which are not. This turns `brasil-archives` into a research-agenda-generation tool.
5. **Tracks health via probes** — the standard quarterly probe extends to check OAI-PMH `Identify` response health and IIIF Content Search endpoint responsiveness.

## Versioning

This document specifies **federation contract v1**. Breaking changes trigger a new version. Backwards-compatible additions do not.

Upgrade projects declare which contract version they conform to via:

```yaml
federation:
  contract_version: v1
```

When contract v2 is introduced, v1-conformant projects continue to work; the harvest and search clients maintain compatibility with declared versions.

## Governance (deferred)

Governance of the federation — who decides what registers, what conformance means, how disputes are resolved — is deferred to a later document. For the initial period (roughly through Phase 4 of the standards adoption roadmap), governance is by `brasil-archives` maintainers. When the project moves toward broader community engagement, a governance model will be published as `docs/governance.md`.

## Change log

- **2026-08-24** — Initial specification. Not yet implemented; guides the schema and Mipibu retrofit.
