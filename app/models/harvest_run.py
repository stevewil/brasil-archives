"""HarvestRun model — one row per invocation of the OAI-PMH harvester.

See ``docs/harvest-design.md`` for the full contract.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db

if TYPE_CHECKING:  # pragma: no cover
    from .aggregated_record import AggregatedRecord
    from .harvest_error import HarvestError
    from .upgrade_project import UpgradeProject


# Enforced editorially in service layer, not as a CHECK constraint, to keep
# migrations simple. See app/services/harvest.py.
STATUS_RUNNING = "running"
STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"

# Where the records came from.
SOURCE_OAI_PMH = "oai_pmh"
SOURCE_STATIC_EXPORT = "static_export"


class HarvestRun(db.Model):
    """One harvest invocation against one upgrade project."""

    __tablename__ = "harvest_runs"
    # Per-source schema — see AggregatedRecord / docs/project-schema-design.md.
    __table_args__ = ({"schema": "source"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upgrade_project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("upgrade_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metadata_prefix: Mapped[str] = mapped_column(String, nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String, nullable=False)

    records_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_upserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    from_ts: Mapped[str | None] = mapped_column(String)
    until_ts: Mapped[str | None] = mapped_column(String)

    source: Mapped[str] = mapped_column(String, nullable=False, default=SOURCE_OAI_PMH)
    notes: Mapped[str | None] = mapped_column(Text)

    upgrade_project: Mapped["UpgradeProject"] = relationship("UpgradeProject")
    errors: Mapped[list["HarvestError"]] = relationship(
        "HarvestError",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    records: Mapped[list["AggregatedRecord"]] = relationship(
        "AggregatedRecord",
        back_populates="harvest_run",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<HarvestRun id={self.id} project={self.upgrade_project_id} "
            f"prefix={self.metadata_prefix} status={self.status}>"
        )
