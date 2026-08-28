"""Tests for scripts.load_calibration.

The loader is idempotent, uses the service layer for supersede
semantics, and touches Archive columns directly for the fields that
aren't stored in FacetValue rows. Tests cover the invariants a
production re-run should preserve.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import (
    Archive,
    DIMENSIONS,
    DimensionScore,
    InstitutionalType,
)
from scripts import load_vocabularies
from scripts.load_calibration import load_calibration


@pytest.fixture()
def seeded_app(app):
    """Adds vocab + one archive on top of the shared `app` fixture.

    Note: the shared `app` fixture in conftest already opens an app
    context, so we can seed directly.
    """
    _seed_vocab()
    _seed_archive("test-archive-alpha", "Alpha archive")
    db.session.commit()
    return app


def _seed_vocab() -> None:
    """Load the full vocabulary set from configs/ into the test DB."""
    load_vocabularies.load_all()


def _seed_archive(slug: str, name: str) -> Archive:
    # Any institutional type slug from the loaded vocab works; use
    # 'research-project' as an intentionally neutral default that the
    # calibration YAML can override.
    itype = db.session.scalar(
        select(InstitutionalType).where(InstitutionalType.slug == "research-project")
    )
    a = Archive(
        slug=slug,
        name=name,
        name_pt=name,
        institutional_type_id=itype.id,
        canonical_url="https://example.org/",
        home_country_code="BR",
        home_state_code="RN",
        no_digital_content=False,
    )
    db.session.add(a)
    db.session.flush()
    return a


def _write_yaml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "calib.yaml"
    p.write_text(dedent(body).lstrip("\n"), encoding="utf-8")
    return p


def _minimal_scores_block(indent: int = 14) -> str:
    """Return a scores: block covering all 8 dimensions.

    Callers embed this inside a triple-quoted YAML template with an
    8-space outer indent. The scores: key sits at 12 spaces; each
    dimension key sits at 14 spaces; each nested field at 16.
    textwrap.dedent then strips the common 8-space prefix, leaving a
    valid YAML fragment.
    """
    pad = " " * indent
    inner = " " * (indent + 2)
    return "\n".join(
        f"{pad}{dim}:\n"
        f"{inner}score: 5\n"
        f"{inner}justification_en: en\n"
        f"{inner}justification_pt: pt"
        for dim in DIMENSIONS
    )


def test_loader_writes_all_scores_facets_and_tags(seeded_app, tmp_path):
    app = seeded_app
    yaml_path = _write_yaml(
        tmp_path,
        f"""
        scored_by: test/pass2
        archives:
          - slug: test-archive-alpha
            scores:
{_minimal_scores_block()}
            facets:
              institutional_type: state-court
              licensing_posture: citation-only
              stated_roadmap: informal
              fair_use_eligible: true
              curatorial_rarity_notes: rare
              prior_use_note: cited widely
            tags:
              periods:
                - second-reign-imperio-1840-1889
              record_types:
                - judicial
              themes:
                - crime-punishment
        """,
    )

    report = load_calibration(yaml_path)

    assert report.archives_processed == 1
    assert report.scores_written == 8
    assert report.scores_unchanged == 0
    assert report.facets_written == 2  # licensing_posture, stated_roadmap
    # institutional_type + fair_use_eligible + curatorial_rarity_notes + prior_use_note.
    assert report.archive_fields_updated == 4

    archive = db.session.scalar(select(Archive).where(Archive.slug == "test-archive-alpha"))
    active = db.session.scalars(
        select(DimensionScore).where(
            DimensionScore.archive_id == archive.id,
            DimensionScore.superseded_at.is_(None),
        )
    ).all()
    assert {row.dimension for row in active} == set(DIMENSIONS)
    assert archive.fair_use_eligible is True
    assert archive.curatorial_rarity_notes == "rare"
    assert archive.institutional_type.slug == "state-court"
    assert {p.slug for p in archive.periods} == {"second-reign-imperio-1840-1889"}


def test_loader_is_idempotent_and_supersedes_only_changes(seeded_app, tmp_path):
    app = seeded_app
    yaml_path = _write_yaml(
        tmp_path,
        f"""
        scored_by: test/pass2
        archives:
          - slug: test-archive-alpha
            scores:
{_minimal_scores_block()}
            facets:
              licensing_posture: citation-only
              stated_roadmap: informal
        """,
    )

    first = load_calibration(yaml_path)
    assert first.scores_written == 8
    assert first.facets_written == 2

    # Re-run: everything should be unchanged.
    second = load_calibration(yaml_path)
    assert second.scores_written == 0
    assert second.facets_written == 0
    assert second.scores_unchanged == 8
    assert second.facets_unchanged == 2

    # Only one active score row per dimension survives.
    active_rows = db.session.scalars(
        select(DimensionScore).where(DimensionScore.superseded_at.is_(None))
    ).all()
    assert len(active_rows) == 8


def test_loader_supersedes_when_score_changes(seeded_app, tmp_path):
    app = seeded_app
    """Changing one dimension's score inserts a fresh active row and
    supersedes the previous one; other rows are untouched."""
    yaml_path = _write_yaml(
        tmp_path,
        f"""
        scored_by: test/pass2
        archives:
          - slug: test-archive-alpha
            scores:
{_minimal_scores_block()}
        """,
    )
    load_calibration(yaml_path)

    # Bump accessibility to 8, leave others.
    original = _minimal_scores_block()
    bumped_scores = original.replace(
        "accessibility:\n                score: 5",
        "accessibility:\n                score: 8",
        1,
    )
    assert bumped_scores != original, "score-replace pattern did not match"
    yaml_path2 = _write_yaml(
        tmp_path,
        f"""
        scored_by: test/pass2
        archives:
          - slug: test-archive-alpha
            scores:
{bumped_scores}
        """,
    )
    report = load_calibration(yaml_path2)
    assert report.scores_written == 1
    assert report.scores_unchanged == 7

    archive = db.session.scalar(select(Archive).where(Archive.slug == "test-archive-alpha"))
    history = db.session.scalars(
        select(DimensionScore)
        .where(
            DimensionScore.archive_id == archive.id,
            DimensionScore.dimension == "accessibility",
        )
        .order_by(DimensionScore.scored_at.desc(), DimensionScore.id.desc())
    ).all()
    assert len(history) == 2
    assert history[0].score == 8
    assert history[0].superseded_at is None
    assert history[1].score == 5
    assert history[1].superseded_at is not None
    assert history[1].superseded_by_id == history[0].id


def test_loader_dry_run_makes_no_changes(seeded_app, tmp_path):
    app = seeded_app
    yaml_path = _write_yaml(
        tmp_path,
        f"""
        scored_by: test/pass2
        archives:
          - slug: test-archive-alpha
            scores:
{_minimal_scores_block()}
        """,
    )
    report = load_calibration(yaml_path, dry_run=True)
    assert report.scores_written == 8

    # Nothing persisted.
    rows = db.session.scalars(select(DimensionScore)).all()
    assert rows == []


def test_loader_warns_on_unknown_archive_and_dimension(seeded_app, tmp_path):
    app = seeded_app
    yaml_path = _write_yaml(
        tmp_path,
        """
        scored_by: test/pass2
        archives:
          - slug: does-not-exist
            scores:
              accessibility:
                score: 5
                justification_en: en
                justification_pt: pt
          - slug: test-archive-alpha
            scores:
              accessibility:
                score: 5
                justification_en: en
                justification_pt: pt
              bogus_dimension:
                score: 5
                justification_en: en
                justification_pt: pt
        """,
    )
    report = load_calibration(yaml_path)
    assert any("Archive not found" in w for w in report.warnings)
    assert any("bogus_dimension" in w for w in report.warnings)
    assert report.archives_processed == 1
    assert report.scores_written == 1


def test_loader_warns_on_unknown_institutional_type(seeded_app, tmp_path):
    app = seeded_app
    yaml_path = _write_yaml(
        tmp_path,
        """
        scored_by: test/pass2
        archives:
          - slug: test-archive-alpha
            facets:
              institutional_type: fake-slug
        """,
    )
    with pytest.raises(ValueError, match="Unknown institutional_type"):
        load_calibration(yaml_path)


def test_loader_size_unit_note_stored_on_archive(seeded_app, tmp_path):
    """size_unit_note is an Archive column (like curatorial_rarity_notes) —
    stored directly, no warning."""
    yaml_path = _write_yaml(
        tmp_path,
        """
        scored_by: test/pass2
        archives:
          - slug: test-archive-alpha
            facets:
              size_unit_note: rows and pages
        """,
    )
    report = load_calibration(yaml_path)
    assert not any("size_unit_note" in w for w in report.warnings)
    assert report.facets_written == 0
    assert report.archive_fields_updated == 1

    archive = db.session.scalar(
        select(Archive).where(Archive.slug == "test-archive-alpha")
    )
    assert archive.size_unit_note == "rows and pages"
