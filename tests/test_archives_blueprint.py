"""Tests for the archives blueprint: list, detail, score, facets."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

import pytest
from sqlalchemy import select

from app.extensions import db as _db
from app.models import (
    Archive,
    DimensionScore,
    FacetValue,
    InstitutionalType,
    Period,
    RecordType,
    Theme,
)
from app.services import scoring as svc
from scripts import load_vocabularies


# --------------------------------------------------------------------------- #
# Fixtures


@pytest.fixture
def seeded_app(app):
    """App with vocabularies + three archives loaded."""
    with app.app_context():
        load_vocabularies.load_all()
        federal = _db.session.scalar(
            select(InstitutionalType).where(InstitutionalType.slug == "federal-university")
        )
        state_court = _db.session.scalar(
            select(InstitutionalType).where(InstitutionalType.slug == "state-court")
        )
        _db.session.add_all(
            [
                Archive(
                    slug="rn-labim-t1r1",
                    name="LABIM/UFRN",
                    institutional_type_id=federal.id,
                    home_state_code="RN",
                    canonical_url="https://labim.example",
                    no_digital_content=False,
                    survey_source="test",
                    survey_row=1,
                ),
                Archive(
                    slug="ma-tjma-t1r2",
                    name="TJMA",
                    institutional_type_id=state_court.id,
                    home_state_code="MA",
                    canonical_url="https://tjma.example",
                    no_digital_content=False,
                    survey_source="test",
                    survey_row=2,
                ),
                Archive(
                    slug="pb-apepb-t2r1",
                    name="APEPB",
                    institutional_type_id=federal.id,
                    home_state_code="PB",
                    canonical_url="https://apepb.example",
                    no_digital_content=True,
                    survey_source="test",
                    survey_row=3,
                ),
            ]
        )
        _db.session.commit()
    return app


# --------------------------------------------------------------------------- #
# Service helpers


def test_record_score_creates_row(seeded_app):
    with seeded_app.app_context():
        archive = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim-t1r1"))
        row = svc.record_score(
            archive=archive,
            dimension="accessibility",
            score=7,
            justification_en="Public search UI works; downloads addressable.",
            justification_pt=None,
            scored_by="tester",
        )
        _db.session.commit()
        assert row.id is not None
        assert row.superseded_at is None


def test_record_score_supersedes_previous(seeded_app):
    with seeded_app.app_context():
        archive = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim-t1r1"))
        first = svc.record_score(
            archive=archive,
            dimension="accessibility",
            score=5,
            justification_en="Initial pass.",
            justification_pt=None,
            scored_by="a",
        )
        _db.session.commit()
        second = svc.record_score(
            archive=archive,
            dimension="accessibility",
            score=7,
            justification_en="Deeper look at the UI.",
            justification_pt=None,
            scored_by="b",
            now=_now() + timedelta(minutes=5),
        )
        _db.session.commit()

        # First row should now be superseded and point at second.
        _db.session.refresh(first)
        assert first.superseded_at is not None
        assert first.superseded_by_id == second.id
        # Only one active row.
        active = svc.active_scores(archive.id)
        assert list(active) == ["accessibility"]
        assert active["accessibility"].id == second.id
        # History returns both, newest first.
        hist = svc.score_history(archive.id, "accessibility")
        assert [r.id for r in hist] == [second.id, first.id]


def test_record_score_rejects_out_of_range(seeded_app):
    with seeded_app.app_context():
        archive = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim-t1r1"))
        with pytest.raises(ValueError):
            svc.record_score(
                archive=archive,
                dimension="accessibility",
                score=11,
                justification_en="x",
                justification_pt=None,
                scored_by=None,
            )


def test_set_facet_value_supersedes(seeded_app):
    with seeded_app.app_context():
        archive = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim-t1r1"))
        first = svc.set_facet_value(
            archive=archive,
            facet="licensing_posture",
            value="citation-only",
            note="metadata only",
            set_by="a",
        )
        _db.session.commit()
        second = svc.set_facet_value(
            archive=archive,
            facet="licensing_posture",
            value="redistribution-friendly",
            note="CC-BY confirmed by counsel",
            set_by="b",
            now=_now() + timedelta(minutes=1),
        )
        _db.session.commit()
        _db.session.refresh(first)
        assert first.superseded_at is not None
        assert first.superseded_by_id == second.id
        active = svc.active_facet_values(archive.id)
        assert active["licensing_posture"].value == "redistribution-friendly"


def test_set_facet_value_noop_on_identical_input(seeded_app):
    with seeded_app.app_context():
        archive = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim-t1r1"))
        svc.set_facet_value(
            archive=archive,
            facet="licensing_posture",
            value="citation-only",
            note="metadata only",
            set_by="a",
        )
        _db.session.commit()
        again = svc.set_facet_value(
            archive=archive,
            facet="licensing_posture",
            value="citation-only",
            note="metadata only",
            set_by="a",
        )
        _db.session.commit()
        # Same identity — no new row inserted.
        n = _db.session.scalar(
            select(_db.func.count()).select_from(FacetValue).where(
                FacetValue.archive_id == archive.id,
                FacetValue.facet == "licensing_posture",
            )
        )
        assert n == 1
        assert again.id is not None
        assert again.superseded_at is None


def test_set_facet_value_clear_supersedes_without_insert(seeded_app):
    with seeded_app.app_context():
        archive = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim-t1r1"))
        first = svc.set_facet_value(
            archive=archive,
            facet="licensing_posture",
            value="citation-only",
            note=None,
            set_by=None,
        )
        _db.session.commit()
        result = svc.set_facet_value(
            archive=archive,
            facet="licensing_posture",
            value="",
            note=None,
            set_by=None,
            now=_now() + timedelta(seconds=1),
        )
        _db.session.commit()
        assert result is None
        _db.session.refresh(first)
        assert first.superseded_at is not None
        assert first.superseded_by_id is None
        assert svc.active_facet_values(archive.id) == {}


def test_set_archive_tags_replaces(seeded_app):
    with seeded_app.app_context():
        archive = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim-t1r1"))
        svc.set_archive_tags(
            archive=archive,
            period_slugs=["second-reign-imperio-1840-1889", "old-republic-1889-1930"],
            record_type_slugs=["judicial"],
            theme_slugs=[],
        )
        _db.session.commit()
        assert {p.slug for p in archive.periods} == {
            "second-reign-imperio-1840-1889",
            "old-republic-1889-1930",
        }
        assert {r.slug for r in archive.record_types} == {"judicial"}
        assert archive.themes == []

        # Replace with a different set — previous rows must clear.
        svc.set_archive_tags(
            archive=archive,
            period_slugs=["independence-first-reign-1822-1831"],
            record_type_slugs=["notarial-land"],
            theme_slugs=[],
        )
        _db.session.commit()
        assert {p.slug for p in archive.periods} == {"independence-first-reign-1822-1831"}
        assert {r.slug for r in archive.record_types} == {"notarial-land"}


def test_set_archive_tags_rejects_unknown_slug(seeded_app):
    with seeded_app.app_context():
        archive = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim-t1r1"))
        with pytest.raises(ValueError):
            svc.set_archive_tags(archive=archive, period_slugs=["nope"])


# --------------------------------------------------------------------------- #
# List view


def test_list_view_default_hides_no_content(seeded_app, client):
    resp = client.get("/archives/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "LABIM/UFRN" in body
    assert "TJMA" in body
    # APEPB has no_digital_content=True and default filter is "with"
    assert "APEPB" not in body


def test_list_view_filter_by_state(seeded_app, client):
    resp = client.get("/archives/?state=MA")
    body = resp.get_data(as_text=True)
    assert "TJMA" in body
    assert "LABIM/UFRN" not in body


def test_list_view_filter_by_institutional_type(seeded_app, client):
    resp = client.get("/archives/?institutional_type=state-court")
    body = resp.get_data(as_text=True)
    assert "TJMA" in body
    assert "LABIM/UFRN" not in body


def test_list_view_content_without(seeded_app, client):
    resp = client.get("/archives/?content=without")
    body = resp.get_data(as_text=True)
    assert "APEPB" in body
    assert "LABIM/UFRN" not in body


def test_list_view_content_all(seeded_app, client):
    resp = client.get("/archives/?content=all")
    body = resp.get_data(as_text=True)
    assert "LABIM/UFRN" in body
    assert "APEPB" in body
    assert "TJMA" in body


def test_list_view_naive_sum_column(seeded_app, client):
    with seeded_app.app_context():
        archive = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim-t1r1"))
        svc.record_score(
            archive=archive,
            dimension="accessibility",
            score=7,
            justification_en="ok",
            justification_pt=None,
            scored_by=None,
        )
        svc.record_score(
            archive=archive,
            dimension="scale",
            score=3,
            justification_en="ok",
            justification_pt=None,
            scored_by=None,
        )
        _db.session.commit()

    resp = client.get("/archives/?sort=score")
    body = resp.get_data(as_text=True)
    # First row after header should be LABIM (sum = 10)
    assert body.index("LABIM/UFRN") < body.index("TJMA")
    assert "10" in body  # naive sum column shows 10


# --------------------------------------------------------------------------- #
# Detail view


def test_detail_view_shows_dimensions(seeded_app, client):
    resp = client.get("/archives/rn-labim-t1r1")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "LABIM/UFRN" in body
    for dim in (
        "accessibility",
        "provenance_curatorial",
        "corpus_completeness",
        "finding_aids",
        "pipeline_ingestion_readiness",
        "uniqueness_non_duplication",
        "scale",
        "linkage_potential",
    ):
        # Each dimension has an anchor id
        assert f'id="{dim}"' in body


def test_detail_view_404_on_missing_slug(seeded_app, client):
    assert client.get("/archives/does-not-exist").status_code == 404


def test_detail_view_shows_history_after_multiple_scores(seeded_app, client):
    with seeded_app.app_context():
        archive = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim-t1r1"))
        svc.record_score(
            archive=archive,
            dimension="accessibility",
            score=4,
            justification_en="first pass",
            justification_pt=None,
            scored_by="a",
        )
        svc.record_score(
            archive=archive,
            dimension="accessibility",
            score=8,
            justification_en="deeper review",
            justification_pt=None,
            scored_by="b",
            now=_now() + timedelta(minutes=1),
        )
        _db.session.commit()

    body = client.get("/archives/rn-labim-t1r1").get_data(as_text=True)
    assert "deeper review" in body
    assert "first pass" in body
    assert "superseded" in body


# --------------------------------------------------------------------------- #
# POST /archives/<slug>/score


def test_submit_score_persists(seeded_app, client):
    resp = client.post(
        "/archives/rn-labim-t1r1/score",
        data={
            "dimension": "accessibility",
            "score": "8",
            "justification_en": "Deep-linkable viewer with search.",
            "justification_pt": "",
            "scored_by": "tester",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with seeded_app.app_context():
        archive = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim-t1r1"))
        rows = svc.score_history(archive.id, "accessibility")
        assert len(rows) == 1
        assert rows[0].score == 8
        assert rows[0].justification_en == "Deep-linkable viewer with search."
        assert rows[0].scored_by == "tester"


def test_submit_score_supersedes_active(seeded_app, client):
    client.post(
        "/archives/rn-labim-t1r1/score",
        data={
            "dimension": "accessibility",
            "score": "5",
            "justification_en": "first",
            "justification_pt": "",
            "scored_by": "a",
        },
    )
    client.post(
        "/archives/rn-labim-t1r1/score",
        data={
            "dimension": "accessibility",
            "score": "9",
            "justification_en": "second, after deeper review",
            "justification_pt": "",
            "scored_by": "b",
        },
    )
    with seeded_app.app_context():
        archive = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim-t1r1"))
        active = svc.active_scores(archive.id)
        assert active["accessibility"].score == 9
        hist = svc.score_history(archive.id, "accessibility")
        assert len(hist) == 2
        assert hist[1].superseded_at is not None


def test_submit_score_rejects_invalid_dimension(seeded_app, client):
    resp = client.post(
        "/archives/rn-labim-t1r1/score",
        data={
            "dimension": "not_a_real_dimension",
            "score": "5",
            "justification_en": "irrelevant",
            "justification_pt": "",
            "scored_by": "",
        },
    )
    assert resp.status_code == 400


def test_submit_score_rejects_out_of_range(seeded_app, client):
    resp = client.post(
        "/archives/rn-labim-t1r1/score",
        data={
            "dimension": "accessibility",
            "score": "42",
            "justification_en": "irrelevant",
            "justification_pt": "",
            "scored_by": "",
        },
        follow_redirects=False,
    )
    # WTForms fails validation → flash + redirect back to detail
    assert resp.status_code == 302
    with seeded_app.app_context():
        archive = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim-t1r1"))
        assert svc.active_scores(archive.id) == {}


# --------------------------------------------------------------------------- #
# POST /archives/<slug>/facets


def test_edit_facets_form_get(seeded_app, client):
    resp = client.get("/archives/rn-labim-t1r1/facets")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Licensing posture" in body
    assert "Fair use eligibility" in body


def test_submit_facets_persists(seeded_app, client):
    resp = client.post(
        "/archives/rn-labim-t1r1/facets",
        data={
            "form": "facets",
            "licensing_posture": "redistribution-friendly",
            "licensing_posture_note": "CC-BY confirmed",
            "stated_roadmap": "published-and-active",
            "stated_roadmap_note": "",
            "curatorial_rarity_notes": "Only extant colonial hand-drawn maps in RN.",
            "prior_use_note": "",
            "fair_use_eligible": "yes",
            "set_by": "tester",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with seeded_app.app_context():
        archive = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim-t1r1"))
        active = svc.active_facet_values(archive.id)
        assert active["licensing_posture"].value == "redistribution-friendly"
        assert active["licensing_posture"].note == "CC-BY confirmed"
        assert active["stated_roadmap"].value == "published-and-active"
        assert archive.fair_use_eligible is True
        assert archive.curatorial_rarity_notes.startswith("Only extant")


def test_submit_tags_persists(seeded_app, client):
    from werkzeug.datastructures import MultiDict

    payload = MultiDict()
    payload.add("form", "tags")
    payload.add("periods", "second-reign-imperio-1840-1889")
    payload.add("periods", "old-republic-1889-1930")
    payload.add("record_types", "judicial")

    resp = client.post(
        "/archives/rn-labim-t1r1/facets",
        data=payload,
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with seeded_app.app_context():
        archive = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim-t1r1"))
        assert {p.slug for p in archive.periods} == {
            "second-reign-imperio-1840-1889",
            "old-republic-1889-1930",
        }
        assert {r.slug for r in archive.record_types} == {"judicial"}
