"""Which audience sees the scored judgments.

``brasil-archives`` serves two audiences from one codebase (see
``app/blueprints/_admin_gate.py``). The catalog and federated search are
public from the start; the *scored judgments* — dimension scores, the two
axis totals, the quadrant label, the legacy naive sum, and the
score-ranked home block — stay private until they are trustworthy enough
to publish.

``scores_visible()`` is the single source of truth: scores show when the
public-scores flag is on **or** this is the internal deployment. Templates
call it as the ``show_scores()`` Jinja global; views import it directly.
"""
from __future__ import annotations

from flask import current_app


def scores_visible() -> bool:
    """True when scored judgments should be rendered for this request.

    ``BRASIL_ARCHIVES_PUBLIC_SCORES=1`` (public greenlight) **or**
    ``BRASIL_ARCHIVES_ADMIN=1`` (internal deployment).
    """
    cfg = current_app.config
    return bool(cfg.get("PUBLIC_SCORES_ENABLED") or cfg.get("ADMIN_UI_ENABLED"))
