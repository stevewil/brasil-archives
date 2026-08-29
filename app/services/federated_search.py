"""Federated search over harvested partner records — Phase 3.5.

brasil-archives harvests partner corpus-explorer records into
``aggregated_records`` (see ``app/services/harvest.py``). This module
makes that store searchable from one public page: a query runs over the
harvested Dublin Core, and each hit is attributed back to its partner
project and deep-links into the partner's own viewer.

Scope (``docs/federation-v1.md`` §"IIIF Content Search" names the eventual
live fan-out as Phase 4; this is the pragmatic precursor):

* **Harvested snapshot, not a live fan-out.** We search the last harvest,
  not the partner's live index. Freshness is bounded by the monthly
  harvest cron.
* **``oai_dc`` only.** Every partner exposes Dublin Core; the ``oai_ead``
  records mipibu also provides describe the same cases and would only
  duplicate hits.
* **Accent-insensitive.** Brazilian users type "sumario" for "Sumário".
  Matching folds diacritics on both sides. At ~10^3 records a full scan
  in Python is well under a frame; move to an FTS5 table with
  ``remove_diacritics=2`` if the harvested corpus reaches ~10^4.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import AggregatedRecord, UpgradeProject
from ..text import fold as _fold

log = logging.getLogger(__name__)

# The prefix whose extractor output has the canonical shape this search
# understands (see app/services/oai_extractors/oai_dc.py).
SEARCH_PREFIX = "oai_dc"

PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 100
# Below this a query is too broad to be useful; the page shows the form
# and the list of partners instead of results.
MIN_QUERY_LEN = 2
DESCRIPTION_SNIPPET_CHARS = 280

# Canonical fields that count as a "strong" hit (title-ish); a match here
# sorts above records matched only on subjects/coverage/identifiers.
_STRONG_FIELDS = ("title", "creator", "publisher", "description")
_WEAK_FIELDS = ("subjects", "coverage", "types", "identifiers", "date")


# ---------------------------------------------------------------------------
# Return shapes
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SearchHit:
    """One harvested record that matched the query."""

    project_slug: str
    project_name: str
    title: str
    creator: str | None
    date_display: str | None
    year_start: int | None
    year_end: int | None
    description: str | None
    subjects: tuple[str, ...]
    link: str | None          # deep link into the partner's own viewer
    source_url: str | None    # external cited source (repository), if any
    oai_identifier: str
    strong: bool              # matched a title/creator/publisher/description field


@dataclass(frozen=True)
class SourceFacet:
    """Per-partner hit count for the current query (drives the filter chips)."""

    slug: str
    name: str
    count: int


@dataclass(frozen=True)
class SearchResponse:
    query: str
    source: str | None
    page: int
    page_size: int
    total: int
    pages: int
    hits: tuple[SearchHit, ...] = ()
    facets: tuple[SourceFacet, ...] = ()
    projects: tuple[UpgradeProject, ...] = ()
    searched: bool = False
    truncated: bool = False

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def search(
    *,
    q: str | None,
    source: str | None = None,
    page: object = 1,
    page_size: object = PAGE_SIZE_DEFAULT,
) -> SearchResponse:
    """Run a federated search and return one page of attributed hits.

    ``source`` restricts the returned page to one partner slug but does
    not change the facet counts — the chips always show the full spread
    so a visitor can widen back out.
    """
    q = (q or "").strip()
    page = _int(page, 1, minimum=1)
    page_size = _int(page_size, PAGE_SIZE_DEFAULT, minimum=1, maximum=PAGE_SIZE_MAX)

    projects = tuple(
        db.session.scalars(
            select(UpgradeProject).order_by(UpgradeProject.name)
        )
    )

    if len(q) < MIN_QUERY_LEN:
        return SearchResponse(
            query=q,
            source=source,
            page=page,
            page_size=page_size,
            total=0,
            pages=0,
            projects=projects,
            searched=False,
        )

    needle = _fold(q)
    records = db.session.scalars(
        select(AggregatedRecord)
        .where(AggregatedRecord.metadata_prefix == SEARCH_PREFIX)
        .options(selectinload(AggregatedRecord.upgrade_project))
    )

    hits: list[SearchHit] = []
    for rec in records:
        canonical = _canonical(rec.extracted_json)
        if canonical is None:
            continue
        strength = _match_strength(canonical, needle)
        if strength is None:
            continue
        hits.append(_build_hit(rec, canonical, strong=(strength == "strong")))

    facet_counts: dict[str, int] = {}
    for hit in hits:
        facet_counts[hit.project_slug] = facet_counts.get(hit.project_slug, 0) + 1
    facets = tuple(
        SourceFacet(slug=p.slug, name=p.name, count=facet_counts[p.slug])
        for p in projects
        if facet_counts.get(p.slug)
    )

    if source:
        hits = [h for h in hits if h.project_slug == source]

    hits.sort(key=lambda h: (not h.strong, _fold(h.title)))

    total = len(hits)
    pages = math.ceil(total / page_size) if total else 0
    start = (page - 1) * page_size
    page_hits = tuple(hits[start : start + page_size])

    return SearchResponse(
        query=q,
        source=source,
        page=page,
        page_size=page_size,
        total=total,
        pages=pages,
        hits=page_hits,
        facets=facets,
        projects=projects,
        searched=True,
    )


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
def _match_strength(canonical: dict, needle: str) -> str | None:
    """Return ``"strong"``, ``"weak"``, or ``None`` for ``needle`` in a record."""
    strong_text = _fold(
        " ".join(str(canonical.get(f) or "") for f in _STRONG_FIELDS)
    )
    if needle in strong_text:
        return "strong"

    weak_bits: list[str] = []
    for f in _WEAK_FIELDS:
        value = canonical.get(f)
        if isinstance(value, (list, tuple)):
            weak_bits.extend(str(v) for v in value)
        elif value:
            weak_bits.append(str(value))
    if needle in _fold(" ".join(weak_bits)):
        return "weak"
    return None


# ---------------------------------------------------------------------------
# Hit construction
# ---------------------------------------------------------------------------
def _canonical(extracted_json: str | None) -> dict | None:
    if not extracted_json:
        return None
    try:
        parsed = json.loads(extracted_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    canonical = parsed.get("canonical")
    return canonical if isinstance(canonical, dict) else None


def _build_hit(
    rec: AggregatedRecord, canonical: dict, *, strong: bool
) -> SearchHit:
    project = rec.upgrade_project
    title = (canonical.get("title") or "").strip() or "(untitled)"
    description = canonical.get("description")
    if isinstance(description, str) and len(description) > DESCRIPTION_SNIPPET_CHARS:
        description = description[:DESCRIPTION_SNIPPET_CHARS].rstrip() + "…"
    subjects = tuple(
        str(s).strip()
        for s in (canonical.get("subjects") or [])
        if str(s).strip()
    )
    link, source_url = _links(project, canonical)
    return SearchHit(
        project_slug=project.slug,
        project_name=project.name,
        title=title,
        creator=(canonical.get("creator") or None),
        date_display=(canonical.get("date") or None),
        year_start=_as_int(canonical.get("year_start")),
        year_end=_as_int(canonical.get("year_end")),
        description=description or None,
        subjects=subjects,
        link=link,
        source_url=source_url,
        oai_identifier=rec.oai_identifier,
        strong=strong,
    )


def _links(project: UpgradeProject, canonical: dict) -> tuple[str | None, str | None]:
    """(deep link into the partner viewer, external cited source).

    The partner's own record URL is whichever ``canonical.urls`` entry
    shares a host with the project's primary URL — mipibu's ``dc:identifier``
    carries ``…/cases/SJM-0001``. Partners whose ``oai_dc`` omits a
    self URL (povos today) fall back to the project home page; the first
    off-host URL, if any, is surfaced separately as the cited source.
    """
    base = (project.primary_url or "").rstrip("/")
    home_host = urlsplit(base).netloc
    urls = [u for u in (canonical.get("urls") or []) if isinstance(u, str)]

    deep_link = None
    source_url = None
    for url in urls:
        if urlsplit(url).netloc == home_host:
            deep_link = deep_link or url
        else:
            source_url = source_url or url
    return (deep_link or base or None), source_url


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _int(value: object, default: int, *, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        n = default
    if n < minimum:
        n = minimum
    if maximum is not None and n > maximum:
        n = maximum
    return n
