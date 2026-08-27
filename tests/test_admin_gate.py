"""Admin/public split — BRASIL_ARCHIVES_ADMIN gate (UI Polish Track 2).

The `app` fixture from conftest sets ``ADMIN_UI_ENABLED = True`` (via
``TestingConfig``) so the rest of the suite exercises the internal UI.
These tests build their own app with the flag *off* to prove the public
deployment hides and 404s the internal surface.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app import create_app
from app.extensions import db as _db
from app.models import Archive, InstitutionalType
from app.services import scoring as svc
from scripts import load_vocabularies


@pytest.fixture
def public_app():
    app = create_app("testing")
    app.config["ADMIN_UI_ENABLED"] = False
    with app.app_context():
        _db.create_all()
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
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def public_client(public_app):
    return public_app.test_client()


# --------------------------------------------------------------------------- #
# Routes 404 when the flag is off


@pytest.mark.parametrize(
    "path",
    ["/harvest/", "/harvest/runs/1", "/harvest/records/1"],
)
def test_harvest_routes_404_without_admin(public_client, path):
    assert public_client.get(path).status_code == 404


def test_score_post_404_without_admin(public_client):
    resp = public_client.post(
        "/archives/rn-labim-t1r1/score",
        data={"dimension": "accessibility", "score": "5", "justification_en": "x"},
    )
    assert resp.status_code == 404


def test_facets_route_404_without_admin(public_client):
    assert public_client.get("/archives/rn-labim-t1r1/facets").status_code == 404
    assert public_client.post("/archives/rn-labim-t1r1/facets").status_code == 404


# --------------------------------------------------------------------------- #
# Public detail page: read-only, no operator controls


def test_public_detail_hides_scoring_form_and_facet_link(public_client):
    body = public_client.get("/archives/rn-labim-t1r1").get_data(as_text=True)
    assert "score-form" not in body
    assert "Edit facets &amp; tags" not in body
    assert "Not yet scored." in body


def test_public_detail_shows_readonly_score_summary(public_app, public_client):
    with public_app.app_context():
        archive = _db.session.scalar(
            select(Archive).where(Archive.slug == "rn-labim-t1r1")
        )
        svc.record_score(
            archive=archive,
            dimension="accessibility",
            score=7,
            justification_en="Good OAI endpoint.",
            justification_pt=None,
            scored_by="tester",
        )
        _db.session.commit()

    body = public_client.get("/archives/rn-labim-t1r1").get_data(as_text=True)
    assert "dimension-summary" in body
    assert "7/10" in body
    assert "Good OAI endpoint." in body
    assert "score-form" not in body


def test_public_base_hides_harvest_nav(public_client):
    body = public_client.get("/").get_data(as_text=True)
    assert "/harvest" not in body


# --------------------------------------------------------------------------- #
# Sanity: same routes work when the flag is on (default test config)


def test_admin_routes_reachable_with_flag_on(client, app):
    # `client`/`app` come from conftest where ADMIN_UI_ENABLED is True.
    assert app.config["ADMIN_UI_ENABLED"] is True
    assert client.get("/harvest/").status_code == 200
