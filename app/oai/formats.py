"""ListMetadataFormats verb (§4.4).

Every archive record supports both formats, so the response is identical
with or without an ``identifier`` (once the identifier is validated).
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

from .constants import METADATA_FORMATS, OAI_NS
from .envelope import sub
from .errors import OaiError
from .identifiers import parse_archive_slug
from .queries import get_public_archive


def build_list_metadata_formats(identifier: str | None = None) -> ET.Element:
    if identifier is not None:
        slug = parse_archive_slug(identifier)
        if get_public_archive(slug) is None:
            raise OaiError("idDoesNotExist", f"no archive for {identifier!r}")
    root = ET.Element(f"{{{OAI_NS}}}ListMetadataFormats")
    for prefix, spec in METADATA_FORMATS.items():
        fmt = sub(root, "metadataFormat")
        sub(fmt, "metadataPrefix", prefix)
        sub(fmt, "schema", spec["schema"])
        sub(fmt, "metadataNamespace", spec["namespace"])
    return root
