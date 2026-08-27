"""ListIdentifiers (§4.6), ListRecords (§4.5), GetRecord (§4.1).

The three verbs share query construction: filter ``Archive`` rows by an
optional set + optional datestamp range, then emit either ``<header>`` or
``<header>`` + ``<metadata>``.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

from ..models import Archive
from .constants import (
    OAI_NS,
    SET_SCHEME_CONTENT,
    SET_SCHEME_ITYPE,
    SET_SCHEME_STATE,
    SUPPORTED_PREFIXES,
)
from .dc import archive_to_dc
from .eag import archive_to_eag
from .envelope import oai_config, sub
from .errors import OaiError
from .identifiers import make_archive_id, parse_archive_slug
from .queries import (
    archive_datestamp,
    count_archives,
    get_public_archive,
    page_archives,
)
from .resumption import Token, decode
from .sets import ParsedSet, parse_set_spec


def _assert_datestamp(value: str | None, arg: str) -> None:
    if value is None:
        return
    parts = value.split("-")
    ok = (
        len(parts) == 3
        and len(parts[0]) == 4
        and len(parts[1]) == 2
        and len(parts[2]) == 2
        and all(p.isdigit() for p in parts)
    )
    if not ok:
        raise OaiError("badArgument", f"{arg} must be YYYY-MM-DD granularity")


def _resolve_query(
    metadata_prefix: str | None,
    set_: str | None,
    from_: str | None,
    until: str | None,
    resumption_token: str | None,
) -> tuple[Token, ParsedSet | None]:
    if resumption_token is not None:
        if any(v is not None for v in (metadata_prefix, set_, from_, until)):
            raise OaiError(
                "badArgument", "resumptionToken is exclusive with other arguments"
            )
        token = decode(resumption_token)
        if token.prefix not in SUPPORTED_PREFIXES:
            raise OaiError("badResumptionToken", "stale metadataPrefix in token")
        return token, parse_set_spec(token.set)

    if not metadata_prefix:
        raise OaiError("badArgument", "metadataPrefix is required")
    if metadata_prefix not in SUPPORTED_PREFIXES:
        raise OaiError(
            "cannotDisseminateFormat",
            f"metadataPrefix {metadata_prefix!r} is not supported",
        )
    _assert_datestamp(from_, "from")
    _assert_datestamp(until, "until")
    parsed_set = parse_set_spec(set_)
    total = count_archives(parsed_set, from_, until)
    token = Token(
        prefix=metadata_prefix,
        set=set_,
        from_=from_,
        until=until,
        cursor=0,
        total=total,
    )
    return token, parsed_set


def _set_specs(archive: Archive) -> list[str]:
    specs: list[str] = []
    if archive.home_state_code:
        specs.append(f"{SET_SCHEME_STATE}:{archive.home_state_code}")
    itype = archive.institutional_type
    if itype is not None:
        specs.append(f"{SET_SCHEME_ITYPE}:{itype.slug}")
    specs.append(
        f"{SET_SCHEME_CONTENT}:"
        + ("no-digital" if archive.no_digital_content else "digital")
    )
    return specs


def _header(archive: Archive) -> ET.Element:
    header = ET.Element(f"{{{OAI_NS}}}header")
    sub(header, "identifier", make_archive_id(archive.slug))
    sub(header, "datestamp", archive_datestamp(archive))
    for spec in _set_specs(archive):
        sub(header, "setSpec", spec)
    return header


def _metadata(archive: Archive, prefix: str) -> ET.Element:
    md = ET.Element(f"{{{OAI_NS}}}metadata")
    if prefix == "oai_dc":
        md.append(archive_to_dc(archive))
    elif prefix == "eag":
        md.append(archive_to_eag(archive))
    else:  # pragma: no cover - guarded upstream
        raise OaiError("cannotDisseminateFormat", f"unknown prefix {prefix!r}")
    return md


def _append_resumption_token(parent: ET.Element, token: Token, page_len: int) -> None:
    """Emit ``<resumptionToken>`` per §3.5.

    - Single-page result → no element at all.
    - More pages → element with the next token as text.
    - Last page of a multi-page result → empty element (attrs only).
    """
    next_cursor = token.cursor + page_len
    if token.cursor == 0 and next_cursor >= token.total:
        return
    rt = sub(parent, "resumptionToken")
    rt.set("completeListSize", str(token.total))
    rt.set("cursor", str(token.cursor))
    if next_cursor < token.total:
        rt.text = Token(
            prefix=token.prefix,
            set=token.set,
            from_=token.from_,
            until=token.until,
            cursor=next_cursor,
            total=token.total,
        ).to_wire()


def build_list_identifiers(
    metadata_prefix, set_, from_, until, resumption_token
) -> ET.Element:
    token, parsed_set = _resolve_query(
        metadata_prefix, set_, from_, until, resumption_token
    )
    if token.total == 0:
        raise OaiError("noRecordsMatch", "no records match the request")
    page_size = oai_config()["page_size"]
    rows = page_archives(parsed_set, token.from_, token.until, token.cursor, page_size)
    root = ET.Element(f"{{{OAI_NS}}}ListIdentifiers")
    for archive in rows:
        root.append(_header(archive))
    _append_resumption_token(root, token, len(rows))
    return root


def build_list_records(
    metadata_prefix, set_, from_, until, resumption_token
) -> ET.Element:
    token, parsed_set = _resolve_query(
        metadata_prefix, set_, from_, until, resumption_token
    )
    if token.total == 0:
        raise OaiError("noRecordsMatch", "no records match the request")
    page_size = oai_config()["page_size"]
    rows = page_archives(parsed_set, token.from_, token.until, token.cursor, page_size)
    root = ET.Element(f"{{{OAI_NS}}}ListRecords")
    for archive in rows:
        record = sub(root, "record")
        record.append(_header(archive))
        record.append(_metadata(archive, token.prefix))
    _append_resumption_token(root, token, len(rows))
    return root


def build_get_record(identifier: str, metadata_prefix: str) -> ET.Element:
    if metadata_prefix not in SUPPORTED_PREFIXES:
        raise OaiError(
            "cannotDisseminateFormat",
            f"metadataPrefix {metadata_prefix!r} is not supported",
        )
    slug = parse_archive_slug(identifier)
    archive = get_public_archive(slug)
    if archive is None:
        raise OaiError("idDoesNotExist", f"no archive for {identifier!r}")
    root = ET.Element(f"{{{OAI_NS}}}GetRecord")
    record = sub(root, "record")
    record.append(_header(archive))
    record.append(_metadata(archive, metadata_prefix))
    return root
