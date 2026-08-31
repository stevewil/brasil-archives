# Supabase Free-tier keep-alive

**Built 2026-08-29 as a standalone tool:** `C:\DEV\supabase-keepalive\`
(project-agnostic; covers `media-pipeline-agent` and any project added to its
config). See that folder's `README.md` for install + cron setup.

This file is kept only as a pointer + the brasil-archives-side context.

---

## Why

Free-plan Supabase projects pause after ~7 days with no activity, where
"activity" means a request to the project's **own** API
(`https://<ref>.supabase.co/...`) — calling the Management API does **not**
count. The tool runs one cPanel cron (`keepalive.sh ping`, e.g. `0 6 * * 1,4`)
that, per configured project: optionally checks status via a Management PAT and
auto-restores if paused, then sends a real keep-alive request.

## brasil-archives relevance

- brasil-archives **prod is still SQLite on cPanel today**, but a Supabase
  project (`brasil-archives`) has been created for the planned SQLite→Postgres
  migration — see [`supabase-migration-spec.md`](supabase-migration-spec.md).
  It is now one of the two projects this tool keeps warm, so it doesn't pause
  before cutover.
- The cPanel host (`fromuagq`) is the convenient always-on box to run the cron
  from. The tool itself is not coupled to brasil-archives.
- Related, separate work: retiring the `area-51-vault` Supabase project by
  moving that vault to encrypted JSON on Wasabi — see
  `C:\DEV\app-dashboard\VAULT-WASABI-BACKUP.md` (and its successor spec).

## Status — DEPLOYED 2026-08-31

Live on cPanel (`premium32`, user `fromuagq`). Repo is now git-tracked at
`github.com/stevewil/supabase-keepalive` (private); its `README.md` §"Live
deployment" is the canonical record. Summary:

- Location `~/flask/supabase-keepalive/`, cloned via the `gh` CLI (device-flow
  auth set up on the box for private repos).
- Interpreter `/opt/alt/python313/bin/python3` (the box's cron `python3` is 3.6,
  too old) — passed via `SUPABASE_KEEPALIVE_PYTHON` in the cron command.
- Cron `0 6 * * 1,4` (Mon + Thu 06:00) → `keepalive.sh ping`. Covers
  `media-pipeline-agent` + `brasil-archives`. Verified: both ping OK, `exit 0`
  in a stripped (cron-equivalent) env.
- `management_pat` not set (ping-only). cPanel Cron Email is the failure channel.
