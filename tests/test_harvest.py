"""Integration tests for the OAI-PMH harvest runner.

We mock the HTTP layer by monkey-patching ``oai_client._fetch`` so the
full harvest pipeline (client → extractors → upsert → error rows)
runs against parsed XML without touching the network.
"""
from __future__ import annotations

from datetime import datetime, timezone
from xml.etree import ElementTree as ET

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
from app.services import harvest, oai_client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
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
def mipibu_project(app, archive):
    project = UpgradeProject(
        slug="mipibu",
        name="Mipibu",
        source_archive_id=archive.id,
        scope_description_en="Judicial records 1800-1900.",
        primary_url="https://mipibu.from-bottom-to.top",
        delivery_status="beta",
        federation_contract_version="v1",
        oai_pmh_base_url="https://example.test/oai",
        supported_metadata_formats="oai_dc,oai_ead",
    )
    db.session.add(project)
    db.session.commit()
    return project


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------
OAI_NS_XMLNS = 'xmlns="http://www.openarchives.org/OAI/2.0/"'
DC_XMLNS = ('xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"')


def _dc_record(ident: str, title: str = "T", date: str = "1872") -> str:
    return f"""
    <record>
      <header>
        <identifier>{ident}</identifier>
        <datestamp>2026-01-01</datestamp>
        <setSpec>mipibu:cases</setSpec>
      </header>
      <metadata>
        <oai_dc:dc {DC_XMLNS}>
          <dc:title>{title}</dc:title>
          <dc:date>{date}</dc:date>
          <dc:identifier>{ident}</dc:identifier>
        </oai_dc:dc>
      </metadata>
    </record>
    """


def _list_records_response(records: list[str], token: str | None = None) -> str:
    body = "".join(records)
    if token is None:
        rt = ""
    else:
        rt = f'<resumptionToken completeListSize="3" cursor="1">{token}</resumptionToken>'
    return f"""<?xml version="1.0"?>
<OAI-PMH {OAI_NS_XMLNS}>
  <responseDate>2026-08-26T00:00:00Z</responseDate>
  <ListRecords>
    {body}
    {rt}
  </ListRecords>
</OAI-PMH>
"""


def _error_response(code: str) -> str:
    return f"""<?xml version="1.0"?>
<OAI-PMH {OAI_NS_XMLNS}>
  <responseDate>2026-08-26T00:00:00Z</responseDate>
  <error code="{code}">boom</error>
</OAI-PMH>
"""


def _fake_fetch_factory(responses):
    """Build a fake `_fetch` that returns pre-canned XML documents.

    `responses` is an iterable of XML strings; each `_fetch` call pops one.
    """
    iterator = iter(responses)

    def fake_fetch(base_url, params):
        try:
            xml = next(iterator)
        except StopIteration as exc:
            raise AssertionError(
                f"unexpected extra fetch: {base_url} {params}"
            ) from exc
        root = ET.fromstring(xml)
        oai_client._raise_for_error(root, url=base_url)
        return root

    return fake_fetch


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_harvest_paginates_and_inserts(app, mipibu_project, monkeypatch):
    page1 = _list_records_response(
        [_dc_record("oai:x:1"), _dc_record("oai:x:2")],
        token="TOK1",
    )
    page2 = _list_records_response(
        [_dc_record("oai:x:3")],
        token=None,
    )
    monkeypatch.setattr(
        oai_client, "_fetch", _fake_fetch_factory([page1, page2])
    )

    summary = harvest.run_harvest("mipibu", "oai_dc")
    assert summary.status == "ok"
    assert summary.records_seen == 3
    assert summary.records_upserted == 3
    assert summary.records_unchanged == 0
    assert summary.error_count == 0

    assert db.session.query(AggregatedRecord).count() == 3
    assert db.session.query(HarvestRun).count() == 1
    run = db.session.query(HarvestRun).one()
    assert run.status == "ok"
    assert run.records_upserted == 3


