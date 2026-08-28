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

- [~] **[L] Pass 3 — score the rest of the survey.** DRAFT landed 2026-08-27
  on branch `feature/pass3-scoring` (`3a21e07`): 15 archives in
  `configs/calibration/pass3.yaml` + `docs/pass3-scoring-notes.md`.
  **Not merged, not loaded** — 8 borderline calls need Steve's review
  (see the notes doc). After review: merge + `python -m scripts.load_calibration
  configs/calibration/pass3.yaml`.
- [ ] **[M] Re-examine the 4-4 axis partition and the 28/40 quadrant
  threshold** after Pass 3 has ~12–15 archives. Changing either requires an
  **ADR-0001 supersession**, not a quiet edit.
- [ ] Get at least one archive labeled `scholarly_access_practical =
  only-via-federation` (first candidate: mipibu's source, once mipibu is
  promoted from UpgradeProject to Archive).

## 6. Infrastructure not yet built

- [~] **[L] Quarterly health probe.** Runner **built + landed** 2026-08-27
  (`d2b808d`), **robustness pass** 2026-08-28 (`9563f47`: per-target 90s
  budget, Wayback/S2 soft-miss handling, `SEMANTIC_SCHOLAR_API_KEY` support).
  Exercised from the workstation — compositing looks sane, a dead host
  terminates in ~94s. **Left:** (a) full real run against prod on cPanel
  (`python -m scripts.probe --all --include-upgrade-projects`), (b) add the
  cPanel cron (lines in `docs/handoff/2026-08-27-runbook.md` Phase 2),
  (c) tune the compositing thresholds during Pass 2 calibration.
- [ ] **[M] Scheduled harvest (cron).** Explicitly deferred in
  `harvest-design.md` until the harvester has run manually against prod at
  least once. Still on-demand only today.
- [~] **[L] Phase 3 standards-native output.** OAI-PMH provider (`/oai`,
  `oai_dc` + `eag` formats) + EAG XML route **built + landed** 2026-08-27
  (`54367f7`). **Left:** EAC-CPF (no authority records yet), register at the
  OAI-PMH registry (runbook in `docs/oai-pmh-provider.md` §6), resolve the
  §7 open questions (public-bar policy, `harvested` passthrough set).
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
- [x] `docs/vocabularies.md` — written 2026-08-27 (`34fc5b3`): consolidates
  every controlled vocabulary + the code single-selects + probe facets.
- [ ] No `LICENSE` file in the repo (README says "TBD — finalized before
  public release").

---

## Suggested next session

**Step-by-step runbook for everything below: `docs/handoff/2026-08-27-runbook.md`.**

1. **Review Pass 3** — `docs/pass3-scoring-notes.md`, the 8 borderline calls;
   then merge `feature/pass3-scoring` + load.
2. **Deploy pending work to cPanel** — `main` (`34fc5b3`+) now carries UI-polish
   Tracks 1+3 **plus** the probe runner, the `/oai` OAI-PMH provider, and the
   `size_unit_note` column. One pull; run `flask db upgrade` (two new
   migrations: `d7f1a2b3c4d5`, `e2c3d4f5a6b7`) and `pybabel compile -d
   app/translations` before the Passenger restart. See `docs/DEPLOY.md`.
3. **Run the probe against prod once**, then decide the harvest + probe crons (§6).
4. **povos `feature/oai-pmh`** — review + merge in that repo; deploy povos;
   then Track C (register as 2nd upgrade project).
5. Track B is effectively done (povos `/oai` built) — Track D (extract shared
   OAI package) is now unblocked but low priority; mipibu + povos have
   parallel implementations to diff first.

## Landed 2026-08-27 (parallel-jobs session)

- `d2b808d` probe runner · `54367f7` OAI-PMH provider + EAG · `34fc5b3`
  `docs/vocabularies.md` · `e2c3d4f5a6b7` `size_unit_note` column.
- Session record: `docs/handoff/2026-08-27-parallel-jobs.md`.
- **Not landed:** Pass 3 (`feature/pass3-scoring`, draft), povos `/oai`
  (`feature/oai-pmh` in that repo).
