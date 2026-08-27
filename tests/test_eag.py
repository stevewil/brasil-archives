"""Tests for EAG 2012 output.

Covers the standalone ``/archives/<slug>/eag.xml`` endpoint and structural
conformance to the EAG 2012 schema (namespace, root, the schema-mandatory
elements, element order, bilingual name mapping). Full XSD validation is
not run here (no lxml/xmlschema dependency); the checks assert the shape
that ``eag_2012.xsd`` requires.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest
from sqlalchemy import select

from app.extensions import db as _db
from app.models import Archive, InstitutionalType, UpgradeProject
from app.oai.eag import archive_to_eag
from scripts import load_vocabularies

EAG_NS = "http://www.archivesportaleurope.net/Portal/profiles/eag_2012/"
XML_NS = "http://www.w3.org/XML/1998/namespace"
E = {"e": EAG_NS}


def _tag(name: str) -> str:
    return f"{{{EAG_NS}}}{name}"


@pytest.fixture
def eag_app(app):
    with app.app_context():
        load_vocabularies.load_all()
        fed = _db.session.scalar(
            select(InstitutionalType).where(InstitutionalType.slug == "federal-university")
        )
        court = _db.session.scalar(
            select(InstitutionalType).where(InstitutionalType.slug == "state-court")
        )
        _db.session.add_all([
            Archive(
                slug="rn-labim", name="LABIM/UFRN", name_pt="LABIM/UFRN (PT)",
                institutional_type_id=fed.id, home_state_code="RN", home_city="Natal",
                canonical_url="https://labim.example", contact_email="labim@example",
                description_en="Judicial records of the 1st Registry.",
                description_pt="Registros judiciais do 1º Cartório.",
                stated_scope="Criminal and probate proceedings 1850-1930.",
                no_digital_content=False, survey_source="test",
            ),
            Archive(
                slug="ba-apeb", name="APEB", institutional_type_id=court.id,
                home_state_code="BA", canonical_url="https://apeb.example",
                no_digital_content=False, survey_source="test",
            ),
            Archive(
                slug="pb-secret", name="Fatal Flaw Co", institutional_type_id=fed.id,
                home_state_code="PB", canonical_url="https://secret.example",
                caveat_emptor=True, no_digital_content=False, survey_source="test",
            ),
        ])
        _db.session.commit()
        labim = _db.session.scalar(select(Archive).where(Archive.slug == "rn-labim"))
        _db.session.add(UpgradeProject(
            slug="mipibu", name="Mipibu", source_archive_id=labim.id,
            scope_description_en="x", primary_url="https://mipibu.from-bottom-to.top",
            delivery_status="stable",
        ))
        _db.session.commit()
    return app


# --------------------------------------------------------------------------- #
# Standalone endpoint

def test_eag_endpoint_serves_xml(eag_app, client):
    resp = client.get("/archives/rn-labim/eag.xml")
    assert resp.status_code == 200
    assert resp.mimetype == "text/xml"
    root = ET.fromstring(resp.data)
    assert root.tag == _tag("eag")
    assert root.get("audience") == "external"


def test_eag_endpoint_unknown_slug_404(eag_app, client):
    assert client.get("/archives/does-not-exist/eag.xml").status_code == 404


def test_eag_endpoint_caveat_emptor_404(eag_app, client):
    assert client.get("/archives/pb-secret/eag.xml").status_code == 404


# --------------------------------------------------------------------------- #
# Structure / schema shape

def test_eag_control_block(eag_app, client):
    root = ET.fromstring(client.get("/archives/rn-labim/eag.xml").data)
    control = root.find("e:control", E)
    assert control is not None
    assert control.findtext("e:recordId", namespaces=E).startswith("BR-")
    assert control.findtext("e:maintenanceStatus", namespaces=E) == "derived"
    assert control.find("e:maintenanceAgency/e:agencyName", E) is not None
    event = control.find("e:maintenanceHistory/e:maintenanceEvent", E)
    assert event.findtext("e:eventType", namespaces=E) == "derived"
    assert event.findtext("e:agentType", namespaces=E) == "machine"
    # full OAI identifier preserved in the unrestricted otherRecordId
    assert control.findtext("e:otherRecordId", namespaces=E) == (
        "oai:brasil-archives.from-bottom-to.top:archive:rn-labim"
    )


def test_eag_identity_maps_names(eag_app, client):
    root = ET.fromstring(client.get("/archives/rn-labim/eag.xml").data)
    identity = root.find("e:archguide/e:identity", E)
    assert identity.findtext("e:autform", namespaces=E) == "LABIM/UFRN (PT)"
    assert identity.findtext("e:parform", namespaces=E) == "LABIM/UFRN"
    assert identity.find("e:repositorid", E).get("countrycode") == "BR"
    assert identity.findtext("e:repositoryType", namespaces=E) == (
        "University and research archives"
    )


def test_eag_repository_has_mandatory_elements_in_order(eag_app, client):
    root = ET.fromstring(client.get("/archives/rn-labim/eag.xml").data)
    repo = root.find("e:archguide/e:desc/e:repositories/e:repository", E)
    children = [c.tag for c in repo]
    for required in ("geogarea", "location", "timetable", "access", "accessibility"):
        assert _tag(required) in children, f"missing <{required}>"
    # schema sequence: geogarea < location < ... < timetable < access < accessibility
    order = [children.index(_tag(t)) for t in
             ("geogarea", "location", "timetable", "access", "accessibility")]
    assert order == sorted(order)

    loc = repo.find("e:location", E)
    assert loc.get("localType") == "visitors address"
    assert loc.find("e:country", E) is not None
    assert loc.find("e:municipalityPostalcode", E) is not None
    assert repo.find("e:access", E).get("question") in {"yes", "no"}
    assert repo.find("e:accessibility", E).get("question") in {"yes", "no"}


def test_eag_geogarea_is_south_america(eag_app, client):
    root = ET.fromstring(client.get("/archives/rn-labim/eag.xml").data)
    repo = root.find("e:archguide/e:desc/e:repositories/e:repository", E)
    assert repo.findtext("e:geogarea", namespaces=E) == "South America"


def test_eag_contact_email_present_when_known(eag_app, client):
    root = ET.fromstring(client.get("/archives/rn-labim/eag.xml").data)
    repo = root.find("e:archguide/e:desc/e:repositories/e:repository", E)
    email = repo.find("e:email", E)
    assert email is not None
    assert email.get("href") == "mailto:labim@example"
    assert repo.find("e:webpage", E).get("href") == "https://labim.example"


def test_eag_email_absent_when_unknown(eag_app, client):
    root = ET.fromstring(client.get("/archives/ba-apeb/eag.xml").data)
    repo = root.find("e:archguide/e:desc/e:repositories/e:repository", E)
    assert repo.find("e:email", E) is None
    assert repo.find("e:webpage", E) is not None  # canonical_url always present


def test_eag_holdings_carries_description(eag_app, client):
    root = ET.fromstring(client.get("/archives/rn-labim/eag.xml").data)
    p = root.find(
        "e:archguide/e:desc/e:repositories/e:repository/e:holdings/e:descriptiveNote/e:p",
        E,
    )
    assert p is not None
    assert "Judicial records" in p.text
    assert "1850-1930" in p.text  # stated_scope folded in


def test_eag_relations_link_to_upgrade_project(eag_app, client):
    root = ET.fromstring(client.get("/archives/rn-labim/eag.xml").data)
    rel = root.find("e:relations/e:resourceRelation", E)
    assert rel is not None
    assert rel.get("resourceRelationType") == "other"
    assert rel.get("href") == "https://mipibu.from-bottom-to.top"


def test_eag_no_relations_block_without_upgrade_projects(eag_app, client):
    root = ET.fromstring(client.get("/archives/ba-apeb/eag.xml").data)
    assert root.find("e:relations", E) is None


def test_eag_embedded_in_oai_matches_standalone(eag_app, client):
    standalone = client.get("/archives/rn-labim/eag.xml").data
    oai = client.get(
        "/oai?verb=GetRecord&metadataPrefix=eag"
        "&identifier=oai:brasil-archives.from-bottom-to.top:archive:rn-labim"
    ).data
    oai_root = ET.fromstring(oai)
    embedded = oai_root.find(
        ".//{http://www.openarchives.org/OAI/2.0/}metadata/"
        "{http://www.archivesportaleurope.net/Portal/profiles/eag_2012/}eag"
    )
    assert embedded is not None
    # Same identity content regardless of serialization path.
    s_root = ET.fromstring(standalone)
    assert (
        embedded.find("e:archguide/e:identity/e:autform", E).text
        == s_root.find("e:archguide/e:identity/e:autform", E).text
    )


def test_archive_to_eag_is_wellformed_for_minimal_row(eag_app):
    """A row with only the NOT NULL columns still produces valid EAG."""
    with eag_app.app_context():
        it = _db.session.scalar(select(InstitutionalType))
        bare = Archive(
            slug="min", name="Minimal", institutional_type_id=it.id,
            canonical_url="https://min.example", survey_source="t",
        )
        _db.session.add(bare)
        _db.session.commit()
        el = archive_to_eag(_db.session.scalar(select(Archive).where(Archive.slug == "min")))
        xml = ET.tostring(el, encoding="unicode")
        reparsed = ET.fromstring(xml)
        assert reparsed.tag == _tag("eag")
        repo = reparsed.find("e:archguide/e:desc/e:repositories/e:repository", E)
        # municipalityPostalcode is schema-mandatory even with no city/state
        assert repo.find("e:location/e:municipalityPostalcode", E) is not None
