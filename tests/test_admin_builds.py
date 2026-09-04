"""``/admin/builds`` — the archive-miner work queue's operator surface.

The one write-capable admin corner. Behind the ``BRASIL_ARCHIVES_ADMIN``
gate like the rest of ``/admin``; CSRF-exempt so the operator can drive it
with curl. Transition guards mirror ``archive_miner.queue.JobQueue``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import create_app
from app.extensions import db as _db
from app.models import BuildJob
from app.services import builds as svc


# --------------------------------------------------------------------------- #
# gate


@pytest.fixture
def public_client():
    app = create_app("testing")
    app.config["ADMIN_UI_ENABLED"] = False
    with app.app_context():
        _db.create_all()
        yield app.test_client()
        _db.session.remove()
        _db.drop_all()


@pytest.mark.parametrize("path", ["/admin/builds", "/admin/builds/1"])
def test_routes_404_without_admin(public_client, path):
    assert public_client.get(path).status_code == 404


def test_create_404_without_admin(public_client):
    resp = public_client.post("/admin/builds", data={"archive_slug": "x"})
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# create


def test_create_via_form_redirects_to_detail(client, app):
    resp = client.post(
        "/admin/builds",
        data={"archive_slug": "rn-labim-t1r8", "construction_mode": "A"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "rn-labim-t1r8" in body
    with app.app_context():
        job = _db.session.scalar(select(BuildJob))
        assert job.archive_slug == "rn-labim-t1r8"
        assert job.construction_mode == "A"
        assert job.status == "queued"
        assert job.stage == "triage"


def test_create_via_json_returns_201_and_status(client):
    resp = client.post(
        "/admin/builds",
        json={"archive_slug": "rn-labim-t1r8", "construction_mode": "A",
              "budget_usd": 25, "options": {"delay": 0.6}},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["anchor"] == "rn-labim-t1r8"
    assert body["mode"] == "A"
    assert body["status"] == "queued"
    assert body["plan"][0] == "triage" and body["plan"][-1] == "deploy"
    assert body["cost"]["budget_usd"] == 25.0


def test_create_rejects_build_without_archive(client):
    resp = client.post("/admin/builds", json={"construction_mode": "A"})
    assert resp.status_code == 400
    assert "archive_slug" in resp.get_json()["error"]


def test_create_rejects_bad_mode(client):
    resp = client.post(
        "/admin/builds", json={"archive_slug": "x", "construction_mode": "Z"}
    )
    assert resp.status_code == 400


def test_create_rejects_bad_options_json_from_form(client):
    resp = client.post(
        "/admin/builds",
        data={"archive_slug": "x", "options": "{not json"},
        follow_redirects=True,
    )
    assert "must be valid JSON" in resp.get_data(as_text=True)


# --------------------------------------------------------------------------- #
# list


def test_list_html_and_json(client, app):
    with app.app_context():
        svc.create_job(archive_slug="a-one", construction_mode="A")
        svc.create_job(archive_slug="a-two")

    html = client.get("/admin/builds").get_data(as_text=True)
    assert "a-one" in html and "a-two" in html

    data = client.get("/admin/builds?format=json").get_json()
    assert data["count"] == 2
    anchors = {j["anchor"] for j in data["jobs"]}
    assert anchors == {"a-one", "a-two"}


def test_list_watched_filter_excludes_terminal(client, app):
    with app.app_context():
        j1 = svc.create_job(archive_slug="active-one")
        j2 = svc.create_job(archive_slug="cancelled-one")
        svc.cancel(j2)
        active_id, cancelled_id = j1.id, j2.id

    data = client.get("/admin/builds?filter=watched&format=json").get_json()
    ids = {j["job_id"] for j in data["jobs"]}
    assert active_id in ids and cancelled_id not in ids


# --------------------------------------------------------------------------- #
# detail


def test_detail_json_shape(client, app):
    with app.app_context():
        job = svc.create_job(archive_slug="shape-test", construction_mode="A")
        jid = job.id

    data = client.get(f"/admin/builds/{jid}?format=json").get_json()
    assert data["job_id"] == jid
    assert data["stage"] == "triage"
    assert data["stage_index"] == 0
    assert data["over_1h"] is False
    assert data["progress"]["unit"] == "items"


def test_detail_404_for_unknown(client):
    assert client.get("/admin/builds/999999").status_code == 404


def test_detail_management_report_appears_after_one_hour(client, app):
    with app.app_context():
        job = svc.create_job(archive_slug="long-runner", construction_mode="A")
        job.status = "running"
        job.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
        job.stage = "enumerate"
        job.progress = {"done": 400, "total": 2515, "unit": "items",
                        "rate_per_min": 80}
        job.eta_at = datetime.now(timezone.utc) + timedelta(minutes=26)
        _db.session.commit()
        jid = job.id

    body = client.get(f"/admin/builds/{jid}").get_data(as_text=True)
    assert "Management report" in body
    assert "400 / 2515" in body

    data = client.get(f"/admin/builds/{jid}?format=json").get_json()
    assert data["over_1h"] is True
    assert data["progress"]["pct"] == 15.9
    assert data["eta_human"] is not None


# --------------------------------------------------------------------------- #
# transitions


def test_pause_then_resume(client, app):
    with app.app_context():
        job = svc.create_job(archive_slug="pause-me")
        job.status = "running"
        _db.session.commit()
        jid = job.id

    r = client.post(f"/admin/builds/{jid}/pause", json={"note": "stopping for the night"})
    assert r.status_code == 200
    assert r.get_json()["status"] == "pause_requested"

    with app.app_context():
        job = _db.session.get(BuildJob, jid)
        job.status = "paused"  # the worker would do this on its way out
        _db.session.commit()

    r = client.post(f"/admin/builds/{jid}/resume", json={})
    assert r.status_code == 200
    assert r.get_json()["status"] == "queued"


def test_pause_rejected_when_not_active(client, app):
    with app.app_context():
        job = svc.create_job(archive_slug="done-job")
        job.status = "done"
        _db.session.commit()
        jid = job.id

    r = client.post(f"/admin/builds/{jid}/pause", json={})
    assert r.status_code == 409
    assert "cannot pause" in r.get_json()["error"]


def test_cancel_is_terminal(client, app):
    with app.app_context():
        job = svc.create_job(archive_slug="cancel-me")
        jid = job.id

    r = client.post(f"/admin/builds/{jid}/cancel", json={"note": "wrong archive"})
    assert r.status_code == 200
    assert r.get_json()["status"] == "cancelled"

    r = client.post(f"/admin/builds/{jid}/cancel", json={})
    assert r.status_code == 409


def test_transition_form_flow_flashes_and_redirects(client, app):
    with app.app_context():
        job = svc.create_job(archive_slug="form-flow")
        job.status = "running"
        _db.session.commit()
        jid = job.id

    resp = client.post(f"/admin/builds/{jid}/pause", data={"note": "n"},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert "Pause requested" in resp.get_data(as_text=True)
