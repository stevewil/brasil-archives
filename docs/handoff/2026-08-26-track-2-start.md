# Handoff — Phase 3 Track 2 kickoff

**Date:** 2026-08-26
**Author:** agent session
**Status:** Track 1 shipped and verified live. Track 2 designed but no code written yet. Safe to reboot.

## Where we are

**Phase 3 progress:**

- ✅ **Track 1 — OAI-PMH endpoint on mipibu.** Live at `https://mipibu.from-bottom-to.top/oai`.
  - Supports `oai_dc` + `oai_ead` metadata formats.
  - 508 case records + ~5000 document records + 1 synthetic fonds record harvestable.
  - 189 setSpecs (top-level + 29 case_types + nested decades).
  - Resumption tokens work (page size 100, stateless base64url JSON).
  - Error handling verified (`badVerb`, `badArgument`, `cannotDisseminateFormat`, `idDoesNotExist`, `noRecordsMatch`).
  - Verifier: `bash scripts/verify_oai_live.sh` in the mipibu repo — 10/10 OK on last run.
  - Commits: `9d9ed99` (blueprint + tests + design doc), `3e00a55` (verify script).

- 🔄 **Track 2 — aggregated-records store in brasil-archives.** Scope locked, design chosen, zero code written. Details below.

- ⬜ **Track 3 — povos-indigenas-rn corpus explorer.** Not started. Will trigger extraction of `app/oai/` into a reusable package.

## Track 2 — locked design decisions

Confirmed with user this session ("Lets go with your recs"):

1. **Scope = Option A: harvest + store only.** No rescoring in this track. Rescoring becomes a separate Track 2.5 or Track 4.
2. **Storage = hybrid.** Raw OAI `<record>` XML blob + JSON `extracted` column produced by per-format extractors. New companion adds one extractor, no schema migration.
3. **Execution = on-demand only.** CLI + optional Flask admin trigger. No cron in this track. We validate the code before letting cron touch prod.

## Track 2 — plan (in order)

1. **Design doc** at `docs/harvest-design.md`
2. **OAI-PMH client** in `app/services/oai_client.py`
   - Verbs used: `Identify` (once at start for `earliestDatestamp`), `ListRecords` with resumption
   - Args: `metadataPrefix`, optional `from` / `until` (both `YYYY-MM-DD`)
   - Reuses HTTP style from existing `app/services/federation.py` (urllib, 8s timeout, UA string)
   - Parses OAI-PMH XML with `xml.etree.ElementTree`; raises on `<error code=...>`
3. **DB models + Alembic migration** — new tables:
   - `aggregated_records(id, upgrade_project_id, oai_identifier, datestamp, metadata_prefix, set_specs_json, raw_xml, extracted_json, harvest_run_id, first_seen_at, last_seen_at)`
     - unique `(upgrade_project_id, oai_identifier, metadata_prefix)`
     - index on `datestamp` for incremental `from` filters
   - `harvest_runs(id, upgrade_project_id, metadata_prefix, started_at, finished_at, status, records_seen, records_upserted, records_unchanged, error_count, from_ts, until_ts)`
   - `harvest_errors(id, harvest_run_id, phase, oai_identifier, message, xml_excerpt)`
4. **Extractors** at `app/services/oai_extractors/{oai_dc.py, oai_ead.py}`
   - Each takes an `<oai_dc:dc>` or `<ead>` Element and returns a dict.
   - `oai_dc` → flatten all 15 DC elements to lists; also lift a canonical `title`, `date`, `year_start`, `year_end`.
   - `oai_ead` → walk the tree, extract `archdesc/did/*`, first `c02`'s `did/*`, and every `c03/did/dao/@href`. Preserve the level path.
   - Extractors are pure; no DB, no HTTP.
