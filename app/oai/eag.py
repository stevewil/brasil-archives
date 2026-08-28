"""EAG 2012 (Encoded Archival Guide) serialization for ``Archive`` rows.

EAG 2012 is the ISDIAH-aligned XML schema for describing institutions with
archival holdings — the institution-level companion to EAD. Namespace
``http://www.archivesportaleurope.net/Portal/profiles/eag_2012/``,
schema v0.6 (2020-10-19), maintained by the Archives Portal Europe
Foundation Working Group on Standards.

The same ``<eag>`` element is used two ways:
  * embedded in an OAI ``<metadata>`` element (metadataPrefix ``eag``)
  * served standalone at ``/archives/<slug>/eag.xml``

Element order and the handful of schema-mandatory elements
(``geogarea`` / ``location`` / ``timetable`` / ``access`` /
``accessibility``) follow ``eag_2012.xsd``. See
``docs/oai-pmh-provider.md`` §"EAG mapping" for the field decisions,
including why a few elements carry conservative placeholder values.
"""
from __future__ import annotations

from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from sqlalchemy import select

from ..extensions import db
from ..models import Archive, UpgradeProject
from .constants import EAG_NS, EAG_SCHEMA_LOCATION, OAI_XSI, XML_NS
from .identifiers import make_archive_id
from .queries import archive_datestamp

_GEOGAREA = "South America"
_LANG_PT = "por"  # ISO 639-2/B
_LANG_EN = "eng"

# brasil-archives institutional-type slug -> EAG repositoryType enumeration.
# Keys are the real slugs from configs/vocabularies/institutional_types.yaml
# (all 11 covered). Slugs with no natural EAG bucket map to "Other".
_REPOSITORY_TYPE = {
    "national": "National archives",
    "federal-university": "University and research archives",
    "state-university": "University and research archives",
    "research-project": "University and research archives",
    "state-archive": "Regional archives",
    "municipal": "Municipal archives",
    "state-court": "Specialised government archives",
    "diocesan": "Church and religious archives",
    "individual": "Private persons and family archives",
    "third-party-hosted": "Other",
    "special-thematic": "Other",
}


