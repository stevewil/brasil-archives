"""Operator side of the archive-miner build queue.

The miner itself (``packages/archive-miner`` in the corpus-explorers repo) is
a standalone process on the dev box / a cloud runner. It reads and writes
``build_jobs`` / ``build_reports`` directly over psycopg
(``archive_miner.queue.JobQueue``). This module is the *other* client of the
same two tables: the ``/admin/builds`` panel calls it to enqueue a job and to
pause / resume / cancel one, and to render a job's status.

The transition guards here are a deliberate mirror of
``archive_miner.queue.JobQueue`` — keep them in lock-step. ``status_dict`` is a
port of ``archive_miner.report.status`` onto the ORM model.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from ..extensions import db
from ..models import BuildJob
from ..models.build_job import (
    KIND_BUILD,
    KIND_SYNC,
    MODE_A,
    MODE_B,
    MODE_C,
    ST_BLOCKED,
    ST_CANCELLED,
    ST_PAUSE_REQUESTED,
    ST_PAUSED,
    ST_QUEUED,
    ST_RUNNING,
    TERMINAL_STATUSES,
)

VALID_KINDS = (KIND_BUILD, KIND_SYNC)
VALID_MODES = (MODE_A, MODE_B, MODE_C)

# Statuses that still want an eye kept on them (active + parked).
WATCHED_STATUSES = frozenset(
    {ST_QUEUED, ST_RUNNING, ST_PAUSE_REQUESTED, ST_PAUSED, ST_BLOCKED}
)

# Stage plan per construction mode — a mirror of
# ``archive_miner.stages.MODE_STAGES`` (that package is not importable here).
MODE_STAGES: dict[str, tuple[str, ...]] = {
    MODE_A: ("triage", "enumerate", "structure", "extract", "freeze", "deploy"),
    MODE_B: ("triage", "enumerate", "extract", "freeze", "deploy"),
    MODE_C: (
        "triage", "enumerate", "fetch", "structure", "ocr", "extract",
        "freeze", "deploy",
    ),
}


class BuildRequestError(ValueError):
    """The operator's create request is malformed (→ HTTP 400)."""


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    d = _utc(dt)
    return d.isoformat() if d else None


