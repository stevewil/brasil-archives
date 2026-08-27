# TODO — what's next

**Updated:** 2026-08-27. Derived from `docs/handoff/2026-08-27-master.md` §4,
`docs/UI-POLISH-PICKUP.md`, `docs/integrations/povos-indigenas-rn.md`, and a
code read. Source of truth for the *why* behind each item is the linked doc;
this file is just the ordered agenda.

Legend: **[S]** small (<1h) · **[M]** medium (1–3h) · **[L]** large / multi-session

---

## 0. Housekeeping (do first, cheap)

- [ ] **[S] Commit the working-tree changes.** `tests/test_loaders.py` +
  `tests/test_template_hygiene.py` got `encoding="utf-8"` on `Path.read_text`/
  `write_text` (Windows cp1252 was choking on UTF-8 fixtures). Plus new
  `DESCRIPTION.md` and this `TODO.md`.
  Suggested: `test(win): pin utf-8 encoding in file-reading test helpers` +
  `docs: add DESCRIPTION.md and TODO.md`.
- [ ] **[S] Fold `load_calibration` into the documented seed sequence.**
  `README.md` and `docs/DEPLOY.md` step 5 list vocab → survey →
  upgrade_projects but **not** `python -m scripts.load_calibration`, so a
  fresh DB has zero scores and every detail page is `—`. Add it. (Loader is
  idempotent; it seeds the 6 Pass-2 anchor archives.)
- [ ] **[S] Decide `size_unit_note` facet.** `load_calibration` warns 6× that
  it has "no storage yet; carried in YAML only". Either add a column /
  `facet_values` entry for it, or note explicitly in `algorithm-v1.md` that
  it stays YAML-only.
- [ ] **[S] Add an `app.bat` start/stop/restart script.** Match the sister
  apps — `mipibu/app.bat` and `povos-indigenas-rn/app.bat` are the template
  (cd to `%~dp0`, `PORT=9000`, `LOG=dev-server.log`, netstat-LISTENING PID
  detection for `is_running`, `start /min`, open the browser, `pause` only
  when double-clicked / no arg). Details:
  - The sister apps launch `.venv\Scripts\python.exe wsgi.py`; **our
    `wsgi.py` only defines `app`, it never calls `app.run()`.** So either
    (a) add an `if __name__ == "__main__": app.run(port=9000, debug=True)`
    block to `wsgi.py` to match the sister-app convention, or (b) have
    `app.bat` run `.venv\Scripts\python.exe -m flask run` (which already
    reads `FLASK_RUN_PORT=9000` from `.env`). (a) is more consistent with
    mipibu/povos.
  - Add `*.log` (or `dev-server.log`) to `.gitignore` — not currently
    ignored.
  - `c:\DEV\ajme\app.bat` has a fancier variant (mkdir-mutex, collision
    prompt, `wait_for_port`); adopt only if the simple version proves racy.
  - If `c:\DEV\app-dashboard` should manage this app too, its
    `controller-api.ts` shells out to `app.bat <action>` with a timeout —
    keep the non-interactive path unpaused (the sister scripts already do).

## 1. Track A — public UI polish (1 of 5 landed)

Full brief: `docs/UI-POLISH-PICKUP.md`. Each sub-track is independently
landable. Recommended order below (value-per-token).

- [x] **Track 4 — locale-aware vocab labels.** Landed `a981b60`.
- [ ] **[S] Tooling prep — `scripts/dev/wrap_i18n.py`.** The other two
  proposed helpers already exist (`scripts/dev/session_state.sh`,
  `tests/test_template_hygiene.py`). Only the i18n codemod is missing; it
  pays for itself on Track 1. Rules in master handoff §5.
- [ ] **[M] Track 5 — metadata + favicon + inline-style cleanup.** Small,
  visible, low-risk. `<meta description>`, OG tags, `favicon.svg`, extract
  ~60 lines of inline `style="…"` from `detail.html`'s upgrade-projects
  section into `style.css`, mobile `@media` rules, empty-state framing for
  unscored archives. **After it lands:** un-skip
  `test_template_hygiene.py::test_no_static_inline_style_attributes`.
- [ ] **[M] Track 2 — admin/public split.** Highest-leverage remaining work:
  gets the 8 blank score forms, the facet-edit link, and the whole
  `/harvest/*` surface off public URLs. Env gate
  (`BRASIL_ARCHIVES_ADMIN=1`), `@admin_only` decorator, `abort(404)` when
  off — **not** a blueprint refactor. Public replacement for the score
  block: read-only "Dimension scores" table. Add one test:
  `/harvest/` → 404 without the env var.
- [ ] **[M] Track 3 — home page redesign.** Needs Track 2 first (clean
  public/admin separation). Featured archives, browse-by-state chips, live
  federation preview inline on `/`.
- [ ] **[L] Track 1 — PT translation catalog.** Most expensive; do last.
  `_()` strings currently render EN (only vocab-table labels are localized).
  Wrap ~100 strings in `list.html`/`detail.html`/`facets.html`, `pybabel
  extract` (from repo root — the mapping misses templates otherwise),
  `init pt`, translate `messages.po` with the domain vocabulary in the
  brief, `compile`. **Do not start without an explicit "yes, do the
  translations."** Consider the scaffolding-only variant (agent produces
  `.pot` + skeleton `.po`, user fills PT in an editor).

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

1. Housekeeping §0 (commit, fold in `load_calibration`).
2. Then either **Track 5** (quick, visible) or **Track 2** (highest
   leverage) per `docs/UI-POLISH-PICKUP.md`.
3. Track B/C only when the user says "get povos federating."
