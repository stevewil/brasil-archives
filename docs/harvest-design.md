# Harvest Design — Phase 3 Track 2

**Status:** Design locked 2026-08-26. Implementation follows this doc.
**Related:** [`docs/federation-v1.md`](federation-v1.md), [`docs/handoff/2026-08-26-track-2-start.md`](handoff/2026-08-26-track-2-start.md).

## Purpose

Ingest OAI-PMH records from every registered upgrade project into a local
`aggregated_records` store, so brasil-archives has real record-level data
available for future two-axis rescoring (Track 2.5 / Track 4) and cross-corpus
analysis. This track is a **data pipe only** — it changes no scores, adds no
UI, and runs no schedule.

## Scope (locked)

- **Option A** (harvest + store only). No rescoring in this track.
- **Hybrid storage** — raw OAI `<record>` XML blob + JSON `extracted` column
  produced by per-format extractors. Adding a companion with a new metadata
  format adds one extractor, not a schema migration.
- **On-demand only** — CLI + optional Flask admin trigger. No cron until the
  code has been run manually against prod at least once.
- **Federation contract v1** — consume `oai_pmh_base_url` and (fallback)
  `oai_dc_export_url` fields already on `upgrade_projects`.
- **Metadata formats** — `oai_dc` (required) and `oai_ead` (used by mipibu).
  Adding a new prefix means adding a new extractor module.

## Non-scope (explicitly excluded)

- Any change to Pipeline or Research axis values, or to their 4-4 partition
  (ADR-0001-protected — needs a supersession, not a track).
- Cron / scheduled harvest.
- IIIF Content Search fanout.
- Extraction of mipibu's `app/oai/` into a reusable package (that's Track 3's
  trigger).
- UI surface for `aggregated_records`. Track 2 is a data pipe with no views.

## Data model

Three new tables, one migration.

### `aggregated_records`

One row per unique `(upgrade_project, oai_identifier, metadata_prefix)`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `upgrade_project_id` | int FK → `upgrade_projects.id` | cascade delete |
| `oai_identifier` | str | e.g. `oai:mipibu.from-bottom-to.top:case:SJM-0001` |
| `metadata_prefix` | str | `oai_dc` \| `oai_ead` |
| `datestamp` | str | `YYYY-MM-DD` from the OAI header |
| `set_specs_json` | JSON text | list[str] of setSpecs from the record header |
| `raw_xml` | text | the `<record>` element serialized verbatim |
| `raw_xml_sha256` | str(64) | for change detection |
| `extracted_json` | JSON text | output of the format-specific extractor |
| `harvest_run_id` | int FK → `harvest_runs.id` | last run that touched this row |
| `first_seen_at` | datetime | set on insert, never changed |
| `last_seen_at` | datetime | updated on every successful re-observation |

Constraints:

- `UNIQUE(upgrade_project_id, oai_identifier, metadata_prefix)`
- Index on `(upgrade_project_id, datestamp)` for incremental `from` filters
- Index on `raw_xml_sha256` for future dedup analytics

### `harvest_runs`

One row per invocation of `harvest_upgrade_project(...)`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `upgrade_project_id` | int FK | |
| `metadata_prefix` | str | |
| `started_at` | datetime | server clock |
| `finished_at` | datetime nullable | null while running |
| `status` | str | `running` \| `ok` \| `partial` \| `failed` |
| `records_seen` | int | rows the endpoint returned |
| `records_upserted` | int | rows inserted or updated |
| `records_unchanged` | int | rows whose sha256 already matched |
| `error_count` | int | count of rows in `harvest_errors` for this run |
| `from_ts` | str nullable | `--since` argument, if any |
| `until_ts` | str nullable | `--until` argument, if any |
| `source` | str | `oai_pmh` \| `static_export` |
| `notes` | text nullable | debug / operator notes |

### `harvest_errors`

