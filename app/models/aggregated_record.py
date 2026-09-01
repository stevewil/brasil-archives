"""AggregatedRecord model — one harvested OAI-PMH record.

Stored hybrid: raw ``<record>`` XML for future re-parsing plus a
format-specific ``extracted_json`` dict. See ``docs/harvest-design.md``
§Data model for the full contract.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db

if TYPE_CHECKING:  # pragma: no cover
    from .harvest_run import HarvestRun
    from .upgrade_project import UpgradeProject


class AggregatedRecord(db.Model):
    """One harvested OAI-PMH record from an upgrade project."""

    __tablename__ = "aggregated_records"
    # Per-source schema: "source" is a symbolic placeholder, rewritten at
    # runtime to src_<slug> on Postgres and collapsed to the single
    # namespace on SQLite. See app/services/sources.py and
    # docs/partner-schema-design.md.
    __table_args__ = (
        UniqueConstraint(
            "upgrade_project_id",
            "oai_identifier",
            "metadata_prefix",
            name="uq_aggregated_records_identity",
        ),
        Index(
            "ix_aggregated_records_project_datestamp",
            "upgrade_project_id",
            "datestamp",
        ),
        Index("ix_aggregated_records_sha", "raw_xml_sha256"),
        {"schema": "source"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Cross-schema FK to the registry — left unqualified so it matches the
    # UpgradeProject mapper (schema None) and resolves via search_path=public
    # on Postgres. Within-source FKs below use the "source." prefix.
    upgrade_project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("upgrade_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    oai_identifier: Mapped[str] = mapped_column(String, nullable=False)
    metadata_prefix: Mapped[str] = mapped_column(String, nullable=False)

    datestamp: Mapped[str] = mapped_column(String, nullable=False)

    # Serialized JSON list[str] of setSpecs from the record header.
    # TEXT for SQLite portability; loaded by the service layer.
    set_specs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # The <record> element serialized verbatim (includes header + metadata).
    raw_xml: Mapped[str] = mapped_column(Text, nullable=False)
    raw_xml_sha256: Mapped[str] = mapped_column(String, nullable=False)

    # Format-specific extractor output; see app/services/oai_extractors/.
    extracted_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    harvest_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("source.harvest_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    upgrade_project: Mapped["UpgradeProject"] = relationship("UpgradeProject")
    harvest_run: Mapped["HarvestRun"] = relationship(
        "HarvestRun", back_populates="records"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AggregatedRecord project={self.upgrade_project_id} "
            f"id={self.oai_identifier} prefix={self.metadata_prefix}>"
        )
