"""Tests for the two-axis aggregation added in ADR-0001.

These cover the service-layer contracts: axis membership integrity, per-axis
sums including partial-score behaviour, and the quadrant helper. Route-level
rendering of the axis columns is covered separately in the archives blueprint
tests.
"""
from __future__ import annotations

import pytest

from app.extensions import db
from app.models import DIMENSIONS, Archive, InstitutionalType
from app.services import scoring as svc


@pytest.fixture()
def seed_archive(app):
    with app.app_context():
        itype = InstitutionalType(
            slug="university-repository",
            label_en="University repository",
            label_pt="Repositório universitário",
            sort_order=1,
        )
        db.session.add(itype)
        db.session.flush()

        archive = Archive(
            slug="rn-axis-test-archive",
            name="Axis test archive",
            name_pt="Arquivo de teste de eixo",
            home_state_code="RN",
            institutional_type_id=itype.id,
            canonical_url="https://example.test/axis",
        )
        db.session.add(archive)
        db.session.commit()
        yield archive.id
        db.session.rollback()


def _score_all(archive_id: int, values: dict[str, int]) -> None:
    archive = db.session.get(Archive, archive_id)
    for dim, value in values.items():
        svc.record_score(
            archive=archive,
            dimension=dim,
            score=value,
            justification_en=f"test score {value}",
            justification_pt=None,
            scored_by="test",
        )
    db.session.commit()


# --------------------------------------------------------------------------- #
# Axis membership integrity


def test_axes_cover_all_dimensions_disjointly(app):
    """AXES must partition DIMENSIONS: every dimension in exactly one axis."""
    with app.app_context():
        members = [d for group in svc.AXES.values() for d in group]
        assert set(members) == set(DIMENSIONS)
        assert len(members) == len(set(members)), "no dimension appears twice"


def test_axis_max_matches_membership(app):
    """AXIS_MAX must equal len(axis members) * 10."""
    with app.app_context():
        for members in svc.AXES.values():
            assert len(members) * 10 == svc.AXIS_MAX


# --------------------------------------------------------------------------- #
# axis_score


def test_axis_score_unscored_returns_none(app, seed_archive):
    with app.app_context():
        assert svc.axis_score(seed_archive, "pipeline") is None
        assert svc.axis_score(seed_archive, "research") is None


def test_axis_score_unknown_axis_raises(app, seed_archive):
    with app.app_context():
        with pytest.raises(ValueError, match="Unknown axis"):
            svc.axis_score(seed_archive, "made-up-axis")


def test_axis_score_full_scores(app, seed_archive):
    """LABIM's Pass 2 profile: pipeline=31, research=26.

    Uses LABIM's exact numbers (from configs/calibration/pass2.yaml) to
    catch a regression where the AXES membership drifted from what the
    ADR documents.
    """
    labim = {
        "accessibility": 8,
        "provenance_curatorial": 6,
        "corpus_completeness": 6,
        "finding_aids": 7,
        "pipeline_ingestion_readiness": 8,
        "uniqueness_non_duplication": 8,
        "scale": 8,
        "linkage_potential": 6,
    }
    with app.app_context():
        _score_all(seed_archive, labim)
        assert svc.axis_score(seed_archive, "pipeline") == 31
        assert svc.axis_score(seed_archive, "research") == 26


def test_axis_score_partial_returns_partial_total(app, seed_archive):
    """A half-scored archive returns the partial axis sum, not None."""
    partial = {
        "accessibility": 8,
        "finding_aids": 6,
        # pipeline_ingestion_readiness and scale unscored
        "provenance_curatorial": 7,
        "corpus_completeness": 5,
        # uniqueness_non_duplication and linkage_potential unscored
    }
    with app.app_context():
        _score_all(seed_archive, partial)
        assert svc.axis_score(seed_archive, "pipeline") == 14  # 8 + 6
        assert svc.axis_score(seed_archive, "research") == 12  # 7 + 5


# --------------------------------------------------------------------------- #
# axis_scores


def test_axis_scores_returns_both(app, seed_archive):
    interpi = {
        "accessibility": 8,
        "provenance_curatorial": 9,
        "corpus_completeness": 6,
        "finding_aids": 6,
        "pipeline_ingestion_readiness": 4,
        "uniqueness_non_duplication": 10,
        "scale": 6,
        "linkage_potential": 8,
    }
    with app.app_context():
        _score_all(seed_archive, interpi)
        got = svc.axis_scores(seed_archive)
        assert got == {"pipeline": 24, "research": 33}


def test_axis_scores_unscored_returns_none_pair(app, seed_archive):
    with app.app_context():
        assert svc.axis_scores(seed_archive) == {"pipeline": None, "research": None}


# --------------------------------------------------------------------------- #
# quadrant_label


@pytest.mark.parametrize(
    "pipeline,research,expected",
    [
        (32, 30, "High pipeline / High research"),
        (32, 20, "High pipeline / Low research"),
        (20, 32, "Low pipeline / High research"),
        (20, 20, "Low pipeline / Low research"),
        (28, 28, "High pipeline / High research"),  # threshold is inclusive
        (27, 27, "Low pipeline / Low research"),
        (None, 30, "n.a."),
        (30, None, "n.a."),
        (None, None, "n.a."),
    ],
)
def test_quadrant_label(pipeline, research, expected, app):
    with app.app_context():
        assert svc.quadrant_label(pipeline, research) == expected


def test_quadrant_label_custom_threshold(app):
    with app.app_context():
        # Anchor-6 threshold puts a 25/25 archive in the high/high quadrant.
        assert (
            svc.quadrant_label(25, 25, threshold=24)
            == "High pipeline / High research"
        )
        assert (
            svc.quadrant_label(25, 25, threshold=28)
            == "Low pipeline / Low research"
        )


# --------------------------------------------------------------------------- #
# scholarly_access_practical facet is registered


def test_scholarly_access_practical_facet_registered(app):
    """New facet must be accepted by set_facet_value and its values validated."""
    with app.app_context():
        assert "scholarly_access_practical" in svc.SINGLE_SELECT_FACETS
        assert svc.SINGLE_SELECT_FACETS["scholarly_access_practical"] == (
            "well-supported",
            "usable-with-effort",
            "only-via-federation",
            "not-yet-assessed",
        )


def test_scholarly_access_practical_facet_set_and_read(app, seed_archive):
    with app.app_context():
        archive = db.session.get(Archive, seed_archive)
        svc.set_facet_value(
            archive=archive,
            facet="scholarly_access_practical",
            value="only-via-federation",
            note="Static PDF tree; needs Mipibu-style companion app.",
            set_by="test",
        )
        db.session.commit()

        active = svc.active_facet_values(seed_archive)
        assert "scholarly_access_practical" in active
        assert active["scholarly_access_practical"].value == "only-via-federation"


def test_scholarly_access_practical_rejects_bad_value(app, seed_archive):
    with app.app_context():
        archive = db.session.get(Archive, seed_archive)
        with pytest.raises(ValueError, match="Invalid value"):
            svc.set_facet_value(
                archive=archive,
                facet="scholarly_access_practical",
                value="fabricated",
                note=None,
                set_by="test",
            )
