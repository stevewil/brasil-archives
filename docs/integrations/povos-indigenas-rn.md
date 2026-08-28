# Integrating povos-indigenas-rn as an upgrade project

**Perspective:** brasil-archives side. What we do to accept povos as a
federated partner. The mirror-image doc lives at
[`povos-indigenas-rn/docs/INTEGRATION.md`](https://github.com/stevewil/povos-indigenas-rn/blob/main/docs/INTEGRATION.md)
and covers povos's side (what endpoints povos must expose).

**Status:** **LANDED 2026-08-28.** `scripts/seed_povos_archive.py` +
`configs/upgrade_projects/povos-indigenas-rn.yaml` +
`tests/test_load_povos.py` (3 tests). povos is upgrade project #2; the
live federation preview on `/archives/povos-indigenas-rn-corpus` fetches
`/api/health` and shows `record_count: 40`. Deploy: cPanel pull + run the
seed + `load_upgrade_projects` (in `docs/DEPLOY.md`). First povos harvest
cycle (`oai_pmh_base_url` is already set) is the remaining follow-up.
The design notes below are kept as the record of the bootstrap.

> **Read this alongside:**
> - [`../federation-v1.md`](../federation-v1.md) — the federation contract povos must speak.
> - [`../harvest-design.md`](../harvest-design.md) — how brasil-archives harvests OAI-PMH into `aggregated_records`.
> - [`../handoff/2026-08-27-master.md`](../handoff/2026-08-27-master.md) — ecosystem overview and standing constraints.
> - [`povos INTEGRATION.md`](https://github.com/stevewil/povos-indigenas-rn/blob/main/docs/INTEGRATION.md) — the mirror doc on povos's side.
> - [`configs/upgrade_projects/mipibu.yaml`](../../configs/upgrade_projects/mipibu.yaml) — the reference registration to copy shape from.

---

## Why this doc exists

Once povos is deployed and federating, integration is *mechanical* — a YAML
file and one script run. But there's a **blocker** discovered on 2026-08-27
that will trip up anyone who tries the mechanical steps without reading this
first: **povos has no source_archive row**, and `upgrade_projects.source_archive_id`
is NOT NULL. This doc spells out the bootstrap.

It also documents what brasil-archives *does* with povos's endpoints, so we
don't have to reverse-engineer that during integration.

## 1. What we get from povos

Povos, once federated, exposes two surfaces we consume:

### Federation JSON contract v1

Four endpoints under `https://povos-indigenas-rn.from-bottom-to.top/api/`:

| Endpoint | Consumed by brasil-archives for |
|----------|---------------------------------|
| `GET /api/health` | Federation-preview card on archive detail page: corpus version, record count, up/degraded status |
| `GET /api/schema` | Nothing yet (informational; future contract-drift detection) |
| `GET /api/records` | Deep-link into povos's browse UI from brasil-archives |
| `GET /api/records/<id>` | Nothing yet (available for future cross-corpus record inspection) |

All four are cached by `app/models/federation_cache.py` with TTL 900 s.

### OAI-PMH endpoint

`https://povos-indigenas-rn.from-bottom-to.top/oai` — consumed by the
harvest runner (`app/services/harvest.py`) to populate
`aggregated_records`. This is Phase 3 Track 2 territory, already implemented
and working for mipibu.

## 2. Ordering — do these steps in exactly this order

The mechanical steps below fail in confusing ways if reordered.

1. **Wait for povos to deploy.** Live at `https://povos-indigenas-rn.from-bottom-to.top`, `/health` returns `status:"ok"`. See [`povos DEPLOY.md`](https://github.com/stevewil/povos-indigenas-rn/blob/main/docs/DEPLOY.md).
2. **Wait for povos federation JSON endpoints.** `curl https://povos-indigenas-rn.from-bottom-to.top/api/health` must return `federation_contract_version: "v1"`. If it 404s, povos hasn't shipped §2 of their INTEGRATION.md yet — stop and unblock that first.
3. **Confirm the `research-project` institutional type exists** in `configs/vocabularies/institutional_types.yaml`. If not, add it (bilingual label) and re-run `python -m scripts.load_vocabularies`.
4. **Seed the archives row** for povos's composite source (§3).
5. **Commit `configs/upgrade_projects/povos-indigenas-rn.yaml`** (§4).
6. **Run `python -m scripts.load_upgrade_projects`** — idempotent upsert.
7. **Verify locally.** `curl http://localhost:5001/archives/povos-indigenas-rn-corpus` should render with a federation-preview block.
8. **Push, pull on cPanel, restart.** See [`../DEPLOY.md`](../DEPLOY.md).
9. **Verify live.** `curl https://brasil-archives.from-bottom-to.top/` should show the upgrade-projects counter at 2. `curl .../archives/povos-indigenas-rn-corpus` should include povos's live record count.
10. **(Later)** When povos OAI-PMH lands, extend the YAML with `oai_pmh_base_url` and run one harvest cycle (§5).

## 3. Archives-row bootstrap

**The blocker.** `upgrade_projects.source_archive_id` is NOT NULL. Every
upgrade project must reference a row in `archives`. Povos's source is a
composite — AHU (Portugal), CRL, UFRN — not a single row in the current
survey. We add an explicit composite row.

### 3a. Recommended: seed script committed to the repo

New file: `scripts/seed_povos_archive.py`

```python
"""Seed the composite archives row for povos-indigenas-rn.

The povos corpus is assembled from multiple institutional holdings
(AHU / CRL / UFRN) rather than a single fonds. This script adds one
'archive' row that represents that composite so the povos upgrade
project has a source to point at.

Idempotent: safe to re-run.
"""
from app import create_app
from app.extensions import db
from app.models import Archive


def main() -> None:
    app = create_app()
    with app.app_context():
        slug = "povos-indigenas-rn-corpus"
        existing = Archive.query.filter_by(slug=slug).first()
        if existing:
            print(f"already present: {slug} (id={existing.id})")
            return

        row = Archive(
            slug=slug,
            name="Povos Indígenas do RN — corpus",
            name_pt="Povos Indígenas do RN — corpus",
            home_state_code="RN",
            institutional_type="research-project",   # must exist in vocab
            no_digital_content=False,
            canonical_url="https://povos-indigenas-rn.from-bottom-to.top",
            notes=(
                "Composite corpus assembled from AHU (Portugal), CRL, "
                "and UFRN holdings. Not a single fonds; the 'archive' "
                "here is the assembled evidence base surfaced by the "
                "povos-indigenas-rn corpus explorer app."
            ),
        )
        db.session.add(row)
        db.session.commit()
        print(f"added: {slug} (id={row.id})")


if __name__ == "__main__":
    main()
```

Run:

```bash
cd /home/user/workspace/brasil-archives
DATABASE_URL=sqlite:///$(pwd)/instance/brasil_archives.db \
FLASK_APP=wsgi.py python scripts/seed_povos_archive.py
```

Commit it. `configs/upgrade_projects/povos-indigenas-rn.yaml` will resolve
its `source_archive_slug` against this row.

### 3b. Vocabulary prerequisite

Confirm `research-project` (or your chosen slug) is in
`configs/vocabularies/institutional_types.yaml`. Check with:

```bash
grep -c "^  - slug: research-project" configs/vocabularies/institutional_types.yaml
```

If it's not there, add it before running the seed script:

```yaml
  - slug: research-project
    label_en: Research project / corpus
    label_pt: Projeto de pesquisa / corpus
```

Then `python -m scripts.load_vocabularies`.

## 4. The upgrade-project YAML

New file: `configs/upgrade_projects/povos-indigenas-rn.yaml`

```yaml
# Povos Indígenas do RN Corpus Explorer — upgrade project registration.
# See docs/federation-v1.md §Registration for the schema.
# See docs/integrations/povos-indigenas-rn.md for the bootstrap sequence.

slug: povos-indigenas-rn
name: Povos Indígenas do RN Corpus Explorer
name_pt: Explorador do Corpus dos Povos Indígenas do RN

# Resolves against the composite row seeded by scripts/seed_povos_archive.py.
source_archive_slug: povos-indigenas-rn-corpus

scope:
  description_en: >
    Documents, community records, essays, and academic works pertaining
    to the indigenous peoples of Rio Grande do Norte, drawing from AHU
    (Portugal), CRL (Center for Research Libraries), and UFRN holdings.
  description_pt: >
    Documentos, registros de comunidades, ensaios e trabalhos acadêmicos
    sobre os povos indígenas do Rio Grande do Norte, com fontes em AHU
    (Portugal), CRL (Center for Research Libraries) e UFRN.
  period_tags:
    - colonial-1500-1815         # confirm slugs against periods.yaml
    - imperio-1822-1889
    - old-republic-1889-1930
  record_types:
    - indigenous-history         # add to record_types.yaml if missing
  geography:
    - name: Rio Grande do Norte
      geonames_id: 3451189
  approximate_size:
    document_count: 40           # confirm against povos /api/stats at load time
    page_equivalents: null

delivery:
  primary_url: https://povos-indigenas-rn.from-bottom-to.top
  source_repo: https://github.com/stevewil/povos-indigenas-rn
  status: beta

federation:
  json_api_base_url: https://povos-indigenas-rn.from-bottom-to.top/api
  # Set to null until povos ships OAI-PMH (see povos/docs/OAI-PMH-PICKUP.md).
  oai_pmh_base_url: null
  iiif_search_endpoint: null
  ead_export_url: null
  eac_cpf_export_url: null
  supported_metadata_formats:
    - oai_dc
  supported_authorities:
    - viaf
    - geonames

license:
  code: MIT
  data: CC-BY-SA-4.0
  attribution_required: true

maintainer:
  name: Steve Williams
  contact_email: stevewil@gmail.com

# Dimension lifts: filled during Pass 2. Empty map = no lifts declared yet.
lifts: {}
```

**Vocabulary prerequisites to double-check before loading:**

- `periods.yaml` includes `colonial-1500-1815`, `imperio-1822-1889`, `old-republic-1889-1930` (or equivalent slugs — align with what's actually in the file).
- `record_types.yaml` includes `indigenous-history` — add it if missing:

```yaml
  - slug: indigenous-history
    label_en: Indigenous history sources
    label_pt: Fontes de história indígena
```

Then `python -m scripts.load_vocabularies` before `load_upgrade_projects`.

## 5. What happens after registration

Once the loader runs cleanly, brasil-archives immediately does the following
without further code changes:

### 5a. Home page counter

`/` shows a stat: "Upgrade projects: 2" (was 1). This is a live count from
the `upgrade_projects` table, not hardcoded. Verified by `curl / | grep -i upgrade`.

### 5b. Archive detail page federation preview

Navigate to `/archives/povos-indigenas-rn-corpus`. The template
`app/templates/archives/detail.html` renders an upgrade-projects section
that fetches from povos's `/api/health` (cached 15 min) and shows:

- Corpus version (sha256 prefix)
- Live record count
- Status badge (ok / degraded / unreachable)
- Deep-link to povos's HTML `/documents` page

If povos is offline, brasil-archives shows a muted "federation unavailable"
panel — no error page. This is `app/services/federation.py`'s fault-tolerance.

### 5c. Harvest — only after OAI-PMH lands on povos

Once povos ships §3 of their INTEGRATION.md (OAI-PMH endpoint at `/oai`):

1. Edit `configs/upgrade_projects/povos-indigenas-rn.yaml`:
   ```yaml
   oai_pmh_base_url: https://povos-indigenas-rn.from-bottom-to.top/oai
   ```
2. Re-run `python -m scripts.load_upgrade_projects`.
3. Do a dry run first:
   ```bash
   python scripts/harvest.py --project povos-indigenas-rn --dry-run
   ```
   Expected: fetches, parses, writes nothing. Reports record count and any
   parse errors.
4. Real harvest:
   ```bash
   python scripts/harvest.py --project povos-indigenas-rn
   ```
5. Verify:
   ```bash
   python -c "
   from app import create_app
   from app.extensions import db
   from app.models import AggregatedRecord
   app = create_app()
   with app.app_context():
       print('total:', db.session.query(AggregatedRecord).count())
       print('povos:', db.session.query(AggregatedRecord).join(AggregatedRecord.upgrade_project).filter_by(slug='povos-indigenas-rn').count())
   "
   ```

The harvest reuses the same extractor path mipibu goes through. If povos's
`oai_dc` output is spec-compliant, no code changes needed on the brasil-archives side.

## 6. Verify end-to-end

After steps 1–9 in §2, this checklist must pass:

- [ ] `curl -s https://brasil-archives.from-bottom-to.top/ | grep -oE 'upgrade[^0-9]*[0-9]+'` shows `2`
- [ ] `curl -sI https://brasil-archives.from-bottom-to.top/archives/povos-indigenas-rn-corpus` returns 200
- [ ] That page contains "povos-indigenas-rn" and a nonzero record count from the federation preview
- [ ] `SELECT COUNT(*) FROM upgrade_projects` on the live DB returns 2
- [ ] `SELECT slug FROM archives WHERE slug = 'povos-indigenas-rn-corpus'` returns one row
- [ ] `tail app/logs/*` shows no federation-fetch errors
- [ ] `pytest -q` still green after adding the seed script and YAML

## 7. Testing

New `tests/test_load_povos.py` — integration test for the loader:

```python
def test_load_povos_upgrade_project(app, db_session):
    """Loading povos-indigenas-rn.yaml creates the upgrade project row
    and links to the seeded archives row."""
    from scripts.seed_povos_archive import main as seed
    from scripts.load_upgrade_projects import load_all
    seed()
    load_all()
    from app.models import UpgradeProject, Archive
    p = UpgradeProject.query.filter_by(slug="povos-indigenas-rn").one()
    assert p.source_archive.slug == "povos-indigenas-rn-corpus"
    assert p.status == "beta"
    assert p.json_api_base_url.startswith("https://")
```

Add to `conftest.py`'s fixtures if the seed script needs a specific app-context setup.

## 8. Anti-patterns — do not do these

- **Don't skip the archives-row seed** — the loader will raise a NOT NULL
  IntegrityError on `source_archive_id` and leave the DB in a mixed state.
- **Don't set `oai_pmh_base_url`** in the YAML until povos actually
  serves `/oai`. A stale URL will make the harvest runner appear broken.
- **Don't invent a new vocab slug on the fly** — add it to the YAML in
  `configs/vocabularies/` first, run `load_vocabularies`, then load the
  upgrade project. The YAML loader validates slugs against the vocab tables.
- **Don't hand-edit `upgrade_projects` rows in SQLite.** The whole point of
  the YAML flow is that `main` on GitHub is the source of truth. If you have
  to change a field, edit the YAML and re-run the loader.
- **Don't add a second archives row per source institution (AHU/CRL/UFRN).**
  Povos is the composite. If we later catalog those source institutions
  individually, they get their own separate rows with their own scores.

## 9. What we get in return

Once integrated, brasil-archives has demonstrated:

- N=2 upgrade projects federating cleanly (was N=1).
- The federation contract v1 handled a second, differently-shaped corpus
  without protocol changes.
- The aggregated-records store handled multi-project harvest.
- The upgrade-projects counter is honest (was `1` reflecting DB truth; now `2` legitimately).

This is what unblocks Phase 4 conversations — "should we generalize the OAI
package" (see [`povos HANDOFF-2026-08-26.md`](https://github.com/stevewil/povos-indigenas-rn/blob/main/docs/HANDOFF-2026-08-26.md) §"Package extraction plan").
Rule of three: with two working callers we can find the real seams; with one
we'd have guessed.

## 10. Estimated effort (brasil-archives side)

Assuming povos has already deployed and shipped its federation JSON:

| Step | Effort |
|------|--------|
| `scripts/seed_povos_archive.py` + commit | ~30 min |
| Vocabulary additions (if needed) | ~15 min |
| `configs/upgrade_projects/povos-indigenas-rn.yaml` + commit | ~30 min |
| Load + local verify | ~15 min |
| Push, cPanel pull, restart, live verify | ~15 min |
| `tests/test_load_povos.py` | ~30 min |
| **Total (federation JSON only)** | **~2 hours** |
| (Later) OAI-PMH URL wire-up + harvest verify | ~30 min |
