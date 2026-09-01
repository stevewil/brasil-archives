"""CLI utility scripts (``python -m scripts.<name>``).

Load the repo-root ``.env`` on import so every script sees the same
configuration the app does. Without this, ``python -m scripts.load_survey``
(and the harvest / calibration loaders) run with ``DATABASE_URL`` unset and
silently fall back to the SQLite default — even when ``.env`` points at
Postgres. That mismatch is how a "reseed" lands in the wrong database.

The Flask CLI (``flask db upgrade``) already auto-loads ``.env``; this makes
the plain-``python`` entry points behave the same. ``override=False`` keeps
an explicitly-exported ``DATABASE_URL`` / CI job env winning over the file.
"""
from __future__ import annotations

from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:  # pragma: no cover - python-dotenv is a hard dependency
    pass
