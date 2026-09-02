# Handoff — corpus-explorers monorepo: povos + mipibu LIVE on Postgres; jornais next

*Session 2026-09-02 (long). Supersedes
`2026-09-02-corpus-explorers-monorepo.md` (that doc froze ~mid-session,
before the PG transition was executed). Nearly all code lives in the new
repo **`github.com/stevewil/corpus-explorers`** (private) / local
`c:\DEV\corpus-explorers`. In `brasil-archives` this session: doc updates
only.*

---

## TL;DR

The "partner corpus explorer" family (mipibu, povos, …) is now a **monorepo**
with a **PostgreSQL** system of record. Both existing partners are
**migrated and live in production on PG**. The forge's crawler exists and
**jornais-digitalizados is enumerated** (39k page images). Next: build the
jornais catalog explorer; OCR is deliberately deferred.

**On resume:** jump to **§5 (jornais plan)**. Everything before it is
finished-state reference.

---

## 1. What is live

| | povos-indigenas-rn | mipibu |
|---|---|---|
| URL | `https://povos-indigenas-rn.from-bottom-to.top` | `https://mipibu.from-bottom-to.top` |
| corpus_version (digest) | `3af9138033e7f36d…` | `dd6a21d506182183…` |
| records | 40 documents | 508 cases |
| cPanel PG database | `fromuagq_povos_indigenas_rn` | `fromuagq_mipibu` |
| app tests (on PG) | 148 green | 41 green |

Both serve the read-only `corpus` schema of their cPanel Postgres DB via the
`<db>_ro` role. **No SQLite in the request path.** The old
`sao-jose-mipibu-audit.db` / `povos_rn.db` are retired.

### Deploy mechanics (cPanel, user `fromuagq`)

- App code: **one clone of the monorepo** at `~/flask/corpus-explorers`
  (`git pull origin main` to update).
- Routing: each domain's `~/domains/<domain>/.htaccess` has
  `PassengerAppRoot "/home/fromuagq/flask/corpus-explorers/partners/<slug>"`
  + `PassengerPython ".../virtualenv/flask/<slug>/3.13/bin/python"`.
- Restart: `touch ~/flask/corpus-explorers/partners/<slug>/tmp/restart.txt`.
- Config: a `.env` file in each partner dir (python-dotenv) with
  `CORPUS_DATABASE_URL` (the `_ro` DSN) + `CORPUS_SCHEMA=corpus`. **Not**
  cPanel's Setup-Python-App env UI — `PassengerApps list_applications` is
  empty; these apps predate/bypass it.
- Shared packages imported via `sys.path` (passenger_wsgi.py + conftest.py
  add `../../packages/{explorer-core,corpus-toolkit}`) — no editable install.
- **Rollback:** each domain has `.htaccess.bak-presql`. Restore it +
  `touch ~/flask/<slug>/tmp/restart.txt` → back on SQLite.

### The cutover was done programmatically

I have SSH as `fromuagq` and `uapi` works. Per partner:
`uapi Postgresql create_database` / `create_user` ×2 / `grant_all_privileges`;
`ALTER ROLE <ro> SET default_transaction_read_only=on` (+ search_path,
timeouts); `scp` the `pg_dump` artifact; `pg_restore --no-owner` as `_o`;
grant `_ro`; apply `corpus-views.sql`; repoint `.htaccess`; restart; verify.

### Passwords (Proton Pass)

- **povos corpus PG — owner** `fromuagq_povos_indigenas_rn_o` : `JNPMyY4fgpxYQgzJjCNiNGNBqqUY`
- **povos corpus PG — app read-only** `fromuagq_povos_indigenas_rn_ro` : `qC8j3QMnumOua5ClzlbXKbA3Z3As`
- **mipibu corpus PG — owner** `fromuagq_mipibu_o` : `IwnEShgAZUJIUyyoCNgmBQoHqSj6`
- **mipibu corpus PG — app read-only** `fromuagq_mipibu_ro` : `lWy4H8IDrRPNfv6pe8XmGAeH8kt7`

