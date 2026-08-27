"""ListSets verb (§4.3) + set-spec parsing.

brasil-archives exposes a single record kind (``Archive`` rows). Sets
partition it along the slices a harvester is most likely to want:

    state:<CODE>              e.g. state:RN
    itype:<slug>             e.g. itype:federal-university
    content:digital          archives with digital holdings
    content:no-digital       archives with no digital content (yet)

Sets are flat (no nesting). setNames are bilingual (xml:lang pt + en) per
OAI-PMH §2.6.
"""
from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

from .constants import (
    OAI_NS,
    SET_SCHEME_CONTENT,
    SET_SCHEME_ITYPE,
    SET_SCHEME_STATE,
    XML_NS,
)
from .envelope import sub
from .errors import OaiError

_SCHEMES = frozenset({SET_SCHEME_STATE, SET_SCHEME_ITYPE, SET_SCHEME_CONTENT})
_CONTENT_VALUES = frozenset({"digital", "no-digital"})


@dataclass(frozen=True)
class ParsedSet:
    scheme: str
    value: str


def parse_set_spec(spec: str | None) -> ParsedSet | None:
    """Parse a ``setSpec`` string. ``None``/empty → no set filter.

    Well-formed but unknown values (e.g. ``state:ZZ``) parse fine and just
    match zero records downstream; the caller decides whether that is
    ``noRecordsMatch``. Only structurally malformed specs raise
    ``badArgument``.
    """
    if not spec:
        return None
    parts = spec.split(":")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise OaiError("badArgument", f"malformed set: {spec!r}")
    scheme, value = parts
    if scheme not in _SCHEMES:
        raise OaiError("badArgument", f"unknown set scheme: {scheme!r}")
    if scheme == SET_SCHEME_CONTENT and value not in _CONTENT_VALUES:
        raise OaiError("badArgument", f"unknown content set: {value!r}")
    return ParsedSet(scheme=scheme, value=value)


def _emit_set(root: ET.Element, spec: str, name_pt: str, name_en: str) -> None:
    s = sub(root, "set")
    sub(s, "setSpec", spec)
    n_pt = sub(s, "setName", name_pt)
    n_pt.set(f"{{{XML_NS}}}lang", "pt")
    n_en = sub(s, "setName", name_en)
    n_en.set(f"{{{XML_NS}}}lang", "en")


def build_list_sets() -> ET.Element:
    """Build ``<ListSets>``. Not paginated — the set space is tiny."""
    # Imported here to avoid a circular import (queries imports sets).
    from .queries import (
        content_splits_in_use,
        distinct_states,
        institutional_types_in_use,
    )

    root = ET.Element(f"{{{OAI_NS}}}ListSets")

    for code in distinct_states():
        _emit_set(
            root,
            f"{SET_SCHEME_STATE}:{code}",
            f"Instituições no estado de {code}",
            f"Institutions in {code}",
        )

    for itype in institutional_types_in_use():
        _emit_set(
            root,
            f"{SET_SCHEME_ITYPE}:{itype.slug}",
            f"Tipo institucional: {itype.label_pt or itype.label_en}",
            f"Institutional type: {itype.label_en or itype.label_pt}",
        )

    labels = {
        "digital": ("Com acervo digital", "With digital holdings"),
        "no-digital": ("Sem conteúdo digital", "No digital content"),
    }
    for value in content_splits_in_use():
        pt, en = labels[value]
        _emit_set(root, f"{SET_SCHEME_CONTENT}:{value}", pt, en)

    return root
