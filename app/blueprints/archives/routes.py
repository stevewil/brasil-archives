"""Archive list, detail, score, and facet-edit views."""
from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import lazy_gettext as _l
from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload

from ...extensions import db
from ...models import (
    DIMENSIONS,
    Archive,
    DimensionScore,
    FacetValue,
    InstitutionalType,
    Period,
    RecordType,
    Theme,
    UpgradeProject,
)
from ...services import federation as fed
from ...services import scoring as svc
from ...text import fold
from .._admin_gate import admin_only
from .forms import FacetForm, ScoreForm, TagsForm

bp = Blueprint("archives", __name__, url_prefix="/archives")


# --------------------------------------------------------------------------- #
# Helpers


def _brazilian_states() -> list[str]:
    """Distinct home_state_code values, alphabetized."""
    rows = db.session.scalars(
        select(Archive.home_state_code)
        .where(Archive.home_state_code.is_not(None))
        .distinct()
    ).all()
    return sorted(rows)


# Descriptive text fields a catalog keyword search looks in.
_SEARCH_FIELDS = (
    "name",
    "name_pt",
    "description_en",
    "description_pt",
    "stated_scope",
    "home_city",
)


def _text_matches(archive: Archive, folded_query: str) -> bool:
    """True when the folded query is a substring of any descriptive field."""
    haystack = fold(
        " ".join(getattr(archive, f) or "" for f in _SEARCH_FIELDS)
    )
    return folded_query in haystack


def _load_archive_or_404(slug: str) -> Archive:
    archive = db.session.scalar(
        select(Archive)
        .where(Archive.slug == slug)
        .options(
            selectinload(Archive.institutional_type),
            selectinload(Archive.periods),
            selectinload(Archive.record_types),
            selectinload(Archive.themes),
        )
    )
    if archive is None:
        abort(404)
    return archive


# --------------------------------------------------------------------------- #
# List


@bp.route("/", methods=["GET"])
def list_archives():
    """List archives with filters and two-axis + naive sum columns.

    Filters:
      * ``q`` — free-text, matched accent- + case-insensitively against
        name / description / stated scope / city (see ``_SEARCH_FIELDS``)
      * ``state`` — home state code, e.g. RN
      * ``institutional_type`` — vocabulary slug
      * ``content`` — ``with`` / ``without`` / ``all`` (default with)
      * ``sort`` — one of ``name`` (default), ``score`` (naive sum),
        ``pipeline`` (Axis A), ``research`` (Axis B). Each score sort is
        descending; ``name`` is ascending.
    """
    q = request.args.get("q", "").strip() or None
    state = request.args.get("state", "").strip() or None
    itype = request.args.get("institutional_type", "").strip() or None
    content = request.args.get("content", "with").strip()
    sort = request.args.get("sort", "name").strip()

    # One subquery covers naive sum + both axis sums. The axis sums use
    # SUM(CASE ... END) so each row's contribution goes into exactly
    # one axis, matching the AXES table in app.services.scoring.
    pipeline_dims = svc.AXES["pipeline"]
    research_dims = svc.AXES["research"]

    def _axis_sum(members: tuple[str, ...]):
        return func.sum(
            case(
                (DimensionScore.dimension.in_(members), DimensionScore.score),
                else_=0,
            )
        )

    scores_sq = (
        select(
            DimensionScore.archive_id.label("aid"),
            func.sum(DimensionScore.score).label("naive_sum"),
            func.count(DimensionScore.id).label("scored_dims"),
            _axis_sum(pipeline_dims).label("axis_pipeline"),
            _axis_sum(research_dims).label("axis_research"),
        )
        .where(DimensionScore.superseded_at.is_(None))
        .group_by(DimensionScore.archive_id)
        .subquery()
    )

    query = (
        select(
            Archive,
            scores_sq.c.naive_sum,
            scores_sq.c.scored_dims,
            scores_sq.c.axis_pipeline,
            scores_sq.c.axis_research,
        )
        .join(scores_sq, scores_sq.c.aid == Archive.id, isouter=True)
        .options(selectinload(Archive.institutional_type))
    )

    if state:
        query = query.where(Archive.home_state_code == state)
    if itype:
        query = query.where(
            Archive.institutional_type.has(InstitutionalType.slug == itype)
        )
    if content == "with":
        query = query.where(Archive.no_digital_content.is_(False))
    elif content == "without":
        query = query.where(Archive.no_digital_content.is_(True))
    # ``all`` = no filter

    # NULLS LAST portable pattern: coalesce to -1 for ordering only.
    _order_by_score = {
        "score": func.coalesce(scores_sq.c.naive_sum, -1).desc(),
        "pipeline": func.coalesce(scores_sq.c.axis_pipeline, -1).desc(),
        "research": func.coalesce(scores_sq.c.axis_research, -1).desc(),
    }
    if sort in _order_by_score:
        query = query.order_by(_order_by_score[sort], Archive.name.asc())
    else:
        query = query.order_by(Archive.name.asc())

    rows = db.session.execute(query).all()

    if q:
        folded = fold(q)
        rows = [row for row in rows if _text_matches(row[0], folded)]

    institutional_types = db.session.scalars(
        select(InstitutionalType).order_by(InstitutionalType.sort_order)
    ).all()

    return render_template(
        "archives/list.html",
        rows=rows,
        states=_brazilian_states(),
        institutional_types=institutional_types,
        axis_max=svc.AXIS_MAX,
        current={
            "q": q or "",
            "state": state or "",
            "institutional_type": itype or "",
            "content": content,
            "sort": sort,
        },
    )


