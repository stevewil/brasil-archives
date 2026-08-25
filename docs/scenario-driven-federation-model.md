# Scenario-Driven Federation Model

- **Status:** draft, 2026-08-24
- **Author:** Steve Williams
- **Related:** `docs/federation-v1.md` (protocol), `docs/algorithm-v1.md` (per-archive scoring), `docs/adr-0001-two-axis-aggregation.md` (why federation appears in the algorithm as a facet).

This document describes how brasil-archives connects to the material in the archives it catalogs, and why we are building **archive apps** rather than a single omnibus harvester. It is a design document, not an implementation spec — the federation protocol itself is specified in `docs/federation-v1.md`.

## The core reframing

Earlier drafts of `federation-v1.md` implicitly assumed that federation would *mirror* holdings across archives — pulling records from each source into a central index rich enough to answer research questions on its own. That framing has two problems:

1. **It misdescribes what most Northeast archives actually expose.** Many are static PDF trees, unstructured HTML lists, or handwritten scans without OCR. Comprehensive mirroring would require heroic per-archive engineering just to reach the record level; the reward would be a normalized index that is still incomplete because OCR fails on the underlying material.
2. **It sets up a treadmill of ingestion work that dwarfs the point of the project.** brasil-archives is a *catalog* of archives. Its scholarly value is that a historian can find and evaluate the archives themselves, then bring the right tool to bear on the ones that matter for their question.

The reframing:

- **Federation is an *index*, not a mirror.** Its job is to point precisely at material known to exist in a specific archive, using whatever normalized handles that archive can honestly emit. It is not a substitute for the archive; it is a routing layer.
- **Testing is *scenario-driven*.** We do not chase completeness archive by archive. We define concrete scholarly scenarios ("show me the probate records from São José de Mipibu between 1850 and 1888 that reference enslaved persons as part of the estate"), then wire up whichever archives are needed to answer that scenario, at the granularity that scenario requires.
- **Where a source archive's own surface is not sufficient for a scholar to use it, we build an *archive app* for it** — a small, focused companion application that turns the raw material into a normalized, searchable, citable interface. Mipibu (`stevewil/mipibu`) is the first such app.
- **Archive apps are monolithic on purpose.** We are not extracting a shared framework until we have at least three apps across at least two material classes to abstract from. See "Refactor trigger" below.

## Four layers

The federation stack is thought of as four layers, from concrete to abstract:

### Layer 1 — Archive metadata (brasil-archives, this app)

Persistent per-archive metadata: institutional type, home state, canonical URL, the eight scored dimensions, the twelve facets, tags, prior use notes, licensing posture, roadmap posture, and — new in this cycle — `scholarly_access_practical`. This is a scholar's map of the landscape: which archives exist, how strong each is on the pipeline vs. research axes, and which ones need our tooling to be practically usable.

Layer 1 is the *only* layer required to launch the public site. The other three layers are built as scenarios call for them.

### Layer 2 — Item index (`ArchiveItem`, future)

Per-archive item-level records — one row per document, box, series, or whatever the smallest citable unit is for that archive. Each row carries whatever normalized fields the archive can honestly emit (`record_type`, date range, principal parties, geographic scope, physical location, canonical citation) and enough source metadata (archive slug, source URL or box/folio, provenance, confidence) to lead the scholar back to the primary source.

Layer 2 is populated per archive, per scenario. It is not required for an archive to appear on brasil-archives; an archive can be catalogued at Layer 1 indefinitely.

Layer 2 rows are what an archive app emits over the federation API described below.

### Layer 3 — Fetch adapter

A per-archive adapter that, given a Layer 2 record id, can return the primary source: image, PDF, transcript, or the archive app's normalized item page. Adapters are called on-demand by scholars answering scenario questions, not run in batch. Some adapters are pass-through (redirect to the archive's stable URL); others go through an archive app.

### Layer 4 — Cluster tooling

Cross-archive tools that operate over Layers 1–2: search a subject across multiple archives, produce a bibliography that spans several sources, build reading lists from a scenario definition. This is not built until multiple archives have Layer 2 rows to search across.

## Archive apps: what they are, why they are monolithic

