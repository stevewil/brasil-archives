"""Harvest views: run index, run detail, record detail.

All routes are read-only and admin-gated. They read the cross-source
``*_all`` views (``app/models/_views.py``) — on Postgres each harvested
source lives in its own ``src_<slug>`` schema, so a run / record is
addressed by ``(source_slug, id)``, not ``id`` alone. Write paths live in
``app/services/harvest.py``.
"""
from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, abort, render_template, request
from flask_babel import lazy_gettext as _l
from sqlalchemy import func, select

from ...extensions import db
from ...models import UpgradeProject
from ...models._views import (
    AggregatedRecordView,
    HarvestErrorView,
    HarvestRunView,
)
from .._admin_gate import admin_only


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
@admin_only
def index():
    """List every harvest run, newest first, with per-source rollups."""
    page = _parse_int(request.args.get("page"), default=1, minimum=1)
    page_size = _parse_int(
        request.args.get("page_size"),
        default=_PAGE_SIZE_DEFAULT,
        minimum=1,
        maximum=_PAGE_SIZE_MAX,
    )
    offset = (page - 1) * page_size

    total = db.session.scalar(
        select(func.count()).select_from(HarvestRunView)
    )

    runs = list(
        db.session.scalars(
            select(HarvestRunView)
            .order_by(HarvestRunView.started_at.desc(), HarvestRunView.id.desc())
            .offset(offset)
            .limit(page_size)
        )
    )

    # Per-(source, prefix) record counts for the summary cards.
    rollups = list(
        db.session.execute(
            select(
                AggregatedRecordView.source_slug.label("slug"),
                AggregatedRecordView.metadata_prefix.label("prefix"),
                func.count().label("record_count"),
            )
            .group_by(
                AggregatedRecordView.source_slug,
                AggregatedRecordView.metadata_prefix,
            )
            .order_by(
                AggregatedRecordView.source_slug,
                AggregatedRecordView.metadata_prefix,
            )
        )
    )

    return render_template(
        "harvest/index.html",
        page_title=_l("Harvest runs"),
        runs=runs,
        rollups=rollups,
        page=page,
        page_size=page_size,
        total=total,
        has_next=(offset + page_size) < total,
        has_prev=page > 1,
    )


@bp.route("/runs/<source_slug>/<int:run_id>", endpoint="run_detail")
@admin_only
def run_detail(source_slug: str, run_id: int):
    """Single harvest run — metadata, error rows, and record page."""
    run = db.session.get(HarvestRunView, (source_slug, run_id))
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

    _rec_where = (
        (AggregatedRecordView.source_slug == source_slug)
        & (AggregatedRecordView.harvest_run_id == run_id)
    )
    records_total = db.session.scalar(
        select(func.count()).select_from(AggregatedRecordView).where(_rec_where)
    )
    records = list(
        db.session.scalars(
            select(AggregatedRecordView)
            .where(_rec_where)
            .order_by(AggregatedRecordView.oai_identifier)
            .offset(offset)
            .limit(page_size)
        )
    )

    record_rows: list[dict[str, Any]] = []
    for rec in records:
        extracted = _json_or_none(rec.extracted_json) or {}
        canonical = extracted.get("canonical", {}) if isinstance(extracted, dict) else {}
        record_rows.append({
            "id": rec.id,
            "source_slug": rec.source_slug,
            "oai_identifier": rec.oai_identifier,
            "datestamp": rec.datestamp,
            "title": canonical.get("title"),
            "year_start": canonical.get("year_start"),
            "year_end": canonical.get("year_end"),
        })

    errors = list(
        db.session.scalars(
            select(HarvestErrorView)
            .where(
                (HarvestErrorView.source_slug == source_slug)
                & (HarvestErrorView.harvest_run_id == run_id)
            )
            .order_by(HarvestErrorView.id)
            .limit(50)
        )
    )

    return render_template(
        "harvest/run_detail.html",
        page_title=_l("Harvest run #%(id)s") % {"id": run.id},
        run=run,
        record_rows=record_rows,
        errors=errors,
        page=page,
        page_size=page_size,
        records_total=records_total,
        has_next=(offset + page_size) < records_total,
        has_prev=page > 1,
    )


@bp.route("/records/<source_slug>/<int:record_id>", endpoint="record_detail")
@admin_only
def record_detail(source_slug: str, record_id: int):
    """One aggregated_record — canonical, sets, raw XML."""
    rec = db.session.get(AggregatedRecordView, (source_slug, record_id))
    if rec is None:
        abort(404)

    project = db.session.scalar(
        select(UpgradeProject).where(UpgradeProject.slug == rec.source_slug)
    )
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
