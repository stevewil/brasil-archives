"""UI Polish Track 1 — PT translation catalog.

Verifies the compiled catalog renders Portuguese end to end and that the
``pt`` catalog is fully translated (no half-finished msgids).

Note: Flask-Babel caches the resolved locale for the lifetime of an app
context, and the ``app`` fixture holds one open per test — so a single
test function cannot assert both EN and PT. Locale assertions are split
into separate test functions on purpose.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from babel.messages.pofile import read_po
from sqlalchemy import select

from app.extensions import db as _db
from app.models import Archive, InstitutionalType
from scripts import load_vocabularies

TRANSLATIONS = Path(__file__).parent.parent / "app" / "translations"


# --------------------------------------------------------------------------- #
# Catalog completeness


def test_pt_catalog_is_fully_translated():
    """Every msgid in the pt catalog has a non-empty msgstr."""
    with (TRANSLATIONS / "pt" / "LC_MESSAGES" / "messages.po").open("rb") as fh:
        catalog = read_po(fh)

    untranslated = []
    for message in catalog:
        if not message.id:  # header
            continue
        if isinstance(message.id, (list, tuple)):
            if not all(message.string):
                untranslated.append(message.id)
        elif not message.string:
            untranslated.append(message.id)

    assert not untranslated, (
        "pt catalog has untranslated msgids:\n"
        + "\n".join(f"  {m!r}" for m in untranslated)
    )


def test_pt_catalog_uses_uso_justo_not_uso_legitimo():
    """Project terminology rule: 'uso justo', never 'uso legítimo'."""
    text = (TRANSLATIONS / "pt" / "LC_MESSAGES" / "messages.po").read_text(
        encoding="utf-8"
    )
    assert "uso justo" in text
    assert "uso legítimo" not in text.lower()


def test_pt_and_en_catalogs_are_compiled():
    for lang in ("pt", "en"):
        assert (TRANSLATIONS / lang / "LC_MESSAGES" / "messages.mo").exists(), (
            f"{lang} catalog not compiled — run `pybabel compile -d app/translations`"
        )


# --------------------------------------------------------------------------- #
# Rendered output


@pytest.fixture
def seeded_app(app):
    with app.app_context():
        load_vocabularies.load_all()
        federal = _db.session.scalar(
            select(InstitutionalType).where(
                InstitutionalType.slug == "federal-university"
            )
        )
        _db.session.add(
            Archive(
                slug="rn-labim-t1r1",
                name="LABIM/UFRN",
                institutional_type_id=federal.id,
                home_state_code="RN",
                canonical_url="https://labim.example",
                no_digital_content=False,
                survey_source="test",
                survey_row=1,
            )
        )
        _db.session.commit()
    return app


def test_index_renders_portuguese(seeded_app, client):
    body = client.get("/?lang=pt").get_data(as_text=True)
    assert "Arquivos catalogados" in body
    assert "Projetos" in body
    assert "Sobre o método" in body


def test_index_still_renders_english(seeded_app, client):
    body = client.get("/?lang=en").get_data(as_text=True)
    assert "Archives cataloged" in body
    assert "About the method" in body


def test_archives_list_renders_portuguese(seeded_app, client):
    body = client.get("/archives/?lang=pt").get_data(as_text=True)
    assert "Ordenar" in body
    assert "Aplicar" in body
    assert "Soma não-ponderada" in body


def test_archives_list_still_renders_english(seeded_app, client):
    body = client.get("/archives/?lang=en").get_data(as_text=True)
    assert "Naive sum (desc)" in body
    assert "No digital content" in body


def test_archive_detail_renders_portuguese(seeded_app, client):
    body = client.get("/archives/rn-labim-t1r1?lang=pt").get_data(as_text=True)
    assert "Perfil de pontuação" in body
    assert "Pontuações por dimensão" in body
    assert "Facetas e etiquetas" in body
    assert "Elegibilidade para uso justo" in body


def test_archive_detail_still_renders_english(seeded_app, client):
    body = client.get("/archives/rn-labim-t1r1?lang=en").get_data(as_text=True)
    assert "Score profile" in body
    assert "Dimension scores" in body
    assert "Fair use eligibility" in body
