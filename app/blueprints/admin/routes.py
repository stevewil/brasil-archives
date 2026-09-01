"""Read-only admin dashboard.

One page, five panels, all derived from queries that already exist
elsewhere in the app. No forms — CSRF exemption is unnecessary.
"""
from __future__ import annotations

from typing import Any

from flask import Blueprint, render_template
from flask_babel import lazy_gettext as _l
from sqlalchemy import func, select

from ...extensions import db
from ...models import (
    DIMENSIONS,
    Archive,
    DimensionScore,
    ProbeResult,
    UpgradeProject,
)
from ...models._views import HarvestErrorView, HarvestRunView
from ...services import federation as fed
from .._admin_gate import admin_only

bp = Blueprint("admin", __name__, url_prefix="/admin")

_RECENT_LIMIT = 10


def _scoring_coverage() -> dict[str, int]:
    """Active-score coverage over the pipeline-viable archive set.

    "Pipeline-viable" mirrors the home page's Featured filter and the
    survey's Table 1: has digital content and is not ruled fair-use
    ineligible (NULL = not yet reviewed still counts).
    """
    viable = (
        select(Archive.id)
        .where(Archive.no_digital_content.is_(False))
        .where(Archive.fair_use_eligible.is_not(False))
        .subquery()
    )
    viable_total = db.session.scalar(
        select(func.count()).select_from(viable)
    ) or 0

    # active dimensions per archive, among the viable set
    per_archive = (
        select(
            DimensionScore.archive_id.label("aid"),
            func.count(DimensionScore.id).label("n"),
        )
        .where(DimensionScore.superseded_at.is_(None))
        .join(viable, viable.c.id == DimensionScore.archive_id)
        .group_by(DimensionScore.archive_id)
        .subquery()
    )
    rows = db.session.execute(select(per_archive.c.n)).scalars().all()

    return {
        "viable_total": viable_total,
        "any_score": len(rows),
        "fully_scored": sum(1 for n in rows if n >= len(DIMENSIONS)),
        "unscored": viable_total - len(rows),
        "dimension_count": len(DIMENSIONS),
    }


def _probe_status() -> dict[str, Any]:
    """How much of the catalog the quarterly health probe has reached."""
    archive_total = db.session.scalar(
        select(func.count()).select_from(Archive)
    ) or 0
    probed = db.session.scalar(
        select(func.count())
        .select_from(Archive)
        .where(Archive.last_probed_at.is_not(None))
    ) or 0
    most_recent = db.session.scalar(select(func.max(Archive.last_probed_at)))

    # A probe "failure" = the most recent run couldn't reach the canonical
    # URL over a valid certificate. Counted over the latest ProbeResult
    # per archive.
    latest_probe = (
        select(
            ProbeResult.archive_id.label("aid"),
            func.max(ProbeResult.probed_at).label("pat"),
        )
        .where(ProbeResult.archive_id.is_not(None))
        .group_by(ProbeResult.archive_id)
        .subquery()
    )
    failing = db.session.scalar(
        select(func.count())
        .select_from(ProbeResult)
        .join(
            latest_probe,
            (latest_probe.c.aid == ProbeResult.archive_id)
            & (latest_probe.c.pat == ProbeResult.probed_at),
        )
        .where(
            (ProbeResult.https_valid.is_(False))
            | (ProbeResult.canonical_http_status >= 400)
        )
    ) or 0

    return {
        "archive_total": archive_total,
        "probed": probed,
        "unprobed": archive_total - probed,
        "most_recent": most_recent,
        "failing": failing,
    }


def _recent_harvest_runs() -> list[HarvestRunView]:
    return list(
        db.session.scalars(
            select(HarvestRunView)
            .order_by(HarvestRunView.started_at.desc(), HarvestRunView.id.desc())
            .limit(_RECENT_LIMIT)
        )
    )


def _recent_harvest_errors() -> list[HarvestErrorView]:
    return list(
        db.session.scalars(
            select(HarvestErrorView)
            .order_by(HarvestErrorView.id.desc())
            .limit(_RECENT_LIMIT)
        )
    )


def _federation_health() -> list[dict[str, Any]]:
    projects = db.session.scalars(
        select(UpgradeProject).order_by(UpgradeProject.name)
    ).all()
    return [{"project": p, "preview": fed.preview(p)} for p in projects]


@bp.route("/", endpoint="index")
@admin_only
def index():
    """The dashboard. Every panel is read-only."""
    return render_template(
        "admin/index.html",
        page_title=_l("Admin dashboard"),
        coverage=_scoring_coverage(),
        probe=_probe_status(),
        harvest_runs=_recent_harvest_runs(),
        harvest_errors=_recent_harvest_errors(),
        federation=_federation_health(),
    )
