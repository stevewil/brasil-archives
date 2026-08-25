# Brazilian Digital Archives Project — State & Roadmap

**Last updated**: 2026-08-24
**Scope**: Everything built to date across `brasil-archives` and `mipibu`, plus a sequenced path to beyond-beta.

## Table of Contents

1. [What we've built](#what-weve-built)
2. [What still needs to happen](#what-still-needs-to-happen)
3. [Sequenced TODO list](#sequenced-todo-list)
4. [Design principles carried forward](#design-principles-carried-forward)
5. [Repositories, buckets, and hosts](#repositories-buckets-and-hosts)
6. [Deferred decisions](#deferred-decisions)

---

## What we've built

### Design foundation (`brasil-archives` repo)

Seven design documents, all in [github.com/stevewil/brasil-archives](https://github.com/stevewil/brasil-archives):

| Document | What it defines |
|---|---|
| `nordeste-digital-archives-survey.md` | Baseline survey of RN/PE/BA digital archives; scoring rubric. |
| `standards.md` | External standards conformance (Dublin Core, EAD, OAI-PMH, IIIF). |
| `schema-v1.md` | Two-axis archive metadata: what the archive is + how it's usable. |
| `algorithm-v1.md` | Scoring algorithm mapping archive attributes to composite scores. |
| `adr-0001-two-axis-aggregation.md` | Architectural decision: aggregate along **archive identity** and **scholarly access practical** as separate axes. |
| `federation-v1.md` | The `/api/health`, `/api/schema`, `/api/records`, `/api/records/<id>` contract. |
| `scenario-driven-federation-model.md` | When federation is needed vs when metadata alone suffices. |

**Coverage**: 6 archives scored (Mipibu is one of them, dogfooding the schema). Quarterly re-probe pattern established in the survey.

**Stated principles baked into the design**:

- Bilingual PT/EN. Northeast Brazil (RN, PE, BA) focus. Ecclesiastical archives given weight.
- National-period historian's lens (1800–1900); age-as-value bias explicitly rejected.
- `scholarly_access_practical` is the fundamental floor — how usable is this archive for a resource-poor scholar right now.
- Fair use / uso justo for scholarly work is the moral floor of the whole project.
- Code MIT/Apache. Data CC-BY-SA.
- brasil-archives holds metadata **about** archives. Corpus-explorer apps (like Mipibu) hold the actual records.

### Mipibu Corpus Explorer (`stevewil/mipibu`)

The first federated archive companion app — bilingual explorer for the São José de Mipibu judicial records (LABIM/UFRN).

**As-built application**:
- Flask factory in `app/__init__.py`, blueprints `main` + `api`
- Existing `/api/*` endpoints: `stats`, `cases`, `cases/<id>`, `boxes`, `facets`, `network`, `duplicates`
- SQL layer in `app/queries.py` with 20+ query functions; base joins across `cases → repository_items → archival_collections → archival_units → digital_files → controlled_terms`
- Presenter layer in `app/presenters.py` producing bilingual dict output
- Filter/paging/sort parser in `app/params.py`, security headers + error handlers
- 508 records (299 criminal + 209 probate) across boxes 07–20
- Read-only SQLite DB opened with `mode=ro&immutable=1`
- cPanel Passenger deployment via `passenger_wsgi.py`, dev via `wsgi.py`

**Deploy tooling added this session** — [commit 2fc814a](https://github.com/stevewil/mipibu/commit/2fc814a), 11 files, 1276 lines:

- `deploy/mipibu-app.sh` — unified operator console with subcommands: `configure`, `init`, `pull`, `status`, `restart`, `stop`, `start`, `logs`, `debug`
- `scripts/sync-corpus.sh` — Wasabi upload/download/status with SHA256 verification
- `.githooks/pre-commit` — auto-uploads corpus DB to Wasabi when `.sha256` is committed
- `.githooks/pre-push` — verifies Wasabi holds every SHA about to be pushed
- `.github/workflows/verify-corpus.yml` — CI double-check via public Wasabi URL
- `.gitattributes` — forces LF line endings (Windows-safe)
- `.gitignore` — excludes DB itself; only SHA sidecar tracked
- `README-CPANEL-DEPLOY.md` — end-to-end deploy guide
- `WASABI-SETUP.md` — Wasabi bucket creation walkthrough

**Architectural invariants enforced by the tooling**:

- **Pull-only**: cPanel host never runs `push`, `commit`, `add`, `merge`. Only `fetch` + `reset --hard origin/<branch>`.
- **Credentials only on workstation**: `~/.aws/credentials` mode 600, one profile per bucket. Never in repo, never on cPanel, never in CI.
- **Content-addressed corpus**: DB fetched by SHA-verified download; mismatch fails the deploy.
- **Restart-before-swap**: Passenger reloads to release file handles before the rsync replaces the DB.

### Wasabi decisions (design, not yet deployed)

- Provider: Wasabi (S3-compatible, no egress fees, US-East-1 for best Brazil peering)
- Bucket `mipibu-corpus`: public-read on `data/*` prefix only; versioning on; SSE-S3
- Bucket `brasil-archives-data`: private, empty, provisioned for future use
- Independent access keys per bucket for rotation isolation
- The mipibu-corpus URL is public: `https://s3.us-west-2.wasabisys.com/mipibu-corpus/data/sao-jose-mipibu-audit.db`

### Workstation setup

- Windows + PowerShell (default) or Git Bash (for scripts)
- Git 2.53 installed at `C:\Program Files\Git\`
- AWS CLI v2 installed at `C:\Program Files\Amazon\AWSCLIV2\`
- Scripts run in Git Bash; PowerShell not used for repo automation

### Sibling projects in memory

Per the Knowledge Wiki index, adjacent projects that touch this work:

- **archive-lens** — historical cross-corpus keyword/entity/OCR dashboard. Related but separate from brasil-archives.
- **povos-indigenas-rn-corpus-explorer** — bilingual Indigenous history corpus for RN. Another candidate for the federation contract.
- **sao-jose-de-mipibu-corpus-explorer** — the older name for what's now stevewil/mipibu.
- **sitecraft** — the deployment-neutral CMS-to-static protocol. Potentially the substrate for a future brasil-archives public site.
- **ajme-cms** — local-first Flask CMS with private Wasabi media. Precedent for the Wasabi pattern.

---

## What still needs to happen

Framed by **what "beyond beta" actually means for this project**:

1. **The federation contract is real, not just designed.** At least Mipibu implements `/api/health`, `/api/schema`, `/api/records`, `/api/records/<id>` per `federation-v1.md`. A second corpus (povos-indigenas or another) implements the same contract, proving the design is portable.
2. **brasil-archives itself has a public face.** Not just design docs in a repo — an actual site that lists the scored archives, their scores, their federation status, and links to the companion apps. Even if it's a static site generated from the design docs.
3. **The corpus is legitimately hosted.** Wasabi bucket exists, corpus is uploaded, deploy pipeline is exercised end-to-end at least once. Rollback plan tested.
4. **A DATA.md or CONTENT.md exists per corpus repo** — the openness posture is articulated, not accidental. Takedown pathway documented.
5. **Tests exist.** The corpus explorer currently has zero tests. Even a smoke-test that hits every `/api/*` endpoint would raise the confidence floor substantially.
6. **A second scored archive gets probed.** The quarterly re-probe pattern in the survey is exercised at least once, proving the scoring is repeatable, not a one-off.
7. **Someone other than you can reproduce a deploy.** README + WASABI-SETUP + a fresh Wasabi account + a fresh cPanel host = working Mipibu. Not tested yet; probably has gaps.

Everything below is the sequenced path to get there.

---

## Sequenced TODO list

Ordered by **dependency and risk**, not by size. Each item lists what unblocks after it lands.

### Phase 1: Prove the Wasabi pipeline (unblocks everything else)

**1.1 Create the `mipibu-corpus` Wasabi bucket**
Console → new bucket, region us-west-2, versioning on, SSE-S3, public-read policy on `data/*`. Documented in [WASABI-SETUP.md](https://github.com/stevewil/mipibu/blob/main/WASABI-SETUP.md).
*Unblocks*: everything below.

**1.2 Create the `brasil-archives-data` Wasabi bucket**
Same steps, no public policy, empty. Provisioning cost is the same whether it's used or not.
*Unblocks*: future brasil-archives asset hosting.

**1.3 Create one Wasabi access key for mipibu-corpus**
Named `wasabi-mipibu-workstation-2026-08` for rotation clarity.
*Unblocks*: 1.4.

**1.4 Configure credentials on the workstation**
In Git Bash, in the mipibu repo:
```bash
git pull
bash deploy/mipibu-app.sh configure
```
Writes profile `wasabi-mipibu` to `~/.aws/credentials`.
*Unblocks*: 1.5.

**1.5 Upload the initial corpus DB**
```bash
bash scripts/sync-corpus.sh --upload-if-changed
bash scripts/sync-corpus.sh --status
```
All three SHAs (local, expected, remote) must match.
*Unblocks*: 1.6, 1.7.

**1.6 Enable the git hooks**
```bash
git config core.hooksPath .githooks
```
From this point on, `.sha256` changes trigger auto-upload; pushes verify Wasabi.
*Unblocks*: safe corpus refreshes.

**1.7 Exercise GitHub Actions**
Bump the `.sha256` file by regenerating from the current DB (should be no-op, produces the same value). Commit + push. Watch `verify-corpus` workflow go green.
*Unblocks*: confidence in CI.

### Phase 2: First real cPanel deploy

**2.1 Copy `mipibu-app.sh` to cPanel host**
SSH or File Manager → `~/bin/mipibu-app`, `chmod +x`. Verify `~/bin` in `PATH`.
*Unblocks*: 2.2.

**2.2 Create cPanel Python App**
Panel: `apps/mipibu-explorer`, Python 3.11, `passenger_wsgi.py`, entry `application`. **Do not** set env vars in the panel — panel writes to `passenger_wsgi.py`.
*Unblocks*: 2.3.

**2.3 Run `mipibu-app init`**
First-time bootstrap: clone, corpus fetch from Wasabi, rsync, pip install, seed `.env`, restart.
*Unblocks*: 2.4.

**2.4 Configure `.env` on cPanel host**
Edit `~/apps/mipibu-explorer/.env` with `SECRET_KEY`, `DATABASE_PATH`, `FLASK_DEBUG=0`, `DEFAULT_LANG`, `APP_VERSION`. Restart with `mipibu-app restart`.
*Unblocks*: 2.5.

**2.5 Smoke-test end-to-end**
Visit the app URL. Check that:
- Homepage loads bilingual UI
- `/api/stats` returns JSON with `record_count: 508`
- `/health` returns 200 (if that endpoint already exists — see 3.1)
- `mipibu-app status` reports green across the board
*Unblocks*: 3.x.

### Phase 3: Federation contract

**3.1 Add `/health` endpoint**
Currently no `/health` route exists. Simplest possible: returns `{status, archive_slug, record_count, schema_version, last_updated_at}`. Per `federation-v1.md`. Add to `app/views/main.py` or new `app/views/health.py`.
*Unblocks*: `mipibu-app status` health probe works cleanly; other apps have a reachability check.

**3.2 Add `/api/federation/schema` endpoint**
Returns the record-type field catalog. Namespace under `/api/federation/*` (safer than colliding with existing `/api/cases` etc.). Sources from a new `app/federation.py` module that declares the field mapping.
*Unblocks*: 3.3.

**3.3 Add `/api/federation/records` endpoint**
Paginated list with filters `record_type`, `date_from`, `date_to`, `subject`, `place`, `page`, `per_page` (cap 200). Maps existing `case_type` → federation `record_type`; wraps existing query functions.
*Unblocks*: 3.4.

**3.4 Add `/api/federation/records/<id>` endpoint**
Full record with normalized fields carrying `source_wording`, `provenance`, `confidence`. Uses existing `case_to_dict` presenter, extends with federation shape.
*Unblocks*: 3.5.

**3.5 Add smoke tests for all four endpoints**
Even minimal: `tests/test_federation_api.py` that hits each endpoint and asserts key fields present, pagination bounded, 404 on unknown ID. Uses Flask's test client, no live server needed.
*Unblocks*: refactor confidence.

**3.6 Deploy and verify against production**
`git push`, `mipibu-app pull` on cPanel, curl the federation endpoints from the internet. Publish the four URLs somewhere brasil-archives can reference.
*Unblocks*: Phase 4.

### Phase 4: brasil-archives goes public

**4.1 Choose the public brasil-archives site substrate**
Options:
- Static generation from the design docs (Sitecraft or MkDocs) — cheapest
- Small Flask app on cPanel with a Wasabi-hosted asset bucket — matches Mipibu pattern
- GitHub Pages from the brasil-archives repo — free but limited

*Decision needed. Recommend Sitecraft-based static, given your existing infra investment.*

**4.2 Design the archive catalog page**
Lists all scored archives with score, federation URL if applicable, `scholarly_access_practical` value, last probe date, primary contact link.

**4.3 Build the archive detail page template**
Per-archive: scores, standards conformance, federation status, screenshots (if available), notes, quarterly re-probe log.

**4.4 Publish to a real domain**
Wire DNS. Whether that's `brasil-archives.pplx.app`, a custom domain, or a subdirectory of another site is a routing decision.

**4.5 Add `DATA.md` and `CONTENT.md` per corpus repo**
Mipibu first. Articulates: what's in the corpus, provenance, our derivative annotations, CC-BY-SA norms, takedown pathway.

### Phase 5: Second corpus (proves portability)

**5.1 Choose the second corpus**
Candidates from your Knowledge Wiki:
- povos-indigenas-rn-corpus-explorer — bilingual, Indigenous history, RN scope, aligned with project focus
- A different Mipibu-adjacent set (LABIM has more collections)

*Recommend povos-indigenas — different record types stress the schema.*

**5.2 Implement the federation contract for the second corpus**
Reuse the pattern from Mipibu. If parts of `app/federation.py` are generic, extract into a small shared library (or copy-and-simplify — YAGNI is fine at N=2).

**5.3 Register the second corpus in brasil-archives**
Add its score, its federation URL, its detail page.

**5.4 Verify federation actually federates**
brasil-archives should be able to hit both `/api/federation/records` endpoints and present them as a unified search. Even minimally.

### Phase 6: Operational hardening

**6.1 Add a takedown-request pathway**
Per-corpus. A form or documented email address that flags a record ID. Corpus schema gains a `hidden` boolean per record. Federation endpoints filter it out.

**6.2 Add archive re-probe automation**
Quarterly cron on brasil-archives that walks each archive's `federation_url` (if any) and its public homepage, records reachability, flags changes.

**6.3 Add corpus regeneration automation**
Doc'd workflow for regenerating the Mipibu DB from source materials (LABIM records), running the pipeline, uploading. Currently manual.

**6.4 Add monitoring**
Health check ping to `/health` from an external source (uptimerobot, Better Stack, or a Perplexity cron). Alerts on outage.

**6.5 Write a `CONTRIBUTING.md` for both repos**
Even brief — how a collaborator would run tests, exercise the deploy pipeline, propose an archive addition.

### Phase 7: Beyond-beta polish

**7.1 Bilingual translations audit**
Ensure every user-facing string in Mipibu is properly translated both directions. Currently mixed.

**7.2 Accessibility pass**
Contrast, keyboard nav, ARIA. brasil-archives is an academic-audience site; accessibility matters.

**7.3 Search inside corpus**
Full-text search across Mipibu records. SQLite FTS5 is the obvious tool; probably already partially there.

**7.4 Citation export**
Per-record BibTeX / RIS / CSL-JSON export. Historians need this.

**7.5 IIIF integration**
If any of the archives (LABIM likely) expose IIIF manifests, wire viewers into the record detail pages. Referenced in `standards.md`.

---

## Design principles carried forward

Every decision in the roadmap defers to these, established across the sessions leading up to now:

1. **Northeast Brazil focus** — RN, PE, BA. Ecclesiastical archives are important. Resource-poor scholars are the design lens.
2. **National-period lens** — 1800–1900 primary, adjacent decades secondary. Age is not value.
3. **Fair use / uso justo is the floor** — scholarly access to public records is the moral baseline the project defends.
4. **Openness is deliberate** — "public because scholarly access is the floor," not "public because it happened to be in git."
5. **Pull-only servers** — production hosts never push, never commit, never authenticate to write anywhere.
6. **Credentials only on workstation** — one place credentials live. Everywhere else is anonymous or nothing.
7. **Content-addressed data** — SHA256 verification on every corpus fetch; mismatch fails the deploy.
8. **Two-axis aggregation** — archive identity and scholarly-access-practical stay separate concerns. Never fold one into the other.
9. **Bilingual PT/EN** — parity, not translation-as-afterthought. Portuguese source wording preserved with English gloss.
10. **MIT/Apache code, CC-BY-SA data** — license posture is explicit and consistent.
11. **Federation is opt-in per archive** — some archives are best represented by metadata alone; some need companion apps. `scenario-driven-federation-model.md` is the decision framework.
12. **Takedown is a first-class facet** — record-level `hidden` flag, documented pathway, no institutional gatekeeping.

---

## Repositories, buckets, and hosts

| Resource | Location | Purpose |
|---|---|---|
| brasil-archives repo | [github.com/stevewil/brasil-archives](https://github.com/stevewil/brasil-archives) | Design docs, archive catalog, scoring |
| mipibu repo | [github.com/stevewil/mipibu](https://github.com/stevewil/mipibu) | São José de Mipibu corpus explorer |
| mipibu-corpus Wasabi bucket | `s3://mipibu-corpus/data/*` (public-read), region us-west-2 | Corpus DB hosting |
| brasil-archives-data Wasabi bucket | private, region us-west-2 | Future asset hosting |
| Workstation | Windows + Git Bash, Git 2.53, AWS CLI v2 | Development + push |
| cPanel host | Serves https://mipibu.from-bottom-to.top/ from ~/apps/mipibu-explorer | Mipibu production runtime |
| Mipibu public URL | https://mipibu.from-bottom-to.top/ | Federation endpoints at /health, /api/federation/* |
| Mipibu archive slug | `sao-jose-mipibu-judicial-1850-1888` (proposed) | Stable identifier used in /health responses and brasil-archives catalog |
| GitHub Actions | Per-repo | CI verification |

---

## Deferred decisions

Things we've deliberately not chosen yet, and what triggers the choice:

- **brasil-archives public site substrate** (Sitecraft/MkDocs/Flask/Pages). Trigger: starting Phase 4.
- **Custom Wasabi domain** (`corpus.mipibu.from-bottom-to.top` vs default `s3.us-west-2.wasabisys.com`). Trigger: any operational reason the default URL becomes awkward — SEO, sharing, branding.
- **Federation URL prefix** (`/api/federation/*` vs sibling `/api/records`). Provisionally: `/api/federation/*` to avoid collision with existing `/api/cases`. Confirm in Phase 3.
- **Second corpus choice** (povos-indigenas vs other). Trigger: end of Phase 4.
- **Corpus-DB-in-Wasabi vs later migration to Git LFS**. Current answer: Wasabi. Reconsider if Wasabi cost model changes.
- **Test framework** (pytest vs plain unittest). Trigger: Phase 3.5. Recommend pytest.
- **Archive re-probe cadence** (quarterly per survey vs more frequent). Trigger: Phase 6.2.

---

## Reading order for someone new to the project

1. This document
2. `nordeste-digital-archives-survey.md` (context: what archives exist and how they score)
3. `schema-v1.md` and `adr-0001-two-axis-aggregation.md` (why the schema looks the way it does)
4. `federation-v1.md` and `scenario-driven-federation-model.md` (why federation exists and when it's warranted)
5. `stevewil/mipibu` — [README-CPANEL-DEPLOY.md](https://github.com/stevewil/mipibu/blob/main/README-CPANEL-DEPLOY.md) and [WASABI-SETUP.md](https://github.com/stevewil/mipibu/blob/main/WASABI-SETUP.md)
6. Code: `app/views/api.py`, `app/queries.py`, `app/presenters.py` in the mipibu repo