One row per per-record failure. A single failed record does **not** abort
the run — it's logged and the run continues. HTTP-level failures (timeouts,
5xx) do abort the run with `status='failed'` and no error rows.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `harvest_run_id` | int FK | |
| `phase` | str | `parse` \| `extract` \| `upsert` |
| `oai_identifier` | str nullable | may be missing if XML failed to parse |
| `message` | text | exception string |
| `xml_excerpt` | text nullable | first 2000 chars of the offending element |

## Module layout

```
app/services/
  oai_client.py            # HTTP + XML parsing; no DB
  oai_extractors/
    __init__.py            # registry: {'oai_dc': extract, 'oai_ead': extract}
    oai_dc.py              # <oai_dc:dc> Element → dict
    oai_ead.py             # <ead>       Element → dict
  harvest.py               # DB orchestration; imports oai_client + extractors

app/models/
  aggregated_record.py
  harvest_run.py
  harvest_error.py

scripts/
  harvest.py               # CLI entrypoint

tests/
  harvest/
    test_oai_client.py     # mock HTTP; resumption; error mapping
    test_extractors_dc.py  # golden DC fragments
    test_extractors_ead.py # golden EAD fragments
    test_harvest.py        # integration with in-memory SQLite
    test_live_mipibu.py    # opt-in via BRASIL_ARCHIVES_LIVE=1
```

## OAI-PMH client contract

Public surface, all pure functions returning parsed XML elements + typed
dataclasses:

```python
def identify(base_url: str) -> IdentifyResult: ...

def list_records(
    base_url: str,
    metadata_prefix: str,
    from_: str | None = None,
    until: str | None = None,
    resumption_token: str | None = None,
) -> ListRecordsPage: ...

def iterate_records(
    base_url: str,
    metadata_prefix: str,
    from_: str | None = None,
    until: str | None = None,
) -> Iterator[Element]:
    """Handle resumption tokens transparently. Yields each <record> Element."""
```

Constants (imitates `app/services/federation.py`):

- `HTTP_TIMEOUT_SECONDS = 30` (harvester is not on the page-load path; can be patient)
- `USER_AGENT = "brasil-archives/harvester (+https://github.com/stevewil/brasil-archives)"`

Errors mapped from OAI `<error code="X">` responses to Python exceptions:

- `badVerb`, `badArgument` → `OaiProtocolError`
- `cannotDisseminateFormat`, `noSetHierarchy` → `OaiUnsupportedError`
- `noRecordsMatch` → **empty iterator**, not an exception (empty result is a
  legitimate query outcome, not a failure)
- `badResumptionToken` → `OaiResumptionError` (aborts the run — token
  state is inconsistent with the server)
- Any non-2xx HTTP → `OaiHTTPError`

## Extractor contract

```python
# app/services/oai_extractors/oai_dc.py
def extract(dc_element: Element) -> dict: ...
```

Both extractors return dicts that share a small common envelope:

```python
{
  "canonical": {
    "title": str | None,
    "date": str | None,       # earliest human-readable date
    "year_start": int | None,
    "year_end": int | None,
    "language": str | None,
    "rights": str | None,
    "identifiers": [str, ...],
    "urls": [str, ...],
  },
  "raw": {                    # format-specific verbatim capture
    ...                       # DC: {element: [values...]} for all 15 DC elements
                              # EAD: nested dict mirroring c01/c02/c03
  }
}
```

The `canonical` block is what Track 2.5's rescoring will consume. The `raw`
block is escape-hatch for signals nobody has thought of yet. Both are
JSON-safe.

## Harvest runner contract

```python
@dataclass
class HarvestSummary:
    run_id: int
    project_slug: str
    metadata_prefix: str
    status: str                 # running | ok | partial | failed
    records_seen: int
    records_upserted: int
    records_unchanged: int
    error_count: int
    duration_seconds: float

def harvest_upgrade_project(
    slug: str,
    metadata_prefix: str = "oai_dc",
    since: str | None = None,
    until: str | None = None,
    dry_run: bool = False,
) -> HarvestSummary: ...
```

**Upsert logic** (idempotent):