*(The `_ro` values also sit in `~/flask/corpus-explorers/partners/<slug>/.env`
on the box. Rotate with `uapi Postgresql set_password`.)*

---

## 2. The monorepo

```
packages/
  corpus-toolkit/   v0.2.0 — build/validate/freeze the corpus PG schema; load_sqlite
  explorer-core/    v0.1.0 — read-only psycopg DB layer + FTS + corpus_meta health + config base
  corpus-build/     v0.0.1 — the forge's crawler (jornais enumeration; more to come)
partners/
  mipibu/                 LIVE on PG
  povos-indigenas-rn/     LIVE on PG   (dir renamed from povos-rn to match the slug)
  jornais-digitalizados/  enumerated; app not built
docs/
  POSTGRES.md        the normative PG rules (17 sections)
  POSTGRES-PLAN.md   the 8-step transition sequence (temporal; retire at step 8)
  MONOREPO.md        topology + migration status
scripts/dev/         docker-compose postgres:10 (:5434); create-corpus-db.sh;
                     corpus-db-bootstrap.sql; db-tunnel.sh; dump/pull/deploy-corpus.sh;
                     cpanel-pg-probe.sql
```

Local dev: `docker compose up -d db` (postgres:10 on :5434) →
`scripts/dev/create-corpus-db.sh <slug>` → work against
`postgresql://postgres:postgres@localhost:5434/<slug>`. Monorepo venv at
`c:\DEV\corpus-explorers\.venv`.

### corpus-toolkit v0.2.0

