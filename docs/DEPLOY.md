# Deploying brasil-archives to cPanel

**Model:** GitHub is the source of truth. cPanel pulls from GitHub. Never push to cPanel directly.

## Database

Prod runs on the **PostgreSQL 10.23 instance the cPanel host provides on
its own `localhost`** (cPanel → *PostgreSQL Databases*), db
`fromuagq_brasil-archives`. The Supabase migration was designed and built
(`docs/supabase-migration-spec.md`) but the shared host only allows
outbound `:443`, so the Supabase pooler is unreachable — the cPanel-local
Postgres is what shipped (2026-09-01). Each partner source gets its own
`src_<slug>` schema; cross-source reads go through the `public.*_all`
views (`docs/partner-schema-design.md`).

- **Config** lives in `~/flask/brasil-archives/.env` (`chmod 600`), read
  by `passenger_wsgi.py` at boot and by `python -m scripts.*`. It is a
  canonical production file — sectioned, every line annotated `[dev: …]`.
- **`DATABASE_URL`** = `postgresql+psycopg://fromuagq_brasil-archives-user:‹pw›@localhost:5432/fromuagq_brasil-archives?sslmode=disable`
  (localhost = no TLS). Password in Proton Pass.
- **Recovery** — the old `prod-db-gets-reseeded` runbook is obsolete: its
  root cause (scripts not loading `.env` → silent SQLite fallback) is
  fixed, and the pre-cutover SQLite snapshot is frozen at
  `instance/brasil_archives.db.pre-pg-2026-09-01`. To restore from
  off-site: fetch the latest `pg/…dump.enc` from Wasabi, decrypt, and
  `pg_restore` (`docs/wasabi-backup.md`).
- **Backup** — weekly encrypted `pg_dump` of the whole DB → Wasabi, cron
  `0 4 * * 0` (`scripts/backup_to_wasabi.py`, `BACKUP_MODE=pgdump`).

## Prerequisites (one-time)

1. cPanel Python app created via **Setup Python App**:
   - Python 3.13
   - Application root: `~/flask/brasil-archives`
   - Application URL: `brasil-archives.from-bottom-to.top`
   - Startup file: `passenger_wsgi.py`
   - Entry point: `application`
2. Repo cloned into the application root:
   ```bash
   cd ~/flask
   git clone https://github.com/stevewil/brasil-archives.git
   cd brasil-archives
   ```
   The private repo needs auth — the box uses `~/bin/gh` (device-flow
   token). Public repos (this one, mipibu, povos) clone without it.
2b. PostgreSQL database + user created via cPanel → **PostgreSQL Databases**
   (`fromuagq_brasil-archives` + `fromuagq_brasil-archives-user`, user added
   to the DB, alphanumeric password). See the "Database" section above.
3. Dependencies installed into the cPanel virtualenv:
   ```bash
   source /home/<cpanel-user>/virtualenv/flask/brasil-archives/3.13/bin/activate
   cd ~/flask/brasil-archives
   pip install -r requirements.txt
   ```
4. `~/flask/brasil-archives/.env` written (`chmod 600`) — this file, not
   the Setup-Python-App panel, is the config mechanism. It is a canonical
   production file; the shape is documented inline in it. Key values:
   - `BRASIL_ARCHIVES_CONFIG=production` — selects ProductionConfig
   - `SECRET_KEY` — real 32+ char random value (production refuses to boot
     without one)
   - `DATABASE_URL` — the localhost Postgres string (Database section above)
   - `BRASIL_ARCHIVES_DB_CHECK=1` — fail-fast DB check at boot
   - `FLASK_DEBUG=0`
   - `WASABI_*` + `BACKUP_*` + `BRASIL_ARCHIVES_BACKUP_KEY` — the backup cron
   - `BRASIL_ARCHIVES_ADMIN` — **leave unset** on the public deployment.
     Set it to `1` only on an internal/operator deployment: it unlocks the
     scoring forms, the facet editor, and the entire `/harvest` surface
     (all 404 otherwise). See `app/blueprints/_admin_gate.py`.
   - `BRASIL_ARCHIVES_PUBLIC_SCORES` — **leave unset** on the public host
     until the scored judgments are greenlit for release. When unset (and
     not an admin deployment) the catalog and federated search work
     normally but the dimension scores, the two axis totals, the quadrant
     label, the naive sum, and the score-ranked home block are hidden.
     Set to `1` to publish them. Independent of `BRASIL_ARCHIVES_ADMIN`
     (which always shows scores). See `app/visibility.py`.
5. DB initialized and seeded (venv active, in `~/flask/brasil-archives`).
   `flask` and `python -m scripts.*` both read `.env` now, so
   `DATABASE_URL` reaches all of them — a fresh Postgres ends up fully
   populated:
   ```bash
   FLASK_APP=wsgi.py flask db upgrade          # creates public schema (+ empty *_all views)
   python -m scripts.load_vocabularies
   python -m scripts.load_survey
   python -m scripts.seed_povos_archive        # composite row povos's upgrade project points at
   python -m scripts.load_upgrade_projects     # mipibu + povos; also stamps the src_<slug> schemas + rebuilds the *_all views
   python -m scripts.load_calibration                                   # Pass 2 anchor scores
   python -m scripts.load_calibration --path configs/calibration/pass3.yaml   # Pass 3 (15 more archives)
   python -m scripts.harvest --project mipibu                           # -> src_mipibu (oai_dc)
   python -m scripts.harvest --project mipibu --format oai_ead          # -> src_mipibu (oai_ead)
   python -m scripts.harvest --project povos-indigenas-rn              # -> src_povos_indigenas_rn
   ```
   Expected totals: archives 80, dimension_scores 168, upgrade_projects 2,
   facet_values 47, `aggregated_records_all` 1161.
