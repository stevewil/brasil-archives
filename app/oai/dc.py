"""Dublin Core (``oai_dc``) serialization for ``Archive`` rows.

DC 1.1 — 15 elements, all optional and repeatable. brasil-archives
describes institutions (ISDIAH level), so the mapping leans on
``dc:title`` / ``dc:description`` / ``dc:coverage`` / ``dc:subject`` and
uses ``xml:lang`` to carry the PT and EN variants the model holds.

See ``docs/oai-pmh-provider.md`` §"oai_dc mapping".
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

from sqlalchemy import select

from ..extensions import db
from ..models import Archive, UpgradeProject
from .constants import (
    DC_NS,
    METADATA_RIGHTS,
    OAI_DC_NS,
    OAI_DC_SCHEMA_LOCATION,
    OAI_XSI,
    XML_NS,
)
from .identifiers import make_archive_id
from .queries import archive_datestamp


def _dc_root() -> ET.Element:
    ET.register_namespace("oai_dc", OAI_DC_NS)
    ET.register_namespace("dc", DC_NS)
    ET.register_namespace("xsi", OAI_XSI)
    return ET.Element(
        f"{{{OAI_DC_NS}}}dc",
        {f"{{{OAI_XSI}}}schemaLocation": OAI_DC_SCHEMA_LOCATION},
    )


def _add(parent: ET.Element, name: str, value: str | None, lang: str | None = None) -> None:
    if value is None:
        return
    text = str(value).strip()
    if not text:
        return
    el = ET.SubElement(parent, f"{{{DC_NS}}}{name}")
    el.text = text
    if lang:
        el.set(f"{{{XML_NS}}}lang", lang)


def _authority_uris(archive: Archive) -> list[str]:
    uris: list[str] = []
    if archive.wikidata_qid:
        uris.append(f"https://www.wikidata.org/entity/{archive.wikidata_qid}")
    if archive.viaf_id:
        uris.append(f"https://viaf.org/viaf/{archive.viaf_id}")
    if archive.isni_id:
        uris.append(f"https://isni.org/isni/{archive.isni_id}")
    if archive.doi:
        uris.append(f"https://doi.org/{archive.doi}")
    if archive.geonames_primary_id:
        uris.append(f"https://www.geonames.org/{archive.geonames_primary_id}/")
    return uris


def _upgrade_project_urls(archive_id: int) -> list[str]:
    rows = db.session.scalars(
        select(UpgradeProject.primary_url).where(
            UpgradeProject.source_archive_id == archive_id
        )
    )
    return [r for r in rows if r]


def archive_to_dc(archive: Archive) -> ET.Element:
    root = _dc_root()

    # Identifiers: OAI id first (§2.4), then resolvable web identifiers.
    _add(root, "identifier", make_archive_id(archive.slug))
    _add(root, "identifier", archive.canonical_url)
    if archive.catalog_url and archive.catalog_url != archive.canonical_url:
        _add(root, "identifier", archive.catalog_url)
    for uri in _authority_uris(archive):
        _add(root, "identifier", uri)

    # Titles / descriptions — bilingual where present.
    _add(root, "title", archive.name, lang="en")
    if archive.name_pt and archive.name_pt != archive.name:
        _add(root, "title", archive.name_pt, lang="pt")
    _add(root, "description", archive.description_en, lang="en")
    _add(root, "description", archive.description_pt, lang="pt")
    _add(root, "description", archive.stated_scope)

    _add(root, "publisher", archive.name)

    # Type: DCMI "Collection" plus the institutional type from our vocab.
    _add(root, "type", "Collection")
    itype = archive.institutional_type
    if itype is not None:
        _add(root, "type", itype.label_en, lang="en")
        if itype.label_pt and itype.label_pt != itype.label_en:
            _add(root, "type", itype.label_pt, lang="pt")

    # Subjects: record types + themes (both language variants).
    for rt in archive.record_types:
        _add(root, "subject", rt.label_en, lang="en")
        if rt.label_pt and rt.label_pt != rt.label_en:
            _add(root, "subject", rt.label_pt, lang="pt")
    for theme in archive.themes:
        _add(root, "subject", theme.label_en, lang="en")
        if theme.label_pt and theme.label_pt != theme.label_en:
            _add(root, "subject", theme.label_pt, lang="pt")

    # Coverage: spatial then temporal.
    place = ", ".join(
        p for p in (
            archive.home_city,
            archive.home_state_code,
            archive.home_country_code,
        ) if p
    )
    _add(root, "coverage", place or None)
    for period in archive.periods:
        label = period.label_en or period.label_pt
        if period.start_year and period.end_year:
            _add(root, "coverage", f"{label} ({period.start_year}/{period.end_year})")
        else:
            _add(root, "coverage", label)

    # Relations: standards endpoints + derived corpus explorers.
    for rel in (
        archive.oai_pmh_base_url,
        archive.ead_finding_aid_url,
        archive.iiif_manifest_root,
    ):
        _add(root, "relation", rel)
    for url in _upgrade_project_urls(archive.id):
        _add(root, "relation", url)

    _add(root, "source", archive.survey_source)
    _add(root, "language", "pt")
    _add(root, "date", archive_datestamp(archive))
    _add(root, "rights", METADATA_RIGHTS)
    return root
