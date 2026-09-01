"""Read-only admin dashboard — GET /admin/.

Behind the existing ``BRASIL_ARCHIVES_ADMIN`` gate: 200 on the internal
deployment, 404 when the flag is unset. No write paths.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app import create_app
from app.extensions import db as _db
from app.models import Archive, InstitutionalType
from app.services import scoring as svc
from app.services.sources import drop_source_views, rebuild_source_views
from scripts import load_vocabularies


def _seed_one_archive(app):
    with app.app_context():
        _db.create_all()
        rebuild_source_views(_db.engine)
        load_vocabularies.load_all()
        # Idempotent: on SQLite each app gets its own :memory: DB, but on a
        # shared Postgres (TEST_DATABASE_URL) the admin_app + public_app
        # fixtures hit the same DB, so the second seed would collide.
        if _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim-t1r1")):
            return
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
        svc.record_score(
            archive=archive,
            dimension="accessibility",
            score=7,
            justification_en="ok",
            justification_pt=None,
            scored_by=None,
        )
        _db.session.commit()


@pytest.fixture
def admin_app():
    app = create_app("testing")
    app.config["ADMIN_UI_ENABLED"] = True
    _seed_one_archive(app)
    yield app
    with app.app_context():
        _db.session.remove()
        drop_source_views(_db.engine)
        _db.drop_all()


@pytest.fixture
def public_app():
    app = create_app("testing")
    app.config["ADMIN_UI_ENABLED"] = False
    _seed_one_archive(app)
    yield app
    with app.app_context():
        _db.session.remove()
        drop_source_views(_db.engine)
        _db.drop_all()


def test_dashboard_200_for_admin(admin_app):
    body = admin_app.test_client().get("/admin/").get_data(as_text=True)
    assert "Admin dashboard" in body
    assert "Scoring coverage" in body
    assert "Probe status" in body
    assert "Federation health" in body
    assert "Recent harvest runs" in body


def test_dashboard_reports_scoring_coverage(admin_app):
    body = admin_app.test_client().get("/admin/").get_data(as_text=True)
    # 1 viable archive, 1 with a score, 0 fully scored.
    assert "Pipeline-viable archives" in body
    assert "With at least one active score" in body


def test_dashboard_renders_portuguese(admin_app):
    body = admin_app.test_client().get("/admin/?lang=pt").get_data(as_text=True)
    assert "Painel administrativo" in body
    assert "Saúde da federação" in body


def test_dashboard_404_without_admin(public_app):
    assert public_app.test_client().get("/admin/").status_code == 404


def test_dashboard_nav_link_only_when_admin(admin_app, public_app):
    admin_body = admin_app.test_client().get("/").get_data(as_text=True)
    assert 'href="/admin/"' in admin_body
    public_body = public_app.test_client().get("/").get_data(as_text=True)
    assert "/admin/" not in public_body


def test_dashboard_is_read_only(admin_app):
    body = admin_app.test_client().get("/admin/").get_data(as_text=True)
    assert "<form" not in body
    # POST is not a registered method on the dashboard route.
    assert admin_app.test_client().post("/admin/").status_code == 405
