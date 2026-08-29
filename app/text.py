"""Small text helpers shared across search surfaces.

Kept dependency-free and Flask-agnostic so the pure logic can be
unit-tested without an app context (see ``tests/test_text.py``).
"""
from __future__ import annotations

import unicodedata


def fold(text: str) -> str:
    """Normalize for accent- and case-insensitive substring matching.

    Case-folds, then decomposes to NFKD and drops combining marks, so
    ``fold("Sumário") == fold("sumario")``. Used by both the federated
    record search and the archive-catalog search.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text).casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))
