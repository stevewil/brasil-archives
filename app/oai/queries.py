"""Database access for the OAI provider.

One record kind: ``Archive`` rows (brasil-archives' own ISDIAH-level
institution descriptions). ``AggregatedRecord`` rows are *not* exposed —
those are harvested from upgrade projects and re-serving them would make
brasil-archives a mirror rather than an index. See
``docs/oai-pmh-provider.md`` §"What the provider exposes".
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import Archive, InstitutionalType
from .constants import (
    DATESTAMP_FLOOR,
    SET_SCHEME_CONTENT,
    SET_SCHEME_ITYPE,
    SET_SCHEME_STATE,
)
from .sets import ParsedSet

_EAGER = (
    selectinload(Archive.institutional_type),
    selectinload(Archive.periods),
    selectinload(Archive.record_types),
    selectinload(Archive.themes),
)


def _public_filter(stmt):
    """Restrict to archives that clear the public bar.

    ``uso justo`` is the project's floor for any public surface
    (docs/handoff/2026-08-27-master.md §2). We drop the fatal-flaw bucket
    and anything explicitly ruled fair-use-ineligible; rows not yet
    reviewed (NULL) and no-digital-content rows are kept — an ISDIAH
    description of a holding-nothing-online institution is still valid
    catalog data.
    """
    return stmt.where(
        Archive.caveat_emptor.is_(False),
        Archive.fair_use_eligible.is_not(False),
    )


def _apply_set(stmt, parsed: ParsedSet | None):
    if parsed is None:
        return stmt
    if parsed.scheme == SET_SCHEME_STATE:
        return stmt.where(Archive.home_state_code == parsed.value)
    if parsed.scheme == SET_SCHEME_ITYPE:
        return stmt.where(
            Archive.institutional_type.has(InstitutionalType.slug == parsed.value)
        )
    if parsed.scheme == SET_SCHEME_CONTENT:
        want_digital = parsed.value == "digital"
        return stmt.where(Archive.no_digital_content.is_(not want_digital))
    return stmt


def _apply_dates(stmt, from_: str | None, until: str | None):
    stamp = func.date(func.coalesce(Archive.updated_at, DATESTAMP_FLOOR))
    if from_:
        stmt = stmt.where(stamp >= from_)
    if until:
        stmt = stmt.where(stamp <= until)
    return stmt


def _selected(parsed_set, from_, until):
    stmt = _public_filter(select(Archive))
    stmt = _apply_set(stmt, parsed_set)
    stmt = _apply_dates(stmt, from_, until)
    return stmt


def count_archives(
    parsed_set: ParsedSet | None, from_: str | None, until: str | None
) -> int:
    stmt = _public_filter(select(func.count(Archive.id)))
    stmt = _apply_set(stmt, parsed_set)
    stmt = _apply_dates(stmt, from_, until)
    return int(db.session.scalar(stmt) or 0)


def page_archives(
    parsed_set: ParsedSet | None,
    from_: str | None,
    until: str | None,
    offset: int,
    limit: int,
) -> list[Archive]:
    stmt = (
        _selected(parsed_set, from_, until)
        .options(*_EAGER)
        .order_by(Archive.slug)
        .offset(offset)
        .limit(limit)
    )
    return list(db.session.scalars(stmt))


def get_public_archive(slug: str) -> Archive | None:
    stmt = _public_filter(select(Archive)).where(Archive.slug == slug).options(*_EAGER)
    return db.session.scalar(stmt)


def first_public_archive_slug() -> str | None:
    """Slug of the first public archive by slug order — used for the
    ``Identify`` sample identifier so it actually resolves via GetRecord."""
    return db.session.scalar(
        _public_filter(select(Archive.slug)).order_by(Archive.slug).limit(1)
    )


def earliest_datestamp() -> str:
    value = db.session.scalar(
        _public_filter(select(func.min(func.date(Archive.updated_at))))
    )
    # SQLite's date() returns a str; Postgres' returns a datetime.date.
    return str(value)[:10] if value else DATESTAMP_FLOOR


def distinct_states() -> list[str]:
    rows = db.session.scalars(
        _public_filter(select(Archive.home_state_code).distinct())
        .where(Archive.home_state_code.is_not(None))
        .order_by(Archive.home_state_code)
    )
    return [r for r in rows if r]


def institutional_types_in_use() -> list[InstitutionalType]:
    stmt = (
        _public_filter(select(InstitutionalType))
        .join(Archive, Archive.institutional_type_id == InstitutionalType.id)
        .distinct()
        .order_by(InstitutionalType.sort_order)
    )
    return list(db.session.scalars(stmt))


def content_splits_in_use() -> list[str]:
    """Return whichever of ``digital`` / ``no-digital`` actually have rows."""
    out: list[str] = []
    has_digital = db.session.scalar(
        _public_filter(select(func.count(Archive.id))).where(
            Archive.no_digital_content.is_(False)
        )
    )
    has_none = db.session.scalar(
        _public_filter(select(func.count(Archive.id))).where(
            Archive.no_digital_content.is_(True)
        )
    )
    if has_digital:
        out.append("digital")
    if has_none:
        out.append("no-digital")
    return out


def archive_datestamp(archive: Archive) -> str:
    updated = getattr(archive, "updated_at", None)
    if isinstance(updated, (date,)):
        return updated.strftime("%Y-%m-%d")
    if updated:
        return str(updated)[:10]
    return DATESTAMP_FLOOR
