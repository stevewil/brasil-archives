"""Harvest views: run index, run detail, record detail.

All routes are read-only. The blueprint is a debugging/sanity-check
surface, not a production data-editing surface — write paths still live
in ``scripts/harvest.py``.
"""
from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, abort, render_template, request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ...extensions import db
from ...models import (
    AggregatedRecord,
    HarvestError,
    HarvestRun,
    UpgradeProject,
)


bp = Blueprint("harvest", __name__, url_prefix="/harvest")


# --------------------------------------------------------------------------- #
# Helpers

_PAGE_SIZE_DEFAULT = 50
_PAGE_SIZE_MAX = 200


def _parse_int(value: str | None, default: int, minimum: int = 0,
               maximum: int | None = None) -> int:
    """Parse a query-string int with clamping. Never raises."""
    try:
        n = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    if n < minimum:
        return minimum
    if maximum is not None and n > maximum:
        return maximum
    return n


def _json_or_none(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Views


@bp.route("/", endpoint="index")
def index():
    """List every harvest run, newest first, with per-project rollups."""
    page = _parse_int(request.args.get("page"), default=1, minimum=1)
    page_size = _parse_int(
        request.args.get("page_size"),
        default=_PAGE_SIZE_DEFAULT,
        minimum=1,
        maximum=_PAGE_SIZE_MAX,
    )
    offset = (page - 1) * page_size

    total = db.session.execute(
        select(db.func.count(HarvestRun.id))
    ).scalar_one()

    stmt = (
        select(HarvestRun)
        .options(selectinload(HarvestRun.upgrade_project))
        .order_by(HarvestRun.started_at.desc(), HarvestRun.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    runs = list(db.session.execute(stmt).scalars())

    # Per-(project, prefix) latest snapshot for the summary cards at top.
    latest_stmt = (
        select(
            UpgradeProject.slug.label("slug"),
            AggregatedRecord.metadata_prefix.label("prefix"),
            db.func.count(AggregatedRecord.id).label("record_count"),
        )
        .join(UpgradeProject,
              UpgradeProject.id == AggregatedRecord.upgrade_project_id)
        .group_by(UpgradeProject.slug, AggregatedRecord.metadata_prefix)
        .order_by(UpgradeProject.slug, AggregatedRecord.metadata_prefix)
    )
    rollups = list(db.session.execute(latest_stmt))

    return render_template(
        "harvest/index.html",
        page_title="Harvest runs",
        runs=runs,
        rollups=rollups,
        page=page,
        page_size=page_size,
        total=total,
        has_next=(offset + page_size) < total,
        has_prev=page > 1,
    )


@bp.route("/runs/<int:run_id>", endpoint="run_detail")
def run_detail(run_id: int):
    """Single harvest run — metadata, error rows, and record page."""
    run = db.session.get(HarvestRun, run_id)
    if run is None:
        abort(404)

    page = _parse_int(request.args.get("page"), default=1, minimum=1)
    page_size = _parse_int(
        request.args.get("page_size"),
        default=_PAGE_SIZE_DEFAULT,
        minimum=1,
        maximum=_PAGE_SIZE_MAX,
    )
    offset = (page - 1) * page_size

    records_total = db.session.execute(
        select(db.func.count(AggregatedRecord.id))
        .where(AggregatedRecord.harvest_run_id == run_id)
    ).scalar_one()

    records_stmt = (
        select(AggregatedRecord)
        .where(AggregatedRecord.harvest_run_id == run_id)
        .order_by(AggregatedRecord.oai_identifier)
        .offset(offset)
        .limit(page_size)
    )
    records = list(db.session.execute(records_stmt).scalars())

    # Decorate rows with a lightweight canonical title (best-effort).
    record_rows: list[dict[str, Any]] = []
    for rec in records:
        extracted = _json_or_none(rec.extracted_json) or {}
        canonical = extracted.get("canonical", {}) if isinstance(extracted, dict) else {}
        record_rows.append({
            "id": rec.id,
            "oai_identifier": rec.oai_identifier,
            "datestamp": rec.datestamp,
            "title": canonical.get("title"),
            "year_start": canonical.get("year_start"),
            "year_end": canonical.get("year_end"),
        })

    errors_stmt = (
        select(HarvestError)
        .where(HarvestError.harvest_run_id == run_id)
        .order_by(HarvestError.id)
        .limit(50)
    )
    errors = list(db.session.execute(errors_stmt).scalars())

    return render_template(
        "harvest/run_detail.html",
        page_title=f"Harvest run #{run.id}",
        run=run,
        record_rows=record_rows,
        errors=errors,
        page=page,
        page_size=page_size,
        records_total=records_total,
        has_next=(offset + page_size) < records_total,
        has_prev=page > 1,
    )


@bp.route("/records/<int:record_id>", endpoint="record_detail")
def record_detail(record_id: int):
    """One aggregated_record — canonical, sets, raw XML."""
    rec = db.session.get(AggregatedRecord, record_id)
    if rec is None:
        abort(404)

    project = db.session.get(UpgradeProject, rec.upgrade_project_id)
    extracted = _json_or_none(rec.extracted_json) or {}
    canonical = (
        extracted.get("canonical", {})
        if isinstance(extracted, dict) else {}
    )
    raw_extracted = (
        extracted.get("raw", {})
        if isinstance(extracted, dict) else {}
    )
    set_specs = _json_or_none(rec.set_specs_json) or []

    return render_template(
        "harvest/record_detail.html",
        page_title=rec.oai_identifier,
        record=rec,
        project=project,
        canonical=canonical,
        raw_extracted=raw_extracted,
        set_specs=set_specs,
    )
