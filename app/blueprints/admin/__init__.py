"""Admin blueprint(s) for the internal deployment.

``routes.bp`` is a single **read-only** observability dashboard
(``GET /admin/``). brasil-archives keeps config in git-tracked YAML/markdown
and periodically reseeds the prod DB, so a direct-write admin panel would be
both unsafe (no auth on shared hosting) and pointless (writes vanish on the
next reseed). See ``docs/handoff/2026-08-29-search-licensing-admin.md`` §4.

``builds.bp`` (``/admin/builds``) is the one exception: the archive-miner
work queue is live runtime state that no script owns, so that corner is
write-capable. Both blueprints are gated by ``BRASIL_ARCHIVES_ADMIN`` —
every route 404s when it is unset.
"""
from .builds import bp as builds_bp
from .routes import bp

__all__ = ["bp", "builds_bp"]