An **archive app** is a small companion application for a single archive whose own surface does not support scholarly workflows. Mipibu is the paradigm case: 508 records from São José de Mipibu boxes 07–20 (299 criminal + 209 probate), with handwritten sources whose OCR failed, exposed by the source archive as a flat PDF tree with no search or enumeration. A scholar cannot practically use that archive without a companion.

**Mipibu-shape features** (the pattern we are copying):

- A structured schema that separates *source-wording* from *normalized-interpretation*, with provenance and confidence per normalized field. This is essential for archives where the interpretation layer is contested (translations, disputed dates, uncertain identifications).
- A durable canonical URL per item, plus a federation API (below) that lets other apps refer to items by handle.
- A stable citation string per item.
- A search UI over the normalized fields; primary source images preserved and linked.
- Bilingual UI (PT/EN) as a first-class concern, not a translation retrofit.

### Why monolithic, not shared framework

We could — and might, one day — extract a shared "archive app framework" that other archives plug into with configuration. We are explicitly not doing that yet. Reasons:

- **The current N is one.** Extracting a framework from one instance is a well-known way to bake in that instance's incidental choices as if they were principles. Mipibu's schema is specific to Mipibu's material (probate + criminal); a shared framework would either be so lean it barely helps or so opinionated that the next archive fights it.
- **Getting archive 2 wrong is cheaper than getting a framework wrong.** A monolithic app for archive 2 that turns out to have a bad choice is a rewrite of one small app. A framework with a bad choice is a rewrite of every app that ever depended on it.
- **The federation API is the abstraction that matters.** Two archive apps can share nothing internally and still cooperate perfectly if they both speak the federation API (below). The API is the contract; internal architecture is not.

### Refactor trigger

Extract a shared archive-app framework only after **three archive apps exist across at least two different material classes** (judicial, press, notarial, ecclesiastical, iconographic, cartographic, photographic, etc.). At that point, we have concrete evidence of what is common versus incidental. Until then, monolithic archive apps are the design.

The natural sequence for reaching that trigger:

1. **Mipibu** (judicial: probate + criminal). Follow-on turn adds the federation API on top of the existing app.
2. **Second archive app**, chosen from `only-via-federation`–tagged archives in brasil-archives once we start scoring the survey list.
3. **Third archive app**, ideally in a different material class from Mipibu and archive 2.

At that point, run a factoring exercise. Not before.

## The federation API contract

Every archive app in the federation exposes the same small HTTP+JSON contract. The contract is deliberately minimal: it names Layer 2 rows and hands out Layer 3 primary-source references.

All endpoints are GET, all responses are JSON, CORS is permissive (the data is public). Every response includes an `archive_slug` field matching the archive's brasil-archives slug.

### `GET /api/health`

```json
{
  "status": "ok",
  "archive_slug": "rn-mipibu-processos-01-t2r1",
  "record_count": 508,
  "schema_version": "1",
  "last_updated_at": "2026-08-24T00:00:00Z"
}
```

Cheap; safe to poll. `status` is `ok` or `degraded`. brasil-archives' quarterly probe (see `docs/algorithm-v1.md §Ongoing infrastructure`) uses this endpoint against archive apps we own.

### `GET /api/schema`

Returns the per-archive normalized-field catalog. Structure:

```json
{
  "archive_slug": "rn-mipibu-processos-01-t2r1",
  "record_types": ["probate", "criminal"],
  "fields": [
    {
      "name": "date_range",
      "type": "date_range",
      "description_en": "Range of dates covered by the case file.",
      "description_pt": "Intervalo de datas coberto pelo processo.",
      "provenance": true,
      "confidence": true
    }
    // ...
  ]
}
```

`fields` lists the normalized fields the app emits per record. `provenance` and `confidence` flags say whether each field carries those meta-attributes. Consumers (cluster tools) use this to know what to expect from `/api/records`.

### `GET /api/records`

Paginated list of Layer 2 rows.

Query parameters (all optional):

- `record_type` — filter by record type slug from the archive's schema
- `date_from`, `date_to` — ISO dates; matches records whose `date_range` overlaps
- `subject` — free-text over a small set of subject-related normalized fields (defined per archive)
- `place` — normalized place name
- `page`, `per_page` — pagination; `per_page` capped at 200

Response:

