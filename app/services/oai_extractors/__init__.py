"""Format-specific extractors for OAI-PMH metadata payloads.

Each extractor is a pure function taking the payload Element (the child
of <metadata>, e.g. <oai_dc:dc> or <ead>) and returning a JSON-safe
dict shaped as::

    {"canonical": {...}, "raw": {...}}

See ``docs/harvest-design.md`` §Extractor contract.
"""
from __future__ import annotations

from typing import Callable
from xml.etree import ElementTree as ET

from . import oai_dc, oai_ead

Extractor = Callable[[ET.Element], dict]

REGISTRY: dict[str, Extractor] = {
    "oai_dc": oai_dc.extract,
    "oai_ead": oai_ead.extract,
}


def extract(prefix: str, payload: ET.Element) -> dict:
    """Route to the extractor registered for the given metadataPrefix."""
    try:
        fn = REGISTRY[prefix]
    except KeyError as exc:
        raise ValueError(f"no extractor registered for prefix {prefix!r}") from exc
    return fn(payload)


__all__ = ["Extractor", "REGISTRY", "extract"]
