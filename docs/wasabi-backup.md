# Wasabi off-site backup — encrypted `pg_dump` of the production database

> **UPDATE 2026-09-01 — prod mode is now `pgdump`.** The cutover landed on
> the cPanel host's own **PostgreSQL 10.23**, and its `pg_dump 10.23`
> matches that server exactly. `BACKUP_MODE=pgdump` now dumps the **whole
> database** (all schemas: `public` + `src_mipibu` + `src_povos_indigenas_rn`,
> plus views and sequences) — verified 2026-09-01 by a dump → restore into a
> scratch DB with every count matching prod. The old `python` logical-dump
> mode reflects `public.*` only and **misses the `src_<slug>` schemas
> entirely** — it's dev/SQLite convenience now, not a prod backup. Sections
> below that describe `python` as the default are pre-cutover history.

**Status:** code done + fidelity-verified. Not yet wired: the weekly cron
and the bucket lifecycle rule.
**Resolves:** migration-spec **D8** (free-tier backup strategy).

## Approach (pre-cutover history — see the UPDATE above)

`pg_dump`'s major must be ≥ the server's. The cPanel box only has `pg_dump`
`10.23` and no newer client is installable there. So the **default mode is a
pure-Python logical dump** — SQLAlchemy reflects the schema, `SELECT *` every
table in FK order, serialise to gzipped JSON. Version-proof, zero client
binary, runs in the app venv. `pg_dump` mode is retained (`--pgdump` /
`BACKUP_MODE=pgdump`) for a GitHub-Actions runner or if a client ever appears.

