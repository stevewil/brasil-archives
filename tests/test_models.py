"""Smoke tests for SQLAlchemy models and their constraints."""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import (
    DIMENSIONS,
    Archive,
    DimensionScore,
    InstitutionalType,
    UpgradeProject,
)


def _make_inst_type(db, slug="university"):
    it = InstitutionalType(slug=slug, label_en="University", label_pt="Universidade", sort_order=1)
    db.session.add(it)
    db.session.commit()
    return it


def _make_archive(db, slug="labim-ufrn"):
    it = _make_inst_type(db)
    a = Archive(
        slug=slug,
        name="LABIM / UFRN",
        canonical_url="https://labim.ufrn.br",
        institutional_type_id=it.id,
    )
    db.session.add(a)
    db.session.commit()
    return a


def test_dimensions_constant_matches_check_constraint():
    # If a dimension is added to DIMENSIONS, schema-v1.md and the CHECK
    # constraint on dimension_scores must be updated in lockstep.
    assert len(DIMENSIONS) == 8
    assert "accessibility" in DIMENSIONS
    assert "linkage_potential" in DIMENSIONS


def test_archive_roundtrip(db):
    a = _make_archive(db)
    fetched = db.session.scalar(select(Archive).where(Archive.slug == "labim-ufrn"))
    assert fetched is not None
    assert fetched.name == "LABIM / UFRN"
    assert fetched.home_country_code == "BR"
    assert fetched.no_digital_content is False


def test_dimension_score_range_check(db):
    a = _make_archive(db)
    bad = DimensionScore(
        archive_id=a.id,
        dimension="accessibility",
        score=42,
        justification_en="out of range",
    )
    db.session.add(bad)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_dimension_score_dimension_check(db):
    a = _make_archive(db)
    bad = DimensionScore(
        archive_id=a.id,
        dimension="not_a_real_dimension",
        score=5,
        justification_en="unknown dimension",
    )
    db.session.add(bad)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_dimension_score_ok(db):
    a = _make_archive(db)
    s = DimensionScore(
        archive_id=a.id,
        dimension="accessibility",
        score=7,
        justification_en="works",
        scored_by="stevewil",
    )
    db.session.add(s)
    db.session.commit()
    assert s.id is not None
    assert s.superseded_at is None


def test_upgrade_project_requires_source_archive(db):
    a = _make_archive(db)
    up = UpgradeProject(
        slug="mipibu",
        name="Mipibu",
        source_archive_id=a.id,
        scope_description_en="LABIM processos",
        primary_url="https://mipibu.pplx.app",
        delivery_status="beta",
    )
    db.session.add(up)
    db.session.commit()
    assert up.federation_contract_version == "v1"
    assert up.source_archive.slug == "labim-ufrn"
