"""OAI-PMH 2.0 client — read-only, stateless, DB-free.

Consumed by ``app/services/harvest.py``. Provides just what the harvester
needs: Identify (for repository sanity), ListRecords with resumption
tokens, and iteration helpers. XML parsing uses ``xml.etree.ElementTree``.

See ``docs/harvest-design.md`` §OAI-PMH client contract for the full API.
"""
from __future__ import annotations

import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterator, Mapping
from xml.etree import ElementTree as ET


log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OAI_NS = "http://www.openarchives.org/OAI/2.0/"
NAMESPACES = {"oai": OAI_NS}

HTTP_TIMEOUT_SECONDS = 30  # Harvester runs off page-load path; be patient.
USER_AGENT = (
    "brasil-archives/harvester "
    "(+https://github.com/stevewil/brasil-archives)"
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class OaiError(Exception):
    """Base class for all OAI-PMH client errors."""


class OaiHTTPError(OaiError):
    """Non-2xx HTTP response, timeout, or connection failure."""


class OaiParseError(OaiError):
    """Response body was not well-formed XML or lacked <OAI-PMH>."""


class OaiProtocolError(OaiError):
    """Server returned <error code='badVerb'|'badArgument'>."""


class OaiUnsupportedError(OaiError):
    """Server returned <error code='cannotDisseminateFormat'|'noSetHierarchy'>."""


class OaiResumptionError(OaiError):
    """Server returned <error code='badResumptionToken'>."""


# noRecordsMatch is NOT an exception: it produces an empty iterator.
_FATAL_ERROR_CODES: Mapping[str, type[OaiError]] = {
    "badVerb": OaiProtocolError,
    "badArgument": OaiProtocolError,
    "cannotDisseminateFormat": OaiUnsupportedError,
    "noSetHierarchy": OaiUnsupportedError,
    "badResumptionToken": OaiResumptionError,
    "idDoesNotExist": OaiProtocolError,
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class IdentifyResult:
    repository_name: str
    base_url: str
    protocol_version: str
    earliest_datestamp: str | None
    deleted_record: str | None
    granularity: str | None
    admin_emails: tuple[str, ...]


@dataclass
class ListRecordsPage:
    """One <ListRecords> response worth of records + optional continuation."""
    records: list[ET.Element]
    resumption_token: str | None
    complete_list_size: int | None
    cursor: int | None


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _fetch(base_url: str, params: Mapping[str, str]) -> ET.Element:
    """Send a GET to base_url with query params. Return parsed root element."""
    qs = urllib.parse.urlencode(params)
    url = f"{base_url}?{qs}" if qs else base_url
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        raise OaiHTTPError(f"HTTP {exc.code} from {url}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise OaiHTTPError(f"Network error for {url}: {exc.reason}") from exc
    except TimeoutError as exc:  # pragma: no cover
        raise OaiHTTPError(f"Timeout after {HTTP_TIMEOUT_SECONDS}s: {url}") from exc

    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        excerpt = body[:500].decode("utf-8", errors="replace")
        raise OaiParseError(f"Malformed XML from {url}: {excerpt!r}") from exc

    if _localname(root.tag) != "OAI-PMH":
        raise OaiParseError(
            f"Expected <OAI-PMH> root, got <{_localname(root.tag)}> from {url}"
        )

    _raise_for_error(root, url=url)
    return root


def _localname(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def _raise_for_error(root: ET.Element, url: str) -> None:
    """Raise the mapped exception if the response contains a fatal <error>.

    Note: noRecordsMatch is intentionally not treated as fatal here; the
    caller sees an absent <ListRecords> element and returns an empty page.
    """
    errors = root.findall(f"{{{OAI_NS}}}error")
    for err in errors:
        code = err.get("code", "")
        message = (err.text or "").strip()
        if code == "noRecordsMatch":
            continue
        exc_cls = _FATAL_ERROR_CODES.get(code, OaiProtocolError)
        raise exc_cls(f"OAI error {code!r} from {url}: {message}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def identify(base_url: str) -> IdentifyResult:
    """Fetch the Identify response and return its parsed contents."""
    root = _fetch(base_url, {"verb": "Identify"})
    ident = root.find(f"{{{OAI_NS}}}Identify")
    if ident is None:
        raise OaiParseError(f"No <Identify> element in response from {base_url}")

    def _text(tag: str) -> str | None:
        el = ident.find(f"{{{OAI_NS}}}{tag}")
        return el.text.strip() if el is not None and el.text else None

    admin_emails = tuple(
        (el.text or "").strip()
        for el in ident.findall(f"{{{OAI_NS}}}adminEmail")
        if el.text
    )
    return IdentifyResult(
        repository_name=_text("repositoryName") or "",
        base_url=_text("baseURL") or base_url,
        protocol_version=_text("protocolVersion") or "",
        earliest_datestamp=_text("earliestDatestamp"),
        deleted_record=_text("deletedRecord"),
        granularity=_text("granularity"),
        admin_emails=admin_emails,
    )


def list_records(
    base_url: str,
    metadata_prefix: str,
    from_: str | None = None,
    until: str | None = None,
    set_: str | None = None,
    resumption_token: str | None = None,
) -> ListRecordsPage:
    """Fetch one page of ListRecords. Returns an empty page on noRecordsMatch.

    Per OAI-PMH §3.5, when a resumption_token is supplied, all other selective
    args must be omitted; this function enforces that on the caller's behalf.
    """
    if resumption_token is not None:
        params = {"verb": "ListRecords", "resumptionToken": resumption_token}
    else:
        params = {"verb": "ListRecords", "metadataPrefix": metadata_prefix}
        if from_:
            params["from"] = from_
        if until:
            params["until"] = until
        if set_:
            params["set"] = set_

    root = _fetch(base_url, params)
    lr = root.find(f"{{{OAI_NS}}}ListRecords")
    if lr is None:
        # noRecordsMatch or otherwise empty — return empty page.
        return ListRecordsPage(
            records=[], resumption_token=None,
            complete_list_size=None, cursor=None,
        )

    records = lr.findall(f"{{{OAI_NS}}}record")
    rt_el = lr.find(f"{{{OAI_NS}}}resumptionToken")
    next_token: str | None = None
    complete_list_size: int | None = None
    cursor: int | None = None
    if rt_el is not None:
        text = (rt_el.text or "").strip()
        next_token = text if text else None
        cls = rt_el.get("completeListSize")
        cur = rt_el.get("cursor")
        if cls is not None:
            try:
                complete_list_size = int(cls)
            except ValueError:  # pragma: no cover — server is broken if this fires
                complete_list_size = None
        if cur is not None:
            try:
                cursor = int(cur)
            except ValueError:  # pragma: no cover
                cursor = None

    return ListRecordsPage(
        records=records,
        resumption_token=next_token,
        complete_list_size=complete_list_size,
        cursor=cursor,
    )


def iterate_records(
    base_url: str,
    metadata_prefix: str,
    from_: str | None = None,
    until: str | None = None,
    set_: str | None = None,
    max_pages: int | None = None,
) -> Iterator[ET.Element]:
    """Follow resumption tokens and yield every <record> Element.

    ``max_pages`` is a safety valve for tests; ``None`` means no cap.
    """
    page = list_records(
        base_url, metadata_prefix,
        from_=from_, until=until, set_=set_,
    )
    pages_seen = 1
    for rec in page.records:
        yield rec

    while page.resumption_token:
        if max_pages is not None and pages_seen >= max_pages:
            log.warning("iterate_records hit max_pages=%d; stopping", max_pages)
            return
        page = list_records(
            base_url, metadata_prefix,
            resumption_token=page.resumption_token,
        )
        pages_seen += 1
        for rec in page.records:
            yield rec


# ---------------------------------------------------------------------------
# Helpers for callers that want to serialize a <record> back to bytes.
# ---------------------------------------------------------------------------
def record_to_xml(record: ET.Element) -> str:
    """Serialize a <record> Element to XML text, preserving namespaces."""
    return ET.tostring(record, encoding="unicode")


def record_header_fields(
    record: ET.Element,
) -> tuple[str | None, str | None, list[str]]:
    """Return (identifier, datestamp, [setSpecs]) from a <record>'s <header>."""
    header = record.find(f"{{{OAI_NS}}}header")
    if header is None:
        return None, None, []
    ident = header.findtext(f"{{{OAI_NS}}}identifier")
    stamp = header.findtext(f"{{{OAI_NS}}}datestamp")
    specs = [
        (el.text or "").strip()
        for el in header.findall(f"{{{OAI_NS}}}setSpec")
        if el.text
    ]
    return (
        ident.strip() if ident else None,
        stamp.strip() if stamp else None,
        specs,
    )


def record_metadata_element(record: ET.Element) -> ET.Element | None:
    """Return the child of <record>/<metadata> (e.g. <oai_dc:dc> or <ead>)."""
    md = record.find(f"{{{OAI_NS}}}metadata")
    if md is None:
        return None
    # metadata always has exactly one child per OAI spec, but be defensive.
    for child in md:
        return child
    return None