**Bonus:** the logical dump works against **SQLite too**, so it can back up
today's SQLite prod DB *before* the Supabase cutover — closing the
reseed-data-loss window ([[prod-db-gets-reseeded]]) early. Post-cutover it
dumps `public` (SQLite has no schemas → it dumps the whole file, which is the
same set of tables minus the `src_*` split that doesn't exist yet).

**Built 2026-08-31:**
- `scripts/backup_to_wasabi.py` — standalone (no app imports). Modes:
  `python` (default) / `pgdump`. Flags: default full run · `--dry-run` ·
  `--selftest` · `--list` · `--fetch` · `--decrypt` · `--restore … --target-url …`.
- `requirements-backup.txt` (`boto3`, `cryptography`) — cron-only. `SQLAlchemy`
  for `python` mode is already a web-app dep.
- `tests/test_backup_to_wasabi.py` — 30 tests, no network (boto3 stubbed;
  SQLite for the dump/restore round-trip). Full app suite still green.
- `.env` (local) — `WASABI_REGION=us-west-1`, `WASABI_ENDPOINT_URL`,
  `BRASIL_ARCHIVES_BACKUP_KEY` (generated; **must also go in Proton Pass**),
  `BACKUP_PREFIX=pg/`, `BACKUP_MODE=python`.
- Verified against the live `brasil-archives` bucket: `--selftest` (SigV4,
  put/get/delete, AES-GCM, ETag==md5) **and** a real dump of SQLite prod
  (20 tables / 1781 rows → 6.8 MB JSON → 307 KB gzip → encrypted → uploaded →
  fetched → restored into a scratch DB, 1781 rows, all data equal — only
  SQLite's cosmetic timestamp text rendering differs, `19:32:20` vs
  `19:32:20.000000`; exact on Postgres).

---

## 1. Purpose, in one paragraph

brasil-archives's prod DB is not durable — today the SQLite file silently
reseeds on some redeploys ([[prod-db-gets-reseeded]]); after cutover it's a
**Supabase free-plan Postgres** with daily backups but **1-day retention and
no PITR**. Either way, thin cover. This adds a second, independent copy: a
weekly **logical dump of the core tables** (`public` after cutover; the whole
SQLite file before), **client-side encrypted**, pushed to a dedicated
**Wasabi** bucket, keeping ~12 weeks. It's an *offsite disaster-recovery
artifact*, not the system of record — everything in `public` also
reconstructs from the git-tracked `configs/*.yaml` + seed scripts
(migration-spec §7.2, "the reseed IS the migration"); the dump just makes a
restore an import instead of a re-derivation, and catches anything
hand-entered that isn't in `configs/`.

## 2. Non-goals

- **Backing up the `src_*` schemas.** They hold only harvested / cached
  partner data, 100% re-derivable by re-running `scripts/harvest.py`. A full
  `pg_dump` (no `--schema`) would sweep them in; we deliberately scope to
  `public` (migration-spec §9.4, `project-schema-design.md` §9).
- **Wasabi as a live or queryable store.** It holds opaque encrypted blobs.
- **Automatic restore.** Restore is a deliberate, operator-run drill (§8).
- **Any change to the Flask app.** This is an ops/cron concern. `app/` and the
  web-app `requirements.txt` are untouched; the script's deps (`boto3`) are
  cron-only.

## 3. What we reuse from the portfolio

Steve already runs Wasabi in two places; this follows those conventions so
there's one mental model.

| Source | What carries over |
|---|---|
| `media-pipeline-agent/hosted/app/image_store.py` | The boto3-against-Wasabi pattern: `WASABI_*` env vars, `endpoint_url`, **SigV4 required** (`BotoConfig(signature_version="s3v4")`), stub-mode fallback when creds absent. `scripts/backup_to_wasabi.py` lifts the ~40 lines it needs — no shared module. |
| `app-dashboard/VAULT-WASABI-SPEC.md` §3 | The **encrypted-envelope** idea: AES-256-GCM over the payload with a base64 content key from `.env`, secrets in Proton Pass, ISO-timestamp in the object key so it sorts chronologically. |
| Both | **Dedicated bucket per use**, **versioning ON + a lifecycle rule for retention** (the script never calls `DeleteObject`), shared portfolio `WASABI_*` key. (mpa/ajme buckets are us-west-2; the `brasil-archives` bucket is us-west-1 — the script derives the endpoint from `WASABI_REGION`.) |
| Neither | The JIT presigned-URL path (`ajme-wasabi-presigner`) — still design-stage portfolio-wide. This cron holds the key directly, like the vault's Option A. Migrating to the presigner later touches only the upload call. |

## 4. What gets backed up

**`python` mode (default).** SQLAlchemy reflects the target schema (`public`
on Postgres; the whole file on SQLite), `SELECT *` every table in FK-safe
order (`MetaData.sorted_tables`), and writes:

```jsonc
{ "format": "brasil-archives-logical-dump", "version": 1,
  "created_at": "...", "dialect": "postgresql", "schema": "public",
  "server_version": "PostgreSQL 17...",
  "tables": [ { "name": "archives", "columns": [...], "rows": [ {...}, ... ] }, ... ] }
```

then `gzip -9` → AES-GCM → upload. Non-JSON types are tagged
(`{"__t__":"dt","v":"<iso>"}` for datetime, `dec` for Decimal, `b64` for
bytes). `alembic_version` is just another table and rides along. Tables
covered = core catalog, vocabularies, `upgrade_projects`, the scoring tables
(`dimension_scores`, `dimension_lifts`, `facet_values`), `probe_results`,
join tables — **not** `src_*` (a `schema="public"` reflection never sees
them). Size measured: 20 tables / 1781 rows → 6.8 MB JSON → **307 KB** gzip.
Single-part PUT.

**`pgdump` mode** (`--pgdump` / `BACKUP_MODE=pgdump`) — kept for a
GitHub-Actions runner or a future client binary:
`pg_dump --schema=public --no-owner --no-privileges -Fc "$DATABASE_URL"`,
restore with `pg_restore`.

## 5. Where it runs

`pg_dump`'s major must be ≥ the server's. cPanel has only `pg_dump 10.23`
(checked 2026-08-31) and no newer client is installable there → **`python`
mode is the default**, and it needs no client binary. Two viable homes:

### A — cPanel weekly cron  ★ chosen

`python -m scripts.backup_to_wasabi` from the app venv (needs
`pip install -r requirements-backup.txt` there — `boto3` + `cryptography`;
SQLAlchemy is already installed). Reads `~/flask/brasil-archives/.env`
(the script calls `load_dotenv` on the repo root). Mirrors the
`supabase-keepalive` cron already on the box. **No new secret location** —
`DATABASE_URL` + `WASABI_*` + `BRASIL_ARCHIVES_BACKUP_KEY` all live in that
one `chmod 600` `.env`.

**Can start now, before cutover:** `python` mode dumps the current SQLite
prod DB fine (verified). Wiring the cron now gives weekly off-site coverage
immediately and closes the reseed-data-loss window ([[prod-db-gets-reseeded]])
months early. At cutover, only `DATABASE_URL` changes.

### B — GitHub Actions weekly workflow  (fallback / `pgdump` mode)

`pip install -r requirements-backup.txt`, run the same command. Only reason to
prefer it: a always-current `pg_dump` for `pgdump` mode. **Downside:** the
Supabase DB password becomes a GitHub Actions secret — encrypted at rest, not
screenshot-leakable, but a wider footprint than cPanel + Proton Pass.

**Decision:** **A**, `python` mode. Revisit B only if the cPanel cron proves
unreliable.

## 6. Bucket + object layout

- **Bucket:** `brasil-archives` — created, live, creds in `.env`. The script
  reads `WASABI_BUCKET_NAME` (+ `WASABI_BUCKET` fallback) and `BACKUP_PREFIX`.
- **Region / endpoint:** `us-west-1` / `https://s3.us-west-1.wasabisys.com`.
  Latency is irrelevant for a weekly blob.
- **Key:** `${BACKUP_PREFIX}brasil-public-<ISO8601>.<ext>` where `<ext>` is
  `json.gz.enc` (`python` mode) or `dump.enc` (`pgdump` mode) —
  e.g. `pg/brasil-public-2026-09-07T04-00-05Z.json.gz.enc`. ISO-in-name sorts
  lexically = chronologically. (`_selftest/` gets a parallel prefix.)
- **Retention = a Wasabi lifecycle rule**, not script-driven deletes:
  expire objects under `${BACKUP_PREFIX}` after **90 days**, noncurrent
  versions after **30 days**. 90 days ≈ 12 weekly dumps and lines up with
  Wasabi's 90-day minimum storage charge (deleting sooner just forfeits the
  charge). The script's Wasabi key therefore needs **no `DeleteObject`**.
