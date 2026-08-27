"""Tests for the vocabulary, survey, and upgrade-project loaders."""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
from sqlalchemy import select

from app.models import (
    Archive,
    DimensionLift,
    InstitutionalType,
    Period,
    RecordType,
    Theme,
    UpgradeProject,
)
from scripts import load_survey, load_upgrade_projects, load_vocabularies


# --------------------------------------------------------------------------- #
# Vocabulary loader


def test_load_vocabularies_inserts_all(app):
    with app.app_context():
        results = load_vocabularies.load_all()
    with app.app_context():
        assert results["periods.yaml"][0] == 12
        assert results["institutional_types.yaml"][0] == 11
        assert results["record_types.yaml"][0] == 11
        assert results["themes.yaml"][0] >= 15
        # Every period from algorithm-v1.md must be present.
        slugs = {p.slug for p in load_vocabularies.db.session.scalars(select(Period)).all()}
        assert "second-reign-imperio-1840-1889" in slugs
        assert "old-republic-1889-1930" in slugs


def test_load_vocabularies_idempotent(app):
    with app.app_context():
        first = load_vocabularies.load_all()
        second = load_vocabularies.load_all()
    for name in first:
        # Second run should insert zero.
        assert second[name][0] == 0


def test_load_vocabularies_updates_labels(app, tmp_path, monkeypatch):
    # First load with real files
    with app.app_context():
        load_vocabularies.load_all()

    # Second load using a modified periods file → label updates
    modified_dir = tmp_path / "vocabularies"
    modified_dir.mkdir()
    for name in ("periods.yaml", "institutional_types.yaml", "record_types.yaml", "themes.yaml"):
        (modified_dir / name).write_bytes((load_vocabularies.CONFIG_DIR / name).read_bytes())
    # Replace second-reign-imperio label
    periods_path = modified_dir / "periods.yaml"
    periods_path.write_text(
        periods_path.read_text(encoding="utf-8").replace(
            "Second Reign / Império (1840–1889)",
            "Second Reign — Império (1840–1889)",
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(load_vocabularies, "CONFIG_DIR", modified_dir)

    with app.app_context():
        results = load_vocabularies.load_all()
        assert results["periods.yaml"] == (0, 1)
        row = load_vocabularies.db.session.scalar(
            select(Period).where(Period.slug == "second-reign-imperio-1840-1889")
        )
        assert row.label_en == "Second Reign — Império (1840–1889)"


# --------------------------------------------------------------------------- #
# Survey parsing


MINI_SURVEY = dedent(
    """\
    # Nordeste Digital Archives Survey (test fixture)

    ## Table 1 — Pipeline-Viable Shortlist

    | # | State | Institution (PT) | Institution type | City | Primary URL | Example document URL | Record types available | Digital availability level | URL addressability | Est. corpus size | Time period | Handwriting era | Access/ToS | Mipibu-fit | Priority notes | Source of lead |
    |---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
    | 1 | RN | LABIM/UFRN Repository | University | Natal | [labim](https://labim.example) | ex1 | judicial | full-scans | addressable | ~1000 items | 1850-1930 | mixed | open | 4 | Top target | [src](https://s1.example) |
    | 2 | MA | TJMA Portal da Memória | Special/thematic (judicial) | São Luís | [tjma](https://tjma.example) | ex2 | judicial | scans | viewer | ~350000 | 1747-1972 | mixed | open | 5 | Top candidate | [src](https://s2.example) |

    ## Table 2 — No-Digital-Content Register

    | State | Institution (PT) | Institution type | City | URL | What is available online | Source of finding |
    |---|---|---|---|---|---|---|
    | PB | APEPB | State archive | João Pessoa | [apepb](https://apepb.example) | Contact only | [src](https://s3.example) |

    ## Cross-cutting findings

    Ignore me.
    """
)


def test_parse_survey_splits_tables():
    rows = load_survey.parse_survey(MINI_SURVEY)
    assert len(rows) == 3
    t1 = [r for r in rows if r.table == 1]
    t2 = [r for r in rows if r.table == 2]
    assert len(t1) == 2 and len(t2) == 1
    assert t1[0].survey_row == 1 and t1[1].survey_row == 2
    assert t2[0].no_digital_content is True
    assert t1[0].no_digital_content is False


def test_parse_survey_extracts_primary_url():
    rows = load_survey.parse_survey(MINI_SURVEY)
    assert rows[0].primary_url == "https://labim.example"
    assert rows[2].primary_url == "https://apepb.example"


def test_load_survey_writes_archives(app, tmp_path):
    survey_path = tmp_path / "mini-survey.md"
    survey_path.write_text(MINI_SURVEY, encoding="utf-8")

    with app.app_context():
        load_vocabularies.load_all()
        parsed, ins, upd = load_survey.load(survey_path)
        assert parsed == 3
        assert ins == 3
        assert upd == 0

        archives = load_survey.db.session.scalars(select(Archive)).all()
        assert len(archives) == 3
        labim = next(a for a in archives if "labim" in a.slug.lower())
        assert labim.slug.endswith("-t1r1")
        assert labim.home_state_code == "RN"
        assert labim.no_digital_content is False
        apepb = next(a for a in archives if "apepb" in a.slug.lower())
        assert apepb.no_digital_content is True


def test_load_survey_idempotent(app, tmp_path):
    survey_path = tmp_path / "mini-survey.md"
    survey_path.write_text(MINI_SURVEY, encoding="utf-8")
    with app.app_context():
        load_vocabularies.load_all()
        load_survey.load(survey_path)
        parsed, ins, upd = load_survey.load(survey_path)
        assert parsed == 3 and ins == 0 and upd == 0


def test_load_survey_uses_real_file(app):
    """Full survey should parse to 50 + 29 rows and load cleanly."""
    real = load_survey.DEFAULT_SURVEY
    if not real.exists():
        pytest.skip(f"Real survey file not available at {real}")
    with app.app_context():
        load_vocabularies.load_all()
        parsed, ins, upd = load_survey.load(real)
        assert parsed == 79
        assert ins == 79
        assert upd == 0
        # 50 pipeline-viable
        with_content = load_survey.db.session.scalars(
            select(Archive).where(Archive.no_digital_content.is_(False))
        ).all()
        no_content = load_survey.db.session.scalars(
            select(Archive).where(Archive.no_digital_content.is_(True))
        ).all()
        assert len(with_content) == 50
        assert len(no_content) == 29


# --------------------------------------------------------------------------- #
# Upgrade project loader


def _write_test_mipibu_yaml(dest_dir: Path) -> Path:
    """Copy real Mipibu YAML into ``dest_dir`` but retarget its source.

    The mini-survey fixture places LABIM at Table 1 row 1 (not row 8),
    so we swap ``source_archive_survey`` to match.
    """
    src = load_upgrade_projects.CONFIG_DIR / "mipibu.yaml"
    text = src.read_text(encoding="utf-8")
    text = text.replace("table: 1\n  row: 8", "table: 1\n  row: 1")
    dest = dest_dir / "mipibu.yaml"
    dest.write_text(text, encoding="utf-8")
    return dest


def test_load_mipibu_upgrade_project(app, tmp_path, monkeypatch):
    survey_path = tmp_path / "mini-survey.md"
    survey_path.write_text(MINI_SURVEY, encoding="utf-8")
    test_config_dir = tmp_path / "upgrade_projects"
    test_config_dir.mkdir()
    _write_test_mipibu_yaml(test_config_dir)
    monkeypatch.setattr(load_upgrade_projects, "CONFIG_DIR", test_config_dir)

    with app.app_context():
        load_vocabularies.load_all()
        load_survey.load(survey_path)
        counts = load_upgrade_projects.load()
        assert "mipibu" in counts

        proj = load_upgrade_projects.db.session.scalar(
            select(UpgradeProject).where(UpgradeProject.slug == "mipibu")
        )
        assert proj is not None
        assert proj.name == "Mipibu Corpus Explorer"
        assert proj.source_archive.slug.endswith("-t1r1")
        assert proj.delivery_status == "beta"
        assert proj.federation_contract_version == "v1"
        # Period tags applied
        period_slugs = {p.slug for p in proj.periods}
        assert "second-reign-imperio-1840-1889" in period_slugs
        assert "old-republic-1889-1930" in period_slugs
        # Record types applied
        rt_slugs = {r.slug for r in proj.record_types}
        assert "judicial" in rt_slugs
        # Empty lifts map → zero DimensionLift rows for now
        lifts = load_upgrade_projects.db.session.scalars(
            select(DimensionLift).where(DimensionLift.upgrade_project_id == proj.id)
        ).all()
        assert lifts == []


def test_load_upgrade_project_idempotent(app, tmp_path, monkeypatch):
    survey_path = tmp_path / "mini-survey.md"
    survey_path.write_text(MINI_SURVEY, encoding="utf-8")
    test_config_dir = tmp_path / "upgrade_projects"
    test_config_dir.mkdir()
    _write_test_mipibu_yaml(test_config_dir)
    monkeypatch.setattr(load_upgrade_projects, "CONFIG_DIR", test_config_dir)

    with app.app_context():
        load_vocabularies.load_all()
        load_survey.load(survey_path)
        load_upgrade_projects.load()
        # Second run: still exactly one project
        load_upgrade_projects.load()
        n = load_upgrade_projects.db.session.scalar(
            select(load_upgrade_projects.db.func.count()).select_from(UpgradeProject)
        )
        assert n == 1
