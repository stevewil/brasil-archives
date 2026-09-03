"""Integration test for the povos-indigenas-rn upgrade-project bootstrap.

Covers the sequence from `docs/integrations/povos-indigenas-rn.md` §7:
seed the composite archives row, then load
`configs/upgrade_projects/povos-indigenas-rn.yaml`.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.models import Archive, UpgradeProject
from scripts import load_upgrade_projects, load_vocabularies, seed_povos_archive


def _povos_only_config_dir(tmp_path: Path) -> Path:
    src = load_upgrade_projects.CONFIG_DIR / "povos-indigenas-rn.yaml"
    dest_dir = tmp_path / "upgrade_projects"
    dest_dir.mkdir()
    (dest_dir / "povos-indigenas-rn.yaml").write_text(
        src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return dest_dir


def test_seed_povos_archive_is_idempotent(app):
    with app.app_context():
        load_vocabularies.load_all()
        first = seed_povos_archive.run()
        assert first.startswith("added")
        second = seed_povos_archive.run()
        assert second.startswith("updated")
        rows = seed_povos_archive.db.session.scalars(
            select(Archive).where(Archive.slug == seed_povos_archive.SLUG)
        ).all()
        assert len(rows) == 1
        archive = rows[0]
        assert archive.institutional_type.slug == "research-project"
        assert archive.home_state_code == "RN"
        assert archive.fair_use_eligible is True
        assert archive.no_digital_content is False


def test_load_povos_upgrade_project(app, tmp_path, monkeypatch):
    monkeypatch.setattr(
        load_upgrade_projects, "CONFIG_DIR", _povos_only_config_dir(tmp_path)
    )
    with app.app_context():
        load_vocabularies.load_all()
        seed_povos_archive.run()
        counts = load_upgrade_projects.load()
        assert "povos-indigenas-rn" in counts

        proj = load_upgrade_projects.db.session.scalar(
            select(UpgradeProject).where(UpgradeProject.slug == "povos-indigenas-rn")
        )
        assert proj is not None
        assert proj.name == "Povos Indígenas do RN Corpus Explorer"
        assert proj.source_archive.slug == "povos-indigenas-rn-corpus"
        assert proj.delivery_status == "beta"
        assert proj.federation_contract_version == "v1"
        assert proj.json_api_base_url == (
            "https://corpus-explorers.from-bottom-to.top/projects/povos-indigenas-rn/api"
        )
        assert proj.oai_pmh_base_url == (
            "https://corpus-explorers.from-bottom-to.top/projects/povos-indigenas-rn/oai"
        )
        assert proj.approximate_document_count == 40

        period_slugs = {p.slug for p in proj.periods}
        assert "second-reign-imperio-1840-1889" in period_slugs
        assert "early-colonial-1500-1700" in period_slugs
        rt_slugs = {r.slug for r in proj.record_types}
        assert rt_slugs == {"administrative-legislative", "manuscripts-books"}


def test_load_povos_is_idempotent(app, tmp_path, monkeypatch):
    monkeypatch.setattr(
        load_upgrade_projects, "CONFIG_DIR", _povos_only_config_dir(tmp_path)
    )
    with app.app_context():
        load_vocabularies.load_all()
        seed_povos_archive.run()
        load_upgrade_projects.load()
        load_upgrade_projects.load()
        n = load_upgrade_projects.db.session.scalar(
            select(load_upgrade_projects.db.func.count()).select_from(UpgradeProject)
        )
        assert n == 1
