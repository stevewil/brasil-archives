"""Identify verb (§4.2)."""
from __future__ import annotations

from xml.etree import ElementTree as ET

from .constants import (
    DELETED_RECORD,
    GRANULARITY,
    OAI_IDENTIFIER_NS,
    OAI_IDENTIFIER_SCHEMA_LOCATION,
    OAI_NS,
    OAI_XSI,
    PROTOCOL_VERSION,
)
from .envelope import oai_base_url, oai_config, sub
from .identifiers import sample_identifier
from .queries import earliest_datestamp


def build_identify() -> ET.Element:
    cfg = oai_config()
    root = ET.Element(f"{{{OAI_NS}}}Identify")
    sub(root, "repositoryName", cfg["repository_name"])
    sub(root, "baseURL", oai_base_url())
    sub(root, "protocolVersion", PROTOCOL_VERSION)
    sub(root, "adminEmail", cfg["admin_email"])
    sub(root, "earliestDatestamp", earliest_datestamp())
    sub(root, "deletedRecord", DELETED_RECORD)
    sub(root, "granularity", GRANULARITY)

    description = sub(root, "description")
    oai_ident = ET.SubElement(
        description,
        f"{{{OAI_IDENTIFIER_NS}}}oai-identifier",
        {f"{{{OAI_XSI}}}schemaLocation": OAI_IDENTIFIER_SCHEMA_LOCATION},
    )
    sub(oai_ident, "scheme", "oai", ns=OAI_IDENTIFIER_NS)
    sub(oai_ident, "repositoryIdentifier", cfg["repository_identifier"],
        ns=OAI_IDENTIFIER_NS)
    sub(oai_ident, "delimiter", ":", ns=OAI_IDENTIFIER_NS)
    sub(oai_ident, "sampleIdentifier", sample_identifier(), ns=OAI_IDENTIFIER_NS)
    return root
