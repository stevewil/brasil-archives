"""``/admin/builds`` — enqueue and steer archive-miner jobs.

This is the one write-capable corner of the admin surface. The rest of
``/admin`` is read-only on purpose (config lives in git, the prod DB is
reseeded); the build queue is the exception because it *is* live runtime
state that no script owns — a corpus build is a long, resumable job driven
from here and executed by the out-of-app miner.

Routes (all behind the ``BRASIL_ARCHIVES_ADMIN`` gate, like the rest of
``/admin``; there is no auth boundary on shared hosting beyond that flag, so
these POSTs are CSRF-exempt to let the operator drive them with curl):

    GET  /admin/builds                 list (HTML, or JSON with ?format=json)
    POST /admin/builds                 create a job (form or JSON body)
    GET  /admin/builds/<id>            status (HTML, or JSON)
    POST /admin/builds/<id>/pause      request pause
    POST /admin/builds/<id>/resume     re-queue a paused / blocked job
    POST /admin/builds/<id>/cancel     terminal cancel

The status view renders ``app.services.builds.status_dict`` and leads with
the management report once a job passes one hour.
"""
from __future__ import annotations

import json
from typing import Any

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import lazy_gettext as _l

from ...services import builds as svc
from .._admin_gate import admin_only

bp = Blueprint("admin_builds", __name__, url_prefix="/admin/builds")

_LIST_LIMIT = 100


def _wants_json() -> bool:
    if request.args.get("format") == "json":
        return True
    if request.is_json:
        return True
    accept = request.accept_mimetypes
    return (
        accept["application/json"] >= accept["text/html"]
        and accept["application/json"] > 0
    )


def _payload() -> dict[str, Any]:
    """Merge a JSON body and form fields into one flat dict."""
    data: dict[str, Any] = {}
    if request.is_json:
        body = request.get_json(silent=True)
        if isinstance(body, dict):
            data.update(body)
    data.update(request.form.to_dict())
    return data


# --------------------------------------------------------------------------- #
# List + create


@bp.route("/", methods=["GET"], endpoint="index", strict_slashes=False)
@admin_only
def index():
    only_watched = request.args.get("filter") == "watched"
    jobs = svc.list_jobs(only_watched=only_watched, limit=_LIST_LIMIT)
    if _wants_json():
        return jsonify(
            {"jobs": [svc.status_dict(j) for j in jobs], "count": len(jobs)}
        )
    return render_template(
        "admin/builds/index.html",
        page_title=_l("Builds"),
        jobs=jobs,
        status_of=svc.status_dict,
        only_watched=only_watched,
        valid_modes=svc.VALID_MODES,
    )


@bp.route("/", methods=["POST"], endpoint="create", strict_slashes=False)
@admin_only
def create():
    data = _payload()

    # A form posts options as a JSON string; a JSON body may send an object.
    options = data.get("options")
    if isinstance(options, str):
        options = options.strip()
        if options:
            try:
                options = json.loads(options)
            except ValueError:
                msg = "options must be valid JSON"
                if _wants_json():
                    return jsonify({"error": msg}), 400
                flash(msg, "error")
                return redirect(url_for("admin_builds.index"))
        else:
            options = None

    try:
        job = svc.create_job(
            kind=data.get("kind") or "build",
            construction_mode=data.get("construction_mode"),
            archive_slug=data.get("archive_slug"),
            project_slug=data.get("project_slug"),
            options=options,
            budget_usd=data.get("budget_usd"),
        )
    except svc.BuildRequestError as exc:
        if _wants_json():
            return jsonify({"error": str(exc)}), 400
        flash(str(exc), "error")
        return redirect(url_for("admin_builds.index"))

    if _wants_json():
        return jsonify(svc.status_dict(job)), 201
    flash(_l("Queued build job #%(id)s.", id=job.id), "success")
    return redirect(url_for("admin_builds.detail", job_id=job.id))


# --------------------------------------------------------------------------- #
# One job


@bp.route("/<int:job_id>", methods=["GET"], endpoint="detail")
@admin_only
def detail(job_id: int):
    job = svc.get_job(job_id)
    if job is None:
        abort(404)
    status = svc.status_dict(job)
    if _wants_json():
        return jsonify(status)
    return render_template(
        "admin/builds/detail.html",
        page_title=_l("Build #%(id)s", id=job.id),
        job=job,
        status=status,
    )


def _transition(job_id: int, action: str):
    job = svc.get_job(job_id)
    if job is None:
        abort(404)

    note = _payload().get("note", "")
    if action == "pause":
        ok = svc.request_pause(job, note)
        done_msg = _l("Pause requested for build #%(id)s.", id=job.id)
    elif action == "resume":
        ok = svc.resume(job)
        done_msg = _l("Re-queued build #%(id)s.", id=job.id)
    else:  # cancel
        ok = svc.cancel(job, note)
        done_msg = _l("Cancelled build #%(id)s.", id=job.id)

    if _wants_json():
        body = svc.status_dict(job)
        if not ok:
            body["error"] = f"cannot {action} a job in status {job.status!r}"
            return jsonify(body), 409
        return jsonify(body)

    if ok:
        flash(done_msg, "success")
    else:
        flash(
            _l("Cannot %(action)s build #%(id)s (status: %(status)s).",
               action=action, id=job.id, status=job.status),
            "error",
        )
    return redirect(url_for("admin_builds.detail", job_id=job.id))


@bp.route("/<int:job_id>/pause", methods=["POST"], endpoint="pause")
@admin_only
def pause(job_id: int):
    return _transition(job_id, "pause")


@bp.route("/<int:job_id>/resume", methods=["POST"], endpoint="resume")
@admin_only
def resume(job_id: int):
    return _transition(job_id, "resume")


@bp.route("/<int:job_id>/cancel", methods=["POST"], endpoint="cancel")
@admin_only
def cancel(job_id: int):
    return _transition(job_id, "cancel")
