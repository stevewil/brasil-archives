"""Scoring and facet write paths.

Central place for the write semantics that history-bearing tables need:
supersede the currently-active row and insert a fresh one. Keeping this
logic in one module means the blueprint code stays thin and the
tests can assert history behaviour without going through the form.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select


def _utcnow() -> datetime:
    # Naive UTC timestamp — matches the DateTime columns used by the
    # models. Prefer this over ``datetime.utcnow()`` which is deprecated
    # on Python 3.14.
    return datetime.now(timezone.utc).replace(tzinfo=None)

from ..extensions import db
from ..models import (
    DIMENSIONS,
    Archive,
    DimensionScore,
    FacetValue,
    Period,
    RecordType,
    Theme,
)


# --------------------------------------------------------------------------- #
# Dimension scores


def active_scores(archive_id: int) -> dict[str, DimensionScore]:
    """Return the currently-active :class:`DimensionScore` per dimension."""
    rows = db.session.scalars(
        select(DimensionScore).where(
            DimensionScore.archive_id == archive_id,
            DimensionScore.superseded_at.is_(None),
        )
    ).all()
    return {row.dimension: row for row in rows}


def score_history(archive_id: int, dimension: str) -> list[DimensionScore]:
    """Return all revisions for a dimension, newest first."""
    return list(
        db.session.scalars(
            select(DimensionScore)
            .where(
                DimensionScore.archive_id == archive_id,
                DimensionScore.dimension == dimension,
            )
            .order_by(DimensionScore.scored_at.desc(), DimensionScore.id.desc())
        )
    )


def naive_sum(archive_id: int) -> int | None:
    """Sum of currently-active dimension scores (0-80). ``None`` if empty.

    Kept alongside the two-axis view as an unweighted total. See
    :data:`AXES` and :func:`axis_scores` for the aggregation that
    supersedes it for ranking purposes.
    """
    rows = active_scores(archive_id)
    if not rows:
        return None
    return sum(r.score for r in rows.values())


# --------------------------------------------------------------------------- #
# Two-axis aggregation (docs/adr-0001-two-axis-aggregation.md)
#
# The eight scored dimensions split into two axes, each aggregated by
# unweighted sum out of 40. This breaks the LABIM/INTERPI naive-sum tie
# by making the underlying profile visible: a pipeline-strong /
# research-thin archive and a research-strong / pipeline-thin archive
# reach the same naive-sum total but land in different quadrants.
#
# Axis A - Pipeline / access readiness: how ready the archive is to
# ingest and browse. Groups the dimensions that describe fetch and
# discovery: reaching, listing, and enumerating documents.
#
# Axis B - Research value / evidentiary density: how rich the material
# is once you have it. Groups the dimensions that describe the
# evidentiary payload: description, coverage, novelty, connectability.
#
# The split is a modeling decision, not archive-data, so it lives in
# code where it is reviewable rather than in a YAML config.


AXES: dict[str, tuple[str, ...]] = {
    "pipeline": (
        "accessibility",
        "finding_aids",
        "pipeline_ingestion_readiness",
        "scale",
    ),
    "research": (
        "provenance_curatorial",
        "corpus_completeness",
        "uniqueness_non_duplication",
        "linkage_potential",
    ),
}

AXIS_MAX: int = 40  # 4 dimensions x 10 points

# Public labels used by templates and the ADR. Kept here so the axis
# ids, dimensions, and human labels stay in one place.
AXIS_LABELS: dict[str, dict[str, str]] = {
    "pipeline": {
        "en": "Pipeline",
        "pt": "Pipeline",
        "long_en": "Pipeline / access readiness",
        "long_pt": "Pipeline / prontidão de acesso",
    },
    "research": {
        "en": "Research",
        "pt": "Pesquisa",
        "long_en": "Research value / evidentiary density",
        "long_pt": "Valor de pesquisa / densidade probatória",
    },
}

# Sanity check at import time: every scored dimension appears in
# exactly one axis. Catches typos in the AXES table early instead of
# silently under-counting an archive's score.
_axis_members = tuple(dim for group in AXES.values() for dim in group)
if set(_axis_members) != set(DIMENSIONS):
    raise RuntimeError(
        "AXES membership must exactly cover DIMENSIONS. "
        f"Missing: {set(DIMENSIONS) - set(_axis_members)!r}; "
        f"extra: {set(_axis_members) - set(DIMENSIONS)!r}"
    )
if len(_axis_members) != len(set(_axis_members)):
    raise RuntimeError("AXES must not repeat a dimension across axes.")


def axis_score(archive_id: int, axis: str) -> int | None:
    """Sum of active scores in ``axis`` (0..AXIS_MAX). ``None`` if empty.

    Only counts dimensions that both belong to ``axis`` and have an
    active row; an archive with a partial score set therefore returns
    a partial axis total rather than ``None``, matching how the
    detail-page dimension cards render.
    """
    if axis not in AXES:
        raise ValueError(f"Unknown axis: {axis!r}")
    rows = active_scores(archive_id)
    if not rows:
        return None
    members = AXES[axis]
    return sum(row.score for dim, row in rows.items() if dim in members)


def axis_scores(archive_id: int) -> dict[str, int | None]:
    """Return both axis totals keyed by axis id.

    Convenience wrapper for templates and the list view that needs
    both totals per row without two DB round trips.
    """
    rows = active_scores(archive_id)
    if not rows:
        return {axis: None for axis in AXES}
    return {
        axis: sum(row.score for dim, row in rows.items() if dim in members)
        for axis, members in AXES.items()
    }


def quadrant_label(
    pipeline: int | None,
    research: int | None,
    *,
    threshold: int = 26,
) -> str:
    """Human label for the four quadrants on the two-axis plane.

    ``threshold`` (default 26, per ADR-0002) splits each axis into
    low/high halves. 26/40 is an average dimension score of ~6.5 — just
    above the field median (pipeline 24, research 22 across the 21 scored
    archives) — and makes "High/High" a non-trivial bucket. ADR-0001
    originally used 28 (avg 7, "uniformly usable"); ADR-0002 lowered it
    after Pass 3 showed 28 admitted only 2 archives to High/High.

    Returns "n.a." when either axis is unscored.
    """
    if pipeline is None or research is None:
        return "n.a."
    a_high = pipeline >= threshold
    b_high = research >= threshold
    if a_high and b_high:
        return "High pipeline / High research"
    if a_high and not b_high:
        return "High pipeline / Low research"
    if not a_high and b_high:
        return "Low pipeline / High research"
    return "Low pipeline / Low research"


def record_score(
    *,
    archive: Archive,
    dimension: str,
    score: int,
    justification_en: str,
    justification_pt: str | None,
    scored_by: str | None,
    now: datetime | None = None,
) -> DimensionScore:
    """Record a new score for ``dimension``, superseding any active row.

    The old row is preserved and its ``superseded_at`` / ``superseded_by_id``
    pointers are set once the new row's primary key is known. Callers
    are expected to hold an outer transaction; this function calls
    ``db.session.flush`` but does not commit.
    """
    if dimension not in DIMENSIONS:
        raise ValueError(f"Unknown dimension: {dimension!r}")
    if not 0 <= score <= 10:
        raise ValueError(f"Score out of range 0-10: {score}")

    prev = db.session.scalar(
        select(DimensionScore).where(
            DimensionScore.archive_id == archive.id,
            DimensionScore.dimension == dimension,
            DimensionScore.superseded_at.is_(None),
        )
    )

    now = now or _utcnow()
    fresh = DimensionScore(
        archive_id=archive.id,
        dimension=dimension,
        score=score,
        justification_en=justification_en.strip(),
        justification_pt=(justification_pt or None),
        scored_by=scored_by,
        scored_at=now,
    )
    db.session.add(fresh)
    db.session.flush()

    if prev is not None:
        prev.superseded_at = now
        prev.superseded_by_id = fresh.id

    return fresh


# --------------------------------------------------------------------------- #
# Single-select facets stored in facet_values


# Facets we let a human edit through this UI. Matches
# docs/algorithm-v1.md §Human-tagged facets minus the ones stored
# directly on Archive (institutional_type, curatorial_rarity_notes,
# prior_use_note) and multi-selects (periods, record_types, themes).
SINGLE_SELECT_FACETS: dict[str, tuple[str, ...]] = {
    "licensing_posture": ("redistribution-friendly", "citation-only", "bulk-restricted"),
    "stated_roadmap": (
        "published-and-active",
        "published-but-unmet",
        "informal",
        "none",
        "not-applicable",
    ),
    # Whether the archive's own nominal access surface supports
    # scholarly workflows (search across record types, enumeration,
    # stable citations, bulk retrieval) or whether practical scholarly
    # access requires our federation tooling. Not a scoring dimension
    # — it annotates the accessibility dimension with a qualitative
    # observation about who actually pays the ingestion cost. See
    # docs/adr-0001-two-axis-aggregation.md §Related facet.
    "scholarly_access_practical": (
        "well-supported",
        "usable-with-effort",
        "only-via-federation",
        "not-yet-assessed",
    ),
}


# Probe-fed single-select facets (docs/algorithm-v1.md §"Probe-updated
# facets"). Written by app/services/probe.py from the quarterly health
# probe, never by a human through the facet editor — hence a separate
# vocabulary table and write path from SINGLE_SELECT_FACETS. The
# freshness stamp lives on ``Archive.last_probed_at``.
PROBE_FACETS: dict[str, tuple[str, ...]] = {
    "web_ops_health": ("healthy", "degraded", "at-risk", "down"),
    "external_preservation": ("preserved", "home-page-only", "unpreserved"),
    "growth_signal": ("active", "slow", "stalled", "wound-down", "unknown"),
    "prior_use_signal": ("foundational", "established", "emerging", "unused", "unknown"),
}


def active_probe_facet_values(archive_id: int) -> dict[str, FacetValue]:
    """Currently-active probe-fed :class:`FacetValue` rows keyed by facet."""
    rows = db.session.scalars(
        select(FacetValue).where(
            FacetValue.archive_id == archive_id,
            FacetValue.facet.in_(tuple(PROBE_FACETS)),
            FacetValue.superseded_at.is_(None),
        )
    ).all()
    return {row.facet: row for row in rows}


def set_probe_facet_value(
    *,
    archive: Archive,
    facet: str,
    value: str,
    note: str | None = None,
    set_by: str | None = "probe",
    now: datetime | None = None,
) -> FacetValue:
    """Supersede the active row for a probe-fed ``facet`` and insert a new one.

    Mirrors :func:`set_facet_value` (supersede-and-insert history) but
    validates against :data:`PROBE_FACETS`. No-ops when the active row
    already carries the same value and note, so unchanged facets don't
    accrue identical rows each quarter. Caller holds the transaction;
    this flushes but does not commit.
    """
    if facet not in PROBE_FACETS:
        raise ValueError(f"Unknown probe facet: {facet!r}")
    if value not in PROBE_FACETS[facet]:
        raise ValueError(f"Invalid value {value!r} for probe facet {facet}")

    prev = db.session.scalar(
        select(FacetValue).where(
            FacetValue.archive_id == archive.id,
            FacetValue.facet == facet,
            FacetValue.superseded_at.is_(None),
        )
    )
    if prev is not None and prev.value == value and (prev.note or "") == (note or ""):
        return prev

    now = now or _utcnow()
    fresh = FacetValue(
        archive_id=archive.id,
        facet=facet,
        value=value,
        note=(note or None),
        set_by=set_by,
        set_at=now,
    )
    db.session.add(fresh)
    db.session.flush()

    if prev is not None:
        prev.superseded_at = now
        prev.superseded_by_id = fresh.id

    return fresh


def active_facet_values(archive_id: int) -> dict[str, FacetValue]:
    rows = db.session.scalars(
        select(FacetValue).where(
            FacetValue.archive_id == archive_id,
            FacetValue.superseded_at.is_(None),
        )
    ).all()
    return {row.facet: row for row in rows}


def facet_history(archive_id: int, facet: str) -> list[FacetValue]:
    return list(
        db.session.scalars(
            select(FacetValue)
            .where(FacetValue.archive_id == archive_id, FacetValue.facet == facet)
            .order_by(FacetValue.set_at.desc(), FacetValue.id.desc())
        )
    )


def set_facet_value(
    *,
    archive: Archive,
    facet: str,
    value: str,
    note: str | None,
    set_by: str | None,
    now: datetime | None = None,
) -> FacetValue | None:
    """Supersede the active row for ``facet`` and insert a new one.

    An empty ``value`` supersedes the active row without inserting a
    replacement (i.e. "clear this facet"). Returns the new row or
    ``None`` when clearing.
    """
    if facet not in SINGLE_SELECT_FACETS:
        raise ValueError(f"Unknown single-select facet: {facet!r}")
    if value and value not in SINGLE_SELECT_FACETS[facet]:
        raise ValueError(f"Invalid value {value!r} for facet {facet}")

    prev = db.session.scalar(
        select(FacetValue).where(
            FacetValue.archive_id == archive.id,
            FacetValue.facet == facet,
            FacetValue.superseded_at.is_(None),
        )
    )

    # No-op guard: same value, same note.
    if prev is not None and prev.value == value and (prev.note or "") == (note or ""):
        return prev

    now = now or _utcnow()
    fresh: FacetValue | None = None
    if value:
        fresh = FacetValue(
            archive_id=archive.id,
            facet=facet,
            value=value,
            note=(note or None),
            set_by=set_by,
            set_at=now,
        )
        db.session.add(fresh)
        db.session.flush()

    if prev is not None:
        prev.superseded_at = now
        if fresh is not None:
            prev.superseded_by_id = fresh.id

    return fresh


# --------------------------------------------------------------------------- #
# Multi-select tags (periods, record types, themes)


def _replace_tag_association(
    collection: list, model: type, wanted_slugs: Iterable[str]
) -> None:
    wanted = list(dict.fromkeys(wanted_slugs))  # preserve order, dedupe
    if wanted:
        rows = db.session.scalars(select(model).where(model.slug.in_(wanted))).all()
        found = {r.slug for r in rows}
        missing = [s for s in wanted if s not in found]
        if missing:
            raise ValueError(f"{model.__tablename__} slugs not found: {missing}")
        collection[:] = sorted(rows, key=lambda r: r.sort_order)
    else:
        collection[:] = []


def set_archive_tags(
    *,
    archive: Archive,
    period_slugs: Iterable[str] = (),
    record_type_slugs: Iterable[str] = (),
    theme_slugs: Iterable[str] = (),
) -> None:
    """Replace the archive's multi-select tag associations in place."""
    _replace_tag_association(archive.periods, Period, period_slugs)
    _replace_tag_association(archive.record_types, RecordType, record_type_slugs)
    _replace_tag_association(archive.themes, Theme, theme_slugs)
