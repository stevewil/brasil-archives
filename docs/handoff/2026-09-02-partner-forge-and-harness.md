# Handoff — partner-forge direction + the research-harness spec

*Session 2026-09-01 (late) / 2026-09-02. All work is docs + one small code
fix. Nothing in `app/` changed. Tree clean, pushed to `main` at `2aae55d`.*

---

## TL;DR

Started as "resume from handoff" (the Postgres cutover — **done**, only
Steve's console tasks left, unchanged). Turned into a design session on
**how to build partner corpus explorers (mipibu / povos) as a repeatable,
agent-driven process**. Produced two new specs and updated one ops doc.

**Resume here:** implement `create_corpus_db` + `validate_corpus_db` per
[`../corpus-db-contract.md`](../corpus-db-contract.md) §9. See §5 below.

---

## What shipped this session

| commit | what |
|---|---|
| `984a164` | `docs/wasabi_iam_provisioning_architecture.md` → **v1.1.0**: §8 Field Notes from the real `srv-brasil-archives-backup` provisioning run; region map fixed (`us-west-2` + `ca-central-1`) in the doc **and** `scripts/ops/wasabi_provisioner.py` |
| `9e30bae` | `docs/archive-research-harness.md` — **new**. The full spec (see §3) |
| `2aae55d` | `docs/corpus-db-contract.md` — **new**, v1. The corpus-DB backbone made normative (see §4) |

`scripts/ops/wasabi_provisioner.py` is the only non-doc change: two lines
added to `WASABI_REGIONS`. `list-regions` verified.

---

## Project status (asked + answered this session)

**Still beta, not 1.0.** 1.0 for this project = the public bilingual site is
live **and** scores are trustworthy enough to publish (or a deliberate
decision to publish catalog + facets without scores). Neither has happened.

- **Infrastructure: production.** Postgres cutover complete + verified
  (cPanel-local PG 10.23; re-checked live this session — `/healthz` green,
  80 archives, both `src_` schemas, backup cron present). Not Supabase
  (deleted). Only Steve's console tasks remain — Proton Pass records,
  Wasabi bucket lifecycle rule, portfolio root-key retirement. See
  [`2026-09-01-supabase-cutover-in-progress.md`](2026-09-01-supabase-cutover-in-progress.md).
- **Catalog app: beta**, in daily internal use.
- **Scoring: alpha.** 21 of ~50 pipeline-viable archives scored; ADR-0002
  found the research axis not internally coherent (α 0.49); Pass 4
  unscheduled. This is the long pole to 1.0 and it's research, not
  engineering.
- **Steve's call: "Research first."** The partner-forge work below **is**
  research infrastructure, so it's aligned — but it's a large build and
  should fall out of doing one more partner by hand (§4 sequencing).

---

## The operating model (decided in discussion)

The plan for building partner corpus explorers #3+:

1. **brasil-archives is both the aggregator and the forge.** It triages
   catalog archives for "buildability", runs/dispatches a research agent,
   reviews the resulting corpus, **scaffolds the partner repo, and hands
   off.**
2. **After handoff the partner is an independent monolith.** The developer
   (Steve) opens it in VS Code and works there to public-view state.
   brasil-archives does not manage it.
3. **Build-time exchange is git + HTTP only** — never a shared DB. Steady
   state stays the periodic OAI-PMH harvest.
4. **The research agent's working data is its own database in the partner's
   build environment** — NOT the brasil-archives catalog DB. Reasons: don't
   pollute the just-won small/durable/backed-up catalog DB with tens of GB
   of OCR intermediate; per-corpus DDL doesn't belong in the catalog's
   Alembic history; "hand off and forget" = partner owns all its data.
5. **The catalog DB gains one small table** — `partner_builds` (metadata
   *about* builds: which archive, lifecycle stage, repo URL, corpus sha256,
   fair-use determination). Schema sketched in the harness doc §7.
6. **The forge admin** extends the read-only `/admin/` dashboard, behind the
   existing `ADMIN_UI_ENABLED` gate (never on the public host). The
   long-running mining worker can't run on cPanel — it runs on the dev box
   or a cloud runner.

**First target:** `jornais-digitalizados` (BCZM/UFRN, ~53k newspaper page
PDFs, open Apache directory listing, **no OCR, no metadata**). Catalog slug
`rn-biblioteca-central-zila-mamede-bczm-ufrn-jornais-digitalizad-t1r3`; the
`archives` row already exists (no povos-style bootstrap needed). Exercises
the **OCR-first** construction mode that neither existing partner does.

**Sequencing (harness doc §9):** don't build the general forge first. Build
`jornais-digitalizados` mostly by hand but instrumented — reuse mipibu/povos
patterns deliberately, write down every seam — then extract the harness from
**three** real corpora instead of two. Rule of three.

---

## 3. `docs/archive-research-harness.md` — what it says

- **§2–3 — what we know**, from a teardown of both repos at `main`:
  - three-layer anatomy (corpus DB / explorer app / federation surface),
    module-by-module table of copy-verbatim vs per-corpus
  - the **convergent corpus-DB backbone** — mipibu + povos independently
    landed on the same shape (now → `corpus-db-contract.md`)
  - `source_assertions` as the research-integrity model
  - **three corpus-construction modes**: A metadata-audit (mipibu),
    B assembly-from-catalogs (povos), C OCR-first (`jornais-digitalizados`)
- **§4 — 11 gaps** + 4 policy questions. Component inventory (§6) has 23
  rows tagged known / to-build / policy.
- **§5** — the 7-phase pipeline diagram (forge ↔ build env).
- **§7** — the three-store DB architecture + `partner_builds` sketch.
- **§8** — open questions (where `corpus_build` lives — leaning "in
  brasil-archives, copied into each partner at handoff"; whether the forge
  admin ships in the deployed app; corpus "done" criteria; manifest scope).
- **§9** — sequencing (above).

## 4. `docs/corpus-db-contract.md` — what it says

v1, extracted from the **live DDL** of `sao-jose-mipibu-audit.db` and
`povos_rn.db`. Normative for partner #3+.

- **§3 provenance backbone (MUST):** `source_assertions` (near-identical in
  both today — the contract), `audit_events`, `repositories` (with
  `rights_statement_original` + `robots_notes` — the fair-use gate's
  evidence). Coverage rule: every non-verbatim value has an assertion row.
- **§4 `controlled_terms`** — bilingual `definition_pt`/`_en`; every vocab
  MUST have a placeholder term (never guess to avoid a NULL).
- **§5 entity conventions** — `<kind>_id` PKs, `_original` (verbatim, never
  cleaned) vs `_normalized` (derived, has an assertion), the in-scope flag
  (`inclusion_status` enum preferred over `is_case` boolean), anti-fabrication
  rules (NULL over guess; coords only when both lat+lon; trust flags
  propagate through `dc:description`).
- **§6 FTS5** — `tokenize = 'unicode61 remove_diacritics 2'` **required**.
- **§8** — the guarantees the shared `CorpusAdapter` relies on.
- **§9 `validate_corpus_db`** — 12 fail checks + warnings.
- **§10** — resolves every mipibu/povos divergence.

---

## 5. RESUME PLAN — implement `create_corpus_db` + `validate_corpus_db`

Next on the harness's critical path (harness doc C6, §9 step 1 follow-up).

### Scope

Two functions/CLIs, home TBD — proposed `brasil-archives/scripts/corpus/`
(per harness doc §8, the corpus-build toolkit is seeded in brasil-archives
and copied into each partner at handoff; a `scripts/corpus/` package is the
natural staging spot). Confirm with Steve before picking the path.

1. **`create_corpus_db(path, manifest) -> None`**
   - Stamps the MUST backbone from `corpus-db-contract.md`:
     `source_assertions`, `audit_events`, `repositories`, `controlled_terms`,
     `external_identifiers`, `schema_version` — exact DDL from the contract
     (§3, §4, §3.4, §7).
   - Reads an **entity-kinds manifest** (format still undefined — harness
     doc C8; define a minimal v0 here: per kind → table name, PK, columns
     with `_original`/`_normalized` tagging, FK targets, FTS columns,
     in-scope mechanism) and generates the entity tables + `fts_<kind>`
     virtual tables (`remove_diacritics 2`).
   - Sets `schema_version` (contract version + corpus entity-schema rev).
   - Does **not** write the `.sha256` sidecar — that's the freeze step.

2. **`validate_corpus_db(path) -> Report`**
   - Implements the 12 checks + warnings in `corpus-db-contract.md` §9.
   - `Report` = list of (level, check, detail); non-zero exit on any MUST
     failure. Usable both as a CLI and importable by the forge.

### Approach notes

- **No app imports.** Standalone like `scripts/backup_to_wasabi.py` — pure
  `sqlite3` + stdlib. It runs in partner build environments that won't have
  the brasil-archives app.
- **Test against the real corpora.** `povos_rn.db` and
  `sao-jose-mipibu-audit.db` are at `c:\DEV\povos-indigenas-rn\data\` and
  `c:\DEV\mipibu\data\`. The validator MUST pass mipibu (it's the reference)
  and SHOULD pass povos with at most documented warnings — if it doesn't,
  either the contract or the check is wrong; reconcile in the contract doc.
- **Round-trip test:** `create_corpus_db` output → `validate_corpus_db` →
  clean.
- Write `tests/test_corpus_db.py` (or in the chosen package).
- The **manifest v0** you define here feeds the eventual Layer-2 scaffold
  generator — keep it small and honest; it will grow when
  `jornais-digitalizados` forces real requirements.

### Definition of done

- `create_corpus_db` + `validate_corpus_db` implemented, standalone, tested.
- `python -m scripts.corpus.validate <path>` runs against all three of:
  a freshly-created empty corpus, `povos_rn.db`, `sao-jose-mipibu-audit.db`.
- Any contract adjustments forced by reality are written back into
  `corpus-db-contract.md` with a change-log entry.
- Committed + pushed; harness doc C6 row updated.

---

## 6. Key docs

| topic | file |
|---|---|
| The forge / harness spec | [`../archive-research-harness.md`](../archive-research-harness.md) |
| Corpus-DB contract (resume target) | [`../corpus-db-contract.md`](../corpus-db-contract.md) |
| Federation contract | [`../federation-v1.md`](../federation-v1.md) |
| Per-source `src_<slug>` schemas | [`../partner-schema-design.md`](../partner-schema-design.md) |
| Postgres cutover (done; console tasks) | [`2026-09-01-supabase-cutover-in-progress.md`](2026-09-01-supabase-cutover-in-progress.md) |
| Ecosystem overview | [`2026-08-27-master.md`](2026-08-27-master.md) |
| Partner repos (local) | `c:\DEV\mipibu`, `c:\DEV\povos-indigenas-rn` (both at `origin/main`) |

---

## 7. Carried forward — still Steve's console tasks only (unchanged)

1. Proton Pass — 2 records (cPanel prod creds, Wasabi backup key).
2. Wasabi console — bucket lifecycle rule to expire `pg/` after ~90d.
3. Portfolio, later — mpa/ajme off the leaked `MMR…` Wasabi root key,
   delete both root keys, TOTP MFA on root
   (`docs/wasabi-iam-plan.md` §10, `docs/wasabi_iam_provisioning_architecture.md` §8.2).