- **Versioning ON** — the corruption net (a bad dump overwriting a key still
  leaves the prior version for 30 days).
- **Key scope:** the key in `.env` (`WASABI_ACCESS_KEY_ID`) currently has
  **`DeleteObject`** — the `--selftest` cleaned up its own probe. That's fine
  for `--selftest` but the backup cron never needs delete (retention is the
  lifecycle rule). A bucket-scoped sub-user (`Get`/`Put`/`List` only, no
  `Delete`) is the better production credential; not a blocker. If you switch
  to a no-delete key, `--selftest` will just log "could not delete probe
  object; lifecycle rule will expire it" and still pass.

## 7. Encryption

The dump contains the **scored judgments**, which are deliberately non-public
(`LICENSING.md`; migration-spec §9.2.1). It must be opaque the moment it
leaves the DB boundary.

- **Client-side, before upload.** AES-256-GCM over the gzipped dump with a
  random 32-byte content key, base64 in `BRASIL_ARCHIVES_BACKUP_KEY`
  (`.env` / cPanel env / GH secret — **and Proton Pass**). Envelope =
  `MAGIC "BAB1" ‖ version ‖ nonce(12) ‖ ciphertext+tag`; the 5-byte header is
  the GCM associated data. Python:
  `cryptography.hazmat.primitives.ciphers.aead.AESGCM`.
