"""OAI-PMH + EAG constants for the brasil-archives provider.

This is brasil-archives' *first* standards-native output surface. The
structure deliberately mirrors mipibu's ``app/oai/`` package (the reference
provider in this ecosystem) so a future extraction into a shared package
has an obvious seam. Values that are deployment identity (repository
identifier, admin email, page size) are read from ``app.config`` at request
time via :func:`app.oai.envelope.oai_config`; the rest are protocol
constants and live here.

See ``docs/oai-pmh-provider.md`` for the full design + the registry runbook.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------
PROTOCOL_VERSION = "2.0"
GRANULARITY = "YYYY-MM-DD"
DELETED_RECORD = "no"  # no soft-delete in schema-v1; see docs/oai-pmh-provider.md

# Floor datestamp for the (rare) archive row with no usable updated_at.
DATESTAMP_FLOOR = "2024-01-01"

OAI_NS = "http://www.openarchives.org/OAI/2.0/"
OAI_XSI = "http://www.w3.org/2001/XMLSchema-instance"
OAI_SCHEMA_LOCATION = (
    "http://www.openarchives.org/OAI/2.0/ "
    "http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd"
)

OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"
DC_NS = "http://purl.org/dc/elements/1.1/"
OAI_DC_SCHEMA_LOCATION = (
    "http://www.openarchives.org/OAI/2.0/oai_dc/ "
    "http://www.openarchives.org/OAI/2.0/oai_dc.xsd"
)

XML_NS = "http://www.w3.org/XML/1998/namespace"

OAI_IDENTIFIER_NS = "http://www.openarchives.org/OAI/2.0/oai-identifier"
OAI_IDENTIFIER_SCHEMA_LOCATION = (
    "http://www.openarchives.org/OAI/2.0/oai-identifier "
    "http://www.openarchives.org/OAI/2.0/oai-identifier.xsd"
)

# EAG 2012 — Encoded Archival Guide, the ISDIAH-aligned companion to EAD.
# Maintained by the Archives Portal Europe Foundation; originally the
# Censo-Guía de los Archivos de España e Iberoamérica.
EAG_NS = "http://www.archivesportaleurope.net/Portal/profiles/eag_2012/"
EAG_SCHEMA = "http://www.archivesportaleurope.net/Portal/profiles/eag_2012.xsd"
EAG_SCHEMA_LOCATION = f"{EAG_NS} {EAG_SCHEMA}"

# ---------------------------------------------------------------------------
# Repository identity — config keys + defaults
# ---------------------------------------------------------------------------
DEFAULT_REPOSITORY_NAME = "brasil-archives — Catálogo de arquivos digitais brasileiros"
DEFAULT_REPOSITORY_IDENTIFIER = "brasil-archives.from-bottom-to.top"
DEFAULT_ADMIN_EMAIL = "stevewil@gmail.com"
DEFAULT_PAGE_SIZE = 100

# ---------------------------------------------------------------------------
# Metadata formats
# ---------------------------------------------------------------------------
METADATA_FORMATS: dict[str, dict[str, str]] = {
    "oai_dc": {
        "schema": "http://www.openarchives.org/OAI/2.0/oai_dc.xsd",
        "namespace": OAI_DC_NS,
    },
    "eag": {
        "schema": EAG_SCHEMA,
        "namespace": EAG_NS,
    },
}
SUPPORTED_PREFIXES = frozenset(METADATA_FORMATS)

# ---------------------------------------------------------------------------
# Identifier scheme
# ---------------------------------------------------------------------------
# oai:<repositoryIdentifier>:archive:<slug>
ID_KIND_ARCHIVE = "archive"

# ---------------------------------------------------------------------------
# Sets
# ---------------------------------------------------------------------------
# brasil-archives exposes one record kind (Archive rows). Sets partition
# that kind along the two axes a harvester is most likely to want a slice
# of: home state and institutional type, plus a digital-content split.
SET_SCHEME_STATE = "state"          # state:RN
SET_SCHEME_ITYPE = "itype"          # itype:federal-university
SET_SCHEME_CONTENT = "content"      # content:digital | content:no-digital

# ---------------------------------------------------------------------------
# Verbs (OAI-PMH §4)
# ---------------------------------------------------------------------------
VERBS = frozenset({
    "Identify",
    "ListMetadataFormats",
    "ListSets",
    "ListIdentifiers",
    "ListRecords",
    "GetRecord",
})

VERB_ARGS: dict[str, dict[str, set[str]]] = {
    "Identify": {"required": set(), "optional": set()},
    "ListMetadataFormats": {"required": set(), "optional": {"identifier"}},
    "ListSets": {"required": set(), "optional": {"resumptionToken"}},
    "ListIdentifiers": {
        "required": {"metadataPrefix"},
        "optional": {"from", "until", "set", "resumptionToken"},
    },
    "ListRecords": {
        "required": {"metadataPrefix"},
        "optional": {"from", "until", "set", "resumptionToken"},
    },
    "GetRecord": {
        "required": {"identifier", "metadataPrefix"},
        "optional": set(),
    },
}

# ---------------------------------------------------------------------------
# Rights / provenance boilerplate carried in every record
# ---------------------------------------------------------------------------
METADATA_RIGHTS = (
    "Catalog metadata: CC BY-SA 4.0 (brasil-archives). "
    "Rights in the described holdings rest with the archival institution."
)
