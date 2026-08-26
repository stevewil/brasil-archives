"""Tests for the /harvest read-only blueprint."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models import (
    AggregatedRecord,
    Archive,
    HarvestError,
    HarvestRun,
    InstitutionalType,
    UpgradeProject,
)


# --------------------------------------------------------------------------- #
# Fixtures


@pytest.fixture
def archive(app):
    it = InstitutionalType(
        slug="university", label_en="University",
        label_pt="Universidade", sort_order=1,
    )
    db.session.add(it)
    db.session.commit()
    a = Archive(
        slug="labim-ufrn",
        name="LABIM/UFRN",
        canonical_url="https://labim.ufrn.br",
        institutional_type_id=it.id,
        home_state_code="RN",
    )
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def project(app, archive):
    p = UpgradeProject(
        slug="mipibu",
        name="Mipibu",
        source_archive_id=archive.id,
        scope_description_en="Judicial records 1800-1900.",
        primary_url="https://mipibu.example",
        delivery_status="beta",
        federation_contract_version="v1",
        oai_pmh_base_url="https://mipibu.example/oai",
        supported_metadata_formats="oai_dc,oai_ead",
    )
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture
def sample_run(app, project):
    now = datetime.now(timezone.utc)
    run = HarvestRun(
        upgrade_project_id=project.id,
        metadata_prefix="oai_dc",
        started_at=now - timedelta(seconds=13),
        finished_at=now,
        status="ok",
        records_seen=2,
        records_upserted=2,
        records_unchanged=0,
        error_count=1,
        source="oai_pmh",
    )
    db.session.add(run)
    db.session.commit()

    rec1 = AggregatedRecord(
        upgrade_project_id=project.id,
        oai_identifier="oai:x:1",
        metadata_prefix="oai_dc",
        datestamp="2026-01-01",
        set_specs_json=json.dumps(["mipibu:cases", "mipibu:cases:x:1870s"]),
        raw_xml="<record><header><identifier>oai:x:1</identifier></header></record>",
        raw_xml_sha256="a" * 64,
        extracted_json=json.dumps({
            "canonical": {
                "title": "Sumário Crime 001",
                "year_start": 1872, "year_end": 1872,
                "urls": ["https://example.org/dl/1.pdf"],
                "identifiers": ["oai:x:1"],
            },
            "raw": {"dc:title": ["Sumário Crime 001"]},
        }),
        harvest_run_id=run.id,
        first_seen_at=now,
        last_seen_at=now,
    )
    rec2 = AggregatedRecord(
        upgrade_project_id=project.id,
        oai_identifier="oai:x:2",
        metadata_prefix="oai_dc",
        datestamp="2026-01-02",
        set_specs_json=json.dumps(["mipibu:cases"]),
        raw_xml="<record><header><identifier>oai:x:2</identifier></header></record>",
        raw_xml_sha256="b" * 64,
        extracted_json=json.dumps({
            "canonical": {"title": "Autoamento 002", "year_start": None,
                          "year_end": None, "urls": [], "identifiers": []},
            "raw": {},
        }),
        harvest_run_id=run.id,
        first_seen_at=now,
        last_seen_at=now,
    )
    err = HarvestError(
        harvest_run_id=run.id,
        phase="extract",
        oai_identifier="oai:x:99",
        message="oops",
        xml_excerpt="<record/>",
    )
    db.session.add_all([rec1, rec2, err])
    db.session.commit()
    return run


# --------------------------------------------------------------------------- #
# Tests


def test_index_shows_runs_and_rollups(client, sample_run):
    resp = client.get("/harvest/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Harvest runs" in body
    # Rollup row
    assert "mipibu" in body
    assert "oai_dc" in body
    # Run row link
    assert f"/harvest/runs/{sample_run.id}" in body
    assert "status--ok" in body


def test_index_when_empty(client, project):
    resp = client.get("/harvest/")
    assert resp.status_code == 200
    assert "No harvest runs recorded yet" in resp.get_data(as_text=True)


def test_run_detail_lists_records_and_errors(client, sample_run):
    resp = client.get(f"/harvest/runs/{sample_run.id}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "oai:x:1" in body
    assert "oai:x:2" in body
    assert "Sumário Crime 001" in body
    # Error row rendered
    assert "oai:x:99" in body
    assert "oops" in body
    # Pagination footer present but no next
    assert "page 1" in body


def test_run_detail_404_for_missing(client, project):
    resp = client.get("/harvest/runs/99999")
    assert resp.status_code == 404


def test_record_detail_renders_canonical_and_raw(client, sample_run):
    rec = db.session.query(AggregatedRecord).filter_by(
        oai_identifier="oai:x:1"
    ).one()
    resp = client.get(f"/harvest/records/{rec.id}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Sumário Crime 001" in body
    assert "mipibu:cases:x:1870s" in body  # setSpecs
    assert "https://example.org/dl/1.pdf" in body
    # Raw XML block present
    assert "&lt;record&gt;" in body or "<record>" in body


def test_record_detail_404_for_missing(client, project):
    resp = client.get("/harvest/records/99999")
    assert resp.status_code == 404


def test_index_pagination_clamps_page_size(client, sample_run):
    # page_size=9999 gets clamped to _PAGE_SIZE_MAX (200); shouldn't 500.
    resp = client.get("/harvest/?page_size=9999")
    assert resp.status_code == 200


def test_navigation_link_present(client, project):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "/harvest" in resp.get_data(as_text=True)
