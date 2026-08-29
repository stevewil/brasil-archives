# Handoff — 2026-08-29 (search shipped · licensing WIP · admin/toggle scoped)

**Read `docs/handoff/2026-08-27-master.md` first** for ecosystem
orientation. This file is the pickup brief for the work in flight right
now.

---

## 1. Where things stand

| Repo | `main` | Deployed | Tests |
|---|---|---|---|
| brasil-archives | **`e2355c3`** | cPanel current + verified | 304 passed / 4 skipped |
| povos-indigenas-rn | **`e73a892`** | cPanel current + verified | 148 passed |

Both cPanel checkouts are clean and current. povos's checkout had
`core.autocrlf` / `core.filemode` set to `false` this session to stop
phantom-modification pull failures (see the memory note
`cpanel-phantom-modifications`).

### Shipped this session (all live)

- **Federated search** — `GET /search`, public, over harvested `oai_dc`
  partner records. Accent/case-insensitive, strong/weak match tiers,
  per-partner facet chips, pagination, bilingual. Curated `SAMPLE_QUERIES`
  chip row on the empty/no-results states.
  `app/services/federated_search.py`, `app/templates/search.html`,
  `docs/federated-search.md`, `docs/federated-search-keywords.md`.
- **Catalog text search** — `GET /archives/?q=` free-text over
  name / description / scope / city, composes with the existing filters.
  `app/text.py` `fold()` (accent folding) is shared by both searches.
- **Deep-link fix** — search results now link to a real record page, not
  the partner home page. `oai_dc` extractor captures `dc:source` into
  `canonical.source_urls`; `_links()` falls through on-host → off-host →
  `dc:source` → home. povos `passage` records emit their parent
  document's URL (`e73a892`). New `scripts/reextract.py` re-derives
  `extracted_json` from stored raw XML without a re-fetch — run it
  whenever an extractor changes; `github-pull` prints the reminder.

---

## 2. Work in progress — LICENSING (uncommitted on disk)

Decisions are **locked** (confirmed with Steve this session):

- **Code → MIT.** Matches `docs/federation-v1.md` and the mipibu/povos
  registration YAMLs.
- **Curated data → CC BY 4.0** (attribution only — no share-alike, no
  responsible-use covenant). Covers *the Nordeste survey + the controlled
  vocabularies*. Steve's call: share-alike is unnecessary friction for a
  project meant to be reused by resource-poor scholars.
- **The scoring output stays non-public** (see item 2) and is deliberately
  *not licensed yet* — `LICENSING.md` says its license will be named when
  the judgments are trustworthy enough to publish (expected CC BY 4.0).
- Copyright holder: **"The Brasil Archives Project contributors"**, year
  **2026**.

### Files already written + committed WIP

