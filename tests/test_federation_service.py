"""Tests for the federation-v1 client service.

These tests stub urllib to avoid any real network calls; every fetch
returns a pre-canned body shaped like Mipibu's live responses.
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import urllib.error

from app.extensions import db as _db
from app.models import Archive, FederationCache, InstitutionalType, UpgradeProject
from app.services import federation as fed


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def archive(db):
    it = InstitutionalType(
        slug="university", label_en="University", label_pt="Universidade", sort_order=1
    )
    db.session.add(it)
    db.session.commit()
    a = Archive(
        slug="labim-ufrn",
        name="LABIM/UFRN — 1st Registry of São José de Mipibu (RN)",
        name_pt="LABIM/UFRN — 1º Cartório de São José de Mipibu (RN)",
        canonical_url="https://labim.ufrn.br",
        institutional_type_id=it.id,
        home_state_code="RN",
    )
    db.session.add(a)
    db.session.commit()
    return a


@pytest.fixture
def mipibu(db, archive):
    p = UpgradeProject(
        slug="mipibu",
        name="Mipibu Corpus Explorer",
        name_pt="Explorador do Corpus de Mipibu",
        source_archive_id=archive.id,
        scope_description_en="Judicial records 1800-1900.",
        primary_url="https://mipibu.from-bottom-to.top",
        delivery_status="beta",
        federation_contract_version="v1",
        json_api_base_url="https://mipibu.from-bottom-to.top/api",
    )
    db.session.add(p)
    db.session.commit()
    return p


@pytest.fixture
def health_body():
    return {
        "federation_contract_version": "v1",
        "status": "ok",
        "record_count": 508,
        "corpus_version": "e5c5e3ce415872ccf2a46612dc45d8aac8df6e6b612c23ace60a98af90cf7e2e",
        "generated_at": "2026-08-26T00:28:07Z",
        "links": {"self": "https://mipibu.from-bottom-to.top/api/health"},
    }


@pytest.fixture
def records_body():
    return {
        "federation_contract_version": "v1",
        "total": 508,
        "page": 1,
        "page_size": 25,
        "results": [
            {
                "id": "SJM-0001",
                "type": "judicial_case",
                "themes": [{"code": "homicidio", "label_pt": "Homicídio", "label_en": "Homicide"}],
                "links": {
                    "self": "https://mipibu.from-bottom-to.top/api/records/SJM-0001",
                    "html": "https://mipibu.from-bottom-to.top/cases/SJM-0001",
                },
            }
        ],
        "notes": [],
        "rejected": [],
        "filters": {"q": None, "period_start": None, "period_end": None, "themes": []},
        # The list-level links.html is what html_deep_link returns — the
        # partner has already applied the filters to it.
        "links": {
            "self": "https://mipibu.from-bottom-to.top/api/records",
            "html": "https://mipibu.from-bottom-to.top/cases?year_from=1870",
            "schema": "https://mipibu.from-bottom-to.top/api/schema",
            "health": "https://mipibu.from-bottom-to.top/api/health",
        },
    }


@pytest.fixture
def schema_body():
    return {
        "federation_contract_version": "v1",
        "fields": [
            {"name": "id", "dublin_core": "dc:identifier", "ead": "unitid"},
            {"name": "title", "dublin_core": "dc:title", "ead": "unittitle"},
        ],
        "query_grammar": {
            "themes": {
                "allowed_values": [
                    {"code": "homicidio", "label_pt": "Homicídio", "label_en": "Homicide"},
                    {"code": "inventario", "label_pt": "Inventário", "label_en": "Probate"},
                ]
            }
        },
        "licensing": {
            "code": {"spdx_id": "MIT"},
            "data": {"spdx_id": "CC-BY-SA-4.0", "share_alike": True},
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _FakeResponse:
    """Minimal urllib.response.addinfourl double."""

    def __init__(self, body: dict, status: int = 200):
        self._raw = json.dumps(body).encode("utf-8")
        self._status = status

    def read(self):
        return self._raw

    def getcode(self):
        return self._status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _mock_ok(body, status=200):
    """Return a patch that makes urlopen return one canned response."""
    return patch(
        "app.services.federation.urllib.request.urlopen",
        return_value=_FakeResponse(body, status),
    )


def _mock_network_error():
    return patch(
        "app.services.federation.urllib.request.urlopen",
        side_effect=urllib.error.URLError("simulated network failure"),
    )


def _mock_http_error(status, body):
    err = urllib.error.HTTPError(
        url="http://x",
        code=status,
        msg="err",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(json.dumps(body).encode("utf-8")),
    )
    return patch(
        "app.services.federation.urllib.request.urlopen",
        side_effect=err,
    )


# ---------------------------------------------------------------------------
# Cache-key stability
# ---------------------------------------------------------------------------
def test_cache_key_is_deterministic_across_dict_orderings():
    a = fed._cache_key("records", "/records", {"page": 1, "themes": ["homicidio"]})
    b = fed._cache_key("records", "/records", {"themes": ["homicidio"], "page": 1})
    assert a == b


def test_cache_key_changes_when_a_param_changes():
    a = fed._cache_key("records", "/records", {"themes": ["homicidio"]})
    b = fed._cache_key("records", "/records", {"themes": ["inventario"]})
    assert a != b


def test_cache_key_ignores_none_params():
    a = fed._cache_key("records", "/records", {"q": None, "page": 1})
    b = fed._cache_key("records", "/records", {"page": 1})
    assert a == b


# ---------------------------------------------------------------------------
# URL & params
# ---------------------------------------------------------------------------
def test_build_url_composes_base_path_query():
    url = fed._build_url(
        "https://mipibu.from-bottom-to.top/api",
        "/records",
        {"themes": ["homicidio"], "period_start": 1850, "q": None},
    )
    assert url.startswith("https://mipibu.from-bottom-to.top/api/records?")
    assert "themes=homicidio" in url
    assert "period_start=1850" in url


def test_build_url_omits_record_id_from_query():
    url = fed._build_url(
        "https://x/api", "/records/SJM-0001", {"record_id": "SJM-0001"}
    )
    assert url == "https://x/api/records/SJM-0001"


def test_clean_records_params_drops_empties_and_normalizes_themes():
    p = fed._clean_records_params(
        q="",
        period_start=1850,
        period_end=None,
        themes=[" homicidio ", "", None, "inventario"],
        page=None,
        page_size=25,
        lang="pt",
    )
    assert p == {
        "period_start": 1850,
        "themes": ["homicidio", "inventario"],
        "page_size": 25,
        "lang": "pt",
    }


# ---------------------------------------------------------------------------
# Deep link — comes from the partner's /api/records links.html, not built here
# ---------------------------------------------------------------------------
def test_html_deep_link_returns_partner_links_html(mipibu, records_body):
    with _mock_ok(records_body):
        url = fed.html_deep_link(mipibu, period_start=1870, period_end=1875)
    assert url == "https://mipibu.from-bottom-to.top/cases?year_from=1870"


def test_html_deep_link_partner_specific_shape(mipibu, records_body):
    """A partner with a different URL shape (e.g. povos /documents) is
    returned verbatim — brasil-archives does not know or care."""
    records_body["links"]["html"] = "https://povos-indigenas-rn.from-bottom-to.top/documents?q=xingu"
    with _mock_ok(records_body):
        url = fed.html_deep_link(mipibu, q="xingu")
    assert url == "https://povos-indigenas-rn.from-bottom-to.top/documents?q=xingu"


def test_html_deep_link_falls_back_to_site_root_on_failure(mipibu):
    # No mock -> the /api/records fetch raises -> fall back to primary_url.
    with patch(
        "app.services.federation.urllib.request.urlopen",
        side_effect=OSError("boom"),
    ):
        url = fed.html_deep_link(mipibu)
    assert url == "https://mipibu.from-bottom-to.top"


def test_html_deep_link_none_when_no_primary_url(mipibu):
    # primary_url is NOT NULL in the schema; empty string is the closest
    # "no delivery URL" state the model allows.
    mipibu.primary_url = ""
    _db.session.commit()
    assert fed.html_deep_link(mipibu) is None


# ---------------------------------------------------------------------------
# Cache miss → fetch → cache write
# ---------------------------------------------------------------------------
def test_fetch_health_stores_cache_row(mipibu, health_body):
    with _mock_ok(health_body):
        r = fed.fetch_health(mipibu)
    assert r.from_cache is False
    assert r.stale is False
    assert r.status == 200
    assert r.body["record_count"] == 508
    assert r.contract_version == "v1"
    assert r.corpus_version == health_body["corpus_version"]

    rows = _db.session.query(FederationCache).all()
    assert len(rows) == 1
    assert rows[0].endpoint == "health"
    assert rows[0].corpus_version == health_body["corpus_version"]
    stored = json.loads(rows[0].response_json)
    assert stored["record_count"] == 508


def test_fetch_records_stores_cache_row_with_filters(mipibu, records_body):
    with _mock_ok(records_body):
        r = fed.fetch_records(mipibu, themes=["homicidio"], period_start=1870, period_end=1880)
    assert r.from_cache is False
    assert r.body["total"] == 508

    row = _db.session.query(FederationCache).one()
    assert row.endpoint == "records"
    assert "themes=homicidio" in row.request_url
    assert "period_start=1870" in row.request_url


# ---------------------------------------------------------------------------
# Cache hit within TTL
# ---------------------------------------------------------------------------
def test_second_call_within_ttl_hits_cache(mipibu, records_body):
    with _mock_ok(records_body) as m:
        fed.fetch_records(mipibu, themes=["homicidio"])
        r2 = fed.fetch_records(mipibu, themes=["homicidio"])
    assert m.call_count == 1
    assert r2.from_cache is True
    assert r2.stale is False


def test_different_filters_use_different_cache_rows(mipibu, records_body):
    with _mock_ok(records_body) as m:
        fed.fetch_records(mipibu, themes=["homicidio"])
        fed.fetch_records(mipibu, themes=["inventario"])
    assert m.call_count == 2
    assert _db.session.query(FederationCache).count() == 2


# ---------------------------------------------------------------------------
# Expired cache → refetch
# ---------------------------------------------------------------------------
def test_expired_cache_row_triggers_refetch(mipibu, records_body):
    with _mock_ok(records_body):
        fed.fetch_records(mipibu, themes=["homicidio"])

    # Manually expire.
    row = _db.session.query(FederationCache).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    _db.session.commit()

    updated_body = dict(records_body)
    updated_body["total"] = 999
    with _mock_ok(updated_body) as m:
        r = fed.fetch_records(mipibu, themes=["homicidio"])
    assert m.call_count == 1
    assert r.from_cache is False
    assert r.body["total"] == 999
    # Same row, updated in place.
    assert _db.session.query(FederationCache).count() == 1


# ---------------------------------------------------------------------------
# Stale-cache fallback when upstream is down
# ---------------------------------------------------------------------------
def test_upstream_failure_serves_stale_cache(mipibu, records_body):
    with _mock_ok(records_body):
        fed.fetch_records(mipibu, themes=["homicidio"])

    # Expire it, then fail upstream.
    row = _db.session.query(FederationCache).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    _db.session.commit()

    with _mock_network_error():
        r = fed.fetch_records(mipibu, themes=["homicidio"])
    assert r.from_cache is True
    assert r.stale is True
    assert r.body["total"] == 508


def test_upstream_failure_with_no_cache_raises(mipibu):
    with _mock_network_error():
        with pytest.raises(fed.FederationUnavailable):
            fed.fetch_records(mipibu, themes=["homicidio"])


def test_missing_json_api_base_url_raises(mipibu):
    mipibu.json_api_base_url = None
    _db.session.commit()
    with pytest.raises(fed.FederationUnavailable):
        fed.fetch_health(mipibu)


# ---------------------------------------------------------------------------
# Contract-version guard
# ---------------------------------------------------------------------------
def test_unrecognized_contract_version_is_rejected(mipibu):
    weird = {"federation_contract_version": "v99", "status": "ok", "record_count": 1}
    with _mock_ok(weird):
        with pytest.raises(fed.FederationContractError):
            fed.fetch_health(mipibu)
    # Nothing should have been cached.
    assert _db.session.query(FederationCache).count() == 0


# ---------------------------------------------------------------------------
# 404 envelope (federation returns JSON on 404)
# ---------------------------------------------------------------------------
def test_record_404_envelope_is_returned_not_raised(mipibu):
    body_404 = {
        "federation_contract_version": "v1",
        "error": "not_found",
        "id": "NOT-REAL",
    }
    with _mock_http_error(404, body_404):
        r = fed.fetch_record(mipibu, "NOT-REAL")
    assert r.status == 404
    assert r.body["error"] == "not_found"


# ---------------------------------------------------------------------------
# Schema fetch parses licensing block
# ---------------------------------------------------------------------------
def test_fetch_schema_exposes_licensing_block(mipibu, schema_body):
    with _mock_ok(schema_body):
        r = fed.fetch_schema(mipibu)
    lic = r.body["licensing"]
    assert lic["code"]["spdx_id"] == "MIT"
    assert lic["data"]["spdx_id"] == "CC-BY-SA-4.0"
    assert lic["data"]["share_alike"] is True
