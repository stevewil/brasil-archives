"""Smoke tests for the Flask scaffold."""
from __future__ import annotations


def test_app_boots(app):
    assert app is not None
    assert app.config["TESTING"] is True
    assert "en" in app.config["LANGUAGES"]
    assert "pt" in app.config["LANGUAGES"]


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["status"] == "ok"
    assert payload["app"] == "brasil-archives"
    assert payload["database"] in ("sqlite", "postgresql")
    assert payload["database_connected"] is True


def test_healthz_degraded_when_db_unreachable(client, monkeypatch):
    """A DATABASE_URL that parses but can't answer -> 503, not a green 200."""
    from app.extensions import db

    def _boom(*_a, **_k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(db.session, "execute", _boom)
    r = client.get("/healthz")
    assert r.status_code == 503
    payload = r.get_json()
    assert payload["status"] == "degraded"
    assert payload["database_connected"] is False
    assert "connection refused" in payload["database_error"]


def test_index_renders_en(client):
    r = client.get("/?lang=en")
    assert r.status_code == 200
    assert b"Brazilian Digital Archives" in r.data
    assert b"Archives cataloged" in r.data


def test_index_renders_pt_fallback(client):
    # No PT catalog yet — English strings should still render.
    r = client.get("/?lang=pt")
    assert r.status_code == 200


def test_lang_switch_present(client):
    r = client.get("/")
    assert b"lang=en" in r.data
    assert b"lang=pt" in r.data


def test_head_metadata_present(client):
    """Track 5: every page carries a description, OG tags, and a favicon."""
    r = client.get("/")
    assert b'<meta name="description"' in r.data
    assert b'property="og:title"' in r.data
    assert b'property="og:description"' in r.data
    assert b'rel="icon"' in r.data and b"favicon.svg" in r.data


def test_og_locale_en(client):
    assert b'property="og:locale" content="en_US"' in client.get("/?lang=en").data


def test_og_locale_pt(client):
    # Separate test: Flask-Babel caches the resolved locale for the life of
    # the app context, and the `app` fixture holds one open per test — so a
    # single test can't exercise both locales.
    assert b'property="og:locale" content="pt_BR"' in client.get("/?lang=pt").data


def test_page_description_is_overridable(client):
    """Per-page {% block description %} overrides the base default."""
    generic = b"A federated catalog of Brazilian digital archives"
    r = client.get("/archives/")
    assert generic not in r.data
    assert b"Browse and filter the surveyed Brazilian digital archives" in r.data
