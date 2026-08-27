# Public UI Polish — Pickup Brief

**Status:** 4 of 5 tracks landed (2, 3, 4, 5). Only Track 1 (i18n
catalog) remains. Continuing in focused batches.
**Scope:** Take `brasil-archives` from "working internal tool" to "coherent public site."

> **See also:** [`docs/handoff/2026-08-27-master.md`](handoff/2026-08-27-master.md) — the master handoff for the whole three-repo ecosystem. This document zooms into the five UI-polish tracks.

---

## Progress

**4 of 5 tracks landed** (2, 3, 4, 5). Remaining: 1.

| Track | Status | Commit | Deployed |
|-------|--------|--------|----------|
| 1 — i18n catalog | In progress | — | — |
| **2 — Admin gating** | **✅ Landed 2026-08-27** | `f60dfe6` | Yes — `/harvest/` 404s live, no nav link |
| **3 — Home redesign** | **✅ Landed 2026-08-27** | `ed381fd` | Not yet — pending cPanel pull |
| **4 — Locale-aware vocab labels** | **✅ Landed 2026-08-27** | `a981b60` | Yes, verified via curl |
| **5 — Metadata + inline-style cleanup** | **✅ Landed 2026-08-27** | `ad8c7d7` | Yes — pulled 2026-08-27 |

## Why the remaining tracks are staged, not one big push

Multi-hour multi-file rewrite spanning five independent tracks. Landing Track 4 (2026-08-27) validated the pipeline: local → GitHub → cPanel pull → curl verify. Each remaining track is independently landable and independently useful. Session budget determines how many land per session.

## Current state (verified 2026-08-27)

- **HEAD:** `a981b60` on `main`, clean.
- **Live URL:** `https://brasil-archives.from-bottom-to.top` (Track 4 verified via curl for both EN and PT).
- **Server:** `http://localhost:5001` runs via
  `DATABASE_URL=sqlite:////home/user/workspace/brasil-archives/instance/brasil_archives.db FLASK_APP=wsgi.py flask run --port 5001 --no-reload`
  (system `flask`, not `.venv/bin/flask` — no venv exists).
- **Tests:** 142 passed, 4 opt-in live skipped (up from 130 pre-Track-4).
- **Data:** 79 archives, 1 upgrade project (mipibu), 1016 aggregated records.
  All `DimensionScore`, `DimensionLift`, `FacetValue` tables empty — so
  detail pages show many `—` placeholders.
- **Babel:** wired (`app/__init__.py:_select_locale`), config sets
  `LANGUAGES=["en","pt"]`, default `en`. `pybabel` 2.18.0 available at
  `/home/user/.local/bin/pybabel`. **No `translations/` directory exists** —
  every `_()` call currently renders the English msgid. The PT/EN switcher
  in `base.html` sets `<html lang>` but doesn't translate any body text.
- **Vocabulary labels (Track 4):** every `x.label_en` in `list.html` and
  `detail.html` now goes through `vocab_label(x)` (Jinja global registered in
  `app/__init__.py`). Falls back to EN when a PT label is missing.

## Token-efficient tooling proposal (do this BEFORE Tracks 1, 2, 5)

