"""Federation client — Phase 2 of the federation-v1 prototype.

This module fetches federation-v1 responses from registered upgrade
projects (currently: mipibu) and caches them for 15 minutes in the
``federation_cache`` table. Its consumers are the archive detail pages
in ``app/blueprints/archives`` and offline scripts that inspect
federation health.

Key design points (see ``docs/scenario-driven-federation-model.md``):

* **Federation is an index, not a mirror.** brasil-archives calls the
  upgrade project on demand; it never proxies bulk content.
* **Cache is authoritative during the TTL.** No conditional GETs, no
  ETag negotiation in v1. Simplicity beats correctness on a 15-minute
  window when the underlying corpus is content-addressed.
* **Failure is normal.** Companion apps are resource-poor (cPanel,
  free tiers). If the upstream is slow or down we serve stale cache
  with a ``stale=True`` flag; if there is no cache at all, callers get
  ``FederationUnavailable`` and render a fallback message.
* **The service is stateless.** All state lives in the DB. This lets
  tests spin up an in-memory SQLite and call ``fetch_records`` without
  any global registration step.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping
from urllib.parse import quote, urlencode

import urllib.error
import urllib.request

from ..extensions import db
from ..models import FederationCache, UpgradeProject
from .sources import bind_source


log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CACHE_TTL_SECONDS = 15 * 60  # 15 minutes; hardcoded for Phase 2
HTTP_TIMEOUT_SECONDS = 8      # short so slow companions don't stall page loads
USER_AGENT = "brasil-archives/federation-client (+https://github.com/stevewil/brasil-archives)"
SUPPORTED_CONTRACT_VERSIONS = frozenset({"v1"})

# Federation query-grammar parameter names, per docs/federation-v1.md and
# mipibu's /api/schema. Ordered so cache keys are deterministic.
KNOWN_FEDERATION_PARAMS: tuple[str, ...] = (
    "q",
    "period_start",
    "period_end",
    "themes",
    "page",
    "page_size",
    "lang",
)


class FederationError(Exception):
    """Base class for federation client failures."""


class FederationUnavailable(FederationError):
    """Raised when the upstream is unreachable and no cache is available."""


class FederationContractError(FederationError):
    """Raised when the upstream returns an unrecognized contract version."""


# ---------------------------------------------------------------------------
# Return shape
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FederationResponse:
    """A federation-v1 response, either fresh or served from cache."""

    endpoint: str
    request_url: str
    status: int
    body: Mapping[str, Any]
    fetched_at: datetime
    expires_at: datetime
    from_cache: bool
    stale: bool
    contract_version: str | None = None
    corpus_version: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def age_seconds(self) -> int:
        return max(0, int((_utcnow() - self.fetched_at).total_seconds()))


# ---------------------------------------------------------------------------
# Public API — high-level convenience wrappers
# ---------------------------------------------------------------------------
def fetch_health(project: UpgradeProject) -> FederationResponse:
    """Fetch or cache-serve ``GET /api/health`` for ``project``."""
    return _fetch(project, endpoint="health", path="/health", params={})


def preview(project: UpgradeProject) -> dict[str, Any]:
    """Return a template-friendly summary of a live federation handshake.

    Never raises. Any failure yields ``{"available": False, "reason": ...}``
    so a downstream outage can't break the page that renders it. Consumed
    by the archive detail page and the home page's projects block.
    """
    if not project.json_api_base_url:
        return {"available": False, "reason": "not_registered"}
    try:
        health = fetch_health(project)
    except FederationError as exc:
        return {"available": False, "reason": str(exc)}
    return {
        "available": True,
        "record_count": health.body.get("record_count"),
        "contract_version": health.contract_version,
        "corpus_version": health.corpus_version,
        "from_cache": health.from_cache,
        "stale": health.stale,
        "deep_link_all": html_deep_link(project),
    }


def fetch_schema(project: UpgradeProject) -> FederationResponse:
    """Fetch or cache-serve ``GET /api/schema`` for ``project``."""
    return _fetch(project, endpoint="schema", path="/schema", params={})


def fetch_records(
    project: UpgradeProject,
    *,
    q: str | None = None,
    period_start: int | None = None,
    period_end: int | None = None,
    themes: Iterable[str] | None = None,
    page: int | None = None,
    page_size: int | None = None,
    lang: str | None = None,
) -> FederationResponse:
    """Fetch or cache-serve ``GET /api/records?<filters>`` for ``project``."""
    params = _clean_records_params(
        q=q,
        period_start=period_start,
        period_end=period_end,
        themes=themes,
        page=page,
        page_size=page_size,
        lang=lang,
    )
    return _fetch(project, endpoint="records", path="/records", params=params)


def fetch_record(project: UpgradeProject, record_id: str) -> FederationResponse:
    """Fetch or cache-serve ``GET /api/records/<id>`` for ``project``."""
    if not record_id or "/" in record_id:
        raise ValueError(f"invalid record_id: {record_id!r}")
    path = f"/records/{quote(record_id, safe='')}"
    return _fetch(project, endpoint="record", path=path, params={"record_id": record_id})


# ---------------------------------------------------------------------------
# Deep-link construction
# ---------------------------------------------------------------------------
def html_deep_link(
    project: UpgradeProject,
    *,
    period_start: int | None = None,
    period_end: int | None = None,
    themes: Iterable[str] | None = None,
    q: str | None = None,
) -> str | None:
    """Return an absolute URL to the companion app's HTML browse view for a
    filter set.

    The URL shape differs per project (mipibu ``/cases?year_from=…``, povos
    ``/documents?q=…``), so we don't construct it — we ask. Every
    federation-v1 ``/api/records`` response carries ``links.html`` pointing
    at the equivalent HTML view with the filters already applied. This
    fetches that (cached 15 min like every federation call) and returns it.

    Falls back to the project's site root on any failure — a valid link is
    always better than a 404. Returns ``None`` only when ``project`` has no
    primary URL at all.
    """
    base = (project.primary_url or "").rstrip("/")
    if not base:
        return None
    try:
        resp = fetch_records(
            project,
            period_start=period_start,
            period_end=period_end,
            themes=themes,
            q=q,
            page_size=1,
        )
        html = (resp.body.get("links") or {}).get("html")
        if isinstance(html, str) and html.startswith(("http://", "https://")):
            return html
    except FederationError:
        log.debug("html_deep_link: /api/records unavailable for %s", project.slug)
    return base


# ---------------------------------------------------------------------------
# Core fetch pipeline
# ---------------------------------------------------------------------------
def _fetch(
    project: UpgradeProject,
    *,
    endpoint: str,
    path: str,
    params: Mapping[str, Any],
) -> FederationResponse:
    """Cache-first fetch of a federation-v1 endpoint.

    Steps:

    1. Compute cache key.
    2. Look for a fresh (unexpired) cache row → return it.
    3. Otherwise call upstream. On success, upsert the cache row and return.
    4. On upstream failure, fall back to the last cache row (even if
       expired). If no cache row exists at all, raise ``FederationUnavailable``.
    """
    if not project.json_api_base_url:
        raise FederationUnavailable(
            f"project {project.slug!r} has no json_api_base_url configured"
        )

    # Route federation_cache reads/writes into this source's schema.
    bind_source(project.slug)

    base = project.json_api_base_url.rstrip("/")
    url = _build_url(base, path, params)
    key = _cache_key(endpoint, path, params)

    now = _utcnow()
    cached = _get_cache(project.id, key)
    if cached is not None and not cached.is_expired(now):
        return _from_cache_row(cached, request_url=url, endpoint=endpoint, stale=False)

    # Cache miss or expired — go upstream.
    try:
        body, status = _http_get_json(url)
    except FederationError as exc:
        if cached is not None:
            log.warning(
                "federation upstream failed; serving stale cache for %s %s",
                project.slug,
                endpoint,
            )
            return _from_cache_row(
                cached, request_url=url, endpoint=endpoint, stale=True
            )
        # No cache to fall back on — promote to FederationUnavailable so
        # callers can render "federated preview unavailable" without
        # having to pattern-match on the generic base class.
        raise FederationUnavailable(
            f"upstream unavailable for {project.slug!r} and no cache row exists: {exc}"
        ) from exc

    contract_version = _extract_contract_version(body)
    corpus_version = body.get("corpus_version") if endpoint == "health" else None

    if contract_version and contract_version not in SUPPORTED_CONTRACT_VERSIONS:
        # Refuse to cache a shape we don't understand.
        raise FederationContractError(
            f"unsupported federation_contract_version={contract_version!r} "
            f"from {project.slug!r}; expected one of {sorted(SUPPORTED_CONTRACT_VERSIONS)}"
        )

    fetched_at = now
    expires_at = fetched_at + timedelta(seconds=CACHE_TTL_SECONDS)
    _upsert_cache(
        project_id=project.id,
        key=key,
        endpoint=endpoint,
        url=url,
        body=body,
        status=status,
        fetched_at=fetched_at,
        expires_at=expires_at,
        contract_version=contract_version,
        corpus_version=corpus_version,
    )

    return FederationResponse(
        endpoint=endpoint,
        request_url=url,
        status=status,
        body=body,
        fetched_at=fetched_at,
        expires_at=expires_at,
        from_cache=False,
        stale=False,
        contract_version=contract_version,
        corpus_version=corpus_version,
        notes=list(body.get("notes", [])) if isinstance(body, dict) else [],
    )


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _http_get_json(url: str) -> tuple[dict, int]:
    """Perform a GET, return (parsed_body, status). Any failure raises FederationError."""
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            raw = response.read()
            status = response.getcode() or 0
    except urllib.error.HTTPError as exc:
        # 4xx/5xx — sometimes still parseable (e.g. federation 404 envelope).
        raw = exc.read() if hasattr(exc, "read") else b""
        status = exc.code
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            raise FederationError(f"HTTP {status} from {url}") from exc
        return body, status
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FederationError(f"network error fetching {url}: {exc}") from exc

    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise FederationError(f"non-JSON body from {url}: {exc}") from exc

    if not isinstance(body, dict):
        raise FederationError(f"unexpected JSON shape from {url}: {type(body).__name__}")
    return body, status


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
def _get_cache(project_id: int, key: str) -> FederationCache | None:
    return (
        db.session.query(FederationCache)
        .filter_by(upgrade_project_id=project_id, cache_key=key)
        .one_or_none()
    )


def _upsert_cache(
    *,
    project_id: int,
    key: str,
    endpoint: str,
    url: str,
    body: Mapping[str, Any],
    status: int,
    fetched_at: datetime,
    expires_at: datetime,
    contract_version: str | None,
    corpus_version: str | None,
) -> None:
    row = _get_cache(project_id, key)
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True)
    if row is None:
        row = FederationCache(
            upgrade_project_id=project_id,
            cache_key=key,
            endpoint=endpoint,
            request_url=url,
            response_json=payload,
            response_status=status,
            fetched_at=fetched_at,
            expires_at=expires_at,
            contract_version=contract_version,
            corpus_version=corpus_version,
        )
        db.session.add(row)
    else:
        row.endpoint = endpoint
        row.request_url = url
        row.response_json = payload
        row.response_status = status
        row.fetched_at = fetched_at
        row.expires_at = expires_at
        row.contract_version = contract_version
        row.corpus_version = corpus_version
    db.session.commit()


def _from_cache_row(
    row: FederationCache,
    *,
    request_url: str,
    endpoint: str,
    stale: bool,
) -> FederationResponse:
    body = json.loads(row.response_json)
    fetched_at = _ensure_utc(row.fetched_at)
    expires_at = _ensure_utc(row.expires_at)
    return FederationResponse(
        endpoint=endpoint,
        request_url=request_url,
        status=row.response_status,
        body=body,
        fetched_at=fetched_at,
        expires_at=expires_at,
        from_cache=True,
        stale=stale,
        contract_version=row.contract_version,
        corpus_version=row.corpus_version,
        notes=list(body.get("notes", [])) if isinstance(body, dict) else [],
    )


def _cache_key(endpoint: str, path: str, params: Mapping[str, Any]) -> str:
    """Deterministic sha256 over (endpoint, path, sorted params)."""
    canon = json.dumps(
        {"endpoint": endpoint, "path": path, "params": _canonicalize_params(params)},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _canonicalize_params(params: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Sort params and stringify values so the cache key is stable across dict orderings."""
    out: list[tuple[str, str]] = []
    for k in sorted(params.keys()):
        v = params[k]
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            for item in v:
                out.append((k, str(item)))
        else:
            out.append((k, str(v)))
    return out


