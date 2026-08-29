# TODO — what's next

**Updated:** 2026-08-27 (parallel-jobs session — see bottom). Derived from `docs/handoff/2026-08-27-master.md` §4,
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
- [x] **Decide `size_unit_note` facet.** Done 2026-08-27 (`e2c3d4f5a6b7`):
  added `Archive.size_unit_note` `Text` column alongside
  `curatorial_rarity_notes` / `prior_use_note`; `load_calibration` now stores
  it (no more warning), backfilled from `pass2.yaml`. See `docs/vocabularies.md`.
- [x] **Add an `app.bat` start/stop/restart script.** Done. `app.bat`
  (start/stop/restart/**status**), `PORT=9000`, `LOG=dev-server.log`,
  netstat-LISTENING PID detection, `pause` only when double-clicked.
  `wsgi.py` gained an `if __name__ == "__main__"` block (option (a)) that
  loads `.env` via python-dotenv and runs with `use_reloader=False` so the
  script tracks a single PID. `dev-server.log` + `*.log` git-ignored.
  Fancier `ajme/app.bat` variant not needed. app-dashboard's
  `controller-api.ts` path stays unpaused (non-interactive => no `pause`).

## 1. Track A — public UI polish (5 of 5 landed) ✅

Full brief: `docs/UI-POLISH-PICKUP.md`. All five sub-tracks landed in code.

- [x] **Deploy Tracks 1 + 3 to cPanel.** Done 2026-08-28 as part of the
  `1cc5ded` deploy (runbook Phase 1). All five UI-polish tracks are now
  live. The deploy also recovered a reseeded prod DB — see `docs/DEPLOY.md`
  2026-08-28 note.

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

Primary ref: `povos-indigenas-rn/docs/oai-pmh-povos.md` (that repo).

- [x] **[L] Give povos its own `/oai` endpoint.** Built by a subagent
  2026-08-27, reviewed + merged to povos `main` 2026-08-28 (`817167c`).
  Self-contained `app/oai/` package (13 modules), `oai_dc` format, 145
  records / 7 kinds, stateless resumption tokens, all 6 verbs + error
  codes. `oai_ead` deferred (povos is a composite AHU+CRL+UFRN evidence
  base, not a single fonds). 134 tests. **Deploy:** routine 3-command pull
  on cPanel (povos is already live). Unblocks Track C.

## 3. Track C — register povos as the 2nd upgrade project

Primary ref: `docs/integrations/povos-indigenas-rn.md`.

- [x] **Register povos as upgrade project #2.** Landed 2026-08-28.
  `scripts/seed_povos_archive.py` (composite `archives` row
  `povos-indigenas-rn-corpus`, `institutional_type=research-project`) +
  `configs/upgrade_projects/povos-indigenas-rn.yaml` (`json_api` + `oai`
  URLs set, `beta`, 6 period tags, `administrative-legislative` +
  `manuscripts-books`) + `tests/test_load_povos.py` (3 tests). Loaded
  locally: 2 upgrade projects; the live federation preview on
  `/archives/povos-indigenas-rn-corpus` shows povos's `record_count: 40`.
  **Deploy:** cPanel pull → `python -m scripts.seed_povos_archive` →
  `python -m scripts.load_upgrade_projects` → restart → home counter 1→2.
- [ ] **[S] First povos harvest cycle.** `oai_pmh_base_url` is set in the
  YAML. Run `python -m scripts.harvest --project povos-indigenas-rn
  --dry-run` then real (workstation or cPanel) to pull povos's `oai_dc`
  into `aggregated_records`.

## 4. Track D — extract a shared OAI package

- [ ] **[L] `CorpusAdapter`-shaped package from the OAI providers.**
  **Now unblocked** — povos has a working `/oai` (`817167c`). But mipibu
  and povos ended up with **parallel from-scratch implementations** (the
  povos build couldn't see mipibu's package — it was only on mipibu's
  `origin/main`). brasil-archives has a *third* provider (`app/oai/`,
  `54367f7`). Diff all three for the real seams before extracting —
  `povos/app/oai/store.py` is explicitly the "CorpusAdapter would replace
  this" module. Low priority. Rule of three is now satisfied (N=3).

## 5. Scoring backlog (the actual research work)

Ref: `docs/algorithm-v1.md` §"Change log", `docs/adr-0001-two-axis-aggregation.md`
§"Open follow-ups".

- [x] **[L] Pass 3 — score the rest of the survey.** Scored 2026-08-27,
  reviewed by Steve + merged + loaded 2026-08-28 (`39a08da`, `b6eceee`).
  15 Nordeste archives; 21 archives now have active scores (6 Pass 2 +
  15 Pass 3). 13 of 15 land Low/Low. Review outcome + all 8 borderline
  calls: `docs/pass3-scoring-notes.md` §"Review outcome". **Deploy:** one
  cPanel pull + `python -m scripts.load_calibration --path
  configs/calibration/pass3.yaml`.
- [x] **Re-examine the 4-4 axis partition and quadrant threshold.** Done
  2026-08-29 — [`docs/adr-0002-axis-re-examination.md`](docs/adr-0002-axis-re-examination.md)
  (`d9376ee`). Over 21 scored archives: partition kept; **threshold 28 → 26**;
  research-axis low coherence (α 0.49) + `uniqueness`/`corpus_completeness`
  flagged for Pass 4; the Scale basis question stays open for Pass 4.
  **Deploy:** `github-pull` (Python-only change; changes 2 archives' quadrant
  labels on the live list/detail pages).
- [x] Get at least one archive labeled `scholarly_access_practical =
  only-via-federation` — done via Pass 3: APEJE, APEPI, and the 3
  FamilySearch collections (`t1r10/37/39/43/47`).

## 6. Infrastructure not yet built

- [~] **[L] Quarterly health probe.** Runner `d2b808d`, robustness pass
  `9563f47`, `http_get` failure-mode fix `77a22ae` (junk/non-ASCII URL,
  `ConnectionResetError`), **detail-page display** `3dbb3ac` ("Observed
  signals" section). **First prod run done 2026-08-28** — 82 targets, all
  now have data. **Left:** (a) add the quarterly cron (lines + confirmed
  paths in `docs/handoff/2026-08-27-runbook.md` Phase 2), (b) tune
  thresholds during Pass 2 calibration.
- [~] **[M] Scheduled harvest (cron).** Unblocked — mipibu harvested against
  prod 2026-08-28. **Left:** run the first prod **povos** harvest once, then
  add the monthly harvest cron (mipibu `oai_dc` + `oai_ead` + povos
  `oai_dc`; lines in runbook Phase 2).
- [~] **[L] Phase 3 standards-native output.** OAI-PMH provider (`/oai`,
  `oai_dc` + `eag` formats) + EAG XML route **built + landed** 2026-08-27
  (`54367f7`). **Left:** EAC-CPF (no authority records yet), register at the
  OAI-PMH registry (runbook in `docs/oai-pmh-provider.md` §6), resolve the
  §7 open questions (public-bar policy, `harvested` passthrough set).
- [x] **[M] Phase 3.5 — cross-corpus aggregated search.** Built 2026-08-29.
  Public `GET /search` (`main` blueprint) over the harvested `oai_dc`
  records in `aggregated_records`: accent/case-insensitive full scan in
  Python, two match tiers (title-ish "strong" ranks above subject-only
  "weak"), per-partner facet chips, deep links back into each partner's
  viewer (host-matched `canonical.urls` entry, home-page fallback),
  pagination, bilingual. Nav link + home "Federated records" stat now
  link in. Empty/no-results states show a curated `SAMPLE_QUERIES` chip
  row; **operator keyword cheat sheet**
  [`docs/federated-search-keywords.md`](docs/federated-search-keywords.md)
  (per-partner productive terms, types, year spans, dead-end terms).
  `app/services/federated_search.py`, `tests/test_federated_search.py`
  (19 tests). Design + follow-ups:
  [`docs/federated-search.md`](docs/federated-search.md).
- [x] **[S] Archive catalog text search.** Built 2026-08-29. `GET /archives/`
  gained a `q` param — accent- + case-insensitive (`app/text.py` `fold()`,
  extracted from Phase 3.5's `_fold` and now shared) matched against
  `name` / `name_pt` / `description_en` / `description_pt` / `stated_scope`
  / `home_city`. Python post-filter on the existing query result (~80
  rows, no FTS); composes with the state / type / content / sort filters;
  input in the filter bar, prefilled from `current.q`; bilingual.
  `tests/test_text.py` (4) + `tests/test_archives_blueprint.py` search
  section (6). Distinct from Phase 3.5, which searches harvested *partner
  records*, not the catalog of archives.
- [ ] **[L] Phase 4 — IIIF Content Search fanout.** Live federated full-text
  search — a query on brasil-archives fans out to every partner's IIIF
  Content Search endpoint. Needs mipibu + povos to implement those endpoints
  first. Ref: `federation-v1.md` §"IIIF Content Search". Supersedes Phase 3.5.
- [x] **Deploy povos to cPanel.** Done — povos live at
  `povos-indigenas-rn.from-bottom-to.top` with `/oai` + federation-v1
  `/api/*` (`466f8c1`).

## 7. Known small gaps found while reading the code

- [x] `federation.html_deep_link` — **fixed 2026-08-28** (`c5fb1f8`). Was
  hardcoded to mipibu's `/cases?…`; now returns the partner's own
  `/api/records` `links.html` (mipibu → `/cases`, povos → `/documents`),
  falling back to the site root. Verified live. **Not yet deployed** —
  next brasil-archives pull.
- [x] **Federated-search result links pointed at the povos home page.**
  Fixed 2026-08-29. `oai_dc` extractor now captures `dc:source` URLs
  (`canonical.source_urls`); `federated_search._links()` falls through
  on-host → off-host → `dc:source` → home. povos side: `passage` records
  now emit their parent document's page URL. New `scripts/reextract.py`
  re-derives `extracted_json` without a re-fetch (needed whenever an
  extractor changes). Follow-ups (povos `/works/<id>` +
  `/ethnic-groups/<id>` pages, passage `dc:date`) in
  [`docs/federated-search.md`](docs/federated-search.md) §Known follow-ups.
- [~] **Licensing — decisions locked, files WIP (2026-08-29).** Code → MIT;
  Nordeste survey + vocabularies → CC BY 4.0 (attribution only, no
  share-alike, no covenant); scoring output stays non-public + unlicensed
  for now. `LICENSE`, `LICENSE-CC-BY-4.0.txt`, `LICENSING.md` written +
  committed as a WIP checkpoint. **Remaining:** `README.md` §License,
  `docs/algorithm-v1.md` §Licensing, `DESCRIPTION.md` line ~304 pointer
  updates — scoped item 1 in
  `docs/handoff/2026-08-29-search-licensing-admin.md` §3.
- [x] `docs/vocabularies.md` — written 2026-08-27 (`34fc5b3`): consolidates
  every controlled vocabulary + the code single-selects + probe facets.

---

## Suggested next session

**Pickup brief: `docs/handoff/2026-08-29-search-licensing-admin.md`.**
Everything through the deep-link fix is built + deployed
(brasil-archives `e2355c3`, povos `e73a892`, both cPanel-current). The
scoped list, in order:

1. **Finish + commit licensing** — `README.md` / `docs/algorithm-v1.md` /
   `DESCRIPTION.md` pointer updates. Files already written + committed WIP.
   ~15 min. Handoff §2–3.
2. **Public-scores visibility toggle** `[M]` —
   `BRASIL_ARCHIVES_PUBLIC_SCORES` (default off), independent of
   `BRASIL_ARCHIVES_ADMIN`. Hides the score profile / axis / quadrant /
   dimension table (detail), the score columns + sorts (list), and the
   score-ranked Featured block (home) from the public until Steve
   greenlights. Handoff §3 item 2 has the full thread-through list.
3. **Read-only admin dashboard** `[M]` — one `/admin/` page behind the
   existing gate: scoring coverage, harvest history, probe status,
   federation health, recent errors. No auth, no write paths. Handoff §3
   item 3.
4. **Archive-draft form** — lowest priority, confirm value first. Must
   generate a reviewable markdown/YAML draft, never write the prod DB
   (non-durable). Handoff §3 item 4.

**Still open, unscheduled:**

- **OAI-PMH registry registration** — `docs/oai-pmh-provider.md` §6; set
  `OAI_PAGE_SIZE=50` on the cPanel host first. User-driven.
- **"Toward 1.0" discussion** — the score-publishing decision (item 2 is
  the mechanism), Pass 4 scoring coverage, whether to publish scores at
  all. Liability context in the handoff §2.
- **Pass 4 scoring** — ADR-0002 deferred `uniqueness` /
  `corpus_completeness` (research axis α 0.49) + the Scale basis question.
- **povos `/works/<id>` + `/ethnic-groups/<id>` detail pages** — ~7
  federated-search results still fall back to an external/home page.
- **Track D** (shared OAI `CorpusAdapter`) — low priority, N=3 providers.

## Landed 2026-08-27/28

Parallel-jobs (`34fc5b3`): `d2b808d` probe runner · `54367f7` OAI-PMH
provider + EAG · `docs/vocabularies.md` · `e2c3d4f5a6b7` `size_unit_note`.
Deploy/review (`0022fc3`): Pass 3 loaded (`b6eceee`), probe robustness
(`9563f47`), EAG fix (`bb044b4`), Track C (`8d81da0`). povos: `/oai`
(`817167c`) + federation-v1 `/api/*` (`466f8c1`), both deployed.
Session records: `docs/handoff/2026-08-27-{parallel-jobs,runbook}.md`.
