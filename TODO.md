# TODO — what's next

**Updated:** 2026-08-27. Derived from `docs/handoff/2026-08-27-master.md` §4,
`docs/UI-POLISH-PICKUP.md`, `docs/integrations/povos-indigenas-rn.md`, and a
code read. Source of truth for the *why* behind each item is the linked doc;
this file is just the ordered agenda.

Legend: **[S]** small (<1h) · **[M]** medium (1–3h) · **[L]** large / multi-session

---

## 0. Housekeeping

- [x] **Commit the working-tree changes.** Done `891f30a` (utf-8 test fix)
  + `f9f57ca` (`DESCRIPTION.md` / `TODO.md`).
- [x] **Fold `load_calibration` into the documented seed sequence.** Done
  `f9f57ca` — `README.md` + `docs/DEPLOY.md` now list it.
- [ ] **[S] Decide `size_unit_note` facet.** `load_calibration` warns 6× that
  it has "no storage yet; carried in YAML only". Either add a column /
  `facet_values` entry for it, or note explicitly in `algorithm-v1.md` that
  it stays YAML-only. *(Still open.)*
- [x] **Add an `app.bat` start/stop/restart script.** Done. `app.bat`
  (start/stop/restart/**status**), `PORT=9000`, `LOG=dev-server.log`,
  netstat-LISTENING PID detection, `pause` only when double-clicked.
  `wsgi.py` gained an `if __name__ == "__main__"` block (option (a)) that
  loads `.env` via python-dotenv and runs with `use_reloader=False` so the
  script tracks a single PID. `dev-server.log` + `*.log` git-ignored.
  Fancier `ajme/app.bat` variant not needed. app-dashboard's
  `controller-api.ts` path stays unpaused (non-interactive => no `pause`).

## 1. Track A — public UI polish (5 of 5 landed) ✅

Full brief: `docs/UI-POLISH-PICKUP.md`. All five sub-tracks have landed in
code. **One action left:**

- [ ] **[S] Deploy Tracks 1 + 3 to cPanel.** One `git pull` on the cPanel
  terminal. Track 1 additionally needs — inside the cPanel venv, before the
  restart — `pybabel compile -d app/translations` (the `.mo` files are
  git-ignored). Then `touch tmp/restart.txt` and verify:
  `curl -s https://brasil-archives.from-bottom-to.top/ | grep -c home-featured` (Track 3, expect >0)
  and `curl -s 'https://brasil-archives.from-bottom-to.top/?lang=pt' | grep -o 'Arquivos Digitais Brasileiros'` (Track 1).
  Full steps in `docs/DEPLOY.md` "Routine deploy". If `pybabel` isn't on
  the cPanel venv PATH, `pip install babel` (it's a Flask-Babel dep).

- [x] **Track 4 — locale-aware vocab labels.** Landed `a981b60`.
- [x] **Tooling prep — `scripts/dev/wrap_i18n.py`.** Not built — Track 1's
  string-wrapping was done by hand (the templates were smaller than the
  ~100-string estimate). The codemod would still be useful if a future
  track adds many templates; skip it otherwise.
- [x] **Track 5 — metadata + favicon + inline-style cleanup.** Landed
  `ad8c7d7`. `<meta description>` (overridable block) + OG/twitter tags +
  `og:locale`, `favicon.svg`, inline `style=""` out of `detail.html` into
  `style.css`, `@media (max-width: 40rem)` block, empty-state note for
  unscored archives, `.table-wrap` around the archives table.
  `test_no_static_inline_style_attributes` un-skipped. **Deployed
  2026-08-27.** The "hide unscored dimensions / collapsible" bit was folded
  into Track 2's public/admin split.
- [x] **Track 2 — admin/public split.** Landed `f60dfe6`. Env gate
  `BRASIL_ARCHIVES_ADMIN=1` + `@admin_only` (`app/blueprints/_admin_gate.py`)
  → `abort(404)` on `submit_score`, `edit_facets`, all `harvest.*`.
  `admin_ui_enabled()` Jinja global hides the scoring forms / facet link /
  Harvest nav; public detail shows a read-only "Dimension scores" table or
  "Not yet scored." `tests/test_admin_gate.py` (9 tests, flag off).
  `TestingConfig.ADMIN_UI_ENABLED = True` keeps the rest of the suite on
  the internal UI. **Deployed 2026-08-27** — `BRASIL_ARCHIVES_ADMIN` unset
  on the public host, `/harvest/` 404s live.
- [x] **Track 3 — home page redesign.** Landed `ed381fd`. Featured-archive
  card grid (top 6 by naive sum, NULLs last, no-content + fair-use-
  ineligible excluded), state-chip cluster (RN/PE/BA + other bucket), live
  federation preview per partner, 3-stat row. `fed.preview()` extracted
  from `archives/detail`'s inline helper (2nd caller). Not yet deployed.
- [x] **Track 1 — PT translation catalog.** Landed 2026-08-27. Strings
  wrapped across `list.html`/`detail.html`/`facets.html`/`harvest/*.html` +
  Python flash/`page_title`. `app/translations/{pt,en}/LC_MESSAGES/messages.po`
  (180 msgids, `pt` fully translated). `.mo` is git-ignored — deploy needs
  `pybabel compile -d app/translations` (in `docs/DEPLOY.md`).
  `tests/test_i18n_catalog.py` (9 tests). Not yet pulled to cPanel.
  **Maintenance:** when UI strings change, re-run
  `pybabel extract -F babel.cfg -k _l -o messages.pot .` then
  `pybabel update -i messages.pot -d app/translations`, translate the new
  `pt` msgids, `pybabel compile`.

## 2. Track B — povos-indigenas-rn OAI-PMH endpoint

Primary ref: `povos-indigenas-rn/docs/OAI-PMH-PICKUP.md` (that repo).

- [ ] **[L] Give povos its own `/oai` endpoint.** ~1.5 days for an `oai_dc`
  MVP, ~3 for parity with mipibu's `oai_ead`. **Rule of three:** copy
  mipibu's `app/oai/` into povos rather than extracting a package —
  premature abstraction with N=1 caller.
  **Trigger to start:** user says "get povos federating."
  Unblocks Track C.

## 3. Track C — register povos as the 2nd upgrade project

Primary ref: `docs/integrations/povos-indigenas-rn.md` (has the bootstrap
baked in). **~2h mechanical once unblocked.**

Blocked on: (a) povos deployed at `povos-indigenas-rn.from-bottom-to.top`
with `/api/health` returning `federation_contract_version: "v1"`, and
(b) Track B for the harvest half.

- [ ] **[S] Add `research-project` institutional type** to
  `configs/vocabularies/institutional_types.yaml` if missing; reload vocab.
- [ ] **[S] `scripts/seed_povos_archive.py`** — the composite `archives` row
  (`source_archive_id` is NOT NULL; povos's source is AHU+CRL+UFRN, not one
  fonds). Code is in the integration doc §3a.
- [ ] **[S] `configs/upgrade_projects/povos-indigenas-rn.yaml`** — copy
  mipibu's shape; `oai_pmh_base_url: null` until Track B ships. YAML is in
  the integration doc §4.
- [ ] **[S] `python -m scripts.load_upgrade_projects`** + local verify
  (`/archives/povos-indigenas-rn-corpus` renders a federation-preview
  block), then push → cPanel pull → restart → live verify (home counter
  1 → 2).
- [ ] **[S] `tests/test_load_povos.py`** — loader integration test (doc §7).
- [ ] **[S] After povos `/oai` lands:** set `oai_pmh_base_url` in the YAML,
  reload, `scripts/harvest.py --project povos-indigenas-rn --dry-run` then
  real.

## 4. Track D — extract a shared OAI package

- [ ] **[L] `CorpusAdapter`-shaped package from mipibu's `app/oai/`.**
  **Blocked on Track B.** Do NOT extract with N=1 caller. Once povos has a
  working `/oai`, find the real seams between the two implementations.
  Shape sketch: `povos-indigenas-rn/docs/HANDOFF-2026-08-26.md`
  §"Package extraction plan".

## 5. Scoring backlog (the actual research work)

Ref: `docs/algorithm-v1.md` §"Change log", `docs/adr-0001-two-axis-aggregation.md`
§"Open follow-ups".

- [ ] **[L] Pass 3 — score the rest of the survey.** Only 6 of ~50
  pipeline-viable archives are scored (Pass 2 calibration set). Pass 3
  targets ~12–15 archives.
- [ ] **[M] Re-examine the 4-4 axis partition and the 28/40 quadrant
  threshold** after Pass 3 has ~12–15 archives. Changing either requires an
  **ADR-0001 supersession**, not a quiet edit.
- [ ] Get at least one archive labeled `scholarly_access_practical =
  only-via-federation` (first candidate: mipibu's source, once mipibu is
  promoted from UpgradeProject to Archive).

## 6. Infrastructure not yet built

- [ ] **[L] Quarterly health probe.** `ProbeResult` table + models exist;
  no runner. Would populate the four probe-fed facets (web ops health,
  external preservation, growth signal, prior-use signal) from HTTPS/cert
  checks, HTTP status sweeps, Wayback CDX, CrossRef/Semantic Scholar.
  Ref: `algorithm-v1.md` §"Ongoing infrastructure".
- [ ] **[M] Scheduled harvest (cron).** Explicitly deferred in
  `harvest-design.md` until the harvester has run manually against prod at
  least once. Still on-demand only today.
- [ ] **[L] Phase 3 standards-native *output*.** Serve brasil-archives' own
  catalog as OAI-PMH; institution descriptions as EAG XML; register with the
  OAI-PMH registry. Ref: `standards.md` Phase 3.
- [ ] **[L] Phase 4 — IIIF Content Search fanout.** Federated full-text
  search across companion apps. Ref: `federation-v1.md` §"IIIF Content
  Search".
- [ ] **[?] Deploy povos to cPanel.** Not this repo, but it's the gate on
  Track C. `povos-indigenas-rn/docs/DEPLOY.md`.

## 7. Known small gaps found while reading the code

- [ ] `federation.html_deep_link` is hardcoded to Mipibu's `/cases?…` URL
  shape with a `# TODO` to switch to a `links.html` template from
  `/api/schema` once a 2nd corpus registers. Revisit during Track C.
- [ ] `LICENSING.md` referenced by `algorithm-v1.md` §Licensing doesn't
  exist yet — "finalized before public release."
- [ ] `docs/vocabularies.md` is referenced (`algorithm-v1.md`) but not
  written; the vocab lives in `configs/vocabularies/*.yaml` + the DB tables.
- [ ] No `LICENSE` file in the repo (README says "TBD — finalized before
  public release").

---

## Suggested next session

1. Housekeeping §0 (fold in `load_calibration`, `app.bat`).
2. UI polish Track A is complete — deploy Track 1 + Track 3 to cPanel
   (Track 1 needs `pybabel compile` on the host; see `docs/DEPLOY.md`).
3. Track B/C only when the user says "get povos federating."
