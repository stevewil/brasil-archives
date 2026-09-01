# brasil-archives

**Brazilian Digital Archives Project** — a scoring algorithm, archive catalog, and eventual public-facing site for pipeline-viable Brazilian digital archives, with a Northeast focus and a Mipibu-corpus-pattern lineage.

## Purpose

Assemble a curated database of Brazilian digital archives that meet a defined pipeline-viability standard — the standard demonstrated by the [Mipibu corpus explorer](https://mipibu.pplx.app). Support both:

1. **Internal use** — help a resource-constrained scholarly team decide which archives are worth building Mipibu-style pipelines against.
2. **Public use** — eventually publish a bilingual PT/EN read-only site where researchers can filter and locate archives by score and facet.

## Scope

Initial scope: the nine states of the Brazilian Northeast (AL, BA, CE, MA, PB, PE, PI, RN, SE). Method-first: once the algorithm and app work in the Northeast, expansion to other regions and international resources is straightforward.

## Fundamental floor

Every archive included in the public site must clear a single non-negotiable eligibility criterion:

> **Fair use / uso justo for scholarly work.** Content presented on the public site must abide by Brazilian and international fair-use / fair-dealing principles for scholarly purposes.

Archives that cannot clear this bar are tracked internally to avoid re-litigating them, but are not exposed on the public interface.

## Repository status

Phase 1 scaffolding — Flask app + SQLAlchemy models + Alembic migration in place. See `docs/` for design:

- `docs/algorithm-v1.md` — scoring algorithm (8 scored dimensions, 12 facets)
- `docs/standards.md` — standards conformance plan (Phases 1–6)
- `docs/federation-v1.md` — upgrade-project federation contract (OAI-PMH + IIIF)
- `docs/schema-v1.md` — data model sketch, mirrored in `app/models/`

## Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
git config core.hooksPath .githooks   # blocks committing a secret from your .env

export FLASK_APP=wsgi.py
.venv/bin/flask db upgrade                # create/migrate SQLite DB

# Load data (order matters)
.venv/bin/python -m scripts.load_vocabularies      # periods, record types, themes, institutional types
.venv/bin/python -m scripts.load_survey            # 79 archives from the Nordeste survey
.venv/bin/python -m scripts.seed_povos_archive     # composite archives row povos's upgrade project points at
.venv/bin/python -m scripts.load_upgrade_projects  # Mipibu + povos (extend by dropping YAML in configs/upgrade_projects/)
.venv/bin/python -m scripts.load_calibration                                    # Pass 2 anchor scores (idempotent)
.venv/bin/python -m scripts.load_calibration --path configs/calibration/pass3.yaml   # Pass 3, 15 more archives

.venv/bin/flask run                       # http://127.0.0.1:5000
.venv/bin/python -m pytest                # test suite
```

Instance data (SQLite DB) lives under `instance/` and is git-ignored.

### Testing against Postgres

The default loop is SQLite. Production runs PostgreSQL **10** (the instance
the cPanel host provides on localhost), so anything touching schema,
migrations, or the per-source `src_<slug>` views should also be checked
against a matching Postgres before pushing:

```bash
docker compose up -d db            # postgres:10, creates app / app_test / migrate_check
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/app_test .venv/bin/pytest
docker compose down                # add -v to wipe the volume
```

To run the app itself on Postgres, point `DATABASE_URL` at
`postgresql+psycopg://postgres:postgres@localhost:5432/app` and re-run
`flask db upgrade` + the loaders. CI runs the full suite on `postgres:10`
on every push.

## Related

- Precedent: [mipibu](https://github.com/stevewil/mipibu) — the RN judicial records corpus explorer that established the pipeline pattern.
- Survey source: the Nordeste digital archives survey (50 pipeline-viable rows + 30 no-content rows across nine states).

## License

Finalized 2026-08-29 — see [`LICENSING.md`](LICENSING.md).

- **Code** — [MIT](LICENSE). All application source, tests, migrations, scripts, deployment helpers, and documentation prose.
- **Curated data** — [CC BY 4.0](LICENSE-CC-BY-4.0.txt), attribution only. The Nordeste digital archives survey (`docs/nordeste-digital-archives-survey.md`) and the controlled vocabularies (`configs/vocabularies/*.yaml`).
- **Scoring output** — not exposed on the public site and not yet licensed; a license (expected CC BY 4.0) will be named when the judgments are trustworthy enough to publish.

Harvested partner records, the source archives' own holdings, and vendored fonts are **not** covered here — each carries its own terms. See [`LICENSING.md`](LICENSING.md).
