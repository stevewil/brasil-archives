"""Quarterly health-probe runner.

Collects the raw signals listed in ``docs/algorithm-v1.md`` §"Ongoing
infrastructure → Quarterly probe" for an :class:`Archive` (and, optionally,
an :class:`UpgradeProject`), composites the four probe-fed facets
(``docs/algorithm-v1.md`` §"Probe-updated facets") and writes:

* one :class:`ProbeResult` row per run — never overwritten; it is a time
  series and the growth signal reads prior rows;
* the composited facet values into ``facet_values`` via
  :func:`app.services.scoring.set_probe_facet_value` (archives only —
  ``FacetValue`` requires an ``archive_id``);
* ``Archive.last_probed_at`` = the run timestamp.

Design mirrors ``app/services/harvest.py``: a summary dataclass with an
``exit_code()``, per-signal failures tolerated (a dead API never aborts a
run), a ``dry_run`` mode that collects + composites + returns without
touching the DB.

Robustness: each target has a ``PROBE_TARGET_BUDGET_SECONDS`` wall-clock
ceiling (a dead host otherwise stacks ~8 sequential socket waits); Wayback
CDX gets a longer ``WAYBACK_TIMEOUT_SECONDS`` because it is routinely slow;
an HTTP 429 (``ProbeRateLimited``) is a *soft* miss — the signal is left
None and recorded in ``signals.notes``, never ``signals.errors``, and does
not flip the run to ``partial``.

All HTTP goes through :func:`http_get` / :func:`tls_cert_expiry`; tests
monkeypatch those two and never hit the network. Public keyless APIs
used: Wayback CDX (``web.archive.org/cdx/search/cdx``), CrossRef
(``api.crossref.org``), Semantic Scholar (``api.semanticscholar.org``;
best-effort, honours ``SEMANTIC_SCHOLAR_API_KEY`` when set).
"""
from __future__ import annotations

import json
import logging
import os
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from xml.etree import ElementTree as ET

from sqlalchemy import select

from ..extensions import db
from ..models import Archive, ProbeResult, UpgradeProject
from . import oai_client
from .scoring import set_probe_facet_value


log = logging.getLogger(__name__)

PROBE_VERSION = "probe-v1"

HTTP_TIMEOUT_SECONDS = 10  # Probe is polite: short timeouts, sequential.
WAYBACK_TIMEOUT_SECONDS = 20  # web.archive.org/cdx is routinely slow.
# Hard wall-clock ceiling per target. Without it a dead host stacks
# ~8 sequential socket waits (canonical GET + TLS + robots + sitemaps +
# interior URLs) and can wedge a batch run. Signals not yet collected when
# the budget runs out are left None and noted.
PROBE_TARGET_BUDGET_SECONDS = 90
# The keyless Semantic Scholar endpoint rate-limits aggressively; a small
# pause before it (and an API key when SEMANTIC_SCHOLAR_API_KEY is set)
# buys a better hit rate. A 429 is a soft miss, never a logged error.
SEMANTIC_SCHOLAR_DELAY_SECONDS = 1.0
USER_AGENT = (
    "brasil-archives/probe "
    "(+https://github.com/stevewil/brasil-archives)"
)
MAX_BODY_BYTES = 3_000_000
INTERIOR_SAMPLE_SIZE = 8

# --- compositing thresholds (see module docstring / final report) --------
CERT_AT_RISK_DAYS = 14
CERT_DEGRADED_DAYS = 45
WEB_OPS_ATRISK_BROKEN_RATIO = 0.5
PRESERVED_INTERIOR_RATIO = 0.5
GROWTH_TOLERANCE_FRACTION = 0.01
WAYBACK_ACTIVE_DAYS = 365
WAYBACK_SLOW_DAYS = 730
PRIOR_USE_FOUNDATIONAL = 50
PRIOR_USE_ESTABLISHED = 15
PRIOR_USE_EMERGING = 1

_FACET_KEYS = (
    "web_ops_health",
    "external_preservation",
    "growth_signal",
    "prior_use_signal",
)


# --------------------------------------------------------------------------- #
# HTTP layer (the only two functions tests monkeypatch)
# --------------------------------------------------------------------------- #
class ProbeHTTPError(Exception):
    """Network-level failure: connection refused, DNS, timeout, TLS."""


class ProbeTLSError(ProbeHTTPError):
    """TLS certificate verification failed."""


