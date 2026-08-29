"""scripts/reextract.py — refresh extracted_json from stored raw_xml."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

import pytest

from app.extensions import db as _db
from app.models import (
    AggregatedRecord,
    Archive,
    HarvestRun,
    InstitutionalType,
    UpgradeProject,
)
from scripts import reextract

_RECORD_XML = (
    '<record xmlns="http://www.openarchives.org/OAI/2.0/">'
    "<header><identifier>oai:x:case:1</identifier>"
    "<datestamp>2026-08-29</datestamp></header>"
    "<metadata>"
    '<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"'
    ' xmlns:dc="http://purl.org/dc/elements/1.1/">'
    "<dc:title>Ação de teste</dc:title>"
    "<dc:identifier>https://partner.example/cases/1</dc:identifier>"
    "<dc:source>https://repo.example/record/1</dc:source>"
    "</oai_dc:dc></metadata></record>"
)


@pytest.fixture
def seeded(app):
    with app.app_context():
        it = InstitutionalType(slug="rp", label_en="RP", label_pt="RP", sort_order=1)
        _db.session.add(it)
        _db.session.flush()
        arch = Archive(
            slug="a", name="A", institutional_type_id=it.id,
            canonical_url="https://a.example", no_digital_content=False,
        )
        _db.session.add(arch)
        _db.session.flush()
        proj = UpgradeProject(
            slug="partner", name="Partner", source_archive_id=arch.id,
            scope_description_en="x", primary_url="https://partner.example",
            delivery_status="beta",
        )
        _db.session.add(proj)
        _db.session.flush()
        run = HarvestRun(
            upgrade_project_id=proj.id, metadata_prefix="oai_dc",
            started_at=datetime(2026, 8, 29), status="ok",
        )
        _db.session.add(run)
        _db.session.flush()
        _db.session.add(AggregatedRecord(
            upgrade_project_id=proj.id, oai_identifier="oai:x:case:1",
            metadata_prefix="oai_dc", datestamp="2026-08-29", set_specs_json="[]",
            raw_xml=_RECORD_XML,
            raw_xml_sha256=hashlib.sha256(_RECORD_XML.encode()).hexdigest(),
            extracted_json=json.dumps({"canonical": {"title": "stale"}}),
            harvest_run_id=run.id,
            first_seen_at=datetime(2026, 8, 29), last_seen_at=datetime(2026, 8, 29),
        ))
        _db.session.commit()
    return app


def _canonical(app):
    with app.app_context():
        rec = _db.session.query(AggregatedRecord).one()
        return json.loads(rec.extracted_json)["canonical"]


def test_reextract_refreshes_stale_rows(seeded, monkeypatch):
    monkeypatch.setattr(reextract, "app", seeded)
    rc = reextract.main(["--project", "partner"])
    assert rc == 0
    canon = _canonical(seeded)
    assert canon["title"] == "Ação de teste"
    assert canon["source_urls"] == ["https://repo.example/record/1"]
    assert "https://partner.example/cases/1" in canon["urls"]


def test_reextract_dry_run_writes_nothing(seeded, monkeypatch, capsys):
    monkeypatch.setattr(reextract, "app", seeded)
    reextract.main(["--dry-run"])
    assert "would change" in capsys.readouterr().out
    assert _canonical(seeded)["title"] == "stale"


def test_reextract_unknown_project_is_usage_error(seeded, monkeypatch):
    monkeypatch.setattr(reextract, "app", seeded)
    assert reextract.main(["--project", "nope"]) == reextract.EXIT_USAGE
