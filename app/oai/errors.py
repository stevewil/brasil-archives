"""OAI-PMH protocol errors (§3.6).

Errors are emitted as ``<error code="...">`` children of the normal
envelope with HTTP 200 — transport errors (404/500) are outside the
protocol. Verb handlers ``raise OaiError(code, message)`` and the
dispatcher in ``__init__`` turns it into a response.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

from flask import Response

from .constants import OAI_NS
from .envelope import build_envelope, xml_response

VALID_CODES = frozenset({
    "badArgument",
    "badResumptionToken",
    "badVerb",
    "cannotDisseminateFormat",
    "idDoesNotExist",
    "noRecordsMatch",
    "noMetadataFormats",
    "noSetHierarchy",
})

# For these codes the OAI spec says to drop the echoed request args.
_CLEAR_ARGS_CODES = frozenset({"badVerb", "badArgument"})


class OaiError(Exception):
    """Raised inside a verb handler to abort with an OAI error response."""

    def __init__(self, code: str, message: str | None = None) -> None:
        if code not in VALID_CODES:  # pragma: no cover - programmer error
            raise AssertionError(f"invalid OAI error code: {code!r}")
        super().__init__(message or code)
        self.code = code
        self.message = message
        self.clear_request_args = code in _CLEAR_ARGS_CODES


def _error_element(code: str, message: str | None) -> ET.Element:
    el = ET.Element(f"{{{OAI_NS}}}error", {"code": code})
    if message:
        el.text = message
    return el


def oai_error_response(error: OaiError, request_args: dict | None = None) -> Response:
    args = {} if error.clear_request_args else (request_args or {})
    root = build_envelope(_error_element(error.code, error.message), request_args=args)
    return xml_response(root)
