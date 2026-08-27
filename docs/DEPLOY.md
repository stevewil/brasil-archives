# Deploying brasil-archives to cPanel

**Model:** GitHub is the source of truth. cPanel pulls from GitHub. Never push to cPanel directly.

Verified working 2026-08-27 with commit `a981b60` (Track 4).

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
5. DB initialized and seeded:
   ```bash
   FLASK_APP=wsgi.py flask db upgrade
   python -m scripts.load_vocabularies
   python -m scripts.load_survey
   python -m scripts.load_upgrade_projects
   python -m scripts.load_calibration   # Pass 2 anchor scores; without it every detail page renders "—"
   ```
6. Restart via **Setup Python App → Restart** or `touch tmp/restart.txt`.

## Routine deploy (every commit)

Standard three-step. All from cPanel terminal.

```bash
cd ~/brasil-archives
git fetch origin
git pull origin main
touch tmp/restart.txt
```

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
This is expected until Track 1 (i18n catalog) lands. Track 4 only localizes vocab table labels (institutional types, periods, record types, themes) — body copy stays English until Track 1.

## Reference

- Master handoff: `docs/handoff/2026-08-27-master.md`
- Sister app deploy pattern: `mipibu/README-CPANEL.md` (the pattern this doc is modeled on)
- UI Polish pickup: `docs/UI-POLISH-PICKUP.md`
