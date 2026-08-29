# Deploying brasil-archives to cPanel

**Model:** GitHub is the source of truth. cPanel pulls from GitHub. Never push to cPanel directly.

Verified working 2026-08-28 with commit `1cc5ded` (UI Tracks 1–5 + probe
runner + `/oai` provider + `size_unit_note`). Prior: `a981b60` (Track 4),
2026-08-27.

**2026-08-28 note:** that deploy found the prod SQLite DB had been reseeded
— missing Pass 2 scores, the harvest tables, and mipibu's `oai_pmh_base_url`.
Recovery was: `flask db upgrade` (3 migrations) → `pybabel compile` →
`python -m scripts.load_calibration` → `python -m scripts.load_upgrade_projects`
→ `python -m scripts.harvest --project mipibu` (both `oai_dc` and `oai_ead`).
Run that same recovery sequence after any future prod DB reseed.

## Prerequisites (one-time)

1. cPanel Python app created via **Setup Python App**:
   - Python 3.11 (or newer)
   - Application root: `~/brasil-archives`
   - Application URL: `brasil-archives.from-bottom-to.top`
   - Startup file: `passenger_wsgi.py`
   - Entry point: `application`
2. Repo cloned into the application root:
   ```bash
   cd ~
   git clone https://github.com/stevewil/brasil-archives.git
   cd brasil-archives
   ```
3. Dependencies installed into the cPanel virtualenv:
   ```bash
   source /home/<cpanel-user>/virtualenv/brasil-archives/3.11/bin/activate
   cd ~/brasil-archives
   pip install -r requirements.txt
   ```
4. Environment variables set in **Setup Python App** panel:
   - `DATABASE_URL` — SQLite absolute path, e.g. `sqlite:////home/<user>/brasil-archives/instance/brasil_archives.db`
   - `SECRET_KEY` — real random value
   - `FLASK_DEBUG=0`
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
5. DB initialized and seeded:
   ```bash
   FLASK_APP=wsgi.py flask db upgrade
   python -m scripts.load_vocabularies
   python -m scripts.load_survey
   python -m scripts.seed_povos_archive        # composite row povos's upgrade project points at
   python -m scripts.load_upgrade_projects     # mipibu + povos
   python -m scripts.load_calibration                                   # Pass 2 anchor scores
   python -m scripts.load_calibration --path configs/calibration/pass3.yaml   # Pass 3 (15 more archives)
   ```
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
source /home/<user>/virtualenv/brasil-archives/3.11/bin/activate
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
cd ~/brasil-archives
git fetch origin
git pull origin main
source /home/<user>/virtualenv/brasil-archives/3.11/bin/activate
FLASK_APP=wsgi.py flask db upgrade
touch tmp/restart.txt
```

## When a track adds a Python dependency

```bash
cd ~/brasil-archives
git fetch origin
git pull origin main
source /home/<user>/virtualenv/brasil-archives/3.11/bin/activate
pip install -r requirements.txt
touch tmp/restart.txt
```

## Rollback

Rollback is a `git reset` on the cPanel side plus a restart. Prefer forward-fixing (revert commit + push + pull) but if you need a fast fallback:

```bash
cd ~/brasil-archives
git log --oneline -5              # find the last-known-good commit
git reset --hard <sha>
touch tmp/restart.txt
```

Warning: this diverges cPanel from `origin/main`. The next `git pull` will fail without `--rebase` or a re-fetch. Cleanest recovery is to revert on GitHub, then pull normally.

## Troubleshooting

**Passenger serves an old version after `touch tmp/restart.txt`.**
Use the cPanel UI: Setup Python App → brasil-archives → Restart. If that also fails, check the app's error log in the UI for import errors.

**`sqlite3.OperationalError: no such table` after pull.**
Migration wasn't run. `FLASK_APP=wsgi.py flask db upgrade` inside the venv.

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
