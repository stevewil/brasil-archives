"""Tests for the quarterly health-probe runner.

All HTTP is mocked by monkeypatching ``probe.http_get`` /
``probe.tls_cert_expiry``; nothing here touches the network. Coverage:

* every vocabulary value of each of the four composited facets;
* ``--dry-run`` / ``dry_run=True`` writes nothing;
* a real run writes exactly one ProbeResult row with correct denormalized
  values and pushes the four facets + ``last_probed_at``;
* a per-signal failure is survivable (run goes ``partial``, row still
  written);
* the growth signal is computed against a seeded prior ProbeResult row.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest

from app.extensions import db
from app.models import Archive, FacetValue, InstitutionalType, ProbeResult
from app.services import probe
from app.services.scoring import active_probe_facet_values


NOW = datetime(2026, 1, 15, 12, 0, 0)


# --------------------------------------------------------------------------- #
# Fixtures + fake HTTP
# --------------------------------------------------------------------------- #
@pytest.fixture
def archive(app):
    it = InstitutionalType(
        slug="university", label_en="University", label_pt="Universidade",
        sort_order=1,
    )
    db.session.add(it)
    db.session.commit()
    a = Archive(
        slug="arq-example",
        name="Arquivo Example",
        canonical_url="https://arq.example",
        institutional_type_id=it.id,
        home_state_code="RN",
    )
    db.session.add(a)
    db.session.commit()
    return a


class FakeHTTP:
    """Substring router for ``probe.http_get``. Routes are matched in the
    order added; register the specific paths before the bare host.
    """

    def __init__(self):
        self.routes: list[tuple[str, int, bytes, Exception | None]] = []
        self.calls: list[str] = []

    def add(self, substr, *, status=200, body=b"", exc=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.routes.append((substr, status, body, exc))
        return self

    def __call__(self, url, *, timeout=probe.HTTP_TIMEOUT_SECONDS, headers=None):
        self.calls.append(url)
        for substr, status, body, exc in self.routes:
            if substr in url:
                if exc is not None:
                    raise exc
                return probe.HTTPResponse(status=status, url=url, body=body)
        return probe.HTTPResponse(status=404, url=url, body=b"")


def _sitemap(n, base="https://arq.example/doc/"):
    urls = "".join(f"<url><loc>{base}{i}</loc></url>" for i in range(n))
    return (
        '<?xml version="1.0"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}</urlset>"
    )


def _cdx(timestamps):
    rows = [["timestamp"]] + [[ts] for ts in timestamps]
    return json.dumps(rows)


def _crossref(total):
    return json.dumps({"message": {"total-results": total}})


def _semscholar(total):
    return json.dumps({"total": total})


def _wire_happy_path(fake, *, sitemap_n=4, home_caps=3, interior_ts="20251201000000",
                     crossref=20, semscholar=8):
    (
        fake
        .add("/robots.txt", status=200, body=b"")
        .add("/sitemap.xml", status=200, body=_sitemap(sitemap_n))
        .add("collapse=timestamp", status=200,
             body=_cdx([f"2020010{i}000000" for i in range(1, home_caps + 1)]))
        .add("web.archive.org/cdx", status=200, body=_cdx([interior_ts]))
        .add("api.crossref.org", status=200, body=_crossref(crossref))
        .add("api.semanticscholar.org", status=200, body=_semscholar(semscholar))
        .add("arq.example", status=200, body=b"<html>ok</html>")
    )
    return fake


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """The probe pauses before Semantic Scholar; never do that in tests."""
    monkeypatch.setattr(probe.time, "sleep", lambda *_a, **_k: None)


@pytest.fixture
def happy_http(monkeypatch):
    fake = _wire_happy_path(FakeHTTP())
    monkeypatch.setattr(probe, "http_get", fake)
    monkeypatch.setattr(probe, "tls_cert_expiry", lambda *a, **k: date(2026, 12, 1))
    return fake


# --------------------------------------------------------------------------- #
# Compositing — web_ops_health (every vocabulary value)
# --------------------------------------------------------------------------- #
def _sig(**kw):
    base = dict(
        canonical_url="https://arq.example",
        https_valid=True,
        cert_expires_at=date(2026, 12, 1),  # ~320 days out from NOW
        canonical_http_status=200,
        interior_http_statuses=[200, 200, 200, 200],
        robots_ok=True,
    )
    base.update(kw)
    return probe.ProbeSignals(**base)


@pytest.mark.parametrize(
    "kw, expected",
    [
        ({}, "healthy"),
        ({"cert_expires_at": NOW.date() + timedelta(days=30)}, "degraded"),
        ({"interior_http_statuses": [200, 200, 200, 404]}, "degraded"),
        ({"robots_ok": False}, "degraded"),
        ({"https_valid": None}, "degraded"),
        ({"canonical_http_status": 403}, "at-risk"),
        ({"https_valid": False}, "at-risk"),
        ({"cert_expires_at": NOW.date() + timedelta(days=10)}, "at-risk"),
        ({"interior_http_statuses": [200, 200, 404, 500]}, "at-risk"),
        ({"canonical_http_status": None}, "down"),
        ({"canonical_http_status": 503}, "down"),
    ],
)
def test_composite_web_ops_health(kw, expected):
    assert probe.composite_web_ops_health(_sig(**kw), now=NOW) == expected


# --------------------------------------------------------------------------- #
# Compositing — external_preservation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "home, ratio, expected",
    [
        (None, None, None),
        (10, 0.75, "preserved"),
        (0, 0.0, "unpreserved"),
        (None, 0.0, "unpreserved"),
        (5, 0.25, "home-page-only"),
        (0, 0.30, "home-page-only"),
    ],
)
def test_composite_external_preservation(home, ratio, expected):
    s = probe.ProbeSignals(
        canonical_url="x", wayback_home_count=home, wayback_interior_hit_ratio=ratio
    )
    assert probe.composite_external_preservation(s) == expected


# --------------------------------------------------------------------------- #
# Compositing — growth_signal (every vocabulary value)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "now_c, y1, y2, wb_age, expected",
    [
        (150, 100, None, None, "active"),
        (80, 100, None, None, "wound-down"),
        (100, 100, 50, None, "slow"),
        (100, None, 50, None, "slow"),
        (100, 100, 100, None, "stalled"),
        (100, 100, None, None, "stalled"),
        (40, None, 100, None, "wound-down"),
        (None, None, None, None, "unknown"),
        (None, None, None, 100, "active"),
        (None, None, None, 500, "slow"),
        (None, None, None, 900, "stalled"),
    ],
)
def test_composite_growth_signal(now_c, y1, y2, wb_age, expected):
    assert (
        probe.composite_growth_signal(
            now_count=now_c,
            count_12m_ago=y1,
            count_24m_ago=y2,
            newest_wayback_age_days=wb_age,
        )
        == expected
    )


def test_growth_tolerance_ignores_noise():
    # 1% of 1000 is 10; a delta of 5 either way is within tolerance.
    assert probe.composite_growth_signal(
        now_count=1005, count_12m_ago=1000, count_24m_ago=1000,
        newest_wayback_age_days=None,
    ) == "stalled"


# --------------------------------------------------------------------------- #
# Compositing — prior_use_signal (every vocabulary value)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "crossref, ss, expected",
    [
        (None, None, "unknown"),
        (60, 0, "foundational"),
        (20, None, "established"),
        (2, 40, "established"),
        (3, 0, "emerging"),
        (0, 0, "unused"),
    ],
)
def test_composite_prior_use_signal(crossref, ss, expected):
    assert probe.composite_prior_use_signal(crossref, ss) == expected


# --------------------------------------------------------------------------- #
# run_probe integration
# --------------------------------------------------------------------------- #
def test_dry_run_writes_nothing(app, archive, happy_http):
    summary = probe.run_probe(archive=archive, dry_run=True, now=NOW)

    assert summary.status == "ok"
    assert summary.web_ops_health == "healthy"
    assert summary.external_preservation == "preserved"
    assert summary.prior_use_signal == "established"
    assert summary.probe_result_id is None

    assert db.session.query(ProbeResult).count() == 0
    assert db.session.query(FacetValue).count() == 0
    db.session.refresh(archive)
    assert archive.last_probed_at is None


def test_real_run_writes_one_row_with_denormalized_values(app, archive, happy_http):
    summary = probe.run_probe(archive=archive, now=NOW)

    assert summary.status == "ok"
    rows = db.session.query(ProbeResult).all()
    assert len(rows) == 1
    row = rows[0]

    assert row.archive_id == archive.id
    assert row.probe_version == "probe-v1"
    assert row.canonical_http_status == 200
    assert row.https_valid is True
    assert row.cert_expires_at == date(2026, 12, 1)
    assert row.directory_url_count_now == 4
    assert row.citation_count_crossref == 20
    assert row.citation_count_semantic_scholar == 8
    assert json.loads(row.interior_url_sample) == [
        f"https://arq.example/doc/{i}" for i in range(4)
    ]
    assert json.loads(row.interior_http_statuses) == [200, 200, 200, 200]

    # denormalized composited facets
    assert row.web_ops_health == "healthy"
    assert row.external_preservation == "preserved"
    assert row.growth_signal == "active"  # via Wayback fallback, no prior rows
    assert row.prior_use_signal == "established"

    # pushed through the facet service
    facets = active_probe_facet_values(archive.id)
    assert {f: v.value for f, v in facets.items()} == {
        "web_ops_health": "healthy",
        "external_preservation": "preserved",
        "growth_signal": "active",
        "prior_use_signal": "established",
    }
    assert all(v.set_by == "probe" for v in facets.values())

    db.session.refresh(archive)
    assert archive.last_probed_at == NOW


def test_second_run_appends_a_second_row(app, archive, happy_http):
    probe.run_probe(archive=archive, now=NOW)
    probe.run_probe(archive=archive, now=NOW + timedelta(days=90))
    assert db.session.query(ProbeResult).count() == 2
    # unchanged facet value is not duplicated in history
    assert db.session.query(FacetValue).filter_by(facet="web_ops_health").count() == 1


def test_per_signal_failure_is_survivable(app, archive, monkeypatch):
    fake = _wire_happy_path(FakeHTTP())
    # CrossRef 500s -> _get_json raises -> caught per-signal.
    fake.routes.insert(0, ("api.crossref.org", 500, b"upstream boom", None))
    monkeypatch.setattr(probe, "http_get", fake)
    monkeypatch.setattr(probe, "tls_cert_expiry", lambda *a, **k: date(2026, 12, 1))

    summary = probe.run_probe(archive=archive, now=NOW)

    assert summary.status == "partial"
    assert any("crossref" in e for e in summary.signal_errors)
    row = db.session.query(ProbeResult).one()
    assert row.citation_count_crossref is None
    assert row.citation_count_semantic_scholar == 8
    # falls back to the Semantic Scholar count alone (8 -> emerging)
    assert row.prior_use_signal == "emerging"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://plain.example/ok", "https://plain.example/ok"),
        ("https://ex.com/caça?q=São", "https://ex.com/ca%C3%A7a?q=S%C3%A3o"),
    ],
)
def test_ascii_url_encodes_non_ascii(url, expected):
    assert probe._ascii_url(url) == expected


@pytest.mark.parametrize(
    "raiser",
    [
        lambda *a, **k: (_ for _ in ()).throw(ValueError("unknown url type: 'n.a.'")),
        lambda *a, **k: (_ for _ in ()).throw(ConnectionResetError(104, "Connection reset by peer")),
    ],
)
def test_http_get_wraps_valueerror_and_oserror(monkeypatch, raiser):
    """A malformed URL or a bare OSError (ConnectionResetError) must surface
    as ProbeHTTPError, not the raw exception — otherwise the whole target
    aborts instead of degrading to web_ops=down."""
    monkeypatch.setattr(probe.urllib.request, "urlopen", raiser)
    with pytest.raises(probe.ProbeHTTPError):
        probe.http_get("https://example.test/")


def test_junk_canonical_url_degrades_to_down_not_abort(app, monkeypatch):
    it = InstitutionalType(slug="u2", label_en="U", label_pt="U", sort_order=2)
    db.session.add(it)
    db.session.commit()
    bad = Archive(
        slug="arq-bad-url", name="Bad URL", institutional_type_id=it.id,
        canonical_url="n.a. (portal URL not published in the source consulted)",
        home_state_code="RN",
    )
    db.session.add(bad)
    db.session.commit()
    monkeypatch.setattr(probe, "tls_cert_expiry", lambda *a, **k: None)
    # No network in tests: every http_get fails fast with ProbeHTTPError.
    def _boom(url, **_kw):
        raise probe.ProbeHTTPError(f"no network in test: {url}")
    monkeypatch.setattr(probe, "http_get", _boom)

    summary = probe.run_probe(archive=bad, now=NOW)

    assert summary.status == "partial"        # not "failed"
    row = db.session.query(ProbeResult).filter_by(archive_id=bad.id).one()
    assert row.web_ops_health == "down"
    assert bad.last_probed_at == NOW


def test_growth_signal_uses_seeded_prior_row(app, archive, monkeypatch):
    prior = ProbeResult(
        archive_id=archive.id,
        probed_at=NOW - timedelta(days=365),
        canonical_url=archive.canonical_url,
        directory_url_count_now=100,
        probe_version="probe-v1",
    )
    db.session.add(prior)
    db.session.commit()

    fake = _wire_happy_path(FakeHTTP(), sitemap_n=150)
    monkeypatch.setattr(probe, "http_get", fake)
    monkeypatch.setattr(probe, "tls_cert_expiry", lambda *a, **k: date(2026, 12, 1))

    summary = probe.run_probe(archive=archive, now=NOW)

    assert summary.growth_signal == "active"
    row = (
        db.session.query(ProbeResult)
        .filter(ProbeResult.probed_at == NOW)
        .one()
    )
    assert row.directory_url_count_now == 150
    assert row.directory_url_count_12m_ago == 100
    assert row.growth_signal == "active"


def test_run_probe_requires_exactly_one_target(app):
    with pytest.raises(ValueError):
        probe.run_probe()


def test_semantic_scholar_429_is_a_soft_miss_not_an_error(app, archive, monkeypatch):
    fake = _wire_happy_path(FakeHTTP())
    # S2 rate-limits. Should NOT land in signal_errors, should NOT flip
    # the run to "partial"; the count is just left None.
    fake.routes.insert(0, ("api.semanticscholar.org", 429, b"slow down", None))
    monkeypatch.setattr(probe, "http_get", fake)
    monkeypatch.setattr(probe, "tls_cert_expiry", lambda *a, **k: date(2026, 12, 1))

    summary = probe.run_probe(archive=archive, now=NOW)

    assert summary.status == "ok"
    assert not any("semantic" in e for e in summary.signal_errors)
    assert any("semantic scholar" in n for n in summary.signal_notes)
    row = db.session.query(ProbeResult).one()
    assert row.citation_count_semantic_scholar is None
    # prior_use still composited from CrossRef alone (20 -> established)
    assert row.prior_use_signal == "established"


def test_wayback_home_timeout_is_soft(app, archive, monkeypatch):
    fake = _wire_happy_path(FakeHTTP())
    fake.routes.insert(
        0, ("collapse=timestamp", 0, b"", probe.ProbeTimeout("Timeout after 20s"))
    )
    monkeypatch.setattr(probe, "http_get", fake)
    monkeypatch.setattr(probe, "tls_cert_expiry", lambda *a, **k: date(2026, 12, 1))

    summary = probe.run_probe(archive=archive, now=NOW)

    assert summary.status == "ok"  # not partial
    assert not any("wayback home" in e for e in summary.signal_errors)
    assert any("wayback home" in n for n in summary.signal_notes)


def test_per_target_budget_caps_wall_clock(app, archive, monkeypatch):
    fake = _wire_happy_path(FakeHTTP())
    monkeypatch.setattr(probe, "http_get", fake)
    monkeypatch.setattr(probe, "tls_cert_expiry", lambda *a, **k: date(2026, 12, 1))
    # Force the deadline to have already passed after step 1.
    clock = iter([0.0] + [10_000.0] * 50)
    monkeypatch.setattr(probe.time, "monotonic", lambda: next(clock))

    sig = probe.collect_signals(
        canonical_url="https://arq.example", citation_query="x", now=NOW,
        budget_seconds=5,
    )

    assert sig.canonical_http_status == 200  # step 1 ran
    assert any("budget" in n for n in sig.notes)
    assert sig.wayback_home_count is None  # later steps skipped


def test_cli_dry_run_smoke(app, archive, happy_http, monkeypatch, capsys):
    import scripts.probe as cli

    monkeypatch.setattr(cli, "app", app)
    rc = cli.main(["--archive", "arq-example", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY RUN" in out
    assert "healthy" in out
    assert db.session.query(ProbeResult).count() == 0


def test_cli_unknown_archive_exits_2(app, happy_http, monkeypatch, capsys):
    import scripts.probe as cli

    monkeypatch.setattr(cli, "app", app)
    rc = cli.main(["--archive", "does-not-exist"])
    assert rc == 2
