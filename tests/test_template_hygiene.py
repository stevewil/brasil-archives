"""Grep-based template hygiene guardrails.

Cheap tests that catch specific regressions in Jinja templates. Each test
protects a landed track from silent reversion. Rationale in
``docs/handoff/2026-08-27-master.md`` §5.

These tests are intentionally simple: they walk template files and grep.
They don't parse Jinja, don't render, and don't touch the DB. They fail
loudly with file:line context when a rule is broken.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TEMPLATE_DIR = Path(__file__).parent.parent / "app" / "templates"


def _templates() -> list[Path]:
    return sorted(TEMPLATE_DIR.rglob("*.html"))


def test_templates_exist():
    """Sanity: this suite must actually be inspecting templates."""
    tpls = _templates()
    assert tpls, f"No templates under {TEMPLATE_DIR} — path drifted?"


def test_no_direct_label_en_or_label_pt_access():
    """Protects Track 4 (locale-aware vocab labels, landed a981b60).

    Direct access to ``x.label_en`` or ``x.label_pt`` in a template
    bypasses the locale-aware ``vocab_label`` helper. Use
    ``{{ vocab_label(x) }}`` instead so PT users see PT labels.

    Exception: none currently. Add an inline ``# hygiene: allow`` marker
    on the offending line if a real exception ever appears, and update
    this test to skip lines containing that marker.
    """
    pattern = re.compile(r"\.label_(en|pt)\b")
    offenders: list[str] = []
    for tpl in _templates():
        for lineno, line in enumerate(
            tpl.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if pattern.search(line):
                rel = tpl.relative_to(TEMPLATE_DIR)
                offenders.append(f"  {rel}:{lineno}: {line.strip()}")

    assert not offenders, (
        "Direct access to .label_en / .label_pt in templates — use "
        "vocab_label(x) instead:\n" + "\n".join(offenders)
    )


@pytest.mark.skip(
    reason="Enable after UI Polish Track 5 lands (inline styles moved to "
    "style.css). Currently detail.html upgrade-projects section has ~60 "
    "lines of intentional inline styles awaiting Track 5."
)
def test_no_static_inline_style_attributes():
    """Guardrail for Track 5.

    Inline ``style="..."`` attributes with a static value belong in
    ``style.css``. Dynamic ones (``style="width: {{ pct }}%"``) are fine.
    """
    offenders: list[str] = []
    for tpl in _templates():
        for lineno, line in enumerate(
            tpl.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if 'style="' not in line:
                continue
            # Extract the value between style=" and the next "
            try:
                after = line.split('style="', 1)[1]
                value = after.split('"', 1)[0]
            except IndexError:
                continue
            if "{{" in value or "{%" in value:
                continue  # dynamic; allowed
            rel = tpl.relative_to(TEMPLATE_DIR)
            offenders.append(f"  {rel}:{lineno}: {line.strip()[:100]}")

    assert not offenders, (
        "Static inline styles — move to app/static/style.css:\n"
        + "\n".join(offenders)
    )