1. Compute `sha256(raw_xml)` on the incoming record.
2. Look up existing row by `(upgrade_project_id, oai_identifier, metadata_prefix)`.
3. If no row exists → INSERT, count as `records_upserted`, set `first_seen_at = last_seen_at = now`.
4. If row exists and `raw_xml_sha256` matches → UPDATE only `last_seen_at`,
   count as `records_unchanged`.
5. If row exists and sha256 differs → UPDATE `raw_xml`, `raw_xml_sha256`,
   `extracted_json`, `datestamp`, `set_specs_json`, `last_seen_at`,
   `harvest_run_id`; keep `first_seen_at`. Count as `records_upserted`.

Records not seen in the current harvest are **not** deleted or flagged.
Deletions are out of scope for Track 2; they will land whenever we add
OAI `deletedRecord` support (mipibu currently declares `deletedRecord=no`).

**Dry run** short-circuits at step 3: no INSERT/UPDATE fires and no
`harvest_run` / `harvest_error` rows are written. The returned
`HarvestSummary` still reports what would have happened.

## CLI

```
python scripts/harvest.py --list
python scripts/harvest.py --project mipibu
python scripts/harvest.py --project mipibu --format oai_ead
python scripts/harvest.py --project mipibu --since 2026-08-01
python scripts/harvest.py --project mipibu --dry-run
python scripts/harvest.py --project mipibu --format oai_ead --since 2026-08-01
```

Exit codes:

- `0` — run completed with `status='ok'`
- `1` — run completed with `status='partial'` (some `harvest_errors` rows)
- `2` — run aborted with `status='failed'` (HTTP or resumption error)
- `64` — usage error (bad arg, unknown project)

## Static-export fallback

If a project has `oai_pmh_base_url IS NULL` but `oai_dc_export_url IS NOT NULL`,
the harvester fetches that URL once (single GET, no resumption), iterates
`<record>` elements from the returned XML, and treats it as a single-page
`ListRecords` response. `harvest_runs.source` is set to `static_export`.

## Testing plan

1. **Unit — client:**
   - Mock HTTP returning canned two-page `ListRecords` responses with a
     resumption token connecting them. Assert `iterate_records` yields all
     records from both pages.
   - Feed error envelopes and assert the correct exceptions.

2. **Unit — extractors:**
   - Golden fragments checked in at `tests/harvest/fixtures/`.
   - One DC fragment covering all 15 elements, one EAD fragment with
     `c01/c02/c03/dao`.
   - Assert canonical + raw dicts have the expected shape.

3. **Integration — harvester + SQLite:**
   - In-memory SQLite via existing fixture pattern.
   - Feed the client mocked-HTTP responses and run
     `harvest_upgrade_project('mipibu')`.
   - Assert `aggregated_records` count matches, `harvest_runs.status='ok'`.
   - Re-run without changing fixtures → `records_unchanged` == total.
   - Change one fixture → next run reports 1 upsert, N-1 unchanged.

4. **Live — opt-in:**
   - `tests/harvest/test_live_mipibu.py` skipped unless
     `BRASIL_ARCHIVES_LIVE=1`.
   - Runs the real harvester against `https://mipibu.from-bottom-to.top/oai`
     and asserts we get 508 case records + 1 fonds record for `oai_dc`.

## Config nits (fixed alongside)

`configs/upgrade_projects/mipibu.yaml`:

- `oai_pmh_base_url` → `https://mipibu.from-bottom-to.top/oai`
- `supported_metadata_formats` → `[oai_dc, oai_ead]`

Reload with `PYTHONPATH=. python scripts/load_upgrade_projects.py` after edit.

## Open questions (deferred, not blockers)

- **Deletions:** mipibu's `deletedRecord=no` today. When a companion switches
  to `persistent` or `transient` and starts emitting `<header status="deleted">`,
  we'll need a `deleted_at` column and matching upsert logic. Not in Track 2.
- **Rate limiting:** none in Track 2. If a companion imposes one we'll add
  a simple sleep between resumption fetches. Log rate-limit responses to
  `harvest_errors` when they happen.
- **Metrics:** `harvest_runs` is the audit trail. If we want Prometheus /
  Datadog metrics later, they can be derived from that table without a
  schema change.