def _human_duration(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    seconds = int(max(seconds, 0))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


# --- create --------------------------------------------------------------

def create_job(
    *,
    kind: str = KIND_BUILD,
    construction_mode: str | None = None,
    archive_slug: str | None = None,
    project_slug: str | None = None,
    options: dict | None = None,
    budget_usd: Any = None,
) -> BuildJob:
    """Enqueue a job. Raises :class:`BuildRequestError` on a bad request."""
    kind = (kind or KIND_BUILD).strip()
    if kind not in VALID_KINDS:
        raise BuildRequestError(f"kind must be one of {VALID_KINDS}")

    archive_slug = (archive_slug or "").strip() or None
    project_slug = (project_slug or "").strip() or None
    if kind == KIND_BUILD and not archive_slug:
        raise BuildRequestError("a build job needs an archive_slug")
    if kind == KIND_SYNC and not project_slug:
        raise BuildRequestError("a sync job needs a project_slug")

    construction_mode = (construction_mode or "").strip().upper() or None
    if construction_mode and construction_mode not in VALID_MODES:
        raise BuildRequestError(
            f"construction_mode must be one of {VALID_MODES} or blank"
        )

    if budget_usd in (None, ""):
        budget_usd = None
    else:
        try:
            budget_usd = float(budget_usd)
        except (TypeError, ValueError):
            raise BuildRequestError("budget_usd must be a number")
        if budget_usd < 0:
            raise BuildRequestError("budget_usd must not be negative")

    if options is None:
        options = {}
    elif not isinstance(options, dict):
        raise BuildRequestError("options must be a JSON object")

    job = BuildJob(
        kind=kind,
        construction_mode=construction_mode,
        archive_slug=archive_slug,
        project_slug=project_slug,
        options=options,
        budget_usd=budget_usd,
        status=ST_QUEUED,
        stage="triage",
        checkpoint={},
        progress={},
    )
    db.session.add(job)
    db.session.commit()
    return job


# --- read ---------------------------------------------------------------

def list_jobs(*, only_watched: bool = False, limit: int = 50) -> list[BuildJob]:
    stmt = select(BuildJob).order_by(
        BuildJob.created_at.desc(), BuildJob.id.desc()
    )
    if only_watched:
        stmt = stmt.where(BuildJob.status.in_(WATCHED_STATUSES))
    return list(db.session.scalars(stmt.limit(limit)))


def get_job(job_id: int) -> BuildJob | None:
    return db.session.get(BuildJob, job_id)


# --- transitions (mirror archive_miner.queue.JobQueue) ------------------

def request_pause(job: BuildJob, note: str = "") -> bool:
    """Ask an active job to pause. The worker stops at the next unit boundary."""
    if job.status not in (ST_QUEUED, ST_RUNNING):
        return False
    job.status = ST_PAUSE_REQUESTED
    job.operator_note = note or None
    db.session.commit()
    return True


def resume(job: BuildJob) -> bool:
    """Re-queue a paused / human-blocked job for the worker to pick back up."""
    if job.status not in (ST_PAUSED, ST_BLOCKED):
        return False
    job.status = ST_QUEUED
    job.operator_note = None
    db.session.commit()
    return True


def cancel(job: BuildJob, note: str = "") -> bool:
    """Terminally cancel a job unless it has already finished."""
    if job.status in TERMINAL_STATUSES:
        return False
    job.status = ST_CANCELLED
    job.operator_note = note or None
    job.finished_at = datetime.now(timezone.utc)
    db.session.commit()
    return True


# --- status dict (port of archive_miner.report.status) -----------------

def status_dict(job: BuildJob, *, now: datetime | None = None) -> dict[str, Any]:
    """The full status surface for one job — JSON body and template context.

    Rendered prominently as the management report once ``over_1h`` is true:
    where the job is, how fast, when it lands, what it has cost, what needs
    attention.
    """
    now = now or datetime.now(timezone.utc)
    started = _utc(job.started_at)
    elapsed = (now - started).total_seconds() if started else 0.0

    prog = job.progress or {}
    done = prog.get("done")
    total = prog.get("total")
    rate = prog.get("rate_per_min")

    eta = _utc(job.eta_at)
    remaining = (eta - now).total_seconds() if eta and eta > now else None

    mode = job.construction_mode
    plan = list(MODE_STAGES.get(mode or "", ()))

    spent = float(job.spent_usd or 0)
    budget = float(job.budget_usd) if job.budget_usd is not None else None

    return {
        "job_id": job.id,
        "kind": job.kind,
        "mode": mode,
        "anchor": job.anchor,
        "archive_slug": job.archive_slug,
        "project_slug": job.project_slug,
        "status": job.status,
        "stage": job.stage,
        "plan": plan,
        "stage_index": plan.index(job.stage) if job.stage in plan else None,
        "progress": {
            "done": done,
            "total": total,
            "rate_per_min": rate,
            "unit": prog.get("unit", "items"),
            "pct": round(100 * done / total, 1) if done and total else None,
        },
        "started_at": _iso(job.started_at),
        "elapsed_seconds": round(elapsed),
        "elapsed_human": _human_duration(elapsed),
        "eta_at": _iso(job.eta_at),
        "eta_human": _human_duration(remaining) if remaining is not None else None,
        "over_1h": elapsed > 3600,
        "cost": {
            "spent_usd": round(spent, 4),
            "budget_usd": budget,
            "pct": round(100 * spent / budget, 1) if budget else None,
        },
        "worker_id": job.worker_id,
        "build_db_name": job.build_db_name,
        "last_error": job.last_error,
        "operator_note": job.operator_note,
        "heartbeat_at": _iso(job.heartbeat_at),
        "created_at": _iso(job.created_at),
        "finished_at": _iso(job.finished_at),
        "recent_reports": [
            {"at": _iso(r.at), "stage": r.stage, "summary": r.summary}
            for r in job.reports[-12:]
        ],
    }
