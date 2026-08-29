"""Locale-aware helpers for i18n.

The main consumer is Jinja: templates render vocabulary labels via
``vocab_label(obj)`` and pick ``label_pt`` vs ``label_en`` based on the
active Flask-Babel locale. Falls back cleanly when a translation is
missing or the object is ``None``.

Kept in a standalone module so the pure fallback logic can be unit-tested
without a Flask app context (see ``tests/test_i18n_vocab_label.py``).
"""
from __future__ import annotations

from typing import Any


def resolve_label(
    obj: Any,
    locale: str,
    fallback_lang: str = "en",
) -> str:
    """Return ``obj.label_<locale>`` with graceful fallback.

    Rules:
      * ``obj is None`` → empty string
      * ``obj.label_<locale>`` if present and non-empty
      * else ``obj.label_<fallback_lang>`` if present and non-empty
      * else empty string

    Kept pure so tests don't need Flask-Babel wired up.
    """
    if obj is None:
        return ""

    primary_attr = f"label_{locale}"
    fallback_attr = f"label_{fallback_lang}"

    value = getattr(obj, primary_attr, None)
    if value:
        return value

    value = getattr(obj, fallback_attr, None)
    if value:
        return value

    return ""


def vocab_label(obj: Any, fallback_lang: str = "en") -> str:
    """Jinja-facing wrapper: reads locale from Flask-Babel at call time.

    Registered as a Jinja global by the app factory. Templates use it as
    ``{{ vocab_label(archive.institutional_type) }}`` in place of the
    older ``.label_en`` accesses.
    """
    from flask_babel import get_locale

    locale = str(get_locale() or fallback_lang)
    return resolve_label(obj, locale, fallback_lang=fallback_lang)


# Bilingual display labels for the probe-fed facet *values*. The value
# slugs (``at-risk`` etc.) come from ``app.services.scoring.PROBE_FACETS``;
# kept here rather than the gettext catalog to match ``vocab_label``.
_PROBE_FACET_LABELS: dict[str, dict[str, dict[str, str]]] = {
    "web_ops_health": {
        "healthy": {"en": "Healthy", "pt": "Saudável"},
        "degraded": {"en": "Degraded", "pt": "Degradado"},
        "at-risk": {"en": "At risk", "pt": "Em risco"},
        "down": {"en": "Down", "pt": "Fora do ar"},
    },
    "external_preservation": {
        "preserved": {"en": "Preserved", "pt": "Preservado"},
        "home-page-only": {"en": "Home page only", "pt": "Apenas a página inicial"},
        "unpreserved": {"en": "Unpreserved", "pt": "Não preservado"},
    },
    "growth_signal": {
        "active": {"en": "Active", "pt": "Ativo"},
        "slow": {"en": "Slow", "pt": "Lento"},
        "stalled": {"en": "Stalled", "pt": "Estagnado"},
        "wound-down": {"en": "Wound down", "pt": "Encerrado"},
        "unknown": {"en": "Unknown", "pt": "Desconhecido"},
    },
    "prior_use_signal": {
        "foundational": {"en": "Foundational", "pt": "Fundamental"},
        "established": {"en": "Established", "pt": "Estabelecido"},
        "emerging": {"en": "Emerging", "pt": "Emergente"},
        "unused": {"en": "No recorded use", "pt": "Sem uso registrado"},
        "unknown": {"en": "Unknown", "pt": "Desconhecido"},
    },
}


def probe_facet_label(facet: str, value: Any, fallback_lang: str = "en") -> str:
    """Locale-aware display label for a probe-fed facet value, e.g.
    ``probe_facet_label('web_ops_health', 'at-risk')`` → "At risk" / "Em
    risco". Unknown facet/value pairs return the raw value."""
    if not value:
        return ""
    from flask_babel import get_locale

    locale = str(get_locale() or fallback_lang)
    entry = _PROBE_FACET_LABELS.get(facet, {}).get(str(value))
    if not entry:
        return str(value)
    return entry.get(locale) or entry.get(fallback_lang) or str(value)