| File | State |
|---|---|
| `LICENSE` | MIT text + a note that it covers code only, pointing at `LICENSE-CC-BY-4.0.txt` |
| `LICENSE-CC-BY-4.0.txt` | Full canonical CC BY 4.0 legalcode (fetched via `curl` from creativecommons.org — 18,657 bytes, verified complete: ends with the CC trademark notice) |
| `LICENSING.md` | The explainer: the split, what's "curated data", the non-public scoring output, what's *not* covered (harvested partner records carry their own licenses; source archives' holdings; fonts), attribution text, the non-binding "no surveillance / no mass reproduction" request, contributions inbound=outbound, history |

### Remaining edits for "finish + commit licensing" (scoped item 1)

1. `README.md` §License (lines ~62-64) — replace the "TBD" paragraph:
   MIT for code, CC BY 4.0 for the survey + vocabularies, scoring output
   unlicensed-and-unpublished for now. Link `LICENSE` + `LICENSING.md`.
2. `docs/algorithm-v1.md` §Licensing (lines ~248-256) — "finalized
   2026-08-29, see `LICENSING.md`"; note the share-alike and RAIL ideas
   were dropped, and that the scoring output's license waits on public
   release.
3. `DESCRIPTION.md` line ~304 — `Code: MIT/Apache. Derived data: CC-BY-SA.`
   `(Finalized before public release.)` → `Code: MIT. Survey + vocab data:
   CC BY 4.0. Scoring output: unpublished, license TBD. (LICENSING.md,
   2026-08-29.)`
4. `TODO.md` §7 — check off the licensing item (currently `[~]`).
5. Commit: `docs(licensing): MIT for code, CC BY 4.0 for the survey data`.

### Context that motivated the next two items

Steve asked whether the licenses release him from liability for downstream
use. Answer given: the MIT/CC "as is / no liability" clauses run **from
licensor to licensee** and shield against *reuser* claims about the
code/data — they are **not** a general shield. They don't touch: third
parties who never took the license (e.g. a catalogued institution
objecting to a "fails fair use" or low-score judgment — defamation /
disparagement territory), non-waivable liability (Brazil CDC, EU), or the
project's own upstream obligations. **The real 1.0 liability surface is
publishing scored judgments about named real organizations under the
project's name.** Hence:

---

## 3. Scoped TODO for the resume session (in order)

### Item 1 — Finish + commit licensing  ✅ DONE 2026-08-29
See §2 above.

### Item 2 — Public-scores visibility toggle  `[M]`

**Goal:** soft-launch the catalog + federated search now; keep the scored
judgments private until Steve greenlights them. Independent of the
existing `BRASIL_ARCHIVES_ADMIN` flag.

- **Config** (`app/config.py`): add to `BaseConfig`
  `PUBLIC_SCORES_ENABLED = os.environ.get("BRASIL_ARCHIVES_PUBLIC_SCORES") == "1"`
  (default **off**). Add `PUBLIC_SCORES_ENABLED = True` to `TestingConfig`
  so the existing score-display tests keep passing; new gate tests build
  their own app with it off (mirror `tests/test_admin_gate.py` /
  `public_app` fixture).
- **Jinja global** (`app/__init__.py`): `public_scores_enabled()` like
  `admin_ui_enabled()`. Effective "show scores" =
  `public_scores_enabled() or admin_ui_enabled()`. Consider passing a
  single `show_scores` bool from the views instead of two globals.
- **Templates / views to thread through:**
  - `app/templates/archives/detail.html` — gate the entire
    `<section class="score-summary">` (Score profile / axis-card /
    Quadrant, lines ~48-80) **and** the `<section class="dimensions">`
    public read-only table (lines ~82-126). When hidden, show a neutral
    one-liner (new msgid, e.g. "Evaluation in progress" / "Avaliação em
    curso"). The admin editing UI below stays gated by `admin_ui_enabled()`
    as today.
  - `app/templates/archives/list.html` — drop the Pipeline / Research /
    Naive sum / Dims `<th>`+`<td>` (lines ~59-77) and the score `<option>`s
    in the Sort `<select>` (lines ~42-44). Lede text (line 8) mentions
    axis totals — needs a no-scores variant.
  - `app/blueprints/archives/routes.py` — `list_archives` still builds the
    score subquery (admin needs it); pass `show_scores`. `detail` already
    computes everything; template gates.
  - `app/templates/index.html` — "Featured archives" section (lines
    ~51-75) is score-ranked with `Score N/80` badges. When scores hidden:
    either drop the section or re-title it ("Archives in the catalog") and
    re-rank neutrally.
  - `app/blueprints/main.py` — `_featured_archives()` ranks by naive sum
    (lines ~48-80). Add a neutral ordering (name, or `created_at desc`)
    when scores are hidden, and don't emit the `naive_sum` badge.
- **"Observed signals" probe facets** (detail.html line ~230) — these are
  observational ("last checked", web-ops health), not judgments.
  Recommendation: **keep them public** even when scores are hidden.
  Confirm with Steve.
- **i18n**: new msgid(s) → `pybabel extract -F babel.cfg -k _l …` +
  `update` + translate `pt` + `compile`. (`.mo` is git-ignored; deploy
  runs `pybabel compile`.)
- **Tests**: `tests/test_public_scores_gate.py` — flag off + not admin:
  `/archives/` has no "Pipeline" header, detail has no "Quadrant" /
  "Score profile", home has no `/80` badge; flag on OR admin: all present.
- **Deploy note**: `BRASIL_ARCHIVES_PUBLIC_SCORES` stays **unset** on the
  public cPanel host until greenlit; document it next to
  `BRASIL_ARCHIVES_ADMIN` in `docs/DEPLOY.md` and `app/config.py`.

### Item 3 — Read-only admin dashboard  `[M]`

**Not** a write-capable CRUD panel — see the "why I pushed back" reasoning
below. A single observability page behind the existing gate.

- New blueprint `app/blueprints/admin/` →
  `Blueprint("admin", __name__, url_prefix="/admin")`, `@admin_only` on
  the index. Register in `app/__init__.py` (and CSRF-exempt is not needed
  — no forms).
- `GET /admin/` renders one dashboard:
  - **Scoring coverage** — archives with active scores / total
    pipeline-viable (`fair_use_eligible is not False`,
    `no_digital_content is False`); Pass 2 vs Pass 3 split if cheap.
  - **Harvest** — last ~10 `HarvestRun` rows (reuse the query in
    `app/blueprints/harvest/routes.py::index`) or just link to `/harvest/`.
  - **Probe** — count probed, most recent `Archive.last_probed_at`, any
    `ProbeResult` rows flagged as failures.
  - **Federation health** — `federation.preview(p)` per `UpgradeProject`.
  - **Recent errors** — last ~10 `HarvestError`.
- Admin-only nav link in `base.html`.
- Tests: `tests/test_admin_dashboard.py` — 200 for admin app, 404 when
  `ADMIN_UI_ENABLED` is off.
- Mostly useful on the **local** checkout ("local is primary").

### Item 4 — Archive-draft form (lowest priority; confirm value first)

`scripts/load_survey.py` parses **`docs/nordeste-digital-archives-survey.md`**
(a markdown table — Table 1 pipeline-viable, Table 2 no-content). Archives
beyond the survey (e.g. `povos-indigenas-rn-corpus`) come from
`scripts/seed_povos_archive.py`.

**The prod SQLite DB is not durable (it gets reseeded).** Anything written
directly to the prod DB and not in a git-tracked source is lost on the
next reseed — the recovery runbook is entirely YAML/script/markdown-based.
So a form must **generate a reviewable draft** (a new markdown survey row,
or a `configs/` YAML snippet), rendered on the page for copy-paste +
commit — **never write the `archives` table directly**. If the script
workflow isn't actually painful, this item can be dropped.

---

## 4. Why a full write-capable /admin/ was pushed back

1. **Non-durable prod DB** — direct DB writes on prod vanish on reseed.
2. **"Config lives in YAML, loaded by idempotent scripts"** is a stated
   convention; the survey markdown is a reviewed audit trail.
3. **Minimal prod attack surface** — today, flag unset → every admin route
   404s. A real panel needs login/sessions/password (none exist) to be
   safe on shared hosting.
4. **"Local is primary, cPanel is public mirror"** — admin work belongs on
   the local checkout, then deploy.

The dashboard (item 3) sidesteps all four: read-only, env-gated, no auth,
no new write paths.

---

## 5. Key files

| Concern | File |
|---|---|
| Existing env gate + `@admin_only` | `app/blueprints/_admin_gate.py` |
| Config flags | `app/config.py` (`BaseConfig`, `TestingConfig`) |
| Jinja globals | `app/__init__.py` (`admin_ui_enabled` etc.) |
| Score display (public read-only) | `app/templates/archives/detail.html` §score-summary, §dimensions |
| Score columns | `app/templates/archives/list.html` |
| Featured-by-score | `app/blueprints/main.py::_featured_archives` |
| Gate test pattern | `tests/test_admin_gate.py` (`public_app` fixture) |
| Survey loader (markdown source) | `scripts/load_survey.py`, `docs/nordeste-digital-archives-survey.md` |
| Licensing | `LICENSE`, `LICENSE-CC-BY-4.0.txt`, `LICENSING.md` |

---

## 6. Safe to clear?

Yes. The three licensing files (`LICENSE`, `LICENSE-CC-BY-4.0.txt`,
`LICENSING.md`) plus the `README` / `algorithm-v1` / `DESCRIPTION` pointer
updates all landed (scoped item 1 done 2026-08-29). Local DB is reextracted
+ reharvested and matches prod.
