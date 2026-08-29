"""Unit tests for app.text.fold — pure, no app context."""
from __future__ import annotations

from app.text import fold


def test_fold_is_case_insensitive():
    assert fold("Sumário") == fold("sumário")


def test_fold_strips_diacritics():
    assert fold("Sumário") == fold("sumario")
    assert fold("índios") == fold("indios")
    assert fold("São José") == fold("sao jose")


def test_fold_handles_empty_and_none_like():
    assert fold("") == ""
    assert fold(None) == ""  # type: ignore[arg-type]


def test_fold_preserves_substring_semantics():
    assert fold("caçador") in fold("O CAÇADOR de arquivos")
