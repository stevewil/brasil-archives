"""Admin blueprint — a single read-only observability dashboard.

Deliberately **not** a write-capable CRUD panel. brasil-archives keeps
config in git-tracked YAML/markdown loaded by idempotent scripts, and the
prod SQLite DB is periodically reseeded, so a direct-write admin panel
would be both unsafe (no auth on shared hosting) and pointless (writes
vanish on the next reseed). See
``docs/handoff/2026-08-29-search-licensing-admin.md`` §4.

``GET /admin/`` gathers scoring coverage, recent harvest runs, probe
status, live federation health, and recent harvest errors onto one page.
Gated by the existing ``BRASIL_ARCHIVES_ADMIN`` env flag — every route
404s when it is unset.
"""
from .routes import bp

__all__ = ["bp"]
