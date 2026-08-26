"""EAD 2002 (oai_ead) extractor.

Mipibu embeds a fonds/case/document hierarchy inside <archdesc>/<dsc>
using <c01> (series), <c02> (case item), <c03> (file). We extract:

  * A top-level canonical view from <archdesc>/<did>.
  * A flat ``items`` list — one entry per <did> found in <archdesc> and
    inside every <cNN>. Each carries level, unitid, unittitle, unitdate,
    normalized year range, and any <dao> URLs.

See ``docs/harvest-design.md`` §Extractor contract.
"""
from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree as ET


EAD_NS = "urn:isbn:1-931666-22-9"
_NORMAL_RANGE_RE = re.compile(r"(\d{4})(?:-\d{2}(?:-\d{2})?)?\s*/\s*(\d{4})")
_NORMAL_SINGLE_RE = re.compile(r"^(\d{4})")


def _ln(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def _find(parent: ET.Element, name: str) -> ET.Element | None:
    return parent.find(f"{{{EAD_NS}}}{name}")


def _findall(parent: ET.Element, name: str) -> list[ET.Element]:
    return parent.findall(f"{{{EAD_NS}}}{name}")


def _text(el: ET.Element | None) -> str | None:
    if el is None:
        return None
    # Include tail-free text from mixed content children.
    parts: list[str] = []
    if el.text:
        parts.append(el.text)
    for child in el:
        if child.text:
            parts.append(child.text)
        if child.tail:
            parts.append(child.tail)
    joined = " ".join(p.strip() for p in parts if p.strip())
    return joined or None


def _parse_normal_dates(normal: str | None) -> tuple[int | None, int | None]:
    if not normal:
        return (None, None)
    m = _NORMAL_RANGE_RE.match(normal)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        return (min(y1, y2), max(y1, y2))
    m = _NORMAL_SINGLE_RE.match(normal)
    if m:
        y = int(m.group(1))
        return (y, y)
    return (None, None)


def _extract_did(did: ET.Element | None) -> dict[str, Any]:
    """Distill an EAD <did> into a flat dict."""
    if did is None:
        return {}
    unitdate_el = _find(did, "unitdate")
    normal = unitdate_el.get("normal") if unitdate_el is not None else None
    year_start, year_end = _parse_normal_dates(normal)

    physdesc_el = _find(did, "physdesc")
    extent = None
    genreform = None
    if physdesc_el is not None:
        extent = _text(_find(physdesc_el, "extent"))
        genreform = _text(_find(physdesc_el, "genreform"))

    daos = [
        (dao.get("href") or "").strip()
        for dao in _findall(did, "dao")
        if dao.get("href")
    ]

    return {
        "unitid": _text(_find(did, "unitid")),
        "unittitle": _text(_find(did, "unittitle")),
        "unitdate": _text(unitdate_el),
        "unitdate_normal": normal,
        "year_start": year_start,
        "year_end": year_end,
        "repository": _text(_find(did, "repository")),
        "origination": _text(_find(did, "origination")),
        "physloc": _text(_find(did, "physloc")),
        "extent": extent,
        "genreform": genreform,
        "dao_urls": daos,
    }


def _walk_c_levels(parent: ET.Element, out: list[dict[str, Any]]) -> None:
    """Recursively collect every <cNN> or <c> descendant."""
    for child in parent:
        local = _ln(child.tag)
        # Match c, c01..c12
        if local == "c" or (local.startswith("c") and local[1:].isdigit()):
            did = _find(child, "did")
            entry = {
                "level_tag": local,
                "level_attr": child.get("level"),
                "id": child.get("id"),
                **_extract_did(did),
            }
            out.append(entry)
            _walk_c_levels(child, out)
        else:
            # Descend into <dsc> and similar non-c wrappers.
            _walk_c_levels(child, out)


def extract(ead_element: ET.Element) -> dict[str, Any]:
    """Extract canonical + raw view of an <ead> element."""
    archdesc = _find(ead_element, "archdesc")
    top_did = _find(archdesc, "did") if archdesc is not None else None
    top = _extract_did(top_did)

    items: list[dict[str, Any]] = []
    if archdesc is not None:
        _walk_c_levels(archdesc, items)

    # Collect all URLs from every level for convenience.
    all_urls: list[str] = list(top.get("dao_urls") or [])
    for it in items:
        all_urls.extend(it.get("dao_urls") or [])

    canonical: dict[str, Any] = {
        "title": top.get("unittitle"),
        "date": top.get("unitdate"),
        "year_start": top.get("year_start"),
        "year_end": top.get("year_end"),
        "identifiers": [top.get("unitid")] if top.get("unitid") else [],
        "urls": all_urls,
        "repository": top.get("repository"),
        "origination": top.get("origination"),
        "item_count": len(items),
    }

    return {
        "canonical": canonical,
        "raw": {
            "top": top,
            "items": items,
        },
    }