5. **Harvest runner** at `app/services/harvest.py`
   - Public entry: `harvest_upgrade_project(slug, metadata_prefix="oai_dc", since=None, dry_run=False) -> HarvestSummary`
   - Steps: create `harvest_run` row → `Identify` → paginate `ListRecords` → for each record: upsert into `aggregated_records`, record error rows for parse failures without aborting the whole run → close `harvest_run`.
   - Idempotent: unchanged records skip the update (compared by `datestamp` + sha256 of raw XML).
6. **CLI** at `scripts/harvest.py`
   - `python scripts/harvest.py --project mipibu`
   - `python scripts/harvest.py --project mipibu --format oai_ead`
   - `python scripts/harvest.py --project mipibu --since 2026-08-01`
   - `python scripts/harvest.py --project mipibu --dry-run` (fetch + parse, no writes)
   - `python scripts/harvest.py --list` (show registered projects with OAI URLs)
7. **Static-export fallback** — if `oai_pmh_base_url` is null but `oai_dc_export_url` is set, fetch the static XML once and iterate `<record>` elements from it. Skip resumption.
8. **Tests** at `tests/harvest/`:
   - Unit: extractor tests against golden XML fragments (steal from mipibu's `tests/fixtures/oai/` if any land, otherwise build minimal ones inline).
   - Integration: mock HTTP with a fixture that returns two `ListRecords` pages via resumption; assert the DB ends up with the expected rows.
   - Smoke: `@pytest.mark.live` test that actually hits mipibu — opt-in via env var so CI stays offline.
9. **Config nits to fix alongside Track 2:**
   - `configs/upgrade_projects/mipibu.yaml`:
     - `oai_pmh_base_url: https://mipibu.from-bottom-to.top/oai` (currently null)
     - `supported_metadata_formats: [oai_dc, oai_ead]` (currently `[oai_dc]` only)
   - Re-run `PYTHONPATH=. python scripts/load_upgrade_projects.py` locally after editing.

## Relevant existing code (already surveyed this session)

- `app/models/upgrade_project.py` — has `oai_pmh_base_url`, `ead_export_url`, `supported_metadata_formats`, `federation_contract_version` fields ready to consume.
- `app/models/federation_cache.py` — 15-min cache from Phase 2, uses `sha256((endpoint + '?' + sorted-normalized qs))` as `cache_key`. Not reused by the harvester (harvester is not on the page-load hot path), but establishes the persistence pattern.
- `app/services/federation.py` — Phase 2 JSON federation client. Style to imitate: urllib, 8s timeout, `USER_AGENT`, dataclasses, stateless service, DB is the only state.
- `configs/upgrade_projects/mipibu.yaml` — the registration file that will need the two edits above.
- `scripts/load_upgrade_projects.py` — upserts registrations. Idempotent (as of `778df05`).
- Migrations dir has 2 revisions so far: `68facc4f886d_initial_schema...` and `b0fd625449a7_add_federation_cache_table_and_json_api_...`. Track 2 will add a third.

## Resume checklist (after reboot)

When you come back, do this in order:

1. Confirm `cd /home/user/workspace/brasil-archives && git status` shows clean and on `main`.
2. Confirm `cd /home/user/workspace/mipibu && git log --oneline -3` shows `3e00a55` at HEAD (or newer if you push more).
3. Optional sanity check: `bash /home/user/workspace/mipibu/scripts/verify_oai_live.sh /tmp/oai-verify` should report `failures: 0`.
4. Tell the agent "resume Track 2" and it should read this file, restore the plan, and start with the `docs/harvest-design.md` write.

## What's NOT in Track 2

Explicitly deferred, do not scope-creep into this track:

- Rescoring / any change to Pipeline or Research axis values.
- Any change to the 4-4 axis partition (ADR-0001-protected).
- Cron/scheduled harvest.
- Extraction of mipibu's `app/oai/` into a reusable package (that's Track 3's trigger).
- IIIF Content Search fanout (that's a separate future track).
- Any UI surface for aggregated_records. Track 2 is a data pipe, no views.