def test_harvest_second_run_marks_unchanged(app, mipibu_project, monkeypatch):
    page = _list_records_response([_dc_record("oai:x:1")], token=None)

    monkeypatch.setattr(
        oai_client, "_fetch", _fake_fetch_factory([page])
    )
    s1 = harvest.run_harvest("mipibu", "oai_dc")
    assert s1.records_upserted == 1

    # Same identical bytes → sha matches → unchanged.
    monkeypatch.setattr(
        oai_client, "_fetch", _fake_fetch_factory([page])
    )
    s2 = harvest.run_harvest("mipibu", "oai_dc")
    assert s2.records_seen == 1
    assert s2.records_unchanged == 1
    assert s2.records_upserted == 0


def test_harvest_content_change_updates_row(app, mipibu_project, monkeypatch):
    monkeypatch.setattr(
        oai_client, "_fetch", _fake_fetch_factory([
            _list_records_response([_dc_record("oai:x:1", title="Old")]),
        ]),
    )
    harvest.run_harvest("mipibu", "oai_dc")

    monkeypatch.setattr(
        oai_client, "_fetch", _fake_fetch_factory([
            _list_records_response([_dc_record("oai:x:1", title="New")]),
        ]),
    )
    s = harvest.run_harvest("mipibu", "oai_dc")
    assert s.records_upserted == 1
    assert s.records_unchanged == 0
    row = db.session.query(AggregatedRecord).one()
    assert "New" in row.raw_xml
    # first_seen_at preserved across the update
    assert row.first_seen_at <= row.last_seen_at


def test_harvest_dry_run_writes_nothing(app, mipibu_project, monkeypatch):
    monkeypatch.setattr(
        oai_client, "_fetch", _fake_fetch_factory([
            _list_records_response([_dc_record("oai:x:1")]),
        ]),
    )
    s = harvest.run_harvest("mipibu", "oai_dc", dry_run=True)
    assert s.status == "ok"
    assert s.records_seen == 1
    assert s.records_upserted == 1  # dry-run reports the preview count
    assert db.session.query(AggregatedRecord).count() == 0
    assert db.session.query(HarvestRun).count() == 0


def test_harvest_per_record_parse_error_becomes_partial(
    app, mipibu_project, monkeypatch,
):
    # A record with no <header> — parse phase will fail.
    bad_record = """
    <record>
      <metadata>
        <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:title>orphan</dc:title>
        </oai_dc:dc>
      </metadata>
    </record>
    """
    monkeypatch.setattr(
        oai_client, "_fetch", _fake_fetch_factory([
            _list_records_response([bad_record, _dc_record("oai:x:1")]),
        ]),
    )
    s = harvest.run_harvest("mipibu", "oai_dc")
    assert s.status == "partial"
    assert s.records_seen == 2
    assert s.records_upserted == 1
    assert s.error_count == 1
    err_row = db.session.query(HarvestError).one()
    assert err_row.phase == "parse"


def test_harvest_protocol_error_aborts_run(app, mipibu_project, monkeypatch):
    monkeypatch.setattr(
        oai_client, "_fetch", _fake_fetch_factory([
            _error_response("cannotDisseminateFormat"),
        ]),
    )
    s = harvest.run_harvest("mipibu", "oai_dc")
    assert s.status == "failed"
    assert s.records_seen == 0
    assert "cannotDisseminateFormat" in (s.notes or "")


def test_harvest_config_error_when_no_endpoint(app, archive, monkeypatch):
    p = UpgradeProject(
        slug="static-only",
        name="Static",
        source_archive_id=archive.id,
        scope_description_en="X",
        primary_url="https://x.example",
        delivery_status="prototype",
        federation_contract_version="v1",
        supported_metadata_formats="oai_dc",
    )
    db.session.add(p)
    db.session.commit()

    s = harvest.run_harvest("static-only", "oai_dc")
    assert s.status == "failed"
    assert "oai_pmh_base_url" in (s.notes or "")


def test_harvest_rejects_unadvertised_prefix(app, mipibu_project):
    s = harvest.run_harvest("mipibu", "mets")
    assert s.status == "failed"
    assert "mets" in (s.notes or "")


def test_list_harvestable_projects(app, mipibu_project):
    projects = harvest.list_harvestable_projects()
    assert [p.slug for p in projects] == ["mipibu"]
