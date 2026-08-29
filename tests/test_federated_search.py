"""Phase 3.5 — federated search over harvested partner records.

Covers the service (matching, ranking, facets, deep links, pagination)
and the public ``GET /search`` view, including bilingual rendering.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

import pytest

from app.extensions import db as _db
from app.models import (
    AggregatedRecord,
    Archive,
    HarvestRun,
    InstitutionalType,
    UpgradeProject,
)
from app.services import federated_search as fs


# --------------------------------------------------------------------------- #
# Fixtures / builders


def _make_record(project, run, ident, canonical, *, prefix="oai_dc"):
    raw = f"<record>{ident}</record>"
    now = datetime(2026, 8, 29)
    return AggregatedRecord(
        upgrade_project_id=project.id,
        oai_identifier=ident,
        metadata_prefix=prefix,
        datestamp="2026-08-29",
        set_specs_json="[]",
        raw_xml=raw,
        raw_xml_sha256=hashlib.sha256(raw.encode()).hexdigest() + ident,
        extracted_json=json.dumps({"canonical": canonical}),
        harvest_run_id=run.id,
        first_seen_at=now,
        last_seen_at=now,
    )


@pytest.fixture
def seeded(app):
    """Two partner projects with a handful of harvested oai_dc records."""
    with app.app_context():
        it = InstitutionalType(
            slug="research-project", label_en="Research project",
            label_pt="Projeto de pesquisa", sort_order=1,
        )
        _db.session.add(it)
        _db.session.flush()
        arch = Archive(
            slug="src-archive", name="Source", institutional_type_id=it.id,
            canonical_url="https://src.example", no_digital_content=False,
        )
        _db.session.add(arch)
        _db.session.flush()

        mipibu = UpgradeProject(
            slug="mipibu", name="Mipibu", source_archive_id=arch.id,
            scope_description_en="Judicial records 1800-1900.",
            primary_url="https://mipibu.from-bottom-to.top",
            delivery_status="beta",
        )
        povos = UpgradeProject(
            slug="povos", name="Povos Indígenas RN", source_archive_id=arch.id,
            scope_description_en="Indigenous history corpus.",
            primary_url="https://povos.from-bottom-to.top",
            delivery_status="beta",
        )
        _db.session.add_all([mipibu, povos])
        _db.session.flush()

        run_m = HarvestRun(
            upgrade_project_id=mipibu.id, metadata_prefix="oai_dc",
            started_at=datetime(2026, 8, 29), status="ok",
        )
        run_p = HarvestRun(
            upgrade_project_id=povos.id, metadata_prefix="oai_dc",
            started_at=datetime(2026, 8, 29), status="ok",
        )
        _db.session.add_all([run_m, run_p])
        _db.session.flush()

        _db.session.add_all([
            _make_record(mipibu, run_m, "oai:m:case:1", {
                "title": "Sumário Crime - Ofensas físicas",
                "creator": "Cartório de São José de Mipibu",
                "year_start": 1872, "year_end": 1872, "date": "1872",
                "subjects": ["Sumário Crime"],
                "urls": ["https://mipibu.from-bottom-to.top/cases/SJM-0001",
                         "http://repositorio.example/bitstream/1.pdf"],
            }),
            _make_record(mipibu, run_m, "oai:m:case:2", {
                "title": "Ação de despejo",
                "creator": "Juízo de Direito",
                "year_start": 1889, "year_end": 1889,
                "description": "Processo envolvendo uma sesmaria disputada.",
                "urls": ["https://mipibu.from-bottom-to.top/cases/SJM-0002"],
            }),
            # oai_ead duplicate of case:1 — must never surface in search.
            _make_record(mipibu, run_m, "oai:m:case:1", {
                "title": "Sumário Crime - Ofensas físicas (EAD)",
            }, prefix="oai_ead"),
            _make_record(povos, run_p, "oai:p:document:1", {
                "title": "Consulta do Conselho Ultramarino sobre aldeias de índios",
                "year_start": 1675, "year_end": 1675,
                "subjects": ["aldeamento", "sesmaria"],
                "urls": ["https://povos.from-bottom-to.top/documents/1"],
            }),
            _make_record(povos, run_p, "oai:p:passage:9", {
                "title": "Passagem sobre os Janduí",
                "year_start": 1701, "year_end": 1701,
                # no partner-host URL -> deep link falls back to the site
                "urls": [],
            }),
        ])
        _db.session.commit()
    return app


# --------------------------------------------------------------------------- #
# Service


def test_short_query_is_not_searched(seeded):
    with seeded.app_context():
        resp = fs.search(q="a")
        assert resp.searched is False
        assert resp.total == 0
        assert len(resp.projects) == 2


def test_title_match(seeded):
    with seeded.app_context():
        resp = fs.search(q="despejo")
        assert resp.searched is True
        assert resp.total == 1
        assert resp.hits[0].oai_identifier == "oai:m:case:2"


def test_accent_and_case_insensitive(seeded):
    with seeded.app_context():
        assert fs.search(q="sumario").total == 1
        assert fs.search(q="SUMÁRIO").total == 1
        assert fs.search(q="índios").total == 1
        assert fs.search(q="indios").total == 1


def test_oai_ead_records_are_excluded(seeded):
    with seeded.app_context():
        resp = fs.search(q="Sumário Crime")
        assert resp.total == 1
        assert all("EAD" not in h.title for h in resp.hits)


def test_facets_count_per_partner_regardless_of_source_filter(seeded):
    with seeded.app_context():
        resp = fs.search(q="sesmaria")  # mipibu case:2 + povos document:1
        assert resp.total == 2
        by_slug = {f.slug: f.count for f in resp.facets}
        assert by_slug == {"mipibu": 1, "povos": 1}

        filtered = fs.search(q="sesmaria", source="povos")
        assert filtered.total == 1
        assert filtered.hits[0].project_slug == "povos"
        # facets still show the full spread so the user can widen out
        assert {f.slug: f.count for f in filtered.facets} == {"mipibu": 1, "povos": 1}


def test_strong_hits_rank_above_weak_hits(seeded):
    with seeded.app_context():
        resp = fs.search(q="sesmaria")
        # case:2 matches in the description (strong); document:1 only in
        # a subject (weak) -> strong sorts first.
        assert resp.hits[0].oai_identifier == "oai:m:case:2"
        assert resp.hits[0].strong is True
        assert resp.hits[1].strong is False


def test_deep_link_prefers_partner_host_then_falls_back(seeded):
    with seeded.app_context():
        resp = fs.search(q="Sumário")
        hit = resp.hits[0]
        assert hit.link == "https://mipibu.from-bottom-to.top/cases/SJM-0001"
        assert hit.source_url == "http://repositorio.example/bitstream/1.pdf"

        passage = fs.search(q="Janduí").hits[0]
        assert passage.link == "https://povos.from-bottom-to.top"
        assert passage.source_url is None


def test_pagination(seeded):
    with seeded.app_context():
        # "sesmaria" matches two records across both partners.
        p1 = fs.search(q="sesmaria", page=1, page_size=1)
        assert p1.total == 2
        assert p1.pages == 2
        assert len(p1.hits) == 1
        assert p1.has_next is True and p1.has_prev is False

        p2 = fs.search(q="sesmaria", page=2, page_size=1)
        assert len(p2.hits) == 1
        assert p2.has_prev is True and p2.has_next is False
        assert p1.hits[0].oai_identifier != p2.hits[0].oai_identifier

        # Out-of-range page clamps to an empty slice, not an error.
        p9 = fs.search(q="sesmaria", page=9, page_size=1)
        assert p9.hits == ()


def test_page_size_is_clamped(seeded):
    with seeded.app_context():
        assert fs.search(q="sesmaria", page_size=99999).page_size == fs.PAGE_SIZE_MAX
        assert fs.search(q="sesmaria", page_size="garbage").page_size == fs.PAGE_SIZE_DEFAULT


# --------------------------------------------------------------------------- #
# View


def test_search_view_renders(seeded, client):
    resp = client.get("/search?q=despejo")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Ação de despejo" in body
    assert "Mipibu" in body  # source attribution badge


def test_search_view_empty_prompt(seeded, client):
    body = client.get("/search").get_data(as_text=True)
    assert "at least two characters" in body
    assert "Mipibu" in body and "Povos Indígenas RN" in body  # partner list


def test_search_view_no_results(seeded, client):
    body = client.get("/search?q=zzznomatch").get_data(as_text=True)
    assert "No results for" in body


def test_search_view_source_filter_chip(seeded, client):
    body = client.get("/search?q=sesmaria").get_data(as_text=True)
    assert "source=povos" in body
    assert "source=mipibu" in body


def test_search_view_renders_portuguese(seeded, client):
    body = client.get("/search?q=despejo&lang=pt").get_data(as_text=True)
    assert "Buscar" in body  # PT for "Search"


def test_search_view_still_renders_english(seeded, client):
    body = client.get("/search?q=despejo&lang=en").get_data(as_text=True)
    assert "result(s) for" in body


def test_search_link_in_nav(seeded, client):
    body = client.get("/").get_data(as_text=True)
    assert 'href="/search"' in body
