"""Tests for the OAI-PMH provider blueprint (``/oai``).

Covers each verb's happy path, every OAI error code, resumption-token
round-tripping, XML well-formedness/namespaces, and the oai_dc field
mapping. EAG-format specifics live in ``tests/test_eag.py``.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest
from sqlalchemy import select

from app.extensions import db as _db
from app.services.sources import drop_source_views
from app.models import Archive, InstitutionalType, RecordType, UpgradeProject
from scripts import load_vocabularies

OAI_NS = "http://www.openarchives.org/OAI/2.0/"
DC_NS = "http://purl.org/dc/elements/1.1/"
OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"
XML_NS = "http://www.w3.org/XML/1998/namespace"
Q = {"oai": OAI_NS, "dc": DC_NS, "oai_dc": OAI_DC_NS}

REPO_ID = "brasil-archives.from-bottom-to.top"


def _oid(slug: str) -> str:
    return f"oai:{REPO_ID}:archive:{slug}"


@pytest.fixture
def oai_app(app):
    """App with a small page size + a spread of archives across states/types."""
    app.config["OAI_PAGE_SIZE"] = 2
    with app.app_context():
        load_vocabularies.load_all()
        fed = _db.session.scalar(
            select(InstitutionalType).where(InstitutionalType.slug == "federal-university")
        )
        court = _db.session.scalar(
            select(InstitutionalType).where(InstitutionalType.slug == "state-court")
        )
        rows = [
            Archive(
                slug="rn-labim", name="LABIM/UFRN", name_pt="LABIM/UFRN (PT)",
                institutional_type_id=fed.id, home_state_code="RN", home_city="Natal",
                canonical_url="https://labim.example", catalog_url="https://labim.example/cat",
                contact_email="labim@example", description_en="Judicial records.",
                description_pt="Registros judiciais.", wikidata_qid="Q123",
                no_digital_content=False, survey_source="test",
            ),
            Archive(
                slug="pe-apeje", name="APEJE", institutional_type_id=fed.id,
                home_state_code="PE", canonical_url="https://apeje.example",
                no_digital_content=False, survey_source="test",
            ),
            Archive(
                slug="ba-apeb", name="APEB", institutional_type_id=court.id,
                home_state_code="BA", canonical_url="https://apeb.example",
                no_digital_content=True, survey_source="test",
            ),
            Archive(
                slug="rn-idema", name="IDEMA", institutional_type_id=court.id,
                home_state_code="RN", canonical_url="https://idema.example",
                no_digital_content=False, survey_source="test",
            ),
            Archive(
                slug="pb-secret", name="Fatal Flaw Co", institutional_type_id=fed.id,
                home_state_code="PB", canonical_url="https://secret.example",
                no_digital_content=False, survey_source="test",
                caveat_emptor=True,
            ),
        ]
        _db.session.add_all(rows)
        _db.session.commit()
        labim = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim"))
        labim.record_types.append(_db.session.scalars(select(RecordType)).first())
        _db.session.add(
            UpgradeProject(
                slug="mipibu", name="Mipibu", source_archive_id=labim.id,
                scope_description_en="Judicial 1800-1900.",
                primary_url="https://mipibu.from-bottom-to.top",
                delivery_status="stable",
            )
        )
        _db.session.commit()
    return app


# 4 public archives (pb-secret is caveat_emptor → excluded everywhere).
PUBLIC_SLUGS = {"rn-labim", "pe-apeje", "ba-apeb", "rn-idema"}


def get_xml(client, query: str) -> ET.Element:
    resp = client.get("/oai" + query)
    assert resp.status_code == 200
    assert resp.mimetype == "text/xml"
    root = ET.fromstring(resp.data)  # raises on malformed XML
    assert root.tag == f"{{{OAI_NS}}}OAI-PMH"
    assert root.find("oai:responseDate", Q) is not None
    assert root.find("oai:request", Q) is not None
    return root


def error_code(client, query: str) -> str:
    root = get_xml(client, query)
    err = root.find("oai:error", Q)
    assert err is not None, ET.tostring(root, encoding="unicode")
    return err.get("code")


# --------------------------------------------------------------------------- #
# Identify

def test_identify(oai_app, client):
    root = get_xml(client, "?verb=Identify")
    ident = root.find("oai:Identify", Q)
    assert ident is not None
    assert ident.findtext("oai:protocolVersion", namespaces=Q) == "2.0"
    assert ident.findtext("oai:deletedRecord", namespaces=Q) == "no"
    assert ident.findtext("oai:granularity", namespaces=Q) == "YYYY-MM-DD"
    assert ident.findtext("oai:repositoryName", namespaces=Q)
    assert ident.findtext("oai:baseURL", namespaces=Q).endswith("/oai")
    assert ident.findtext("oai:earliestDatestamp", namespaces=Q)
    scheme = ident.find(".//{http://www.openarchives.org/OAI/2.0/oai-identifier}scheme")
    assert scheme is not None and scheme.text == "oai"


def test_identify_sample_identifier_resolves(oai_app, client):
    """The Identify sampleIdentifier must be a real record — a harvester
    (and the OAI validator) calls GetRecord on it."""
    root = get_xml(client, "?verb=Identify")
    sample = root.find(
        ".//{http://www.openarchives.org/OAI/2.0/oai-identifier}sampleIdentifier"
    ).text
    got = get_xml(client, f"?verb=GetRecord&identifier={sample}&metadataPrefix=oai_dc")
    assert got.find("oai:error", Q) is None
    assert got.findtext("oai:GetRecord/oai:record/oai:header/oai:identifier", namespaces=Q) == sample


# --------------------------------------------------------------------------- #
# ListMetadataFormats

def test_list_metadata_formats(oai_app, client):
    root = get_xml(client, "?verb=ListMetadataFormats")
    prefixes = {
        f.findtext("oai:metadataPrefix", namespaces=Q)
        for f in root.findall("oai:ListMetadataFormats/oai:metadataFormat", Q)
    }
    assert prefixes == {"oai_dc", "eag"}


def test_list_metadata_formats_by_identifier(oai_app, client):
    root = get_xml(
        client, f"?verb=ListMetadataFormats&identifier={_oid('rn-labim')}"
    )
    assert root.find("oai:ListMetadataFormats", Q) is not None


def test_list_metadata_formats_unknown_identifier(oai_app, client):
    assert (
        error_code(client, f"?verb=ListMetadataFormats&identifier={_oid('nope')}")
        == "idDoesNotExist"
    )


# --------------------------------------------------------------------------- #
# ListSets

def test_list_sets(oai_app, client):
    root = get_xml(client, "?verb=ListSets")
    specs = {s.findtext("oai:setSpec", namespaces=Q)
             for s in root.findall("oai:ListSets/oai:set", Q)}
    assert "state:RN" in specs
    assert "state:BA" in specs
    assert "itype:federal-university" in specs
    assert "content:digital" in specs
    assert "content:no-digital" in specs
    # bilingual setName
    first = root.find("oai:ListSets/oai:set", Q)
    langs = {n.get(f"{{{XML_NS}}}lang") for n in first.findall("oai:setName", Q)}
    assert langs == {"pt", "en"}


def test_list_sets_rejects_resumption_token(oai_app, client):
    assert error_code(client, "?verb=ListSets&resumptionToken=x") == "badResumptionToken"


# --------------------------------------------------------------------------- #
# ListIdentifiers / ListRecords happy paths

def test_list_identifiers(oai_app, client):
    ids = _harvest_identifiers(client, "oai_dc")
    assert ids == {_oid(s) for s in PUBLIC_SLUGS}


def test_list_records_oai_dc(oai_app, client):
    root = get_xml(client, "?verb=ListRecords&metadataPrefix=oai_dc")
    recs = root.findall("oai:ListRecords/oai:record", Q)
    assert recs
    for rec in recs:
        assert rec.find("oai:header/oai:identifier", Q) is not None
        assert rec.find("oai:metadata/oai_dc:dc", Q) is not None


def test_list_records_eag(oai_app, client):
    root = get_xml(client, "?verb=ListRecords&metadataPrefix=eag")
    md = root.find("oai:ListRecords/oai:record/oai:metadata", Q)
    assert md is not None
    assert md[0].tag == (
        "{http://www.archivesportaleurope.net/Portal/profiles/eag_2012/}eag"
    )


def test_headers_carry_setspecs(oai_app, client):
    root = get_xml(client, "?verb=ListRecords&metadataPrefix=oai_dc&set=state:RN")
    for rec in root.findall("oai:ListRecords/oai:record", Q):
        specs = {s.text for s in rec.findall("oai:header/oai:setSpec", Q)}
        assert "state:RN" in specs
        assert any(s.startswith("itype:") for s in specs)
        assert any(s.startswith("content:") for s in specs)


def test_set_filter_by_state(oai_app, client):
    root = get_xml(client, "?verb=ListIdentifiers&metadataPrefix=oai_dc&set=state:RN")
    ids = {h.findtext("oai:identifier", namespaces=Q)
           for h in root.findall("oai:ListIdentifiers/oai:header", Q)}
    # RN has rn-labim + rn-idema, and page size is 2 → exactly one page, no token
    assert ids == {_oid("rn-labim"), _oid("rn-idema")}


def test_set_filter_content_no_digital(oai_app, client):
    root = get_xml(
        client, "?verb=ListIdentifiers&metadataPrefix=oai_dc&set=content:no-digital"
    )
    ids = {h.findtext("oai:identifier", namespaces=Q)
           for h in root.findall("oai:ListIdentifiers/oai:header", Q)}
    assert ids == {_oid("ba-apeb")}


# --------------------------------------------------------------------------- #
# GetRecord

def test_get_record_oai_dc(oai_app, client):
    root = get_xml(
        client, f"?verb=GetRecord&metadataPrefix=oai_dc&identifier={_oid('rn-labim')}"
    )
    rec = root.find("oai:GetRecord/oai:record", Q)
    assert rec.findtext("oai:header/oai:identifier", namespaces=Q) == _oid("rn-labim")
    assert rec.find("oai:metadata/oai_dc:dc", Q) is not None


def test_get_record_eag(oai_app, client):
    root = get_xml(
        client, f"?verb=GetRecord&metadataPrefix=eag&identifier={_oid('rn-labim')}"
    )
    assert root.find("oai:GetRecord/oai:record/oai:metadata", Q) is not None


def test_get_record_unknown_id(oai_app, client):
    assert (
        error_code(client, f"?verb=GetRecord&metadataPrefix=oai_dc&identifier={_oid('nope')}")
        == "idDoesNotExist"
    )


def test_get_record_foreign_namespace_id(oai_app, client):
    assert (
        error_code(client, "?verb=GetRecord&metadataPrefix=oai_dc&identifier=oai:elsewhere.org:archive:x")
        == "idDoesNotExist"
    )


def test_get_record_caveat_emptor_hidden(oai_app, client):
    """A fatal-flaw archive is not disseminated even by direct id."""
    assert (
        error_code(client, f"?verb=GetRecord&metadataPrefix=oai_dc&identifier={_oid('pb-secret')}")
        == "idDoesNotExist"
    )


# --------------------------------------------------------------------------- #
# Errors

def test_bad_verb_missing(oai_app, client):
    assert error_code(client, "") == "badVerb"


def test_bad_verb_unknown(oai_app, client):
    assert error_code(client, "?verb=Frobnicate") == "badVerb"


def test_bad_argument_missing_required(oai_app, client):
    assert error_code(client, "?verb=ListRecords") == "badArgument"


def test_bad_argument_unknown_arg(oai_app, client):
    assert error_code(client, "?verb=Identify&foo=bar") == "badArgument"


def test_bad_argument_getrecord_missing_identifier(oai_app, client):
    assert error_code(client, "?verb=GetRecord&metadataPrefix=oai_dc") == "badArgument"


def test_cannot_disseminate_format(oai_app, client):
    assert (
        error_code(client, "?verb=ListRecords&metadataPrefix=marcxml")
        == "cannotDisseminateFormat"
    )


def test_no_records_match(oai_app, client):
    assert (
        error_code(client, "?verb=ListRecords&metadataPrefix=oai_dc&set=state:ZZ")
        == "noRecordsMatch"
    )


def test_bad_resumption_token(oai_app, client):
    assert (
        error_code(client, "?verb=ListRecords&resumptionToken=not-a-real-token")
        == "badResumptionToken"
    )


def test_resumption_token_exclusive_with_other_args(oai_app, client):
    root = get_xml(client, "?verb=ListRecords&metadataPrefix=oai_dc")
    token = root.findtext("oai:ListRecords/oai:resumptionToken", namespaces=Q)
    assert token
    assert (
        error_code(
            client,
            f"?verb=ListRecords&metadataPrefix=oai_dc&resumptionToken={token}",
        )
        == "badArgument"
    )


# --------------------------------------------------------------------------- #
# Resumption-token round-trip

def _harvest_identifiers(client, prefix: str) -> set[str]:
    ids: list[str] = []
    root = get_xml(client, f"?verb=ListIdentifiers&metadataPrefix={prefix}")
    while True:
        for h in root.findall("oai:ListIdentifiers/oai:header", Q):
            ids.append(h.findtext("oai:identifier", namespaces=Q))
        token = root.findtext("oai:ListIdentifiers/oai:resumptionToken", namespaces=Q)
        if not token:
            break
        root = get_xml(client, f"?verb=ListIdentifiers&resumptionToken={token}")
    assert len(ids) == len(set(ids)), "duplicate identifiers across pages"
    return set(ids)


def test_resumption_roundtrip_list_records(oai_app, client):
    ids: list[str] = []
    root = get_xml(client, "?verb=ListRecords&metadataPrefix=oai_dc")
    pages = 0
    while True:
        pages += 1
        for rec in root.findall("oai:ListRecords/oai:record", Q):
            ids.append(rec.findtext("oai:header/oai:identifier", namespaces=Q))
        token = root.findtext("oai:ListRecords/oai:resumptionToken", namespaces=Q)
        if not token:
            break
        root = get_xml(client, f"?verb=ListRecords&resumptionToken={token}")
    assert pages >= 2  # page size 2, 4 public rows
    assert len(ids) == len(set(ids))
    assert set(ids) == {_oid(s) for s in PUBLIC_SLUGS}


def test_resumption_token_reports_complete_list_size(oai_app, client):
    root = get_xml(client, "?verb=ListRecords&metadataPrefix=oai_dc")
    rt = root.find("oai:ListRecords/oai:resumptionToken", Q)
    assert rt.get("completeListSize") == "4"
    assert rt.get("cursor") == "0"


# --------------------------------------------------------------------------- #
# oai_dc mapping

def test_oai_dc_field_mapping(oai_app, client):
    root = get_xml(
        client, f"?verb=GetRecord&metadataPrefix=oai_dc&identifier={_oid('rn-labim')}"
    )
    dc = root.find("oai:GetRecord/oai:record/oai:metadata/oai_dc:dc", Q)
    identifiers = [e.text for e in dc.findall("dc:identifier", Q)]
    assert _oid("rn-labim") in identifiers
    assert "https://labim.example" in identifiers
    assert "https://www.wikidata.org/entity/Q123" in identifiers

    titles = {(e.get(f"{{{XML_NS}}}lang"), e.text) for e in dc.findall("dc:title", Q)}
    assert ("en", "LABIM/UFRN") in titles
    assert ("pt", "LABIM/UFRN (PT)") in titles

    descr = {e.text for e in dc.findall("dc:description", Q)}
    assert "Judicial records." in descr
    assert "Registros judiciais." in descr

    coverage = " ".join(e.text or "" for e in dc.findall("dc:coverage", Q))
    assert "RN" in coverage
    relations = {e.text for e in dc.findall("dc:relation", Q)}
    assert "https://mipibu.from-bottom-to.top" in relations
    assert dc.findtext("dc:rights", namespaces=Q)


# --------------------------------------------------------------------------- #
# Transport

def test_post_is_accepted(oai_app, client):
    resp = client.post("/oai", data={"verb": "Identify"})
    assert resp.status_code == 200
    assert ET.fromstring(resp.data).find("oai:Identify", Q) is not None


def test_provider_is_public_without_admin():
    """The provider is a public catalog surface — not admin-gated."""
    from app import create_app

    public = create_app("testing")
    public.config["ADMIN_UI_ENABLED"] = False
    with public.app_context():
        _db.create_all()
        try:
            resp = public.test_client().get("/oai?verb=Identify")
            assert resp.status_code == 200
        finally:
            _db.session.remove()
            drop_source_views(_db.engine)
            _db.drop_all()
