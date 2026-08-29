"""Main blueprint — the landing page and the federated search view."""
from __future__ import annotations

from flask import Blueprint, render_template, request
from flask_babel import lazy_gettext as _l
from sqlalchemy import func, select

from ..extensions import db
from ..models import Archive, DimensionScore, UpgradeProject
from ..services import federated_search as fedsearch
from ..services import federation as fed
from ..visibility import scores_visible

bp = Blueprint("main", __name__)

# States the project treats as primary (docs/handoff §2). The rest of the
# Nordeste is grouped into one "other" chip.
PRIMARY_STATES = ("RN", "PE", "BA")
FEATURED_LIMIT = 6


@bp.get("/")
def index() -> str:
    """Landing page: counts, featured archives, browse-by-state, partners."""
    archive_count = db.session.scalar(select(func.count()).select_from(Archive)) or 0
    upgrade_count = (
        db.session.scalar(select(func.count()).select_from(UpgradeProject)) or 0
    )

    return render_template(
        "index.html",
        page_title=_l("Brazilian Digital Archives"),
        archive_count=archive_count,
        upgrade_count=upgrade_count,
        record_count=_aggregated_record_count(),
        featured=_featured_archives(),
        state_groups=_browse_by_state(),
        partners=_partner_previews(),
    )


@bp.get("/search")
def search() -> str:
    """Public search across harvested partner records (Phase 3.5).

    Query params: ``q`` (the search string), ``source`` (restrict to one
    partner slug), ``page``. See ``app/services/federated_search.py``.
    """
    resp = fedsearch.search(
        q=request.args.get("q", ""),
        source=(request.args.get("source", "").strip() or None),
        page=request.args.get("page", 1),
    )
    return render_template(
        "search.html",
        page_title=_l("Search partner records"),
        resp=resp,
    )


def _aggregated_record_count() -> int:
    from ..models import AggregatedRecord

    return db.session.scalar(
        select(func.count()).select_from(AggregatedRecord)
    ) or 0


def _featured_archives() -> list[dict]:
    """Up to FEATURED_LIMIT archives to spotlight on the home page.

    When scores are visible, ranked by naive sum of active dimension
    scores (NULLs last), then name. When scores are hidden (the public
    default until greenlit — see ``app/visibility.py``), ranked by name
    only and the ``naive_sum`` is not exposed. Always excludes
    no-digital-content rows and anything already ruled fair-use-ineligible
    — the home page is a public surface.
    """
    show_scores = scores_visible()

    naive_sum = (
        select(
            DimensionScore.archive_id.label("aid"),
            func.sum(DimensionScore.score).label("total"),
        )
        .where(DimensionScore.superseded_at.is_(None))
        .group_by(DimensionScore.archive_id)
        .subquery()
    )

    query = (
        select(Archive, naive_sum.c.total)
        .join(naive_sum, naive_sum.c.aid == Archive.id, isouter=True)
        .where(Archive.no_digital_content.is_(False))
        .where(Archive.fair_use_eligible.is_not(False))
        .limit(FEATURED_LIMIT)
    )
    if show_scores:
        query = query.order_by(
            func.coalesce(naive_sum.c.total, -1).desc(),
            Archive.name.asc(),
        )
    else:
        query = query.order_by(Archive.name.asc())

    rows = db.session.execute(query).all()

    return [
        {"archive": archive, "naive_sum": total if show_scores else None}
        for archive, total in rows
    ]


def _browse_by_state() -> list[dict]:
    """State chips with archive counts: primary states first, then one
    'other Nordeste' bucket, each linking into the archives filter."""
    counts = dict(
        db.session.execute(
            select(Archive.home_state_code, func.count(Archive.id))
            .where(Archive.home_state_code.is_not(None))
            .group_by(Archive.home_state_code)
        ).all()
    )

    groups: list[dict] = []
    for code in PRIMARY_STATES:
        if counts.get(code):
            groups.append({"code": code, "label": code, "count": counts[code]})

    other = sorted(c for c in counts if c not in PRIMARY_STATES)
    if other:
        groups.append({"code": None, "states": other})
    return groups


def _partner_previews() -> list[dict]:
    """Live federation handshake per registered upgrade project."""
    projects = db.session.scalars(
        select(UpgradeProject).order_by(UpgradeProject.name)
    ).all()
    return [{"project": p, "preview": fed.preview(p)} for p in projects]
