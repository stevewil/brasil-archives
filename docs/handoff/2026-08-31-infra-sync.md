# Handoff — 2026-08-31 · infra sync + supabase-keepalive deploy

Short session. No app-code changes. Everything that was built in the
2026-08-29 session got deployed, a new standalone tool went live, and all
repos are now level across local ↔ GitHub ↔ cPanel.

**Next session picks up: the SQLite → Supabase Postgres migration (§"Pick up
here").**

---

## What shipped this session

### 1. GitHub auth on the cPanel box (was blocking everything else)

The cPanel host (`fromuagq@premium32`) could not clone **private** repos —
brasil-archives / mipibu / povos are all public, so deploys never needed auth,
and `supabase-keepalive` was the first private one. Fine-grained PATs kept
failing (per-repo allow-list didn't include the new repo).

**Fix:** installed the GitHub CLI as a static binary at `~/bin/gh` (v2.98.0)
and ran `gh auth login` → device flow. That stores an **account-wide OAuth
token** (`gho_…`, scopes `repo, read:org, gist, workflow`) and registers a git
credential helper (`credential.https://github.com.helper = !gh auth
git-credential`). Every private repo is now reachable, permanently. Details:
`[[cpanel-github-auth-gh-cli]]` memory.

- Token file `~/.config/gh/hosts.yml`, `chmod 600`.
- **Cron caveat:** the git helper needs `~/bin` on PATH; cron may not source
  `~/.bashrc`. For any future `git pull` deploy cron, set the helper
  explicitly per-repo:
  `git config credential.helper '!'"$HOME/bin/gh"' auth git-credential'`.

### 2. supabase-keepalive — deployed + operational

Standalone tool (private repo `github.com/stevewil/supabase-keepalive`), keeps
Supabase Free-plan projects from pausing (~7-day idle → pause).

- Cloned to `~/flask/supabase-keepalive/` on cPanel.
- Interpreter: `/opt/alt/python313/bin/python3` — the box's cron `python3` is
  3.6 and too old (`from __future__ import annotations` fails). Passed via
  `SUPABASE_KEEPALIVE_PYTHON` **inline in the cron command**.
- Cron (live): `0 6 * * 1,4 SUPABASE_KEEPALIVE_PYTHON=/opt/alt/python313/bin/python3 /home/fromuagq/flask/supabase-keepalive/keepalive.sh ping`
  — Mon + Thu 06:00, max ~3.5-day gap.
- Config `keepalive.config.json` (`chmod 600`, gitignored): two projects —
  **`media-pipeline-agent`** and **`brasil-archives`** (its Supabase Postgres
  project, created ahead of the migration so it doesn't pause before cutover).
  Free plan is at its 2-active-project cap.
- `management_pat` **not** set (ping-only; no auto-restore). cPanel Cron Email
  is the only failure channel — script is silent on success.
- Verified: `./keepalive.sh check` green; `ping -v` → both projects `OK`,
  `exit 0`, in a stripped (cron-equivalent) env.
- Canonical record: that repo's `README.md` §"Live deployment". brasil-archives
  side: `docs/supabase-keepalive.md`. Memory: `[[supabase-keepalive-deployed]]`.
- Decision made & held: keep the ping **simple** (no `--if-due` jitter, no
  fake-activity generator). If Supabase ever objects, upgrade to Pro. Rationale
  in the session transcript — a transparent minimal ping is more defensible
  than disguised traffic.

### 3. brasil-archives — 2026-08-29 backlog deployed to cPanel

`github-pull` fast-forwarded `82b5742..1e3462d` (5 commits), `pybabel compile`
ran (`.po` changed), Passenger restarted. Now **live on prod**:

- **Licensing** — MIT code / CC BY 4.0 survey+vocab data; `LICENSING.md`
  canonical (`[[licensing-2026-08-29]]`).
- **`BRASIL_ARCHIVES_PUBLIC_SCORES` gate** — scores hidden on the public host
  (env var **stays unset**). `[[public-scores-and-admin-gates]]`.
- **Read-only `/admin/` dashboard** — 404 unless `BRASIL_ARCHIVES_ADMIN=1`
  (also unset on public).
- The two Postgres-migration spec docs (were untracked; now committed).

**Prod DB verified intact** after the pull (the recurring reseed gremlin did
NOT fire this time): `/archives/` lists 52 rows, federated `/search?q=terra`
returns 8 results, zero score labels on the public list (gate working).

### 4. Everything synced

| repo | local | GitHub | cPanel |
|---|---|---|---|
| brasil-archives | `1e3462d` | pushed | pulled + restarted, DB intact |
| supabase-keepalive | `0851a65` | pushed | pulled |
| povos-indigenas-rn | current | — | current (untracked `tmp/` only) |
| mipibu | current | — | current (untracked `passenger_wsgi_orgi.py`, `tmp/`) |

### 5. Scheduled jobs on cPanel — verified present (`crontab -l`)

| schedule | job |
|---|---|
| `15 3 1 1,4,7,10 *` | `scripts.probe --all --include-upgrade-projects --quiet` → `~/logs/probe.log` |
| `30 2 1 * *` | `scripts.harvest --project mipibu --quiet` → `~/logs/harvest.log` |
| `33 2 1 * *` | `scripts.harvest --project mipibu --format oai_ead --quiet` |
| `36 2 1 * *` | `scripts.harvest --project povos-indigenas-rn --quiet` |
| `0 6 * * 1,4` | supabase keep-alive ping |

All use the 3.13 venv python. **This closes the "quarterly probe cron" and
"monthly harvest cron" items** that `TODO.md §6` still listed as open —
`TODO.md` is stale there; the runbook (`2026-08-27-runbook.md` §Phase 2) is
right.

---

## Open items (were "still open", status after this session)

1. **Revoke the two exposed GitHub PATs** — *in progress.* Two fine-grained
   PATs were pasted in full in screenshots while debugging the clone
   (`github_pat_11ABDJPGI0LuX8…` = the app-dashboard vault token, scoped
   "Public repositories" read-only, GitHub token id `18954675`, name
   "myGitHub PAT"; `github_pat_11ABDJPGI0YEL…` = a throwaway). Steve is
   deleting them via GitHub Settings → Developer settings → Fine-grained
   tokens. **Follow-up:** the app-dashboard vault `GITHUB_PAT` entry (used by
   the "push credential to GitHub Actions secrets" feature) — blank it, or
   replace with a properly-scoped token only if that feature is actually used.
   cPanel no longer needs it (uses `gh`).

2. **First povos prod harvest** — *effectively confirmed.* The povos harvest
   cron (`36 2 1 * *`) is present, and per the runbook checklist that cron is
   only added *after* the first manual prod harvest has run (runbook says done
   2026-08-28, 145 records). One `curl` spot-check
   (`/search?q=ind%C3%ADgena` for povos hits) was not pasted back but is
   low-stakes. Treat as done; re-check if a search looks thin.

---

## Pick up here — SQLite → Supabase Postgres migration `[L]`

**Specs (in-repo, read both):**
- `docs/supabase-migration-spec.md` — the backend move. §9.1 = the prep
  checklist, §10 = decisions (all resolved), §11 = effort.
- `docs/partner-schema-design.md` — per-source schemas. §12 = sub-decisions
  P1–P5.

**Why it's low-risk (spec §1):** code is already near-dialect-agnostic
(`DATABASE_URL` honored, partial indexes carry `postgresql_where`, JSON is
`TEXT`+`json.loads`, no PRAGMAs). And there's **no precious data** — everything
authoritative is git-tracked YAML loaded by idempotent `scripts/load_*`, and
harvested records re-derive from `scripts/harvest.py`. The migration *is*:
point at Postgres, `flask db upgrade`, run the seed sequence once.

**Decisions already locked (spec §10):**
- D1 → **per-source schemas** `src_<slug>` (one identical table template each),
  NOT a single `harvest` schema. ⚠️ Spec §9.1 item 3 and §9.3 still say
  "`harvest` schema" in places — that wording predates the D1 resolution;
  `partner-schema-design.md` + `TODO.md`'s phase 1a/1b breakdown are current.
- D2 → fix the existing 5 migrations (they're nearly PG-ready), don't squash.
- D4 → keep SQLite for local dev + unit tests; add a **Postgres CI job** for
  fidelity.
- D5 → app-side **`NullPool`** on cPanel, let Supavisor pool (Passenger
  fork-safety).
- D6 → **defer** Phase 2 (`jsonb`, SQL search) — ship the durable backend
  first.
- D7 → `upgrade_projects` stays in `public` (it's curated config).

**Phase 1a — the entry point (do on a branch, no prod impact):**
1. `requirements.txt` += `psycopg[binary]>=3.1,<4.0` (psycopg 3).
2. `app/config.py` — add `SQLALCHEMY_ENGINE_OPTIONS` when the URL is Postgres
   (NullPool, pre-ping, `sslmode=require`) — spec §5.2.
3. `migrations/env.py` — `include_schemas=True` + the SQLite
   `schema_translate_map` — spec §6.4.
4. New GitHub Actions CI job: `services: postgres:16`,
   `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/test`,
   run the full suite. Goal: **both** SQLite and Postgres suites green.

**Phase 1b:** per-source plumbing — `{"schema": "source"}` on the 4 auxiliary
models, `app/services/sources.py`, view models, fold schema-sync into
`load_upgrade_projects`, dual-backend tests green. Then merge.

**Phase 2 (cutover, spec §9.2–9.4):** create the Supabase project (region =
cPanel datacenter, confirm — likely `us-east-1`); the `brasil-archives`
Supabase project the keep-alive already references is a **placeholder** — the
real one for cutover may be it or a fresh one, decide at §9.2. Session pooler
URL → `DATABASE_URL` on cPanel, `flask db upgrade` + seed, verify, rename the
old SQLite file. Rollback = unset `DATABASE_URL`, restart.

**Post-cutover cleanup:** delete the `prod-db-gets-reseeded` memory (problem
solved), update `docs/DEPLOY.md` + `docs/handoff/2026-08-27-master.md` storage
line, add a weekly `pg_dump --schema=public` cron.

---

## Lower priority / unscheduled

- OAI-PMH registry registration — `docs/oai-pmh-provider.md` §6; set
  `OAI_PAGE_SIZE=50` on cPanel first.
- Pass 4 scoring — ADR-0002 deferred `uniqueness` / `corpus_completeness`
  (research axis α 0.49) + the Scale basis question.
- "Toward 1.0" — whether/when to publish scores publicly (the gate mechanism
  is now in place and deployed).
- povos `/works/<id>` + `/ethnic-groups/<id>` detail pages — ~7 federated-search
  results still fall back to an external/home page.
- Track D — shared OAI `CorpusAdapter` package (N=3 providers, no urgency).