# --------------------------------------------------------------------------- #
# Detail


@bp.route("/<slug>/eag.xml", methods=["GET"])
def eag_xml(slug: str):
    """Institution description as EAG 2012 XML (public, machine surface).

    Same content served under the OAI ``eag`` metadataPrefix; this is the
    stable per-institution URL. 404s for unknown slugs and for archives
    that do not clear the public bar (see app/oai/queries.py).
    """
    from ...oai.eag import archive_to_eag
    from ...oai.envelope import xml_response
    from ...oai.queries import get_public_archive

    archive = get_public_archive(slug)
    if archive is None:
        abort(404)
    return xml_response(archive_to_eag(archive))


@bp.route("/<slug>", methods=["GET"])
def detail(slug: str):
    archive = _load_archive_or_404(slug)

    active_scores = svc.active_scores(archive.id)
    scores_by_dim = {
        dim: {
            "active": active_scores.get(dim),
            "history": svc.score_history(archive.id, dim),
            "form": ScoreForm(
                data={
                    "dimension": dim,
                    "score": (active_scores[dim].score if dim in active_scores else None),
                    "justification_en": "",
                }
            ),
        }
        for dim in DIMENSIONS
    }

    active_facets = svc.active_facet_values(archive.id)

    upgrade_projects = list(
        db.session.scalars(
            select(UpgradeProject).where(UpgradeProject.source_archive_id == archive.id)
        )
    )

    # Build federation previews per upgrade project. Each entry is either
    # a dict with live counts + deep link, or {"available": False, ...}
    # on any failure. Never let a federated outage break archive detail.
    federation_previews = {}
    for proj in upgrade_projects:
        federation_previews[proj.id] = fed.preview(proj)

    axes = svc.axis_scores(archive.id)
    quadrant = svc.quadrant_label(axes["pipeline"], axes["research"])

    return render_template(
        "archives/detail.html",
        archive=archive,
        dimensions=DIMENSIONS,
        scores_by_dim=scores_by_dim,
        naive_sum=svc.naive_sum(archive.id),
        axes=axes,
        axis_labels=svc.AXIS_LABELS,
        axis_max=svc.AXIS_MAX,
        axis_members=svc.AXES,
        quadrant=quadrant,
        active_facets=active_facets,
        facet_history=lambda facet: svc.facet_history(archive.id, facet),
        upgrade_projects=upgrade_projects,
        federation_previews=federation_previews,
    )


# --------------------------------------------------------------------------- #
# Submit score