- **Not bucket-level SSE.** SSE breaks the ETag == MD5 integrity check the
  upload relies on (mpa's `wasabi_uploader.py` docstring flags exactly this).
  Client-side encryption keeps the check: we hash the ciphertext we send.
- **`age` / `gpg` alternative** — fine for the GitHub Actions path (`age` is
  one `apt` line) or if you'd rather hold an `age` recipient key than an env
  secret. The script supports "encrypt command reads stdin, writes stdout" via
  `BACKUP_ENCRYPT_CMD` so either works.
- **Recovery needs one secret:** `BRASIL_ARCHIVES_BACKUP_KEY` (or the `age`
  identity). Unlike the vault there's no second passphrase layer — the dump
  isn't itself pre-encrypted, so one good key is the whole boundary. Keep it
  in Proton Pass; losing it means falling back to the seed-script re-derivation.

## 8. `scripts/backup_to_wasabi.py`

One standalone script. No web-app imports. Pipeline:

1. **Dump** — `python` mode: SQLAlchemy reflect + `SELECT *` in FK order →
   JSON → `gzip -9` (all in memory). `pgdump` mode: `subprocess` `pg_dump` to
   a temp file. Either fails loudly and uploads nothing on error.
2. **Encrypt** — AES-GCM (§7), or pipe through `BACKUP_ENCRYPT_CMD`.
3. **Upload** — boto3 `put_object` (SigV4). Verify returned ETag == local MD5
   of the ciphertext (skip with a warning on a multipart-shaped ETag). Retry
   3× exp-backoff on 5xx / connection errors; fail fast on 4xx.
4. **Prune — none.** Retention is the lifecycle rule (§6); the key needs no
   `DeleteObject`.
5. **Report** — key + size to stderr; non-zero exit on any failure so cron
   email fires.

Flags: `--dry-run` · `--keep <path>` · `--selftest` (crypto + Wasabi
round-trip, synthetic payload, no DB) · `--list` · `--fetch KEY OUT` ·
`--decrypt IN OUT` (raw bytes) · `--restore IN --target-url URL`
(`python` mode: decrypt + gunzip + wipe-and-reload into a **scratch** DB;
refuses `--target-url == DATABASE_URL` without `--force`) · `--python` /
`--pgdump` (override `BACKUP_MODE`).

Deps: `requirements-backup.txt` (`boto3`, `cryptography`). `pip install` into
the cPanel venv. SQLAlchemy (for `python` mode) is already there.

## 9. Cron

```
# cPanel — Sunday 04:00, app venv python, .env auto-loaded by the script.
# Pattern mirrors the supabase-keepalive cron line.
0 4 * * 0  cd /home/fromuagq/flask/brasil-archives && venv/bin/python -m scripts.backup_to_wasabi >> ~/logs/backup.log 2>&1
```

(`venv/bin/python` = the 3.13 virtualenv; adjust to the real activate path.
GH Actions equivalent: `schedule: - cron: "0 4 * * 0"`.)

## 10. Restore drill — add to `docs/DEPLOY.md`

An untested backup is not a backup. Once after wiring the cron, then
~quarterly. `python` mode:

```bash
cd ~/flask/brasil-archives    # or a local checkout
venv/bin/python -m scripts.backup_to_wasabi --list                     # find the newest key
venv/bin/python -m scripts.backup_to_wasabi --fetch pg/<newest>.json.gz.enc ./restore.enc

# scratch DB with the current schema, then load:
#   Postgres:  createdb brasil_drill; DATABASE_URL=postgresql+psycopg://…/brasil_drill flask db upgrade
#   SQLite:    DATABASE_URL=sqlite:///drill.db flask db upgrade
venv/bin/python -m scripts.backup_to_wasabi --restore ./restore.enc \
  --target-url postgresql+psycopg://…/brasil_drill

# verify (adjust to backend)
psql brasil_drill -c "select count(*) from archives;"                                    # ~80
psql brasil_drill -c "select count(*) from dimension_scores where superseded_at is null;"# ~168
psql brasil_drill -c "select count(*) from upgrade_projects;"                            # 2
```

`--restore` refuses to touch `DATABASE_URL` without `--force`. `pgdump` mode:
`--decrypt` then `pg_restore --no-owner --dbname <scratch>`.

## 11. Env vars

```
WASABI_ACCESS_KEY_ID          Wasabi key (currently the shared portfolio key)
WASABI_SECRET_ACCESS_KEY
WASABI_REGION                 us-west-1        (bucket's region)
WASABI_ENDPOINT_URL          https://s3.us-west-1.wasabisys.com   (default: derived from region)
WASABI_BUCKET_NAME           brasil-archives  (script also accepts WASABI_BUCKET, mpa's name)
BACKUP_PREFIX                 default "pg/"
BACKUP_MODE                   "python" (default) | "pgdump"
BRASIL_ARCHIVES_BACKUP_KEY    base64 32 bytes — absent ⇒ the script refuses to run (no plaintext uploads)
BACKUP_ENCRYPT_CMD            optional — overrides built-in AES-GCM (e.g. "age -r age1...")
BACKUP_DECRYPT_CMD            optional — the matching decrypt
DATABASE_URL                  the DB to dump; not needed for --selftest
```

Local `.env` is set. **cPanel `.env`** (`~/flask/brasil-archives/.env`,
`chmod 600`) — append `WASABI_ACCESS_KEY_ID`, `WASABI_SECRET_ACCESS_KEY`,
`WASABI_REGION`, `WASABI_ENDPOINT_URL`, `WASABI_BUCKET_NAME`,
`BRASIL_ARCHIVES_BACKUP_KEY`, `BACKUP_PREFIX`, `BACKUP_MODE=python`. The web
app ignores all of them.

Generate the key: `python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"`
→ set it, **store in Proton Pass** (sole recovery boundary).

## 12. Testing

`tests/test_backup_to_wasabi.py` — 30 tests, no network (boto3 stubbed;
SQLite for the dump/restore round-trip):
- value codec round-trips (datetime, Decimal, bytes, primitives);
- AES-GCM encrypt → decrypt; flipped byte fails the tag; wrong key / bad magic
  rejected; `BACKUP_ENCRYPT_CMD` / `_DECRYPT_CMD` override;
- `python_dump` → `python_restore` round-trip into a fresh SQLite (FK order,
  types preserved); restore refuses missing tables / `DATABASE_URL` w/o force;
- key layout ISO-sortable; `_ext` tracks the mode;
- `_pg_url` strips `+psycopg`; `pg_dump` mode refuses non-Postgres URLs;
- upload retry (500 ×2 → success), 4xx fail-fast, ETag mismatch → raise.

Verified manually against the live bucket: `--selftest`, and a full loop on
SQLite prod data (dump → upload → fetch → restore, 1781 rows equal).

## 13. Not built / deferred

- **JIT presigned URLs** via the portfolio presigner — long-term, same as the
  vault. Swap the `put_object` call for a presigner URL + plain PUT.
- **Bucket-scoped no-delete sub-user** instead of the shared key (§6).
- **Monitoring beyond cron email** — e.g. a probe target on the newest key's
  age. The weekly cadence makes a silent gap visible within a week anyway.
- **`src_*` capture** — only if a partner re-harvest ever gets expensive; then
  a monthly full dump under a separate prefix.
- **`pg_dump` in the cron** — `pgdump` mode stays code-complete but unused
  unless a GH Actions runner is adopted.

## 14. Open questions

1. **Start the cron now, or at cutover?** `python` mode already backs up the
   current SQLite prod DB (verified). Starting now closes the reseed window
   ([[prod-db-gets-reseeded]]) months early for ~zero cost. Leaning: **now.**
2. **Production Wasabi credential** — keep the shared portfolio key, or a
   bucket-scoped no-delete sub-user (§6)? Not a blocker.
3. **Regenerate `BRASIL_ARCHIVES_BACKUP_KEY`?** The generated value appeared in
   a chat transcript. If that matters, rotate it before the first real upload
   (nothing's encrypted with it yet that we'd lose).
4. **Restore-drill scratch DB** — local Docker `postgres:10`
   (`docker compose up -d db`) vs SQLite. SQLite is enough to prove the loop;
   PG 10 matches production.

RESOLVED: bucket (`brasil-archives`, us-west-1); dump approach (`python`
logical dump — cPanel has only `pg_dump 10`); encryption (built-in AES-256-GCM,
`age`/`gpg` available via `BACKUP_*_CMD`); where it runs (cPanel weekly cron).