**Context:** During the 2026-08-27 session the user asked why polish tracks are so token-expensive. The answer, and a concrete proposal, are in [`docs/handoff/2026-08-27-master.md` §5](handoff/2026-08-27-master.md#5-ui-polish-token-efficient-tooling-proposal). Summary:

1. **`scripts/dev/session_state.sh`** — bootstrap digest so a new session doesn't spend ~5k tokens re-discovering state. Prints git status, test count, live URL health, DB counts.
2. **`scripts/dev/wrap_i18n.py`** — codemod that wraps bare text nodes in `{{ _() }}`. Handles the mechanical bulk of Track 1's ~100 template edits.
3. **`tests/test_template_hygiene.py`** — grep-based linter that fails if `label_en`/`label_pt` sneak back into templates (protects Track 4) and eventually if inline styles do (protects Track 5).

Estimated savings across the remaining four tracks: 40–80k tokens.

**Suggested commit order for next session(s):**

1. `chore(dev): tooling for token-efficient polish work` — the three scripts above.
2. Track 5.
3. Track 2.
4. Track 3.
5. Track 1 (heaviest; consider the scaffolding-only variant — agent produces `.pot` + skeleton `.po`, user fills PT translations in a text editor).


## What "polish the public UI" means, concretely

Five independent tracks. Do them in this order; each is landable alone.

### Track 1 — i18n catalog (foundational)

**Problem:** `_()` calls exist in `base.html` and `index.html` but no
translation catalog exists, so PT selection does nothing. `list.html` and
`detail.html` have zero `_()` calls — hard-coded English.

**Deliverable:** working PT translations end-to-end.

**Steps:**

1. Verify `babel.cfg`:
   ```
   [python: app/**.py]
   [jinja2: app/templates/**.html]
   extensions=jinja2.ext.i18n
   ```
2. Wrap all remaining hard-coded strings in `_()`:
   - `app/templates/archives/list.html` (~30 strings — filters, table
     headers, badges, empty state, page header lede)
   - `app/templates/archives/detail.html` (~50 strings — section headings,
     dimension labels, facet labels, form labels, federation-preview copy)
   - `app/templates/archives/facets.html` (~15 strings, if this stays
     public; see Track 2)
   - `app/templates/harvest/*.html` (only if harvest stays public; see
     Track 2)
3. From repo root: `pybabel extract -F babel.cfg -o messages.pot .`
   (must run from repo root or pybabel misses the templates via the
   mapping — verified 2026-08-26.)
4. `pybabel init -i messages.pot -d app/translations -l pt`
5. `pybabel init -i messages.pot -d app/translations -l en` (default source
   is EN, but a catalog anchors it for coherent updates)
6. Translate `app/translations/pt/LC_MESSAGES/messages.po`. Estimated
   ~100 strings total. Use domain-consistent vocabulary:
   - "Archive" → "Arquivo" (in the digital-archive sense; not "arquivo" as
     in file)
   - "Pipeline axis" → "Eixo de pipeline" (keep "pipeline" — Brazilian
     archivists use the English term for the ETL sense)
   - "Research axis" → "Eixo de pesquisa"
   - "Naive sum" → "Soma ingênua" or "Soma não-ponderada" (project has been
     using the latter in prose)
   - "Fair use eligibility" → "Elegibilidade para uso justo" (project
     insists on "uso justo," not "uso legítimo")
   - "Digital content" → "Conteúdo digital"
   - "Finding aids" → "Instrumentos de pesquisa"
   - "Provenance & curatorial" → "Proveniência e curadoria"
7. `pybabel compile -d app/translations`
8. Add `.gitignore` entry for `*.mo` if you'd rather ship source `.po` and
   compile at build (recommended for cPanel deployment). Or check `.mo`
   into git for simpler deploys — user preference.
9. Test: `curl 'http://localhost:5001/?lang=pt'` and confirm hero text
   changes.

**Files added:** `app/translations/pt/LC_MESSAGES/messages.po` (+ `.mo` if
compiling in tree).

**Files modified:** all templates listed above.

**Test additions:** extend `tests/test_smoke.py` to hit key routes with
`?lang=pt` and assert a known Portuguese string is in the body.

---

### Track 2 — Admin gating (public/internal split) ✅ LANDED 2026-08-27

**Delivered:** commit `f60dfe6`. Pulled to cPanel 2026-08-27 — verified
live: `/harvest/` returns 404, the home page carries no `/harvest` link.

**What shipped (matches the plan below, with these specifics):**

- `app/config.py` — `ADMIN_UI_ENABLED = os.environ.get("BRASIL_ARCHIVES_ADMIN") == "1"`;
  `TestingConfig.ADMIN_UI_ENABLED = True` (not a conftest fixture — the
  flag lives on the config class, and the gate tests build their own app
  with it flipped off).
- `app/blueprints/_admin_gate.py` — `@admin_only` → `abort(404)`.
- `app/__init__.py` — `admin_ui_enabled()` Jinja global (closes over
  `app.config`, no `current_app` needed).
- `@admin_only` on `archives.submit_score`, `archives.edit_facets`,
  `harvest.index`, `harvest.run_detail`, `harvest.record_detail`.
- `detail.html` — scoring forms + per-dimension revision history are
  admin-only; public gets a read-only `.dimension-summary` table
  (dimension, score/10, locale-aware justification, date) or an
  `.empty-note` "Not yet scored."; facet link + Harvest nav gated.
- `tests/test_admin_gate.py` — 9 tests (flag off): routes 404, detail is
  read-only, nav hidden; plus one sanity check that the routes 200 with
  the flag on.

**Not done (moved out of scope):** `facets.html` itself is unreachable
publicly (route is gated) so it was left as-is; the read-only facet
*values* already render on the public detail page.

**Original plan (kept for reference):**

**Problem:** Every archive detail page shows 8 blank score-submission
forms and an "Edit facets & tags" link. `/harvest/*` shows harvest-run
internals. That's an operator UI on a public URL.

**Deliverable:** env-gated guard. `BRASIL_ARCHIVES_ADMIN=1` unlocks
internal UI; unset shows public-only.

**Chosen approach: env-gated guard, NOT a blueprint refactor.**
Reason: URL-prefix refactor rewrites every `url_for()` reference and every
test path. Env gate is ~50 lines total, zero test breakage.

**Steps:**

1. Add to `app/config.py`:
   ```python
   ADMIN_UI_ENABLED = os.environ.get("BRASIL_ARCHIVES_ADMIN") == "1"
   ```
2. Expose to Jinja in `app/__init__.py`:
   ```python
   app.jinja_env.globals["admin_ui_enabled"] = lambda: current_app.config["ADMIN_UI_ENABLED"]
   ```
3. Add a decorator `@admin_only` in `app/blueprints/_admin_gate.py`:
   ```python
   def admin_only(view):
       @functools.wraps(view)
       def wrapper(*args, **kwargs):
           if not current_app.config.get("ADMIN_UI_ENABLED"):
               abort(404)
           return view(*args, **kwargs)
       return wrapper
   ```
4. Apply to `archives.submit_score`, `archives.edit_facets`, and every
   `harvest.*` route.
5. In templates, wrap admin-visible bits:
   - `detail.html` scoring `<form>` block → `{% if admin_ui_enabled() %}`
   - `detail.html` "Edit facets & tags" link → same
   - `base.html` Harvest nav link → same
6. **Public replacement for scoring block:** when not admin, show a compact
   read-only "Dimension scores" table (dim name, current score, current
   justification, scored-at). If empty, one line: "Not yet scored."
7. Tests: existing tests set `ADMIN_UI_ENABLED=1` via `conftest.py`
   fixture so they keep passing. Add one test that hits `/harvest/` without
   the env var and asserts 404.

**Files added:** `app/blueprints/_admin_gate.py`, one test.
**Files modified:** `app/config.py`, `app/__init__.py`, three route
files, `base.html`, `detail.html`, `conftest.py`.

---

### Track 3 — Home page redesign ✅ LANDED 2026-08-27

**Delivered:** commit `ed381fd`. Not yet pulled to cPanel.

**What shipped:**

- `main.py` — `index()` gathers: featured archives (top 6 by naive sum of
  active scores, NULLs last, `no_digital_content=False` and
  `fair_use_eligible IS NOT False`), browse-by-state groups (RN/PE/BA
  primary + one "other" bucket of the remaining states), and a live
  `fed.preview()` per `UpgradeProject`. Also passes an aggregated-record
  count for the third stat tile.
- `services/federation.py` — **extracted `fed.preview(project)`** from the
  inline `_federation_preview` in `archives/routes.py` (the rule-of-three
  second caller). Never raises; returns
  `{"available": bool, "record_count", "deep_link_all", "stale", ...}`.
- `index.html` — rebuilt: hero, 3-stat row (archives / partners /
  federated records), `.state-chip-cluster`, `.home-featured__grid` of
  cards, `.home-federation__list`, method blurb.
- `style.css` — `.state-chip*`, `.home-featured*`, `.home-federation*`,
  and single-column rules in the `@media (max-width: 40rem)` block.
- 3 home-page tests in `tests/test_archives_blueprint.py`.

**Deviation from plan:** dropped "3 recent aggregated records" and the
"pick by record_count when unscored" fallback — aggregated_records only
tie to mipibu's one source archive, so they're not a meaningful catalog-
wide featured signal. Unscored archives simply sort last and show a
"Not yet scored" badge.

**Original steps (kept for reference):**

1. Add to `main.py` route: fetch top-5 archives by naive sum (or by
   `axis_research` when scoring exists), 3 recent aggregated records, and
   registered upgrade projects with live federation counts.
2. Rewrite `index.html`:
   - Hero (keep)
   - "Browse by state" chip cluster (RN, PE, BA, and rest as
     "other Nordeste")
   - "Featured archives" — 3-6 archive cards linking to detail pages;
     when no scores exist, pick by `record_count` from aggregated_records
   - "Live from partner projects" — surface the mipibu federation preview
     inline (record count + browse link)
   - Stats dl (keep, but reformat)
   - Method/rationale link (keep)
3. Add CSS classes: `.home-featured`, `.home-featured__card`,
   `.home-federation`, `.state-chip-cluster`.
4. Test: assert card links resolve; assert federation-preview block
   appears when mipibu is reachable and hides gracefully when it isn't.

**Files modified:** `app/blueprints/main.py`, `index.html`, `style.css`.

---

### Track 4 — Locale-aware vocabulary labels ✅ LANDED 2026-08-27

**Delivered:** commit `a981b60`. Live and verified via curl for both EN
("Federal university") and PT ("Universidade federal").

**What actually shipped (may differ slightly from the plan below — the
plan is preserved for the pattern):**

- `app/i18n.py` — pure `resolve_label()` + Flask-facing `vocab_label()`
  wrapper. Chose a module rather than an `app/__init__.py` inline function
  so it's independently testable and the fallback chain is unit-tested.
- `app/__init__.py` — registers `vocab_label` as a Jinja global.
- `app/templates/archives/list.html` — 2 `.label_en` → `vocab_label()`.
- `app/templates/archives/detail.html` — 4 `.label_en` → `vocab_label()`.
- `tests/test_i18n_vocab_label.py` — 8 unit tests (no DB, no app context).
- `tests/test_archives_blueprint.py` — 2 render-level EN/PT assertions.
- No `facets.html` changes needed (it had zero direct `.label_*` refs).

**Fallback chain:** requested locale → English → empty string. Some vocab
rows have `label_pt` null; those fall back to EN transparently.

**Guardrail:** planned `tests/test_template_hygiene.py::test_no_direct_label_en_access` in the tooling proposal above will fail if this regresses.

**Original plan (kept for reference):**

1. Add Jinja global `vocab_label(obj, fallback_lang="en")` — done via module.
2. Replace every `x.label_en` in templates — done for list.html and
   detail.html; facets.html had no direct refs.
3. Tests: assert PT locale renders `label_pt` where set; assert fallback
   to EN when PT is missing — done.

---

### Track 5 — Metadata, empty states, inline-style cleanup ✅ LANDED 2026-08-27

**Delivered:** commit `ad8c7d7`. Pulled to cPanel 2026-08-27.

**What shipped:**

- `base.html` — `<meta name="description">` fed by an overridable
  `{% block description %}`; `og:type/site_name/title/description/locale`
  (locale is `pt_BR`/`en_US` off `get_locale()`); `twitter:card`;
  `<link rel="icon" href=".../favicon.svg">`.
- `app/static/favicon.svg` — verde-brasil rounded square, "bA" monogram.
- Per-page `{% block description %}` on `index.html`, `list.html`,
  `detail.html` (detail interpolates archive name + type + state).
- `detail.html` — every inline `style=""` in the upgrade-projects /
  federation-preview block replaced by named classes; new `.empty-note`
  above the score profile when `naive_sum is none`.
- `list.html` — archives table wrapped in `.table-wrap`.
- `style.css` — extracted `.upgrade-project-card*`, `.federation-live*`,
  `.federation-unavailable`, `.corpus-version`, `.empty-note`,
  `.table-wrap`; a `@media (max-width: 40rem)` block (header wrap, stacked
  filter bar, single-column axis card + summary grid).
- `tests/test_app.py` — 4 head-metadata / og:locale / description-override
  assertions. Note: Flask-Babel caches the resolved locale for the app
  context's lifetime and the `app` fixture holds one open per test, so the
  EN and PT og:locale checks must be separate test functions.
- `tests/test_template_hygiene.py::test_no_static_inline_style_attributes`
  un-skipped (149 passed / 4 skipped).

**Deferred within the track:** hiding unscored dimensions behind a
collapsible `<details>` — that's a public-vs-admin view decision, so it
moves to Track 2.

**Original steps (kept for reference):**

1. `base.html` head block:
   - Add `{% block description %}A federated catalog of Brazilian digital archives.{% endblock %}` and render as `<meta name="description">`
   - Add OG tags: `og:title`, `og:description`, `og:type=website`,
     `og:locale` from `get_locale()`
   - Add `<link rel="icon" href="/static/favicon.svg">` — ship a simple
     SVG mark; even a monogram is enough
2. Per-page `{% block description %}` overrides on `list.html`,
   `detail.html`, `index.html`.
3. Extract inline styles from `detail.html` upgrade-projects section to
   `style.css`:
   - `.upgrade-project-card` — border, padding, radius
   - `.upgrade-project-card__title-row` — flex layout
   - `.federation-live` — success-tinted panel
   - `.federation-unavailable` — muted-warning panel
   - `.corpus-version` — monospaced small
4. Empty-state framing for detail pages when scoring is empty:
   - Above the score card, when `naive_sum is none`:
     `<p class="disclaimer">{{ _("This archive has not been scored yet. The two-axis profile appears here after evaluation.") }}</p>`
   - Hide dimensions with no active score in public view; move to a
     collapsible `<details>` block "Dimensions pending review".
5. Mobile: add `@media (max-width: 40rem)` to `style.css`:
   - `.filter-bar` → stack vertically
   - `.archives-table` → wrap in `.archives-table-wrap` with
     `overflow-x: auto` (or convert to card list on small viewports)
   - Header nav → hamburger or wrap

**Files modified:** `base.html`, `index.html`, `list.html`, `detail.html`,
`style.css`. New: `app/static/favicon.svg`.

---

## Assets & references

- **Design tokens (already in `app/static/style.css`):**
  - `--fg: #1a1a1a` foreground
  - `--bg: #fafaf7` paper-like background
  - `--muted: #666`
  - `--accent: #005a2b` verde brasil, muted
  - `--border: #e4e4de`
  - `--max: 68rem` container width
- **Font stack:** system-ui default (fine). Consider adding a serif
  (`Charter, Bitstream Charter, Cambria, serif`) for `h1/h2` if you want
  archival tone.
- **Routes inventory** (`app/blueprints/`):
  - `main.bp`: `/`, `/healthz`
  - `archives.bp` (prefix `/archives`): `list_archives`, `detail`,
    `submit_score`, `edit_facets`
  - `harvest.bp` (prefix `/harvest`): `index`, `run_detail`,
    `record_detail`
- **Templates all extend `base.html`.** All internal navigation uses
  `url_for()` — a URL refactor would only need blueprint-mount changes,
  not template edits. (But we're not doing that; env-gate is cheaper.)

## Non-goals

- Not building a search UI (semantic or lexical) — that's a separate
  Phase 2 concern.
- Not building a map view — the state chip cluster covers geography.
- Not touching the scoring algorithm (`app/services/scoring.py`) — the
  ADR-0001 two-axis model stays as-is.
- Not migrating to Tailwind or any CSS framework. Hand-authored CSS with
  design tokens is the project convention.

## Estimated effort per track

- Track 1 (i18n): 1.5–2 hours, mostly translation writing
- Track 2 (admin gate): 45 min
- Track 3 (home redesign): 1 hour
- Track 4 (locale vocab): 30 min
- Track 5 (metadata + cleanup): 1 hour

Total: ~5 hours. Individually landable. Recommended order above.

## Commit convention

One commit per track. Suggested messages:

- `feat(i18n): compile PT translations catalog; wrap remaining templates`
- `feat(admin): gate scoring, facets, and harvest UIs behind BRASIL_ARCHIVES_ADMIN`
- `feat(home): featured archives, browse-by-state, live federation preview on index`
- `feat(i18n): vocab_label helper follows active locale for InstitutionalType/Period/etc.`
- `feat(ui): metadata, favicon, mobile CSS, extract detail.html inline styles`

## Pre-push checklist per track

1. `pytest -q` — must be green
2. `curl http://localhost:5001/` returns 200 with expected content
3. `curl 'http://localhost:5001/?lang=pt'` returns 200 (and shows PT once
   Track 1 lands)
4. `git status` clean of stray `.pot`/`.mo`/`__pycache__`
5. `git push` with `api_credentials=["github"]`

## Post-push checklist per track (cPanel deploy)

From `docs/handoff/2026-08-27-master.md` §7:

1. On cPanel terminal:
   ```bash
   cd ~/brasil-archives
   git fetch origin
   git pull origin main
   ```
2. Restart Passenger: `touch tmp/restart.txt` **or** cPanel UI → Setup Python App → Restart.
3. Verify live:
   ```bash
   curl -s https://brasil-archives.from-bottom-to.top/healthz
   curl -s https://brasil-archives.from-bottom-to.top/archives/ | head -30
   curl -s 'https://brasil-archives.from-bottom-to.top/archives/?lang=pt' | head -30
   ```
4. If EN/PT don't switch, Passenger didn't restart — repeat step 2.
