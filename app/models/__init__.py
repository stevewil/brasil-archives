"""SQLAlchemy ORM models for brasil-archives.

Mirrors ``docs/schema-v1.md``. History-bearing tables retain
``superseded_at`` / ``superseded_by_id`` pointers so revisions are
auditable without destructive updates.
"""
from __future__ import annotations

from .aggregated_record import AggregatedRecord
from .archive import Archive
from .federation_cache import FederationCache
from .harvest_error import HarvestError
from .harvest_run import HarvestRun
from .upgrade_project import UpgradeProject
from .scoring import DimensionScore, DimensionLift, FacetValue
from .probe import ProbeResult
from .vocabularies import (
    Period,
    RecordType,
    Theme,
    InstitutionalType,
)
from .joins import (
    archive_periods,
    archive_record_types,
    archive_themes,
    upgrade_project_periods,
    upgrade_project_record_types,
)

# Allowed dimension slugs — kept aligned with algorithm-v1.md and the
# CHECK constraint in schema-v1.md.
DIMENSIONS: tuple[str, ...] = (
    "accessibility",
    "provenance_curatorial",
    "corpus_completeness",
    "finding_aids",
    "pipeline_ingestion_readiness",
    "uniqueness_non_duplication",
    "scale",
    "linkage_potential",
)

__all__ = [
    "AggregatedRecord",
    "Archive",
    "FederationCache",
    "HarvestError",
    "HarvestRun",
    "UpgradeProject",
    "DimensionScore",
    "DimensionLift",
    "FacetValue",
    "ProbeResult",
    "Period",
    "RecordType",
    "Theme",
    "InstitutionalType",
    "archive_periods",
    "archive_record_types",
    "archive_themes",
    "upgrade_project_periods",
    "upgrade_project_record_types",
    "DIMENSIONS",
]
