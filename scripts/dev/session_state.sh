#!/usr/bin/env bash
# Session bootstrap digest for brasil-archives.
#
# Print a compact overview of current state so a new agent session
# (human or LLM) doesn't spend context re-discovering it. Rationale
# in docs/handoff/2026-08-27-master.md §5.
#
# Usage: bash scripts/dev/session_state.sh
#
# Assumes:
#   - Run from anywhere; script cd's to repo root itself.
#   - System `python` and `flask` on PATH (no venv in sandbox).
#   - DATABASE_URL either pre-set or falls back to instance SQLite.

set -u  # NOT -e: some steps are opportunistic and shouldn't abort the digest

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

DB_URL="${DATABASE_URL:-sqlite:///$REPO_ROOT/instance/brasil_archives.db}"

echo "=== brasil-archives session state ==="
echo "repo: $REPO_ROOT"
echo "date: $(date -u '+%Y-%m-%d %H:%M UTC')"
echo

echo "--- git ---"
git log --oneline -3 2>/dev/null || echo "(not a git repo?)"
echo
git_status="$(git status --short 2>/dev/null)"
if [ -z "$git_status" ]; then
    echo "working tree clean"
else
    echo "$git_status"
fi
echo

echo "--- tests ---"
if command -v python >/dev/null 2>&1; then
    # `pytest --collect-only` (no -q) ends with a "NN tests collected" line.
    python -m pytest --collect-only 2>&1 | grep -E '[0-9]+ (tests? collected|error)' | tail -1
else
    echo "python not on PATH"
fi
echo

echo "--- live URL ---"
if command -v curl >/dev/null 2>&1; then
    curl -sS --max-time 5 https://brasil-archives.from-bottom-to.top/healthz \
        || echo "  (offline or unreachable)"
    echo
else
    echo "curl not on PATH"
fi
echo

echo "--- DB counts ---"
DATABASE_URL="$DB_URL" FLASK_APP=wsgi.py python - <<'PY' 2>&1
try:
    from app import create_app
    from app.extensions import db
    from app.models import (
        Archive,
        UpgradeProject,
        AggregatedRecord,
        HarvestRun,
    )
    app = create_app()
    with app.app_context():
        for label, model in [
            ("archives", Archive),
            ("upgrade_projects", UpgradeProject),
            ("aggregated_records", AggregatedRecord),
            ("harvest_runs", HarvestRun),
        ]:
            try:
                print(f"{label}: {db.session.query(model).count()}")
            except Exception as exc:
                print(f"{label}: (query failed: {exc})")
except Exception as exc:
    print(f"(unable to open DB: {exc})")
PY

echo
echo "--- sister repos (if present) ---"
for sibling in ../mipibu ../povos-indigenas-rn; do
    if [ -d "$sibling/.git" ]; then
        printf "%s:  " "$(basename "$sibling")"
        (cd "$sibling" && git log --oneline -1 2>/dev/null)
    fi
done

echo
echo "=== end ==="