# ---------------------------------------------------------------------------
# URL & param helpers
# ---------------------------------------------------------------------------
def _build_url(base: str, path: str, params: Mapping[str, Any]) -> str:
    """Compose a base + path + querystring URL for a federation call."""
    if not path.startswith("/"):
        path = "/" + path
    url = base + path
    pairs: list[tuple[str, str]] = []
    for k, v in params.items():
        if v is None:
            continue
        if k == "record_id":  # already in the path
            continue
        if isinstance(v, (list, tuple)):
            for item in v:
                pairs.append((k, str(item)))
        else:
            pairs.append((k, str(v)))
    if pairs:
        url = f"{url}?{urlencode(pairs, doseq=False)}"
    return url


def _clean_records_params(
    *,
    q: str | None,
    period_start: int | None,
    period_end: int | None,
    themes: Iterable[str] | None,
    page: int | None,
    page_size: int | None,
    lang: str | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if q:
        params["q"] = q
    if period_start is not None:
        params["period_start"] = int(period_start)
    if period_end is not None:
        params["period_end"] = int(period_end)
    theme_list = _normalize_themes(themes)
    if theme_list:
        params["themes"] = theme_list
    if page is not None:
        params["page"] = int(page)
    if page_size is not None:
        params["page_size"] = int(page_size)
    if lang:
        params["lang"] = lang
    return params


def _normalize_themes(themes: Iterable[str] | None) -> list[str]:
    if themes is None:
        return []
    if isinstance(themes, str):
        themes = [themes]
    cleaned: list[str] = []
    for t in themes:
        if t is None:
            continue
        s = str(t).strip()
        if s:
            cleaned.append(s)
    return cleaned


def _extract_contract_version(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    v = body.get("federation_contract_version")
    if isinstance(v, str) and v:
        return v
    return None


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