```json
{
  "archive_slug": "rn-mipibu-processos-01-t2r1",
  "page": 1,
  "per_page": 50,
  "total": 209,
  "records": [
    {
      "id": "mipibu-p-1857-034",
      "record_type": "probate",
      "date_range": {"from": "1857-03-12", "to": "1858-11-04"},
      "normalized_summary_en": "Estate inventory of Maria da Conceição, freed woman, São José de Mipibu.",
      "normalized_summary_pt": "Inventário de bens de Maria da Conceição, forra, São José de Mipibu.",
      "canonical_url": "https://mipibu.pplx.app/records/mipibu-p-1857-034",
      "primary_source_url": "https://source-archive.example/box08/pf034.pdf"
    }
    // ...
  ]
}
```

`id` is stable across time within an archive; other apps store it as their reference. The URL fields are always absolute.

### `GET /api/records/<id>`

Full record. Everything in the list response plus the normalized fields declared in `/api/schema`, plus, per normalized field, the `source_wording`, `provenance`, and `confidence` if the schema flagged them.

### Versioning

Endpoints are versioned by `schema_version` in `/api/health`. The contract above is version `"1"`. Breaking changes to the shape of `/api/records` or `/api/records/<id>` bump `schema_version`; brasil-archives will refuse to consume an app whose version it doesn't recognize.

## Where brasil-archives fits

- brasil-archives is Layer 1. It catalogs every archive we are aware of, whether or not it has an archive app.
- Archive apps we build show up in brasil-archives as Archive records with `scholarly_access_practical = only-via-federation` — they are the *archive*, and the app is their access surface.
- The archive-list page's Pipeline axis (see `docs/adr-0001-two-axis-aggregation.md`) will trend toward high values for archives with a federation companion, because a well-designed archive app is exactly what accessibility, finding_aids, and pipeline_ingestion_readiness ask about.
- The Research axis is independent of federation — federation cannot manufacture provenance clarity, curatorial completeness, or linkage potential. Those are properties of the material itself.

## Scenario 1: São José de Mipibu probate + slavery references, 1850–1888

The first scenario we intend to build end-to-end. Question:

> "Quais inventários de São José de Mipibu entre 1850 e 1888 referenciam pessoas escravizadas como parte do espólio?"
>
> ("What probate records from São José de Mipibu between 1850 and 1888 reference enslaved persons as part of the estate?")

This scenario is deliberately narrow. It uses:

- **Layer 1:** the (future) Mipibu Archive row in brasil-archives, tagged `only-via-federation`.
- **Layer 2:** the 209 probate records from Mipibu boxes 07–20 that fall within the 1850–1888 window.
- **Layer 3:** direct-link to the Mipibu app's record page (with primary source PDF underneath).
- **Layer 4:** none — the question is answered inside one archive.

The scenario exercises the whole federation contract without requiring cross-archive tooling. It also exercises Mipibu's schema separation between source-wording and normalized-interpretation, because "references enslaved persons as part of the estate" is exactly the kind of interpretive claim that needs provenance and confidence attached — the source wording will use period vocabulary, and the normalized interpretation is where the modern search actually happens.

### Preconditions (do not exist yet, staged in follow-on turns)

- `stevewil/mipibu` gains the federation API described above.
- A Mipibu deployment is available for our testing (the user is running one on cPanel; see the follow-on turn).
- Mipibu is promoted from `UpgradeProject` to `Archive` in brasil-archives with `scholarly_access_practical = only-via-federation`.
- A small runner (out of scope for this doc) can be pointed at a scenario definition and execute Layer 2 queries + Layer 3 fetches.

Neither this turn nor the current brasil-archives changes attempt those preconditions. This document establishes the shape they will take.

## What this document is not

- **Not the federation protocol spec.** That lives in `docs/federation-v1.md`. This document is the *why*; the protocol document is the *what and how*.
- **Not a schema for Layer 2.** Layer 2 schemas are per-archive by design. Each archive app defines its own via `/api/schema`.
- **Not a commitment to a specific number of archive apps.** We build one when a scenario calls for one. Some archives will never need one.

## Change log

- **2026-08-24** — Initial draft. Federation reframed as index rather than mirror; monolithic archive apps adopted; refactor trigger set at "three apps, two material classes"; federation API contract sketched; Scenario 1 named.