def _e(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    el = ET.SubElement(parent, f"{{{EAG_NS}}}{tag}", {k: v for k, v in attrs.items() if v})
    if text is not None:
        el.text = text
    return el


def _lang(el: ET.Element, code: str) -> ET.Element:
    el.set(f"{{{XML_NS}}}lang", code)
    return el


def _note(parent: ET.Element, tag: str, text: str, lang: str) -> None:
    """``<tag><descriptiveNote><p>text</p></descriptiveNote></tag>``."""
    holder = _e(parent, tag)
    dn = _e(holder, "descriptiveNote")
    _lang(_e(dn, "p", text), lang)


def _country_name(code: str | None) -> str:
    return {"BR": "Brazil"}.get((code or "").upper(), code or "Brazil")


def archive_to_eag(archive: Archive) -> ET.Element:
    """Build a complete, schema-ordered ``<eag>`` element for one archive."""
    ET.register_namespace("", EAG_NS)
    ET.register_namespace("xsi", OAI_XSI)

    name_pt = archive.name_pt or archive.name
    name_en = archive.name
    now = datetime.now(timezone.utc)

    eag = ET.Element(
        f"{{{EAG_NS}}}eag",
        {
            "audience": "external",
            f"{{{OAI_XSI}}}schemaLocation": EAG_SCHEMA_LOCATION,
        },
    )

    # ---- control ----------------------------------------------------------
    control = _e(eag, "control")
    _lang(control, _LANG_EN)
    # recordId is pattern-constrained (country code + short token); the full
    # OAI identifier goes in otherRecordId, which is unrestricted.
    _e(control, "recordId", f"BR-{archive.id}")
    _e(control, "otherRecordId", make_archive_id(archive.slug))

    agency = _e(control, "maintenanceAgency")
    _e(agency, "agencyCode", "BR-brasil-archives")
    _lang(_e(agency, "agencyName", "brasil-archives"), _LANG_EN)

    _e(control, "maintenanceStatus", "derived")

    history = _e(control, "maintenanceHistory")
    event = _e(history, "maintenanceEvent")
    _e(event, "agent", "brasil-archives OAI/EAG provider")
    _e(event, "agentType", "machine")
    _e(
        event,
        "eventDateTime",
        archive_datestamp(archive),
        standardDateTime=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    _e(event, "eventType", "derived")

    for abbr, cite in (
        ("EAG", "EAG (Encoded Archival Guide) 2012"),
        ("ISDIAH",
         "International Standard for Describing Institutions with Archival Holdings"),
    ):
        conv = _e(control, "conventionDeclaration")
        _e(conv, "abbreviation", abbr)
        _e(conv, "citation", cite)

    # ---- archguide / identity ------------------------------------------
    archguide = _e(eag, "archguide")
    identity = _e(archguide, "identity")
    _e(
        identity,
        "repositorid",
        countrycode=(archive.home_country_code or "BR").upper(),
        repositorycode=f"BR-{archive.slug}",
    )
    _lang(_e(identity, "autform", name_pt), _LANG_PT)
    if name_en and name_en != name_pt:
        _lang(_e(identity, "parform", name_en), _LANG_EN)
    itype = archive.institutional_type
    repo_type = _REPOSITORY_TYPE.get(itype.slug) if itype is not None else None
    if repo_type:
        _e(identity, "repositoryType", repo_type)

    # ---- archguide / desc ---------------------------------------------
    desc = _e(archguide, "desc")
    repository = _e(_e(desc, "repositories"), "repository")
    _lang(_e(repository, "repositoryName", name_pt), _LANG_PT)
    _e(repository, "geogarea", _GEOGAREA)

    location = _e(repository, "location", localType="visitors address")
    _lang(_e(location, "country", _country_name(archive.home_country_code)), _LANG_EN)
    municipality = ", ".join(
        p for p in (archive.home_city, archive.home_state_code) if p
    ) or "—"
    _e(location, "municipalityPostalcode", municipality)

    if archive.contact_email:
        _e(
            repository,
            "email",
            archive.contact_email,
            href=f"mailto:{archive.contact_email}",
        )
    _e(repository, "webpage", archive.canonical_url, href=archive.canonical_url)
    if archive.catalog_url and archive.catalog_url != archive.canonical_url:
        _e(repository, "webpage", archive.catalog_url, href=archive.catalog_url)

    # holdings — free-text description of the institution and its scope.
    holdings_en = " ".join(
        t.strip() for t in (archive.description_en, archive.stated_scope)
        if t and t.strip()
    )
    if holdings_en:
        _note(repository, "holdings", holdings_en, _LANG_EN)

    # timetable / access / accessibility are schema-mandatory but the
    # catalog does not hold this data; emit honest placeholders.
    timetable = _e(repository, "timetable")
    _lang(
        _e(timetable, "opening",
           "Consult the institution's own website for opening hours."),
        _LANG_EN,
    )
    access = _e(repository, "access", question="yes")
    _lang(
        _e(access, "restaccess",
           "Access conditions are set by the institution; consult it directly."),
        _LANG_EN,
    )
    accessibility = _e(repository, "accessibility", question="no")
    _lang(accessibility, _LANG_EN)
    accessibility.text = "Not recorded in the brasil-archives catalog."

    # descriptiveNote — repository-level PT prose, last in the sequence.
    if archive.description_pt and archive.description_pt.strip():
        dn = _e(repository, "descriptiveNote")
        _lang(_e(dn, "p", archive.description_pt.strip()), _LANG_PT)

    # ---- relations ---------------------------------------------------
    upgrade_urls = [
        url
        for url in db.session.scalars(
            select(UpgradeProject.primary_url).where(
                UpgradeProject.source_archive_id == archive.id
            )
        )
        if url
    ]
    if upgrade_urls:
        relations = _e(eag, "relations")
        for url in upgrade_urls:
            rel = _e(relations, "resourceRelation", resourceRelationType="other", href=url)
            _lang(_e(rel, "relationEntry", "Derived corpus explorer"), _LANG_EN)

    return eag
