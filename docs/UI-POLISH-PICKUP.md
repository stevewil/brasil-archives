# Public UI Polish — Pickup Brief

**Status:** Deferred 2026-08-26. Assessment complete; no code changes landed.
**Scope:** Take `brasil-archives` from "working internal tool" to "coherent public site."

---

## Why this was deferred

Two-hour+ multi-file rewrite spanning five independent tracks. Deferred in
favor of a documented pickup so the work can be done in focused batches when
credits allow. Each track below is independently landable and independently
useful.

## Current state (verified 2026-08-26)

- **HEAD:** `07c97af` on `main`, clean.
- **Server:** `http://localhost:5001` runs via
  `DATABASE_URL=sqlite:////home/user/workspace/brasil-archives/instance/brasil_archives.db FLASK_APP=wsgi.py flask run --port 5001 --no-reload`
  (system `flask`, not `.venv/bin/flask` — no venv exists).
- **Tests:** 130 passed, 4 opt-in live skipped.
- **Data:** 79 archives, 1 upgrade project (mipibu), 1016 aggregated records.
  All `DimensionScore`, `DimensionLift`, `FacetValue` tables empty — so
  detail pages show many `—` placeholders.
- **Rendered pages verified via `curl`:** `/`, `/archives/`, one archive
  detail. All return 200 with expected content.
- **Babel:** wired (`app/__init__.py:_select_locale`), config sets
  `LANGUAGES=["en","pt"]`, default `en`. `pybabel` 2.18.0 available at
  `/home/user/.local/bin/pybabel`. **No `translations/` directory exists** —
  every `_()` call currently renders the English msgid. The PT/EN switcher
  in `base.html` sets `<html lang>` but doesn't translate any body text.

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

### Track 2 — Admin gating (public/internal split)

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

### Track 3 — Home page redesign

**Problem:** `/` is 30 lines: hero + 2 stats + status blurb. No way in
beyond nav. A new visitor can't see the point of the site.

**Deliverable:** home page that invites exploration.

**Steps:**

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

### Track 4 — Locale-aware vocabulary labels

**Problem:** All vocab tables (InstitutionalType, Period, RecordType,
Theme) have `label_pt` and `label_en` columns, but every template renders
`.label_en` unconditionally. PT users see English vocabulary.

**Deliverable:** vocab labels follow active locale.

**Steps:**

1. Add Jinja global `vocab_label(obj, fallback_lang="en")` in
   `app/__init__.py`:
   ```python
   def _vocab_label(obj, fallback_lang="en"):
       if obj is None:
           return None
       loc = str(get_locale() or fallback_lang)
       return getattr(obj, f"label_{loc}", None) or getattr(obj, f"label_{fallback_lang}", None) or ""
   app.jinja_env.globals["vocab_label"] = _vocab_label
   ```
2. Replace every `x.label_en` in templates with `vocab_label(x)`:
   - `list.html`: institutional_type select, table row type column
   - `detail.html`: institutional_type in page-header lede; periods,
     record_types, themes tag clouds
   - `facets.html`: similar
3. Tests: assert PT locale renders `label_pt` where set; assert fallback
   to EN when PT is missing (some rows may have `label_pt` null).

**Files modified:** `app/__init__.py`, three templates.
**Test additions:** `tests/test_units.py` — add `vocab_label` fallback
tests (no DB, pure function).

---

### Track 5 — Metadata, empty states, inline-style cleanup

**Problem:** Thin `<title>`, no meta description, no OG tags, no favicon.
`detail.html` upgrade-projects section has ~60 lines of inline
`style="…"`. Detail pages show many `—` placeholders without framing.

**Deliverable:** polished production feel.

**Steps:**

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
