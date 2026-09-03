"""Opt-in live smoke test against the real mipibu OAI-PMH endpoint.

Enabled with::

    BRASIL_ARCHIVES_LIVE_MIPIBU=1 pytest tests/test_live_mipibu.py -v

Skipped by default so CI stays offline. These tests exercise the full
harvest pipeline in dry-run mode (no DB writes) against a capped number
of pages, so they finish in a few seconds and don't scrape the whole
corpus.
"""
from __future__ import annotations

import os

import pytest

from app.services import oai_client
from app.services.oai_extractors import extract


LIVE_ENABLED = os.environ.get("BRASIL_ARCHIVES_LIVE_MIPIBU") == "1"
BASE_URL = "https://corpus-explorers.from-bottom-to.top/projects/mipibu/oai"


pytestmark = pytest.mark.skipif(
    not LIVE_ENABLED,
    reason="Set BRASIL_ARCHIVES_LIVE_MIPIBU=1 to enable live tests",
)


def test_identify_returns_expected_fields():
    r = oai_client.identify(BASE_URL)
    assert r.protocol_version == "2.0"
    assert r.granularity == "YYYY-MM-DD"
    assert "Mipibu" in r.repository_name or "mipibu" in r.repository_name.lower()


@pytest.mark.parametrize("prefix", ["oai_dc", "oai_ead"])
def test_first_page_records_extract_cleanly(prefix):
    page = oai_client.list_records(BASE_URL, prefix)
    assert len(page.records) > 0
    for rec in page.records[:5]:
        ident, stamp, sets = oai_client.record_header_fields(rec)
        assert ident and stamp
        payload = oai_client.record_metadata_element(rec)
        assert payload is not None
        out = extract(prefix, payload)
        assert isinstance(out["canonical"], dict)
        assert isinstance(out["raw"], dict)


def test_bad_verb_raises_protocol_error():
    with pytest.raises(oai_client.OaiProtocolError):
        # noinspection PyProtectedMember
        oai_client._fetch(BASE_URL, {"verb": "NoSuchVerb"})
