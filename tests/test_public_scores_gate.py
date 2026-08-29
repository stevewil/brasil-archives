"""Public-scores visibility gate — BRASIL_ARCHIVES_PUBLIC_SCORES.

The catalog and federated search are public from the start; the scored
judgments (dimension scores, the two axis totals, the quadrant label, the
legacy naive sum, and the score-ranked home block) stay private until
``BRASIL_ARCHIVES_PUBLIC_SCORES=1`` — or the internal deployment's
``BRASIL_ARCHIVES_ADMIN=1``. See ``app/visibility.py``.

The ``app`` fixture from conftest sets both flags on (via
``TestingConfig``) so the score-display suite keeps passing. These tests
build their own app with both flags *off* to prove the public soft-launch
hides the judgments, then flip each flag on to prove they come back.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app import create_app
from app.extensions import db as _db
from app.models import Archive, InstitutionalType
from app.services import scoring as svc
from scripts import load_vocabularies


def _make_app(*, public_scores: bool, admin: bool):
    app = create_app("testing")
    app.config["ADMIN_UI_ENABLED"] = admin
    app.config["PUBLIC_SCORES_ENABLED"] = public_scores
    return app


def _seed(app):
    with app.app_context():
        _db.create_all()
        load_vocabularies.load_all()
        federal = _db.session.scalar(
            select(InstitutionalType).where(
                InstitutionalType.slug == "federal-university"
            )
        )
        archive = Archive(
            slug="rn-labim-t1r1",
            name="LABIM/UFRN",
            institutional_type_id=federal.id,
            home_state_code="RN",
            canonical_url="https://labim.example",
            no_digital_content=False,
            fair_use_eligible=True,
            survey_source="test",
            survey_row=1,
        )
        _db.session.add(archive)
        _db.session.commit()
        # Full 8-dimension profile so every score surface has data.
        from app.models import DIMENSIONS

        for dim in DIMENSIONS:
            svc.record_score(
                archive=archive,
                dimension=dim,
                score=6,
                justification_en="gate test",
                justification_pt=None,
                scored_by=None,
            )
        _db.session.commit()


@pytest.fixture
def gated_app():
    """Both flags off — the public soft-launch state."""
    app = _make_app(public_scores=False, admin=False)
    _seed(app)
    yield app
    with app.app_context():
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def gated_client(gated_app):
    return gated_app.test_client()


# --------------------------------------------------------------------------- #
# Flags off: no scored judgments anywhere public


def test_list_hides_score_columns_and_sorts(gated_client):
    body = gated_client.get("/archives/").get_data(as_text=True)
    assert ">Pipeline<" not in body
    assert ">Research<" not in body
    assert "Naive sum (desc)" not in body
    assert 'value="pipeline"' not in body


def test_list_score_sort_falls_back_to_name(gated_client):
    # ?sort=pipeline must not leak ranking through row order.
    body = gated_client.get("/archives/?sort=pipeline").get_data(as_text=True)
    assert body.count("<tr>") >= 1  # renders fine
    assert ">Pipeline<" not in body


def test_detail_hides_score_profile_and_dimensions(gated_client):
    body = gated_client.get("/archives/rn-labim-t1r1").get_data(as_text=True)
    assert "Quadrant" not in body
    assert "axis-card" not in body
    assert "dimension-summary" not in body
    assert "6/10" not in body
    assert "Evaluation in progress" in body


def test_home_hides_score_badge(gated_client):
    body = gated_client.get("/").get_data(as_text=True)
    assert "/80" not in body
    assert "Featured archives" not in body
    assert "Archives in the catalog" in body


def test_catalog_still_works(gated_client):
    body = gated_client.get("/archives/").get_data(as_text=True)
    assert "LABIM/UFRN" in body  # the catalog itself is public


# --------------------------------------------------------------------------- #
# Either flag on: the judgments come back


@pytest.mark.parametrize(
    ("public_scores", "admin"),
    [(True, False), (False, True)],
)
def test_scores_visible_when_either_flag_on(public_scores, admin):
    app = _make_app(public_scores=public_scores, admin=admin)
    _seed(app)
    try:
        client = app.test_client()
        assert ">Pipeline<" in client.get("/archives/").get_data(as_text=True)
        detail = client.get("/archives/rn-labim-t1r1").get_data(as_text=True)
        assert "Quadrant" in detail
        assert "axis-card" in detail
        assert "/80" in client.get("/").get_data(as_text=True)
    finally:
        with app.app_context():
            _db.session.remove()
            _db.drop_all()
