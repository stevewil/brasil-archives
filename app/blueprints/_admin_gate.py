"""Admin/public split for the internal UI.

`brasil-archives` serves two audiences from one deployment codebase: a
resource-constrained scoring team (internal) and, later, a read-only
public catalog. Rather than a URL-prefix blueprint refactor — which would
rewrite every ``url_for`` and test path — the internal-only views are
guarded by a single env flag, ``BRASIL_ARCHIVES_ADMIN=1``
(``config["ADMIN_UI_ENABLED"]``).

When the flag is off, guarded routes return 404 (not 403 — a public
visitor should not learn the route exists) and templates hide the
controls via the ``admin_ui_enabled()`` Jinja global.
"""
from __future__ import annotations

import functools
from typing import Callable, TypeVar

from flask import abort, current_app

F = TypeVar("F", bound=Callable)


def admin_only(view: F) -> F:
    """Return 404 unless ``ADMIN_UI_ENABLED`` is set for this deployment."""

    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if not current_app.config.get("ADMIN_UI_ENABLED"):
            abort(404)
        return view(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
