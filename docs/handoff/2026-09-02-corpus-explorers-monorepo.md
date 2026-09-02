# Handoff — corpus-explorers monorepo + corpus-toolkit v0.1.0 + the Postgres pivot

*Session 2026-09-02 (continued from `2026-09-02-partner-forge-and-harness.md`).
Most of the work landed in a **new repo**, `c:\DEV\corpus-explorers`. In this
repo: docs only (contract v1.1 relax → then superseded, harness-doc updates,
this file).*

> **Late-session pivot — read `corpus-explorers/docs/POSTGRES-PLAN.md` first.**
> After `corpus-toolkit` v0.1.0 (SQLite) shipped, Steve decided the corpus
> **system of record moves to PostgreSQL** — SQLite retired everywhere,
> mipibu and povos included. Hosting mirrors the brasil-archives catalog
> (cPanel-local PG 10 prod, `postgres:10` Docker for dev). §§ below marked
> **[pre-pivot]** describe what shipped; the plan going forward is
> POSTGRES-PLAN.md. The backbone table shapes, manifest v0, and contract
> v1.1 conformance levels all carry over — only the SQLite dialect,
> FTS5, `.sha256` sidecar, and file distribution are obsolete.

---

## TL;DR

Picked up the resume task ("implement `create_corpus_db` + `validate_corpus_db`").
Two direction decisions changed the shape first:

1. **Monorepo, not per-partner repos.** New repo `corpus-explorers` holds the
   build tooling, the (future) shared explorer engine, and every partner
   instance. Supersedes the "independent monolith + hand off" model.
   Rationale + migration status: `corpus-explorers/docs/MONOREPO.md`.
2. **mipibu + povos migrate in now** — source vendored under
   `partners/mipibu/` and `partners/povos-rn/` (no `.git`/`.venv`/`.env`/`data`).
   The originals at `c:\DEV\mipibu` and `c:\DEV\povos-indigenas-rn` stay the
   **deployed** source of truth until `explorer-core` is extracted.

Then built **`corpus-toolkit` v0.1.0** and shipped it.

**Resume here:** `explorer-core` extraction is blocked on a third real corpus
→ start `jornais-digitalizados` (OCR-first). Or: build
`packages/corpus-build` (crawl/extract/OCR). See §4.

---

## What shipped

### New repo: `c:\DEV\corpus-explorers` (git init'd, 2 commits, not pushed)

```
packages/corpus-toolkit/      v0.1.0 — DONE (see below)
packages/explorer-core/       README placeholder — extracted after N=3
partners/mipibu/              vendored source (80 files)
partners/povos-rn/            vendored source (105 files)
partners/jornais-digitalizados/  README — the build target
docs/MONOREPO.md              topology + what changed + migration table
LICENSE (MIT), README, .gitignore, .gitattributes
```

Not pushed — **no GitHub remote yet**. Create `corpus-explorers` (private or
public — code is MIT, no secrets vendored; confirmed by scan) and push.

### `corpus-toolkit` v0.1.0

`sqlite3` + stdlib only (runs in a bare partner build env). `corpus_toolkit/`:

| module | what |
|---|---|
| `contract.py` | backbone DDL + constants, contract **v1.1** |
| `manifest.py` | manifest v0 loader + structural validation (dataclasses, JSON) |
| `create.py` | `create_corpus_db(path, manifest)` — backbone + entity/`fts_<kind>` tables + placeholder terms + `schema_version`/`migrations` rows |
| `validate.py` | `validate_corpus_db(path[, manifest])` — `Report` of `Finding(level, check, detail)`; manifest-free + manifest modes |
| `freeze.py` | `write_sidecar(path)` — the `.sha256` |
| `__main__.py` | `python -m corpus_toolkit {create,validate,freeze}` |

- **18 tests pass** (`packages/corpus-toolkit/tests/test_corpus_db.py`). Run:
  `cd packages/corpus-toolkit && pytest` (needs `pytest`; used the
  brasil-archives `.venv` python this session).
