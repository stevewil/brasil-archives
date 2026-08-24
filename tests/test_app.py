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
