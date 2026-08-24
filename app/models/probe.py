"""ProbeResult model.

One row per probe run. Not overwritten — historical time series. Rows
attach to either an archive or an upgrade project (or both), enforced
by a CHECK constraint on the pair.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db

if TYPE_CHECKING:  # pragma: no cover
    from .archive import Archive
    from .upgrade_project import UpgradeProject


class ProbeResult(db.Model):
    """One probe run against an archive or upgrade project."""

    __tablename__ = "probe_results"
    __table_args__ = (
        CheckConstraint(
            "(archive_id IS NOT NULL) OR (upgrade_project_id IS NOT NULL)",
            name="ck_probe_results_target",
        ),
        Index("idx_probe_results_archive_time", "archive_id", "probed_at"),
        Index("idx_probe_results_upgrade_time", "upgrade_project_id", "probed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    archive_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("archives.id"))
    upgrade_project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("upgrade_projects.id")
    )
    probed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    # Web ops signals
    canonical_url: Mapped[str] = mapped_column(String, nullable=False)
    https_valid: Mapped[bool | None] = mapped_column(Boolean)
    cert_expires_at: Mapped[date | None] = mapped_column(Date)
    canonical_http_status: Mapped[int | None] = mapped_column(Integer)
    # JSON-encoded lists (kept as TEXT; parse in Python)
    interior_url_sample: Mapped[str | None] = mapped_column(Text)
    interior_http_statuses: Mapped[str | None] = mapped_column(Text)

    # OAI-PMH signals (upgrade projects)
    oai_pmh_identify_ok: Mapped[bool | None] = mapped_column(Boolean)
    oai_pmh_earliest_datestamp: Mapped[date | None] = mapped_column(Date)
    oai_pmh_record_count: Mapped[int | None] = mapped_column(Integer)

    # IIIF signal (upgrade projects)
    iiif_search_endpoint_ok: Mapped[bool | None] = mapped_column(Boolean)

    # External preservation
    wayback_home_count: Mapped[int | None] = mapped_column(Integer)
    wayback_interior_hit_ratio: Mapped[float | None] = mapped_column(Float)

    # Growth
    directory_url_count_now: Mapped[int | None] = mapped_column(Integer)
    directory_url_count_12m_ago: Mapped[int | None] = mapped_column(Integer)
    directory_url_count_24m_ago: Mapped[int | None] = mapped_column(Integer)

    # Prior use
    citation_count_crossref: Mapped[int | None] = mapped_column(Integer)
    citation_count_semantic_scholar: Mapped[int | None] = mapped_column(Integer)

    # Denormalized computed facet values (for query speed)
    web_ops_health: Mapped[str | None] = mapped_column(String)
    external_preservation: Mapped[str | None] = mapped_column(String)
    growth_signal: Mapped[str | None] = mapped_column(String)
    prior_use_signal: Mapped[str | None] = mapped_column(String)

    # Probe metadata
    probe_version: Mapped[str] = mapped_column(String, nullable=False)
    probe_notes: Mapped[str | None] = mapped_column(Text)

    archive: Mapped["Archive | None"] = relationship("Archive")
    upgrade_project: Mapped["UpgradeProject | None"] = relationship("UpgradeProject")

    def __repr__(self) -> str:
        target = f"archive={self.archive_id}" if self.archive_id else f"up={self.upgrade_project_id}"
        return f"<ProbeResult {target} at {self.probed_at}>"