- **DoD met:** `python -m corpus_toolkit validate <path>` runs clean against
  (a) a freshly-created corpus, (b) `povos_rn.db`, (c)
  `sao-jose-mipibu-audit.db` — both real corpora pass **manifest-free** with
  warnings only.
- `examples/povos-rn.manifest.json` — illustrative; round-trips
  (create → validate) clean. **Not** an exact description of the hand-built
  `povos_rn.db` (column names differ), so manifest-*mode* validation of the
  real file is not expected to pass — that's fine.
- `docs/manifest-v0.md` — the annotated manifest reference.

---

## Contract v1.1 (this repo: `docs/corpus-db-contract.md`)

Building the validator showed **neither reference corpus satisfied v1's
`MUST` set** — v1 had resolved mipibu/povos divergences toward povos, but
both DDLs were already frozen. Per Steve's call ("relax contract to
reality"), the following v1 `MUST`s became `SHOULD` (validator warns), each
flagged `[v1.1: was MUST]` inline + full list in §11 change log:

- `audit_events.http_status` (povos omits)
- `repositories.robots_notes` + `custodian_of_originals_original` (povos omits);
  `rights_statement_original` **stays a hard MUST** (non-NULL per row)
- `controlled_terms.is_placeholder` col + placeholder-per-vocab; bilingual
  `definition_pt/_en` (mipibu omits)
- `source_assertions.evidence_type` CHECK contents no longer pinned
- coverage rule → SHOULD outside freeze, MUST at freeze
- `*_normalized` → `controlled_terms` FK required only for manifest-`controlled` columns
- in-scope mechanism → `primary` kinds only, not every table
- non-zero `schema_version` value → SHOULD (povos ships empty table)
- `.sha256` sidecar → MUST for frozen/distributed; warn on working DB, fail `--frozen`

Intent of v1 unchanged — meeting every SHOULD is still the target.

Also updated `docs/archive-research-harness.md`: operating-model note (→
monorepo), §4.1 (C6 DONE), C6/C8 inventory rows, §7 build-workspace row
(→ **dedicated Postgres instance** — Steve's "separate Postgres instance";
provisioning TBD), §8 Q1 resolved.

---

## 4. Resume plan — the Postgres transition (`corpus-explorers/docs/POSTGRES-PLAN.md`)

Order decided this session:

1. **Docker + cPanel scaffolding** — `docker-compose.yml` (`postgres:10`),
   `.env.example`, `scripts/dev/` mirroring `brasil-archives/scripts/dev/`;
   create the per-corpus cPanel databases + read-only roles.
2. **contract v2** — rewrite `docs/corpus-db-contract.md` Postgres-native
   (banner at its top lists the deltas).
3. **corpus-toolkit → PG** — `create_corpus_schema` / `validate_corpus_schema`
   / `freeze_corpus` / `load_sqlite`; port the 18 tests to `postgres:10`.
4. **explorer-core DB + FTS + search layer** — extracted now (the migration
   forces it): PG read-only connection layer, `portuguese_unaccent` search.
5. **Migrate povos** end to end (`load_sqlite` → wire app → port FTS →
   deploy). Simplest, proves the stack.
6. **Migrate mipibu.**
7. **`jornais-digitalizados`** — first forge-built corpus, native PG.
8. **Delete SQLite** — `.db` files, `sqlite3` imports, FTS5, `sync-corpus.sh`.

Plus, any time: **push `corpus-explorers`** to a new GitHub remote (2 local
commits, no remote).

Open items in POSTGRES-PLAN.md §"Open items": cPanel DB-count + disk-quota
check; `portuguese` vs `simple` stemmer; build-tier host for jornais OCR.

---

## 5. Still Steve's console tasks only (unchanged, carried from prior handoff)

1. Proton Pass — 2 records (cPanel prod creds, Wasabi backup key).
2. Wasabi console — bucket lifecycle rule to expire `pg/` after ~90d.
3. Portfolio — mpa/ajme off the leaked `MMR…` Wasabi root key; delete root
   keys; TOTP MFA on root.
