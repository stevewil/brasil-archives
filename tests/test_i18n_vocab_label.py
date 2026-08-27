"""Unit tests for ``app.i18n.resolve_label`` — pure fallback logic.

Kept intentionally free of Flask app context / DB. The Jinja-facing
``vocab_label`` wrapper is exercised indirectly by the blueprint tests
that render templates against real vocabulary rows.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.i18n import resolve_label


def _vocab(**labels):
    """Build a minimal duck-typed vocab row with ``label_*`` attrs."""
    return SimpleNamespace(**labels)


class TestResolveLabel:
    def test_returns_empty_when_obj_is_none(self):
        assert resolve_label(None, locale="pt") == ""

    def test_returns_pt_label_when_locale_is_pt_and_pt_set(self):
        obj = _vocab(label_en="Judicial", label_pt="Judicial (PT)")
        assert resolve_label(obj, locale="pt") == "Judicial (PT)"

    def test_returns_en_label_when_locale_is_en(self):
        obj = _vocab(label_en="Judicial", label_pt="Judicial (PT)")
        assert resolve_label(obj, locale="en") == "Judicial"

    def test_falls_back_to_en_when_pt_label_missing(self):
        obj = _vocab(label_en="Judicial", label_pt=None)
        assert resolve_label(obj, locale="pt") == "Judicial"

    def test_falls_back_to_en_when_pt_label_empty_string(self):
        obj = _vocab(label_en="Judicial", label_pt="")
        assert resolve_label(obj, locale="pt") == "Judicial"

    def test_returns_empty_when_both_missing(self):
        obj = _vocab(label_en=None, label_pt=None)
        assert resolve_label(obj, locale="pt") == ""

    def test_unknown_locale_falls_back_to_english(self):
        """A locale for which no ``label_<xx>`` attribute exists must not
        raise; it should fall through to the fallback language."""
        obj = _vocab(label_en="Judicial", label_pt="Judicial (PT)")
        assert resolve_label(obj, locale="fr") == "Judicial"

    def test_custom_fallback_lang_honored(self):
        obj = _vocab(label_en="Judicial", label_pt="Judicial (PT)")
        # fr is unknown; fall back to pt instead of en
        assert resolve_label(obj, locale="fr", fallback_lang="pt") == "Judicial (PT)"

    @pytest.mark.parametrize("locale", ["en", "pt"])
    def test_missing_attr_does_not_raise(self, locale):
        """Some objects may lack the label attributes entirely (e.g. a
        model with only ``name``). We treat that as 'no label'."""
        obj = _vocab(name="something")
        assert resolve_label(obj, locale=locale) == ""
