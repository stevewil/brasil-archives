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
| **Deep link = the `canonical.urls` entry that shares a host with the project's `primary_url`.** | mipibu's `dc:identifier` carries `…/cases/SJM-0001`. Partners whose `oai_dc` omits a self URL (povos passages today) fall back to the project home page; the first off-host URL is surfaced separately as "Cited source". |
| **Facet counts ignore the `source` filter.** | The per-partner chips always show the full spread so a visitor who narrowed to one partner can widen back out. |

## Known follow-ups

- **povos `oai_dc` enrichment.** povos `passage:*` records harvest with no
  `dc:identifier` URL and no `dc:date`, so they deep-link only to the
  povos home page and show no date. If povos adds a per-record
  `dc:identifier` (e.g. `https://povos-indigenas-rn.from-bottom-to.top/passages/<id>`)
  and `dc:date` where known, those hits improve with no change here.
- **Tie search hits back into the catalog.** Each hit could also link to
  the brasil-archives archive-detail page for the partner's
  `source_archive`. Deferred — keeps the row clean for v1.
- **FTS5** if the harvested corpus grows (see the table above).