6. Compile the translation catalogs (the `.mo` files are git-ignored, so
   they must be built on the deploy host — see `app/translations/`):
   ```bash
   pybabel compile -d app/translations
   ```
7. Restart via **Setup Python App → Restart** or `touch tmp/restart.txt`.

## Helper scripts (repo root, on the cPanel checkout)

- **`venv`** — *source* it to activate the virtualenv and `cd` to the app
  root: `source ~/flask/brasil-archives/venv` (or add
  `alias venv='source ~/flask/brasil-archives/venv'` to `~/.bashrc`).
- **`github-pull`** — *execute* it for a routine deploy:
  `~/flask/brasil-archives/github-pull`. It pulls `--ff-only`, then runs
  `pip install` / `flask db upgrade` / `pybabel compile` only when the
  relevant files changed, and `touch tmp/restart.txt`. It prints (but does
  not run) the data-loader commands when `configs/` changed, and the
  `scripts.reextract` command when an OAI extractor changed.
- **`scripts/reextract.py`** — re-derives `extracted_json` for
  already-harvested `aggregated_records` from their stored raw XML, with
  no network. Run it after an extractor change
  (`app/services/oai_extractors/`): a plain harvest only refreshes rows
  whose raw XML changed. `python -m scripts.reextract --dry-run` previews;
  `python -m scripts.reextract` writes; `--project <slug>` narrows.

## Routine deploy (every commit)

`~/flask/brasil-archives/github-pull` covers it. The manual equivalent:

```bash
cd ~/flask/brasil-archives
git fetch origin
git pull origin main
touch tmp/restart.txt
```

**If the pull touched `app/translations/**/*.po`** (i.e. UI strings or
translations changed — no schema change needed), recompile the catalogs
inside the venv before restarting:

```bash
source /home/<user>/virtualenv/flask/brasil-archives/3.13/bin/activate
pybabel compile -d app/translations
touch tmp/restart.txt
```

The compiled `.mo` files are git-ignored, so a plain `git pull` never
updates them.

Then verify from any shell:

```bash
curl -s https://brasil-archives.from-bottom-to.top/healthz
# expect: {"app":"brasil-archives","status":"ok","version":"..."}
```

## Verifying a track landed correctly

**Bilingual smoke test — should return one line each after Track 4+:**

```bash
curl -s https://brasil-archives.from-bottom-to.top/archives/ | \
  grep -oE 'Federal university|State court' | sort -u
# expect: Federal university, State court

curl -s 'https://brasil-archives.from-bottom-to.top/archives/?lang=pt' | \
  grep -oE 'Universidade federal|Tribunal de justiça' | sort -u
# expect: Tribunal de justiça, Universidade federal
```

If EN and PT return the same values (i.e. Passenger is serving stale code), the restart didn't take. Re-run `touch tmp/restart.txt` or restart via UI.

## When a track adds schema

None of the currently deferred UI-polish tracks require migrations. If a future track does, the deploy becomes four steps:

```bash
cd ~/flask/brasil-archives
git fetch origin
git pull origin main
source /home/<user>/virtualenv/flask/brasil-archives/3.13/bin/activate
FLASK_APP=wsgi.py flask db upgrade
touch tmp/restart.txt
```

## When a track adds a Python dependency

```bash
cd ~/flask/brasil-archives
git fetch origin
git pull origin main
source /home/<user>/virtualenv/flask/brasil-archives/3.13/bin/activate
pip install -r requirements.txt
touch tmp/restart.txt
```

## Rollback

Rollback is a `git reset` on the cPanel side plus a restart. Prefer forward-fixing (revert commit + push + pull) but if you need a fast fallback:

```bash
cd ~/flask/brasil-archives
git log --oneline -5              # find the last-known-good commit
git reset --hard <sha>
touch tmp/restart.txt
```

Warning: this diverges cPanel from `origin/main`. The next `git pull` will fail without `--rebase` or a re-fetch. Cleanest recovery is to revert on GitHub, then pull normally.

## Troubleshooting

**Passenger serves an old version after `touch tmp/restart.txt`.**
Use the cPanel UI: Setup Python App → brasil-archives → Restart. If that also fails, check the app's error log in the UI for import errors.

**`relation "…" does not exist` / `no such table` after pull.**
A migration wasn't applied: `FLASK_APP=wsgi.py flask db upgrade` inside
the venv. (`github-pull` does this automatically when
`migrations/versions/` changed.)

**`/healthz` → `"database_connected": false`, `503`.**
The app can't reach Postgres. Check `DATABASE_URL` in `.env` and that the
password matches the DB role. `python -m scripts.pg_diagnose` walks the
connection outside-in.

**`ModuleNotFoundError` after pull.**
Dependency added but venv not updated. `pip install -r requirements.txt` inside the venv.

**Locale switch returns English on `?lang=pt`.**
Since UI-Polish Track 1 landed, `?lang=pt` translates body copy too. If it
doesn't, the `.mo` files weren't compiled after the pull — run
`pybabel compile -d app/translations` inside the venv, then restart
Passenger. (Vocab table labels — institutional types, periods, record
types, themes — come from Track 4 and work independently of the catalog.)

## Reference

- Master handoff: `docs/handoff/2026-08-27-master.md`
- Sister app deploy pattern: `mipibu/README-CPANEL.md` (the pattern this doc is modeled on)
- UI Polish pickup: `docs/UI-POLISH-PICKUP.md`
