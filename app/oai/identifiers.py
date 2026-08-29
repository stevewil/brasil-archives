"""OAI identifier parsing + existence checks.

One identifier kind:

    oai:<repositoryIdentifier>:archive:<slug>

e.g. ``oai:brasil-archives.from-bottom-to.top:archive:rn-...-t1r8``
"""
from __future__ import annotations

from .constants import ID_KIND_ARCHIVE
from .envelope import oai_config
from .errors import OaiError


def make_archive_id(slug: str) -> str:
    repo = oai_config()["repository_identifier"]
    return f"oai:{repo}:{ID_KIND_ARCHIVE}:{slug}"


def parse_archive_slug(identifier: str) -> str:
    """Return the archive slug from an OAI identifier.

    Anything outside this repository's namespace raises ``idDoesNotExist``
    (harvester convention: "wrong repo prefix" == "not here").
    """
    repo = oai_config()["repository_identifier"]
    prefix = f"oai:{repo}:{ID_KIND_ARCHIVE}:"
    if not identifier or not identifier.startswith(prefix):
        raise OaiError("idDoesNotExist", f"unknown identifier: {identifier!r}")
    slug = identifier[len(prefix):]
    if not slug:
        raise OaiError("idDoesNotExist", "identifier has an empty slug")
    return slug


def sample_identifier() -> str:
    """A real, resolvable identifier for the ``Identify`` response.

    A harvester (and the OAI validator) will call ``GetRecord`` on this, so
    it must exist. Falls back to a placeholder only when the catalog is
    empty (fresh DB / tests)."""
    from .queries import first_public_archive_slug

    return make_archive_id(first_public_archive_slug() or "example-archive")
