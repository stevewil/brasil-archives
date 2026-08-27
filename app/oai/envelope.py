"""OAI-PMH XML envelope + shared XML helpers.

Every response (success or error) uses the same ``<OAI-PMH>`` envelope.
This module owns envelope construction, the ``<responseDate>`` stamp, the
``<request>`` echo, and the Flask ``Response`` wrapper. Verb modules build
their content as an ``ElementTree.Element`` and hand it back here.

Uses ``xml.etree.ElementTree`` from the stdlib — same choice as
``app/services/oai_client.py`` and mipibu's provider — to keep deploy
friction low on cPanel.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Union
from xml.etree import ElementTree as ET

from flask import Response, current_app, request

from .constants import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_PAGE_SIZE,
    DEFAULT_REPOSITORY_IDENTIFIER,
    DEFAULT_REPOSITORY_NAME,
    OAI_IDENTIFIER_NS,
    OAI_NS,
    OAI_SCHEMA_LOCATION,
    OAI_XSI,
)

# Args echoed back on <request> per OAI-PMH §3.1.1.
_REQUEST_ATTRS = (
    "verb",
    "identifier",
    "metadataPrefix",
    "from",
    "until",
    "set",
    "resumptionToken",
)


def utc_now_stamp() -> str:
    """ISO-8601 UTC datetime, seconds granularity, ``Z`` suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def oai_config() -> dict:
    """Deployment identity for the provider, from ``app.config`` with defaults."""
    cfg = current_app.config
    return {
        "repository_name": cfg.get("OAI_REPOSITORY_NAME", DEFAULT_REPOSITORY_NAME),
        "repository_identifier": cfg.get(
            "OAI_REPOSITORY_IDENTIFIER", DEFAULT_REPOSITORY_IDENTIFIER
        ),
        "admin_email": cfg.get("OAI_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL),
        "page_size": int(cfg.get("OAI_PAGE_SIZE", DEFAULT_PAGE_SIZE)),
    }


def oai_base_url() -> str:
    """Absolute URL of this OAI endpoint (the value for ``<request>``/baseURL)."""
    # request.url_root already ends with '/'.
    return request.url_root.rstrip("/") + "/oai"


def request_args() -> dict:
    """Known OAI args from the current request (GET query or POST form)."""
    src = request.values
    return {k: src.get(k) for k in _REQUEST_ATTRS if src.get(k)}


def raw_arg_names() -> set[str]:
    """Every argument name the caller sent, known or not (for badArgument)."""
    return set(request.values.keys())


def _register_namespaces() -> None:
    ET.register_namespace("", OAI_NS)
    ET.register_namespace("xsi", OAI_XSI)
    ET.register_namespace("oai-identifier", OAI_IDENTIFIER_NS)


def build_envelope(
    verb_content: Union[ET.Element, Iterable[ET.Element], None],
    *,
    request_args: dict | None = None,
) -> ET.Element:
    """Build ``<OAI-PMH>`` with responseDate, request echo, and content."""
    _register_namespaces()
    root = ET.Element(
        f"{{{OAI_NS}}}OAI-PMH",
        {f"{{{OAI_XSI}}}schemaLocation": OAI_SCHEMA_LOCATION},
    )

    ET.SubElement(root, f"{{{OAI_NS}}}responseDate").text = utc_now_stamp()

    request_el = ET.SubElement(root, f"{{{OAI_NS}}}request")
    request_el.text = oai_base_url()
    for key in _REQUEST_ATTRS:
        value = (request_args or {}).get(key)
        if value:
            request_el.set(key, value)

    if verb_content is None:
        return root
    if isinstance(verb_content, ET.Element):
        root.append(verb_content)
    else:
        for el in verb_content:
            root.append(el)
    return root


def xml_response(root: ET.Element, status: int = 200) -> Response:
    """Serialize an element tree and wrap it in a Flask ``Response``."""
    body = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
        short_empty_elements=True,
    )
    return Response(body, status=status, content_type="text/xml; charset=utf-8")


def sub(
    parent: ET.Element,
    tag: str,
    text: str | None = None,
    ns: str = OAI_NS,
    **attrs: str,
) -> ET.Element:
    """``ET.SubElement`` in a namespace, with optional text + attributes."""
    el = ET.SubElement(parent, f"{{{ns}}}{tag}", {k: v for k, v in attrs.items()})
    if text is not None:
        el.text = text
    return el
