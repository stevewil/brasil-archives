# Supabase Free-tier keep-alive (planned — not yet built)

**Status:** parked 2026-08-29 while resolving an unrelated Supabase issue.
Resume after that is fixed.

**Where this runs:** as a cPanel cron on the brasil-archives host (user
`fromuagq`). If the Supabase project turns out to belong to a different
project, move this doc there — nothing here is brasil-archives-specific
except the cron host.

---

## Background: what "paused" means on the Free plan

Free-plan projects pause after **7 days with no activity** (no requests to
the project's own endpoints). On pause:

- All project endpoints go offline — REST/PostgREST, Auth, Realtime,
  Storage, direct Postgres. Client calls fail until restored.
- **Data is retained**, not deleted. Restore brings it back in the same
  state. Restore takes several minutes (fresh compute + volume restore),
  not instant.
- Paused-project data retention is finite (Supabase has quoted ~90 days);
  after that an un-restored project can be permanently removed. Verify the
  current number against Supabase docs.
- Free plan allows **2 active (non-paused) projects** per org.

"Activity" = any request that touches the project. One request per week
resets the clock.

## Key facts for the script

- **Calling the Management API does NOT count as project activity.** Only
  hitting the *project's* endpoints (`https://<ref>.supabase.co/...`) keeps
  it alive.
- **Check status:** `GET https://api.supabase.com/v1/projects` with a
  Personal Access Token (from Supabase account settings) → each project has
  a `status` field.
  - `ACTIVE_HEALTHY` = running
  - `INACTIVE` = paused
  - `RESTORING` / `COMING_UP` = restore in progress
  - `PAUSING` / `GOING_DOWN` = shutting down
  - `INIT_FAILED` = provisioning/restore failed
- **Unpause via API:** `POST https://api.supabase.com/v1/projects/{ref}/restore`
  with the PAT. Corresponding `POST .../pause` exists. Confirm request body
  against the current Management API reference (these endpoints are newer
  and have shifted). Restore can fail if the org is already at the
  2-active-project limit or the project is mid-transition — check the HTTP
  status/body.
- Management API is rate-limited (~60 req/min); a twice-weekly cron is far
  under it.

---

## Plan

### 1. Tiny table so the ping exercises Postgres (run once in SQL editor)

```sql
create table public.keepalive (id int primary key default 1, pinged_at timestamptz default now());
insert into public.keepalive (id) values (1);
alter table public.keepalive enable row level security;
create policy "anon read" on public.keepalive for select to anon using (true);
```

(`/auth/v1/health` with an `apikey` header also works if we'd rather not
create a table.)

### 2. Script — `~/scripts/supabase_keepalive.py`

Stdlib only (system `/usr/bin/python3` is fine). Silent on success,
non-zero exit on failure so cPanel cron emails only on problems.

```python
#!/usr/bin/env python3
"""Keep a Supabase Free project active; restore it if it has already paused."""
import json, os, sys, urllib.request, urllib.error

REF  = os.environ["SUPABASE_PROJECT_REF"]
ANON = os.environ["SUPABASE_ANON_KEY"]
PAT  = os.environ.get("SUPABASE_PAT")  # optional: enables status check + auto-restore

def _req(url, headers, method="GET", data=None):
    r = urllib.request.Request(url, headers=headers, data=data, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return resp.status, resp.read()

def ping():
    url = f"https://{REF}.supabase.co/rest/v1/keepalive?select=id&limit=1"
    status, _ = _req(url, {"apikey": ANON, "Authorization": f"Bearer {ANON}"})
    if status != 200:
        sys.exit(f"keepalive ping got HTTP {status}")

def project_status():
    _, body = _req("https://api.supabase.com/v1/projects",
                   {"Authorization": f"Bearer {PAT}"})
    for p in json.loads(body):
        if REF in (p.get("id"), p.get("ref")):
            return p.get("status")
    sys.exit(f"project {REF} not found")

def main():
    if PAT:
        st = project_status()
        if st == "INACTIVE":
            _req(f"https://api.supabase.com/v1/projects/{REF}/restore",
                 {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"},
                 method="POST", data=b"{}")
            print(f"{REF}: was paused — restore requested")
            return
        if st != "ACTIVE_HEALTHY":
            sys.exit(f"{REF}: transitional state {st!r}, skipping ping")
    ping()

try:
    main()
except urllib.error.HTTPError as e:
    sys.exit(f"HTTP {e.code}: {e.read()[:300]!r}")
```

### 3. Secrets — `~/.config/supabase-keepalive.env` (chmod 600)

```
SUPABASE_PROJECT_REF=abcdefghijklmnop
SUPABASE_ANON_KEY=eyJhbGciOi...
SUPABASE_PAT=sbp_...          # omit for ping-only, no auto-restore
```

### 4. Wrapper — `~/scripts/supabase-keepalive.sh` (chmod 700)

```bash
#!/bin/bash
set -euo pipefail
set -a
source "$HOME/.config/supabase-keepalive.env"
set +a
exec /usr/bin/python3 "$HOME/scripts/supabase_keepalive.py"
```

### 5. cPanel cron (Advanced → Cron Jobs)

- **Cron Email:** set to Steve's address (script is silent on success →
  only emails on failure).
- **Schedule:** `0 6 * * 1,4` (Mon & Thu 06:00 — 3–4 day spacing, never
  near the 7-day limit).
- **Command:** `/home/fromuagq/scripts/supabase-keepalive.sh`

### 6. Test

```bash
~/scripts/supabase-keepalive.sh; echo "exit: $?"   # 0 + no output = ok
```

Then pause the project from the dashboard and re-run to confirm the
restore branch fires (needs `SUPABASE_PAT`).

Optional positive heartbeat: append `&& date >> ~/logs/supabase-keepalive.log`
to the cron command.

---

## Alternative schedulers (rejected for now)

- **GitHub Actions `schedule:`** — free, but scheduled runs get disabled
  after 60 days with no repo commits, and cron is delayed under load.
- cPanel cron wins: already in use here, independent of the Supabase
  project, reliable.