@bp.route("/<slug>/score", methods=["POST"])
@admin_only
def submit_score(slug: str):
    archive = _load_archive_or_404(slug)
    form = ScoreForm()
    if not form.validate_on_submit():
        # Flash the first error per field so the user knows why.
        for field, errors in form.errors.items():
            for err in errors:
                flash(f"{field}: {err}", "error")
        return redirect(url_for("archives.detail", slug=slug))

    if form.dimension.data not in DIMENSIONS:
        abort(400)

    try:
        svc.record_score(
            archive=archive,
            dimension=form.dimension.data,
            score=form.score.data,
            justification_en=form.justification_en.data,
            justification_pt=form.justification_pt.data,
            scored_by=form.scored_by.data or None,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    flash(_l("Recorded score for %(dim)s.") % {"dim": form.dimension.data}, "success")
    return redirect(url_for("archives.detail", slug=slug, _anchor=form.dimension.data))


# --------------------------------------------------------------------------- #
# Facet edit


@bp.route("/<slug>/facets", methods=["GET", "POST"])
@admin_only
def edit_facets(slug: str):
    archive = _load_archive_or_404(slug)
    active = svc.active_facet_values(archive.id)

    if request.method == "GET":
        form = FacetForm(
            data={
                "licensing_posture": (
                    active["licensing_posture"].value if "licensing_posture" in active else ""
                ),
                "licensing_posture_note": (
                    active["licensing_posture"].note if "licensing_posture" in active else ""
                ),
                "stated_roadmap": (
                    active["stated_roadmap"].value if "stated_roadmap" in active else ""
                ),
                "stated_roadmap_note": (
                    active["stated_roadmap"].note if "stated_roadmap" in active else ""
                ),
                "scholarly_access_practical": (
                    active["scholarly_access_practical"].value
                    if "scholarly_access_practical" in active else ""
                ),
                "scholarly_access_practical_note": (
                    active["scholarly_access_practical"].note
                    if "scholarly_access_practical" in active else ""
                ),
                "curatorial_rarity_notes": archive.curatorial_rarity_notes or "",
                "prior_use_note": archive.prior_use_note or "",
                "fair_use_eligible": (
                    "" if archive.fair_use_eligible is None
                    else ("yes" if archive.fair_use_eligible else "no")
                ),
            }
        )
        tags_form = _tags_form_for(archive)
        return render_template(
            "archives/facets.html",
            archive=archive,
            form=form,
            tags_form=tags_form,
        )

    # POST — figure out which sub-form was submitted.
    which = request.form.get("form", "")
    if which == "facets":
        form = FacetForm()
        if not form.validate_on_submit():
            for field, errors in form.errors.items():
                for err in errors:
                    flash(f"{field}: {err}", "error")
            return redirect(url_for("archives.edit_facets", slug=slug))
        try:
            svc.set_facet_value(
                archive=archive,
                facet="licensing_posture",
                value=form.licensing_posture.data or "",
                note=form.licensing_posture_note.data or None,
                set_by=form.set_by.data or None,
            )
            svc.set_facet_value(
                archive=archive,
                facet="stated_roadmap",
                value=form.stated_roadmap.data or "",
                note=form.stated_roadmap_note.data or None,
                set_by=form.set_by.data or None,
            )
            svc.set_facet_value(
                archive=archive,
                facet="scholarly_access_practical",
                value=form.scholarly_access_practical.data or "",
                note=form.scholarly_access_practical_note.data or None,
                set_by=form.set_by.data or None,
            )
            archive.curatorial_rarity_notes = (
                form.curatorial_rarity_notes.data.strip() or None
            )
            archive.prior_use_note = form.prior_use_note.data.strip() or None
            if form.fair_use_eligible.data == "yes":
                archive.fair_use_eligible = True
            elif form.fair_use_eligible.data == "no":
                archive.fair_use_eligible = False
            else:
                archive.fair_use_eligible = None
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        flash(_l("Facets updated."), "success")
        return redirect(url_for("archives.edit_facets", slug=slug))

    if which == "tags":
        tags_form = _tags_form_for(archive, populate_from_request=True)
        if not tags_form.validate_on_submit():
            for field, errors in tags_form.errors.items():
                for err in errors:
                    flash(f"{field}: {err}", "error")
            return redirect(url_for("archives.edit_facets", slug=slug))
        try:
            svc.set_archive_tags(
                archive=archive,
                period_slugs=tags_form.periods.data,
                record_type_slugs=tags_form.record_types.data,
                theme_slugs=tags_form.themes.data,
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        flash(_l("Tags updated."), "success")
        return redirect(url_for("archives.edit_facets", slug=slug))

    abort(400)


def _tags_form_for(archive: Archive, populate_from_request: bool = False) -> TagsForm:
    periods = db.session.scalars(select(Period).order_by(Period.sort_order)).all()
    record_types = db.session.scalars(
        select(RecordType).order_by(RecordType.sort_order)
    ).all()
    themes = db.session.scalars(select(Theme).order_by(Theme.sort_order)).all()

    form = TagsForm() if populate_from_request else TagsForm(
        data={
            "periods": [p.slug for p in archive.periods],
            "record_types": [r.slug for r in archive.record_types],
            "themes": [t.slug for t in archive.themes],
        }
    )
    form.periods.choices = [(p.slug, p.label_en) for p in periods]
    form.record_types.choices = [(r.slug, r.label_en) for r in record_types]
    form.themes.choices = [(t.slug, t.label_en) for t in themes]
    return form
