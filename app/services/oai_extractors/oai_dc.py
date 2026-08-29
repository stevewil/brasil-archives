"""Dublin Core (oai_dc) extractor.

Input: an ``<oai_dc:dc>`` Element.
Output: ``{"canonical": {...}, "raw": {"dc:<element>": [values...]}}``

See ``docs/harvest-design.md`` §Extractor contract.
"""
from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree as ET


DC_NS = "http://purl.org/dc/elements/1.1/"

# Dublin Core 1.1 — 15 elements, all optional and repeatable.
DC_ELEMENTS: tuple[str, ...] = (
    "contributor", "coverage", "creator", "date", "description",
    "format", "identifier", "language", "publisher", "relation",
    "rights", "source", "subject", "title", "type",
)

_YEAR_RANGE_RE = re.compile(r"(\d{4})\s*[/\-]\s*(\d{4})")
_SINGLE_YEAR_RE = re.compile(r"\b(1[6-9]\d{2}|20\d{2})\b")
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _text(el: ET.Element) -> str | None:
    if el.text is None:
        return None
    t = el.text.strip()
    return t or None


def _collect_by_element(root: ET.Element) -> dict[str, list[str]]:
    """Return {'dc:title': [...], 'dc:date': [...], ...} for the 15 DC tags."""
    result: dict[str, list[str]] = {f"dc:{name}": [] for name in DC_ELEMENTS}
    for child in root:
        # Only capture the 15 canonical DC elements.
        if not child.tag.startswith(f"{{{DC_NS}}}"):
            continue
        local = child.tag.split("}", 1)[1]
        key = f"dc:{local}"
        if key not in result:
            continue
        value = _text(child)
        if value:
            result[key].append(value)
    return result


def _first(values: list[str]) -> str | None:
    return values[0] if values else None


def _extract_years(date_values: list[str], coverage_values: list[str]) -> tuple[int | None, int | None]:
    """Best-effort year_start / year_end inference from dc:date + dc:coverage.

    We scan the concatenated candidate strings for a YYYY/YYYY or YYYY-YYYY
    range first; if none, we fall back to a single YYYY.
    """
    candidates: list[str] = []
    candidates.extend(date_values)
    candidates.extend(coverage_values)
    for candidate in candidates:
        m = _YEAR_RANGE_RE.search(candidate)
        if m:
            y1, y2 = int(m.group(1)), int(m.group(2))
            return (min(y1, y2), max(y1, y2))
    for candidate in candidates:
        m = _SINGLE_YEAR_RE.search(candidate)
        if m:
            year = int(m.group(1))
            return (year, year)
    return (None, None)


def _partition_urls(identifiers: list[str]) -> tuple[list[str], list[str]]:
    """Split dc:identifier values into (urls, non_url_ids)."""
    urls = [v for v in identifiers if _URL_RE.match(v)]
    ids = [v for v in identifiers if not _URL_RE.match(v)]
    return urls, ids


def extract(dc_element: ET.Element) -> dict[str, Any]:
    """Extract a canonical + raw view of an <oai_dc:dc> element."""
    raw = _collect_by_element(dc_element)

    identifiers = raw["dc:identifier"]
    urls_from_identifier, non_url_identifiers = _partition_urls(identifiers)
    # dc:relation is often used for related URLs (e.g. document downloads).
    urls_from_relation = [v for v in raw["dc:relation"] if _URL_RE.match(v)]
    urls = urls_from_identifier + urls_from_relation

    # dc:source points at where the record came from (a repository record,
    # a catalog page). Not a canonical location for the item itself, but a
    # useful fallback link when the provider gives no self URL.
    source_urls = [v for v in raw["dc:source"] if _URL_RE.match(v)]

    year_start, year_end = _extract_years(raw["dc:date"], raw["dc:coverage"])

    canonical: dict[str, Any] = {
        "title": _first(raw["dc:title"]),
        "date": _first(raw["dc:date"]),
        "year_start": year_start,
        "year_end": year_end,
        "language": _first(raw["dc:language"]),
        "rights": _first(raw["dc:rights"]),
        "identifiers": non_url_identifiers,
        "urls": urls,
        "source_urls": source_urls,
        "types": raw["dc:type"],           # keep all — often multi-valued
        "subjects": raw["dc:subject"],
        "creator": _first(raw["dc:creator"]),
        "publisher": _first(raw["dc:publisher"]),
        "coverage": raw["dc:coverage"],
        "description": _first(raw["dc:description"]),
    }

    return {"canonical": canonical, "raw": raw}