class ProbeRateLimited(ProbeHTTPError):
    """The remote returned HTTP 429. A soft miss — the caller drops the
    signal (leaves it None) and does NOT record an error."""


class ProbeTimeout(ProbeHTTPError):
    """The request exceeded its timeout. Soft for routinely-slow services
    (Wayback CDX); still an error for the canonical URL."""


@dataclass
class HTTPResponse:
    status: int
    url: str
    body: bytes


def http_get(
    url: str,
    *,
    timeout: int = HTTP_TIMEOUT_SECONDS,
    headers: dict[str, str] | None = None,
) -> HTTPResponse:
    """GET ``url``. A 4xx/5xx still returns an :class:`HTTPResponse` (with
    that status and whatever body came back); only transport failures raise.
    """
    all_headers = {"User-Agent": USER_AGENT}
    if headers:
        all_headers.update(headers)
    req = urllib.request.Request(url, headers=all_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HTTPResponse(
                status=resp.status,
                url=resp.geturl(),
                body=resp.read(MAX_BODY_BYTES),
            )
    except urllib.error.HTTPError as exc:  # 4xx/5xx — not a transport failure
        try:
            body = exc.read(MAX_BODY_BYTES)
        except Exception:  # pragma: no cover
            body = b""
        return HTTPResponse(status=exc.code, url=url, body=body)
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, ssl.SSLCertVerificationError):
            raise ProbeTLSError(f"TLS verify failed for {url}: {reason}") from exc
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise ProbeTimeout(f"Timeout after {timeout}s: {url}") from exc
        raise ProbeHTTPError(f"Network error for {url}: {reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise ProbeTimeout(f"Timeout after {timeout}s: {url}") from exc


def tls_cert_expiry(
    host: str, port: int = 443, *, timeout: int = HTTP_TIMEOUT_SECONDS
) -> date | None:
    """Return the ``notAfter`` date of ``host``'s TLS certificate, or None."""
    ctx = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
            cert = ssock.getpeercert()
    not_after = (cert or {}).get("notAfter")
    if not not_after:
        return None
    return datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").date()


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _host_of(url: str) -> str | None:
    return urllib.parse.urlsplit(url).hostname


def _origin_of(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _get_json(
    url: str,
    *,
    timeout: int = HTTP_TIMEOUT_SECONDS,
    headers: dict[str, str] | None = None,
):
    resp = http_get(url, timeout=timeout, headers=headers)
    if resp.status == 429:
        raise ProbeRateLimited(f"HTTP 429 from {url}")
    if resp.status >= 400:
        raise ProbeHTTPError(f"HTTP {resp.status} from {url}")
    return json.loads(resp.body.decode("utf-8", errors="replace"))


def _iter_sitemap_locs(xml_bytes: bytes) -> tuple[list[str], bool]:
    """Return (loc values, is_sitemap_index) from a sitemap or sitemapindex."""
    root = ET.fromstring(xml_bytes)
    tag = root.tag.split("}", 1)[-1]
    locs = [
        (el.text or "").strip()
        for el in root.iter()
        if el.tag.split("}", 1)[-1] == "loc" and el.text and el.text.strip()
    ]
    return locs, (tag == "sitemapindex")


# --------------------------------------------------------------------------- #
# Individual signal collectors — each tolerates failure at the caller
# --------------------------------------------------------------------------- #
def discover_interior_urls(
    canonical_url: str,
    *,
    limit: int = INTERIOR_SAMPLE_SIZE,
    deadline: float | None = None,
) -> tuple[list[str], int | None]:
    """Return (sample of up to ``limit`` interior URLs, total URL count).

    Sources, in order: ``robots.txt`` ``Sitemap:`` lines, ``/sitemap.xml``
    (following one level of ``<sitemapindex>``), then Wayback CDX distinct
    originals. ``total`` is the sitemap ``<loc>`` count (the growth signal's
    directory size), or None when no sitemap was found. Stops early once
    ``deadline`` (a ``time.monotonic()`` value) is past.
    """
    origin = _origin_of(canonical_url)
    sitemap_urls: list[str] = []

    # robots.txt Sitemap: directives
    try:
        r = http_get(f"{origin}/robots.txt")
        if r.status < 400:
            for line in r.body.decode("utf-8", errors="replace").splitlines():
                if line.lower().startswith("sitemap:"):
                    sitemap_urls.append(line.split(":", 1)[1].strip())
    except ProbeHTTPError:
        pass
    if not sitemap_urls:
        sitemap_urls = [f"{origin}/sitemap.xml"]

    all_locs: list[str] = []
    total: int | None = None
    for sm in sitemap_urls[:3]:
        if _past(deadline):
            break
        try:
            resp = http_get(sm)
            if resp.status >= 400:
                continue
            locs, is_index = _iter_sitemap_locs(resp.body)
            if is_index:
                for child in locs[:3]:
                    if _past(deadline):
                        break
                    try:
                        cr = http_get(child)
                        if cr.status < 400:
                            child_locs, _ = _iter_sitemap_locs(cr.body)
                            all_locs.extend(child_locs)
                    except (ProbeHTTPError, ET.ParseError):
                        continue
            else:
                all_locs.extend(locs)
        except (ProbeHTTPError, ET.ParseError):
            continue

    if all_locs:
        uniq = sorted({u for u in all_locs if u.rstrip("/") != canonical_url.rstrip("/")})
        total = len(all_locs)
        return _stride_sample(uniq, limit), total

    if _past(deadline):
        return [], total

    # Fallback: Wayback CDX distinct originals for the domain.
    try:
        host = _host_of(canonical_url)
        data = _get_json(
            "http://web.archive.org/cdx/search/cdx?"
            + urllib.parse.urlencode(
                {
                    "url": f"{host}/*",
                    "output": "json",
                    "fl": "original",
                    "collapse": "urlkey",
                    "limit": "200",
                }
            ),
            timeout=WAYBACK_TIMEOUT_SECONDS,
        )
        rows = data[1:] if data and isinstance(data, list) else []
        cdx_urls = sorted(
            {
                row[0]
                for row in rows
                if row and row[0].rstrip("/") != canonical_url.rstrip("/")
            }
        )
        if cdx_urls:
            return _stride_sample(cdx_urls, limit), None
    except (ProbeHTTPError, ValueError, KeyError, IndexError):
        pass

    return [], total


def _past(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() > deadline


def _stride_sample(items: list[str], limit: int) -> list[str]:
    if len(items) <= limit:
        return list(items)
    step = len(items) / limit
    return [items[int(i * step)] for i in range(limit)]


def robots_reachable(canonical_url: str) -> bool | None:
    """True if ``robots.txt`` returned any HTTP status (200 or 404 both fine);
    False on a transport failure; None if the check itself blew up.
    """
    try:
        resp = http_get(f"{_origin_of(canonical_url)}/robots.txt")
        return resp.status < 500
    except ProbeHTTPError:
        return False


def wayback_home_count(canonical_url: str) -> int | None:
    host = _host_of(canonical_url)
    data = _get_json(
        "http://web.archive.org/cdx/search/cdx?"
        + urllib.parse.urlencode(
            {
                "url": f"{host}/",
                "output": "json",
                "fl": "timestamp",
                "collapse": "timestamp:6",
                "limit": "500",
            }
        ),
        timeout=WAYBACK_TIMEOUT_SECONDS,
    )
    if not data or not isinstance(data, list):
        return 0
    return max(0, len(data) - 1)  # first row is the column header


def wayback_interior_coverage(
    urls: list[str], *, now: datetime, deadline: float | None = None
) -> tuple[float | None, int | None]:
    """Return (fraction of ``urls`` with >=1 Wayback capture, age in days of
    the newest capture seen across all of them). Stops early once
    ``deadline`` is past; the ratio is then over the URLs actually checked.
    """
    if not urls:
        return None, None
    hits = 0
    checked = 0
    newest: datetime | None = None
    for u in urls:
        if _past(deadline):
            break
        checked += 1
        try:
            data = _get_json(
                "http://web.archive.org/cdx/search/cdx?"
                + urllib.parse.urlencode(
                    {"url": u, "output": "json", "fl": "timestamp", "limit": "50"}
                ),
                timeout=WAYBACK_TIMEOUT_SECONDS,
            )
        except (ProbeHTTPError, ValueError):
            continue
        rows = data[1:] if data and isinstance(data, list) else []
        if not rows:
            continue
        hits += 1
        for row in rows:
            try:
                dt = datetime.strptime(row[0][:8], "%Y%m%d")
            except (ValueError, IndexError):
                continue
            if newest is None or dt > newest:
                newest = dt
    ratio = hits / checked if checked else None
    age = (now - newest).days if newest is not None else None
    return ratio, age


def crossref_works_count(query: str) -> int | None:
    data = _get_json(
        "https://api.crossref.org/works?"
        + urllib.parse.urlencode({"query": query, "rows": "0"})
    )
    return int(data["message"]["total-results"])


def semantic_scholar_count(query: str) -> int | None:
    """Best-effort. The keyless endpoint 429s often — that propagates as
    :class:`ProbeRateLimited` and the caller treats it as a soft miss.
    Set ``SEMANTIC_SCHOLAR_API_KEY`` in the environment to use a key."""
    headers: dict[str, str] | None = None
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers = {"x-api-key": api_key}
    data = _get_json(
        "https://api.semanticscholar.org/graph/v1/paper/search?"
        + urllib.parse.urlencode({"query": query, "limit": "1", "fields": "title"}),
        headers=headers,
    )
    return int(data.get("total", 0))


# --------------------------------------------------------------------------- #
# Raw-signal bundle
# --------------------------------------------------------------------------- #
@dataclass
class ProbeSignals:
    canonical_url: str
    https_valid: bool | None = None
    cert_expires_at: date | None = None
    canonical_http_status: int | None = None
    interior_url_sample: list[str] = field(default_factory=list)
    interior_http_statuses: list[int | None] = field(default_factory=list)
    robots_ok: bool | None = None
    wayback_home_count: int | None = None
    wayback_interior_hit_ratio: float | None = None
    newest_wayback_age_days: int | None = None
    directory_url_count_now: int | None = None
    citation_count_crossref: int | None = None
    citation_count_semantic_scholar: int | None = None
    oai_pmh_identify_ok: bool | None = None
    oai_pmh_earliest_datestamp: date | None = None
    iiif_search_endpoint_ok: bool | None = None
    errors: list[str] = field(default_factory=list)
    # Informational, non-error: rate-limited soft misses, budget skips.
    notes: list[str] = field(default_factory=list)


def collect_signals(
    *,
    canonical_url: str,
    citation_query: str | None,
    now: datetime,
    oai_pmh_base_url: str | None = None,
    iiif_search_endpoint: str | None = None,
    budget_seconds: float = PROBE_TARGET_BUDGET_SECONDS,
) -> ProbeSignals:
    """Run every signal collector, swallowing per-signal failures into
    ``signals.errors`` so one dead endpoint never aborts the run. A
    per-target wall-clock ``budget_seconds`` caps total time — signals not
    reached when it runs out are left None and noted (a dead host otherwise
    stacks ~8 sequential socket waits).
    """
    s = ProbeSignals(canonical_url=canonical_url)
    parts = urllib.parse.urlsplit(canonical_url)
    is_https = parts.scheme == "https"
    deadline = time.monotonic() + budget_seconds

    def over_budget(step: str) -> bool:
        if time.monotonic() <= deadline:
            return False
        s.notes.append(f"budget {budget_seconds:.0f}s exceeded; skipped {step}")
        return True

    # 1. canonical GET + TLS validity
    try:
        resp = http_get(canonical_url)
        s.canonical_http_status = resp.status
        if is_https:
            s.https_valid = True
    except ProbeTLSError as exc:
        s.https_valid = False
        s.errors.append(f"canonical TLS: {exc}")
    except ProbeHTTPError as exc:
        s.errors.append(f"canonical GET: {exc}")
    if not is_https:
        s.https_valid = False

    # 2. cert expiry
    if is_https and parts.hostname and not over_budget("cert expiry"):
        try:
            s.cert_expires_at = tls_cert_expiry(parts.hostname)
        except Exception as exc:  # noqa: BLE001 — any TLS/socket error is non-fatal
            s.errors.append(f"cert expiry: {exc}")

    # 3. interior URL discovery + directory size
    if not over_budget("interior discovery"):
        try:
            s.interior_url_sample, s.directory_url_count_now = discover_interior_urls(
                canonical_url, deadline=deadline
            )
        except Exception as exc:  # noqa: BLE001
            s.errors.append(f"interior discovery: {exc}")

    # 4. interior HTTP statuses
    for u in s.interior_url_sample:
        if over_budget("interior HTTP statuses"):
            break
        try:
            s.interior_http_statuses.append(http_get(u).status)
        except ProbeHTTPError:
            s.interior_http_statuses.append(None)

    # 5. robots.txt
    if not over_budget("robots"):
        try:
            s.robots_ok = robots_reachable(canonical_url)
        except Exception as exc:  # noqa: BLE001
            s.errors.append(f"robots: {exc}")

    # 6. Wayback home coverage — Wayback CDX is routinely slow; a timeout
    # or rate-limit here is a soft miss (interior coverage carries the
    # preservation signal anyway), not a run-fails-partial error.
    if not over_budget("wayback home"):
        try:
            s.wayback_home_count = wayback_home_count(canonical_url)
        except (ProbeTimeout, ProbeRateLimited) as exc:
            s.notes.append(f"wayback home: {exc}")
        except Exception as exc:  # noqa: BLE001
            s.errors.append(f"wayback home: {exc}")

    # 7. Wayback interior coverage
    if not over_budget("wayback interior"):
        try:
            s.wayback_interior_hit_ratio, s.newest_wayback_age_days = (
                wayback_interior_coverage(
                    s.interior_url_sample, now=now, deadline=deadline
                )
            )
        except Exception as exc:  # noqa: BLE001
            s.errors.append(f"wayback interior: {exc}")

    # 8. CrossRef + Semantic Scholar
    if citation_query and not over_budget("citations"):
        try:
            s.citation_count_crossref = crossref_works_count(citation_query)
        except ProbeRateLimited:
            s.notes.append("crossref: rate-limited")
        except Exception as exc:  # noqa: BLE001
            s.errors.append(f"crossref: {exc}")
        time.sleep(SEMANTIC_SCHOLAR_DELAY_SECONDS)
        try:
            s.citation_count_semantic_scholar = semantic_scholar_count(citation_query)
        except ProbeRateLimited:
            s.notes.append("semantic scholar: rate-limited (429) — soft miss")
        except Exception as exc:  # noqa: BLE001
            s.errors.append(f"semantic scholar: {exc}")

    # 9. OAI-PMH (upgrade projects)
    if oai_pmh_base_url:
        try:
            ident = oai_client.identify(oai_pmh_base_url)
            s.oai_pmh_identify_ok = True
            if ident.earliest_datestamp:
                try:
                    s.oai_pmh_earliest_datestamp = datetime.strptime(
                        ident.earliest_datestamp[:10], "%Y-%m-%d"
                    ).date()
                except ValueError:
                    pass
        except Exception as exc:  # noqa: BLE001
            s.oai_pmh_identify_ok = False
            s.errors.append(f"oai identify: {exc}")

    # 10. IIIF Content Search endpoint (upgrade projects)
    if iiif_search_endpoint:
        try:
            s.iiif_search_endpoint_ok = http_get(iiif_search_endpoint).status < 400
        except ProbeHTTPError as exc:
            s.iiif_search_endpoint_ok = False
            s.errors.append(f"iiif search: {exc}")

    return s


# --------------------------------------------------------------------------- #
# Compositing — pure functions, every vocabulary value reachable
# --------------------------------------------------------------------------- #
def _broken_ratio(statuses: list[int | None]) -> float:
    if not statuses:
        return 0.0
    broken = sum(1 for st in statuses if st is None or st >= 400)
    return broken / len(statuses)


def composite_web_ops_health(s: ProbeSignals, *, now: datetime) -> str:
    """``healthy`` / ``degraded`` / ``at-risk`` / ``down`` (worst wins).

    * ``down``   — canonical URL unreachable, or returns 5xx.
    * ``at-risk``— canonical returns 4xx; or HTTPS invalid; or cert expires
      within 14 days; or >=50% of the interior sample is broken.
    * ``degraded``— cert expires within 45 days; or any interior URL is
      broken; or robots.txt fetch failed at the transport level; or HTTPS
      validity could not be confirmed though the site answered.
    * ``healthy`` — none of the above.
    """
    cert_days = (
        (s.cert_expires_at - now.date()).days if s.cert_expires_at is not None else None
    )
    broken = _broken_ratio(s.interior_http_statuses)

    if s.canonical_http_status is None or s.canonical_http_status >= 500:
        return "down"
    if (
        s.canonical_http_status >= 400
        or s.https_valid is False
        or (cert_days is not None and cert_days <= CERT_AT_RISK_DAYS)
        or broken >= WEB_OPS_ATRISK_BROKEN_RATIO
    ):
        return "at-risk"
    if (
        (cert_days is not None and cert_days <= CERT_DEGRADED_DAYS)
        or broken > 0.0
        or s.robots_ok is False
        or s.https_valid is None
    ):
        return "degraded"
    return "healthy"


def composite_external_preservation(s: ProbeSignals) -> str | None:
    """``preserved`` / ``home-page-only`` / ``unpreserved``; None when the
    Wayback CDX gave us nothing at all (facet left untouched).

    * ``preserved``     — >=50% of the interior sample has a Wayback capture.
    * ``unpreserved``   — zero home captures and zero interior captures.
    * ``home-page-only``— anything in between.
    """
    if s.wayback_home_count is None and s.wayback_interior_hit_ratio is None:
        return None
    ratio = s.wayback_interior_hit_ratio or 0.0
    home = s.wayback_home_count or 0
    if ratio >= PRESERVED_INTERIOR_RATIO:
        return "preserved"
    if home == 0 and ratio == 0.0:
        return "unpreserved"
    return "home-page-only"


def _direction(cur: int | None, base: int | None) -> int | None:
    """+1 grew / -1 shrank / 0 flat / None if either side missing."""
    if cur is None or base is None:
        return None
    tol = max(1.0, GROWTH_TOLERANCE_FRACTION * base)
    if cur - base > tol:
        return 1
    if base - cur > tol:
        return -1
    return 0


def composite_growth_signal(
    *,
    now_count: int | None,
    count_12m_ago: int | None,
    count_24m_ago: int | None,
    newest_wayback_age_days: int | None,
) -> str:
    """``active`` / ``slow`` / ``stalled`` / ``wound-down`` / ``unknown``.

    Primary: directory (sitemap ``<loc>``) count now vs. the counts stored
    on the ~12- and ~24-month-old prior ``ProbeResult`` rows.

    * ``active``    — grew vs. 12 months ago.
    * ``slow``      — flat vs. 12 months ago but grew across the 24-month
      window (or only the 24-month datum exists and it grew).
    * ``stalled``   — flat across every window we can compare.
    * ``wound-down``— the URL count dropped.
    * ``unknown``   — no current count and no prior rows.

    Fallback when directory counts are unavailable: newest Wayback capture
    age — <=365d ``active``, <=730d ``slow``, older ``stalled``, none
    ``unknown``.
    """
    if now_count is not None:
        d1 = _direction(now_count, count_12m_ago)
        d2 = _direction(now_count, count_24m_ago)
        if d1 == 1:
            return "active"
        if d1 == -1:
            return "wound-down"
        if d1 == 0:
            if d2 == 1:
                return "slow"
            if d2 == -1:
                return "wound-down"
            return "stalled"
        # d1 is None — no 12-month datum
        if d2 == 1:
            return "slow"
        if d2 == -1:
            return "wound-down"
        if d2 == 0:
            return "stalled"

    if newest_wayback_age_days is None:
        return "unknown"
    if newest_wayback_age_days <= WAYBACK_ACTIVE_DAYS:
        return "active"
    if newest_wayback_age_days <= WAYBACK_SLOW_DAYS:
        return "slow"
    return "stalled"


def composite_prior_use_signal(
    crossref: int | None, semantic_scholar: int | None
) -> str:
    """``foundational`` / ``established`` / ``emerging`` / ``unused`` /
    ``unknown``. Uses ``max`` of the two sources (they overlap; the larger
    is the better lower bound). ``unknown`` when both lookups failed.

    Thresholds on that count: >=50 foundational, >=15 established, >=1
    emerging, 0 unused.
    """
    if crossref is None and semantic_scholar is None:
        return "unknown"
    n = max(crossref or 0, semantic_scholar or 0)
    if n >= PRIOR_USE_FOUNDATIONAL:
        return "foundational"
    if n >= PRIOR_USE_ESTABLISHED:
        return "established"
    if n >= PRIOR_USE_EMERGING:
        return "emerging"
    return "unused"


def composite_facets(
    s: ProbeSignals,
    *,
    now: datetime,
    count_12m_ago: int | None,
    count_24m_ago: int | None,
) -> dict[str, str | None]:
    return {
        "web_ops_health": composite_web_ops_health(s, now=now),
        "external_preservation": composite_external_preservation(s),
        "growth_signal": composite_growth_signal(
            now_count=s.directory_url_count_now,
            count_12m_ago=count_12m_ago,
            count_24m_ago=count_24m_ago,
            newest_wayback_age_days=s.newest_wayback_age_days,
        ),
        "prior_use_signal": composite_prior_use_signal(
            s.citation_count_crossref, s.citation_count_semantic_scholar
        ),
    }


# --------------------------------------------------------------------------- #
# Public run summary
# --------------------------------------------------------------------------- #
@dataclass
class ProbeSummary:
    target_kind: str  # "archive" | "upgrade_project"
    target_slug: str
    status: str  # "ok" | "partial" | "failed"
    archive_id: int | None = None
    upgrade_project_id: int | None = None
    probe_result_id: int | None = None
    web_ops_health: str | None = None
    external_preservation: str | None = None
    growth_signal: str | None = None
    prior_use_signal: str | None = None
    signal_errors: list[str] = field(default_factory=list)
    signal_notes: list[str] = field(default_factory=list)  # rate limits, budget skips
    dry_run: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    notes: str | None = None

    def exit_code(self) -> int:
        return {"ok": 0, "partial": 1}.get(self.status, 2)


# --------------------------------------------------------------------------- #
# Prior-row lookup for the growth signal
# --------------------------------------------------------------------------- #
def _closest_prior_count(
    rows: list[ProbeResult], target: datetime, *, window_days: int
) -> int | None:
    best: ProbeResult | None = None
    best_delta = timedelta(days=window_days)
    for r in rows:
        delta = abs(r.probed_at - target)
        if delta <= best_delta:
            best_delta = delta
            best = r
    if best is None:
        return None
    return best.directory_url_count_now


def _prior_directory_counts(
    *, archive_id: int | None, upgrade_project_id: int | None, now: datetime
) -> tuple[int | None, int | None]:
    stmt = select(ProbeResult).order_by(ProbeResult.probed_at)
    if archive_id is not None:
        stmt = stmt.where(ProbeResult.archive_id == archive_id)
    else:
        stmt = stmt.where(ProbeResult.upgrade_project_id == upgrade_project_id)
    rows = list(db.session.scalars(stmt))
    y1 = _closest_prior_count(rows, now - timedelta(days=365), window_days=150)
    y2 = _closest_prior_count(rows, now - timedelta(days=730), window_days=200)
    return y1, y2


# --------------------------------------------------------------------------- #
# Main entry points
# --------------------------------------------------------------------------- #
def run_probe(
    *,
    archive: Archive | None = None,
    upgrade_project: UpgradeProject | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
) -> ProbeSummary:
    """Probe one target. Writes a :class:`ProbeResult` row (unless
    ``dry_run``), pushes the four composited facets through the facet
    service (archives only) and stamps ``Archive.last_probed_at``.
    """
    if (archive is None) == (upgrade_project is None):
        raise ValueError("pass exactly one of archive= / upgrade_project=")

    now = now or _utcnow()
    if archive is not None:
        kind, slug = "archive", archive.slug
        canonical_url = archive.canonical_url
        citation_query = archive.name
        oai_base = None
        iiif_endpoint = None
        archive_id, up_id = archive.id, None
    else:
        assert upgrade_project is not None
        kind, slug = "upgrade_project", upgrade_project.slug
        canonical_url = upgrade_project.primary_url
        citation_query = upgrade_project.name
        oai_base = upgrade_project.oai_pmh_base_url
        iiif_endpoint = upgrade_project.iiif_search_endpoint
        archive_id, up_id = None, upgrade_project.id

    summary = ProbeSummary(
        target_kind=kind,
        target_slug=slug,
        status="failed",
        archive_id=archive_id,
        upgrade_project_id=up_id,
        dry_run=dry_run,
        started_at=now,
    )

    try:
        signals = collect_signals(
            canonical_url=canonical_url,
            citation_query=citation_query,
            now=now,
            oai_pmh_base_url=oai_base,
            iiif_search_endpoint=iiif_endpoint,
        )
    except Exception as exc:  # noqa: BLE001 — collect_signals shouldn't raise
        summary.notes = f"signal collection aborted: {exc}"
        summary.finished_at = _utcnow()
        log.error("probe %s aborted: %s", slug, exc)
        return summary

    y1, y2 = _prior_directory_counts(
        archive_id=archive_id, upgrade_project_id=up_id, now=now
    )
    facets = composite_facets(signals, now=now, count_12m_ago=y1, count_24m_ago=y2)

    summary.web_ops_health = facets["web_ops_health"]
    summary.external_preservation = facets["external_preservation"]
    summary.growth_signal = facets["growth_signal"]
    summary.prior_use_signal = facets["prior_use_signal"]
    summary.signal_errors = list(signals.errors)
    summary.signal_notes = list(signals.notes)
    summary.status = "partial" if signals.errors else "ok"

    if dry_run:
        summary.finished_at = _utcnow()
        _log_summary(summary)
        return summary

    notes = json.dumps(
        {
            "robots_ok": signals.robots_ok,
            "newest_wayback_age_days": signals.newest_wayback_age_days,
            "citation_query": citation_query,
            "signal_errors": signals.errors,
            "signal_notes": signals.notes,
        },
        ensure_ascii=False,
    )

    row = ProbeResult(
        archive_id=archive_id,
        upgrade_project_id=up_id,
        probed_at=now,
        canonical_url=canonical_url,
        https_valid=signals.https_valid,
        cert_expires_at=signals.cert_expires_at,
        canonical_http_status=signals.canonical_http_status,
        interior_url_sample=json.dumps(signals.interior_url_sample, ensure_ascii=False),
        interior_http_statuses=json.dumps(signals.interior_http_statuses),
        oai_pmh_identify_ok=signals.oai_pmh_identify_ok,
        oai_pmh_earliest_datestamp=signals.oai_pmh_earliest_datestamp,
        iiif_search_endpoint_ok=signals.iiif_search_endpoint_ok,
        wayback_home_count=signals.wayback_home_count,
        wayback_interior_hit_ratio=signals.wayback_interior_hit_ratio,
        directory_url_count_now=signals.directory_url_count_now,
        directory_url_count_12m_ago=y1,
        directory_url_count_24m_ago=y2,
        citation_count_crossref=signals.citation_count_crossref,
        citation_count_semantic_scholar=signals.citation_count_semantic_scholar,
        web_ops_health=facets["web_ops_health"],
        external_preservation=facets["external_preservation"],
        growth_signal=facets["growth_signal"],
        prior_use_signal=facets["prior_use_signal"],
        probe_version=PROBE_VERSION,
        probe_notes=notes,
    )
    db.session.add(row)
    db.session.flush()
    summary.probe_result_id = row.id

    if archive is not None:
        for facet in _FACET_KEYS:
            value = facets[facet]
            if value is not None:
                set_probe_facet_value(
                    archive=archive, facet=facet, value=value, now=now
                )
        archive.last_probed_at = now

    db.session.commit()
    summary.finished_at = _utcnow()
    _log_summary(summary)
    return summary


def run_all_probes(
    *,
    include_upgrade_projects: bool = False,
    dry_run: bool = False,
    now: datetime | None = None,
) -> list[ProbeSummary]:
    summaries: list[ProbeSummary] = []
    for archive in db.session.scalars(select(Archive).order_by(Archive.slug)):
        summaries.append(run_probe(archive=archive, dry_run=dry_run, now=now))
    if include_upgrade_projects:
        for up in db.session.scalars(
            select(UpgradeProject).order_by(UpgradeProject.slug)
        ):
            summaries.append(run_probe(upgrade_project=up, dry_run=dry_run, now=now))
    return summaries


def load_archive(slug: str) -> Archive | None:
    return db.session.scalar(select(Archive).where(Archive.slug == slug))


def load_upgrade_project(slug: str) -> UpgradeProject | None:
    return db.session.scalar(select(UpgradeProject).where(UpgradeProject.slug == slug))


def list_probe_targets(
    *, include_upgrade_projects: bool = False
) -> tuple[list[Archive], list[UpgradeProject]]:
    archives = list(db.session.scalars(select(Archive).order_by(Archive.slug)))
    ups: list[UpgradeProject] = []
    if include_upgrade_projects:
        ups = list(
            db.session.scalars(select(UpgradeProject).order_by(UpgradeProject.slug))
        )
    return archives, ups


def _log_summary(summary: ProbeSummary) -> None:
    log.info(
        "probe %s/%s status=%s web_ops=%s preservation=%s growth=%s "
        "prior_use=%s errors=%d notes=%d dry_run=%s",
        summary.target_kind,
        summary.target_slug,
        summary.status,
        summary.web_ops_health,
        summary.external_preservation,
        summary.growth_signal,
        summary.prior_use_signal,
        len(summary.signal_errors),
        len(summary.signal_notes),
        summary.dry_run,
    )
