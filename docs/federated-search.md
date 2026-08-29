# Federated search (Phase 3.5)

**Status:** built 2026-08-29. Route `GET /search` (`main` blueprint,
public). Service: [`app/services/federated_search.py`](../app/services/federated_search.py).
Template: `app/templates/search.html`. Tests: `tests/test_federated_search.py`.

> **Not to be confused with the archive-catalog search.** `GET /archives/?q=…`
> (built the same day) is a free-text filter over the ~80 catalogued
> *archives* — their names and descriptions. This page searches the
> harvested *records* inside partner corpora. Both share
> [`app/text.py`](../app/text.py) `fold()` for accent-insensitive matching.

## What it is

One public search box over every record brasil-archives has **harvested**
from a partner corpus explorer into `aggregated_records`. Each hit is
attributed to its partner project and links back into that partner's own
viewer.

This is the pragmatic precursor to **Phase 4** (live IIIF Content Search
fan-out — `federation-v1.md` §"IIIF Content Search"). Phase 4 queries the
partners' live indexes; Phase 3.5 queries our last harvest.

**What's actually in there:** the two federated corpora are narrow.
[`federated-search-keywords.md`](federated-search-keywords.md) is the
operator cheat sheet — productive terms, document/case types, year spans
per partner, and the queries that deliberately return nothing (e.g.
`escravo`). The empty and no-results states of the page also show a
curated `SAMPLE_QUERIES` row (`app/services/federated_search.py`) — keep
the two in sync.

## Design decisions

| Decision | Why |
|---|---|
| **Search the harvested snapshot, not a live fan-out.** | Phase 4's job. Freshness here is bounded by the monthly harvest cron. |
| **`oai_dc` records only.** | Every partner exposes Dublin Core. mipibu also provides `oai_ead` for the same cases; including it would double every mipibu hit. Filter is `metadata_prefix == "oai_dc"`. |
| **Full scan in Python, no FTS5 (yet).** | ~10³ harvested records; a scan + parse is well under a frame. The spec (`TODO.md` §6) anticipated a `LIKE`/`json_extract` scan. Move to an FTS5 virtual table with a `remove_diacritics=2` tokenizer if the corpus reaches ~10⁴ (mirror povos's `fts_documents`). |
| **Accent- and case-insensitive matching.** | Brazilian users type "sumario" for "Sumário". Both needle and haystack are `NFKD`-folded with combining marks stripped. An FTS5 `LIKE` prefilter would be accent-sensitive, which is why the current version scans instead. |
| **Two match tiers.** | A hit in title/creator/publisher/description ("strong") sorts above a hit only in subjects/coverage/identifiers/date ("weak"). Within a tier, alphabetical by folded title. |
| **Result link, best available first.** | (1) an on-host URL — the partner's own record page (mipibu `…/cases/SJM-0001`, povos `…/documents/N`, including the parent document a passage carries); (2) an off-host URL from `dc:identifier`/`dc:relation` (povos `collection` → gov.br Projeto Resgate); (3) a `dc:source` URL — where the record was catalogued from (povos `passage`/`work`); (4) the project home page, last resort. The "Cited source" secondary link shows only when it is a *different* destination than the primary. |
| **Facet counts ignore the `source` filter.** | The per-partner chips always show the full spread so a visitor who narrowed to one partner can widen back out. |

The extractor captures `dc:source` http values into `canonical.source_urls`
for tier (3). After an extractor change, `python -m scripts.reextract`
re-derives `extracted_json` for already-harvested rows (a plain harvest
only refreshes rows whose raw XML changed).

## Known follow-ups

- **povos `passage` / `work` deep links go off-site.** As of povos
  `e73a892` (2026-08-29) a `passage` deep-links to its **parent document
  page** on povos (`/documents/N`); `work` and the 5 `ethnic-group` rows
  with no `portal_url` still land on an external page or the povos home,
  because povos has no per-record detail page for those kinds. Add a
  `/works/<id>` / `/ethnic-groups/<id>` view on povos if that matters.
- **povos `passage` records have no `dc:date`.** They show no year in
  results. povos could carry the parent document's date.
- **Tie search hits back into the catalog.** Each hit could also link to
  the brasil-archives archive-detail page for the partner's
  `source_archive`. Deferred — keeps the row clean for v1.
- **FTS5** if the harvested corpus grows (see the table above).
