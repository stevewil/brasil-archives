"""Unit tests for OAI-PMH extractor pipeline."""
from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from app.services.oai_extractors import extract, oai_dc, oai_ead


DC_XML = """
<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
           xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>Sumário Crime</dc:title>
  <dc:title>Alt title</dc:title>
  <dc:date>1872</dc:date>
  <dc:coverage>1870/1875</dc:coverage>
  <dc:language>pt</dc:language>
  <dc:rights>Metadata: CC BY-SA 4.0</dc:rights>
  <dc:identifier>oai:example:case:001</dc:identifier>
  <dc:identifier>https://example.org/cases/001</dc:identifier>
  <dc:relation>https://example.org/downloads/001.pdf</dc:relation>
  <dc:relation>see also X</dc:relation>
  <dc:source>https://repositorio.example/catalog/001</dc:source>
  <dc:source>Fundo X</dc:source>
  <dc:type>Text</dc:type>
  <dc:type>InteractiveResource</dc:type>
  <dc:subject>Ofensas físicas</dc:subject>
  <dc:creator>Autor</dc:creator>
</oai_dc:dc>
"""


def test_dc_canonical_pulls_first_and_ranges():
    el = ET.fromstring(DC_XML)
    out = extract("oai_dc", el)
    can = out["canonical"]
    assert can["title"] == "Sumário Crime"
    assert can["language"] == "pt"
    assert can["year_start"] == 1870
    assert can["year_end"] == 1875
    assert can["identifiers"] == ["oai:example:case:001"]
    assert "https://example.org/cases/001" in can["urls"]
    assert "https://example.org/downloads/001.pdf" in can["urls"]
    # dc:source http values are captured separately; non-URL sources dropped
    assert can["source_urls"] == ["https://repositorio.example/catalog/001"]
    assert can["types"] == ["Text", "InteractiveResource"]


def test_dc_year_falls_back_to_single_year_from_date():
    xml = """
    <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
               xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:title>T</dc:title>
      <dc:date>1899</dc:date>
    </oai_dc:dc>
    """
    out = oai_dc.extract(ET.fromstring(xml))
    assert out["canonical"]["year_start"] == 1899
    assert out["canonical"]["year_end"] == 1899


def test_dc_year_returns_none_when_missing():
    xml = """
    <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
               xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:title>T</dc:title>
    </oai_dc:dc>
    """
    out = oai_dc.extract(ET.fromstring(xml))
    assert out["canonical"]["year_start"] is None
    assert out["canonical"]["year_end"] is None


def test_dc_raw_captures_repeated_elements():
    el = ET.fromstring(DC_XML)
    out = oai_dc.extract(el)
    assert out["raw"]["dc:title"] == ["Sumário Crime", "Alt title"]
    assert len(out["raw"]["dc:identifier"]) == 2


EAD_XML = """
<ead xmlns="urn:isbn:1-931666-22-9">
  <eadheader/>
  <archdesc level="fonds">
    <did>
      <unittitle>São José de Mipibu — Juízo Municipal e de Órfãos</unittitle>
      <unitid>SJM</unitid>
      <unitdate normal="1800/1900">1800/1900</unitdate>
      <repository>LABIM/UFRN</repository>
      <origination>Cartório</origination>
    </did>
    <dsc type="combined">
      <c01 level="series" id="series-x">
        <did>
          <unittitle>Ofensas físicas</unittitle>
          <unitid>physical_assault</unitid>
        </did>
        <c02 level="item" id="case-001">
          <did>
            <unittitle>Case 001</unittitle>
            <unitid>SJM-0001</unitid>
            <unitdate normal="1872">1872</unitdate>
            <physloc>SJM-RN</physloc>
          </did>
          <c03 level="file" id="file-1">
            <did>
              <unitid>1</unitid>
              <unittitle>C07V01-1872.pdf</unittitle>
              <dao href="https://example.org/dl/1.pdf"/>
            </did>
          </c03>
        </c02>
      </c01>
    </dsc>
  </archdesc>
</ead>
"""


def test_ead_top_level_canonical():
    el = ET.fromstring(EAD_XML)
    out = extract("oai_ead", el)
    can = out["canonical"]
    assert can["title"] == "São José de Mipibu — Juízo Municipal e de Órfãos"
    assert can["year_start"] == 1800
    assert can["year_end"] == 1900
    assert can["identifiers"] == ["SJM"]
    assert can["item_count"] == 3  # c01 + c02 + c03


def test_ead_walks_hierarchy_and_captures_daos():
    el = ET.fromstring(EAD_XML)
    out = oai_ead.extract(el)
    items = out["raw"]["items"]
    assert [it["level_tag"] for it in items] == ["c01", "c02", "c03"]
    assert items[1]["year_start"] == 1872
    assert items[2]["dao_urls"] == ["https://example.org/dl/1.pdf"]
    # dao_urls aggregate into canonical.urls
    assert "https://example.org/dl/1.pdf" in out["canonical"]["urls"]


def test_ead_handles_missing_archdesc_gracefully():
    xml = '<ead xmlns="urn:isbn:1-931666-22-9"><eadheader/></ead>'
    out = oai_ead.extract(ET.fromstring(xml))
    assert out["canonical"]["item_count"] == 0
    assert out["canonical"]["title"] is None


def test_extractor_registry_rejects_unknown_prefix():
    el = ET.fromstring("<x/>")
    with pytest.raises(ValueError, match="no extractor registered"):
        extract("mets", el)
