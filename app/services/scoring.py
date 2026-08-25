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

    v0 placeholder per docs/algorithm-v1.md §Aggregation; decision on a
    real aggregation waits for Pass 2.
    """
    rows = active_scores(archive_id)
    if not rows:
        return None
    return sum(r.score for r in rows.values())


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
}


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