`create_corpus_schema(dsn, manifest)` · `validate_corpus_schema(dsn[,manifest])`
· `freeze_corpus(dsn, manifest)` (populate `search_tsv`, GIN, digest, stamp
`corpus_meta`) · `compute_content_digest(dsn)` · `load_sqlite(sqlite, dsn, manifest)`.
Manifest v0.1 (JSON, PG types). CLI `python -m corpus_toolkit {create-schema,
validate,freeze,digest,load-sqlite}`. 17 tests on postgres:10.
Contract version **2.0**; `fts.populate_sql` added for cross-table search
indexes (mipibu's `fts_case_metadata` spanned 3 tables).

### explorer-core v0.1.0

`explorer_core.db` (per-request RO connection, `query_all`/`query_one`/
`scalar`/`has_table`/`has_column`) · `explorer_core.search`
(`to_tsquery_arg` + `search_ids` ranked by `ts_rank_cd`) · `explorer_core.health`
(`corpus_meta`/`corpus_version`) · `explorer_core.config` (`CorpusExplorerConfig`).
17 tests.

---

## 3. Key architecture decisions (this session)

- **DB-per-corpus, two schemas.** `build` (harness workspace, local/runner
  only) + `corpus` (frozen, read-only role, `corpus_meta.content_digest` =
  version). POSTGRES.md §2, §7.
- **No `unaccent` extension.** The Namecheap server ships PostgreSQL 10.23
  with **no contrib** (probed: `pg_available_extensions` empty for unaccent/
  pg_trgm/citext; a cPanel user can't `CREATE EXTENSION`). Accent-insensitive
  search uses a pure-SQL `IMMUTABLE` `corpus.immutable_unaccent(text)`
  (`translate()` over ~24 Portuguese accented letters) + the built-in
  `simple` config + `:*` prefix terms — behaviourally identical to the old
  FTS5 `remove_diacritics 2` + `"term"*`. No stemmer.
- **cPanel probe results:** `CREATE SCHEMA` / `GRANT` / `REVOKE` /
  `ALTER DEFAULT PRIVILEGES` / `ALTER ROLE <self> SET` all work.
  `CREATE ROLE` / `CREATE EXTENSION` denied (neither needed).
- **cPanel = Namecheap Stellar Plus:** unlimited DBs/users; **300k inodes
  account-wide** and **2 GB RAM** are binding → nothing writes one-file-per-
  item on the box; index builds happen in the build tier and ship inside
  `pg_dump`; jornais page text will go to Wasabi. POSTGRES.md §12.
- **contract-db-contract.md is NOT rewritten to v2** — POSTGRES.md is the
  interim normative source; the doc has a banner. A v2 rewrite is deferred.

---

## 4. Cleanup still pending (Phase 4 — after both have been stable a few days)

- cPanel: `rm -rf ~/flask/povos-indigenas-rn ~/flask/mipibu ~/povos-indigenas-rn`
  (the old SQLite checkouts; reclaims inodes — home is ~224k/300k).
  Then remove each domain's `.htaccess.bak-presql`.
- GitHub: archive `stevewil/povos-indigenas-rn` and `stevewil/mipibu`
  (read-only, for history).
- Local: retire `c:\DEV\mipibu` and `c:\DEV\povos-indigenas-rn`
  (migrated source is now under `corpus-explorers/partners/`).
- MONOREPO.md migration table → mark cleanup done.
- brasil-archives catalog still has a dev-only SQLite fallback in
  `scripts/load_*` — **out of scope** (separate concern, prod is PG).

---

## 5. Jornais-digitalizados — the resume plan

**Slug:** `jornais-digitalizados`. **Catalog `archives` row already exists**
in brasil-archives: `rn-biblioteca-central-zila-mamede-bczm-ufrn-jornais-digitalizad-t1r3`.

### What's done (session 1 — committed)

- `packages/corpus-build` v0.0.1: `build_schema` (crawl_nodes + page_images +
  build_events), `crawl.enumerate_source()` (polite, resumable
  Apache-`mod_autoindex` walker), `parse_filename.parse()`, CLI
  `python -m corpus_build {enumerate,report}`.
- `partners/jornais-digitalizados/docs/rights-and-provenance.md` — the
  fair-use gate: **no robots.txt** (404); open autoindex, no auth/rate
  limit; titles **1877–1952 all public domain by age**; **TRIBUNA DO NORTE
  excluded** (library-gated at `tribuna_restrito`); OCR text + images to
  Wasabi, only metadata + `search_tsv` in PG.
- **Enumeration complete** into the local `jornais_digitalizados` DB's
  `build` schema:
  - **39,112 page images**, **~27 GB**, **94% filename-parsed** (36,603 with
    title/issue/date/page)
  - **67 newspaper titles** (14 top-level + ~53 under "Jornais Diversos"),
    **1862–1952**
  - 198 dirs listed, 2 skipped (TRIBUNA), **1 transient SSL error** — the
    `Jornais Diversos/A PALAVRA/` dir (re-run `python -m corpus_build
    enumerate` to retry; it's resumable).
- Filenames: `<FRAME>.<SEQ> - <TITLE> ano<N>, n.<ISSUE>, <DATE>,p.<PAGE>.png`
  — the structure is IN the filenames, so this is closer to "assembly +
  light OCR" than pure OCR-first. Files are **PNG page images** (~500–850 KB
  each), not PDFs as the survey said. Some year dirs also have a `.pdf`
  (bound year) and `.txt` (a stale image-name manifest — **not** OCR).

### Session 2 — catalog-only explorer (NO OCR)

Goal: a browsable finding aid for 67 RN newspapers, each page linking to its
BCZM scan, before spending anything on download/OCR. Steps:

1. **`corpus-build` project step** — group `build.page_images` into
   `newspaper_title` → `newspaper_issue` (key: title + ano + issue_number +
   date) → `page`, into a `build.candidate_*` set, with a `source_assertions`
   row per derived value (`evidence_type='file_inspection'`,
   `method='filename_parse'`). Flag unparseable images
   `inclusion_status='flagged_unverified'`.
2. **`partners/jornais-digitalizados/jornais-digitalizados.manifest.json`** —
   entity kinds `newspaper_title` (reference), `newspaper_issue` (primary,
   in_scope=inclusion_status), `page` (child). `page.search_tsv` +
   `page.ocr_text_wasabi_key` + `page.ocr_engine` + `page.ocr_confidence`
   **declared but left NULL** — filled by the later OCR pass via re-freeze.
   `page.image_bczm_url` is the link to the scan.
3. **`create_corpus_schema` + project→corpus load + `freeze`** —
   catalog-only `corpus` schema (issue/page metadata, no page text). New
   digest.
4. **Minimal explorer app** `partners/jornais-digitalizados/app/` on
   `explorer_core` — browse title → year → issue → page (thumbnail/link to
   BCZM); search issue-level metadata (title, date, masthead terms parsed
   from p.1 filenames). Reuse the mipibu/povos app skeleton (factory,
   config, db shim, i18n, templates).
5. **Deploy** — `uapi Postgresql create_database` etc. (same playbook);
   `jornais-digitalizados.from-bottom-to.top` (confirm the domain exists in
   cPanel first — it may need creating).

### OCR — DEFERRED. Only confirmation-testing for now.

Steve's call: **hold OCR**. When we do touch it, first run a **small
confirmation sample** (the mipibu phase-1 sampling pattern — a
`sampled_phase1`-style flag): OCR ~20–40 pages spanning the date range and
the print-quality spread, record per-page confidence + a legibility grade,
and eyeball the output. This is **calibration input for the archive's score**
(is this corpus OCR-tractable? what quality tier?), not a production pass.

The full OCR pass (later, its own decision) needs:
- **build-tier host** — dev box vs a cloud spot VM for the 27 GB download +
  ~35k-page OCR;
- **OCR engine** — Tesseract (local, free, rough on 1880s newsprint) vs a
  cloud vision API (~$50 for the corpus, much better on degraded scans).
- Then: download images → Wasabi (content-addressed), OCR → `build`,
  re-`freeze` (populates `page.search_tsv` from the OCR text, ships the text
  to Wasabi, new digest), re-deploy.

### Testing regime / score calibration (Steve flagged this)

Set up a **repeatable OCR-quality test harness** as part of the score model:
sample N pages stratified by decade + source title + visual condition; run
the candidate engine(s); score against a small hand-keyed ground-truth set
(CER/WER); feed the result into the archive's "pipeline-viability" /
research-axis score in brasil-archives. This makes "can we OCR archive X"
a measured input rather than a guess — useful for triaging archives #4+ too.

---

## 6. Other deferred work

- **`explorer-core` v0.2** — today it's only the data layer. Each partner
  still carries its own near-identical OAI-PMH provider, federation-v1 JSON
  adapter, presenters, params, i18n, Flask factory, templates. Extracting
  those into `explorer-core` (partner = manifest + queries + branding) is
  the real remaining consolidation. **Spec it after jornais's app exists**
  as the third data point (rule of three).
- **contract-db-contract.md v2** — full Postgres rewrite (POSTGRES.md is the
  interim source of truth).
- **`partner_builds` table** in the brasil-archives catalog (harness §7) —
  the forge control-plane state. Not started.
- **Wasabi `corpus/` prefix** — `dump-corpus.sh` uploads there when
  `WASABI_BUCKET` is set; not wired to real creds yet (deploys used `scp`
  direct). Set up a corpus-scoped Wasabi key + lifecycle when jornais needs
  it.

---

## 7. Carried forward — Steve's console tasks (unchanged from prior handoffs)

1. Proton Pass — cPanel prod creds, Wasabi backup key (+ now the 4 corpus PG
   passwords in §1).
2. Wasabi console — bucket lifecycle rule to expire `pg/` after ~90d.
3. Portfolio — mpa/ajme off the leaked `MMR…` Wasabi root key; delete root
   keys; TOTP MFA on root.
