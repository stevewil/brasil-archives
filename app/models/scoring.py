"""Scoring and facet history tables.

- :class:`DimensionScore` is history-bearing: new score → new row, old
  row keeps its data and gets ``superseded_at`` / ``superseded_by_id``.
- :class:`DimensionLift` records how an upgrade project lifts a
  dimension against its source archive.
- :class:`FacetValue` covers single-select facets that aren't derived
  from probes; multi-select facets use the join tables in :mod:`joins`.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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


_ACTIVE_ONLY = "superseded_at IS NULL"


class DimensionScore(db.Model):
    """One (archive, dimension) score revision. Historical."""

    __tablename__ = "dimension_scores"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 10", name="ck_dimension_scores_range"),
        CheckConstraint(
            "dimension IN ("
            "'accessibility',"
            "'provenance_curatorial',"
            "'corpus_completeness',"
            "'finding_aids',"
            "'pipeline_ingestion_readiness',"
            "'uniqueness_non_duplication',"
            "'scale',"
            "'linkage_potential'"
            ")",
            name="ck_dimension_scores_dimension",
        ),
        Index(
            "idx_dimension_scores_active",
            "archive_id",
            "dimension",
            sqlite_where=db.text(_ACTIVE_ONLY),
            postgresql_where=db.text(_ACTIVE_ONLY),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    archive_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("archives.id"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    justification_en: Mapped[str] = mapped_column(Text, nullable=False)
    justification_pt: Mapped[str | None] = mapped_column(Text)
    scored_by: Mapped[str | None] = mapped_column(String)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime)
    superseded_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("dimension_scores.id")
    )

    archive: Mapped["Archive"] = relationship("Archive")
    superseded_by: Mapped["DimensionScore | None"] = relationship(
        "DimensionScore", remote_side="DimensionScore.id"
    )

    def __repr__(self) -> str:
        return f"<DimensionScore archive={self.archive_id} {self.dimension}={self.score}>"


class DimensionLift(db.Model):
    """How an upgrade project lifts a dimension vs. its source archive."""

    __tablename__ = "dimension_lifts"
    __table_args__ = (
        CheckConstraint(
            "source_archive_score >= 0 AND source_archive_score <= 10",
            name="ck_dimension_lifts_source_range",
        ),
        CheckConstraint(
            "upgrade_score >= 0 AND upgrade_score <= 10",
            name="ck_dimension_lifts_upgrade_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upgrade_project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("upgrade_projects.id"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String, nullable=False)
    source_archive_score: Mapped[int] = mapped_column(Integer, nullable=False)
    upgrade_score: Mapped[int] = mapped_column(Integer, nullable=False)
    justification_en: Mapped[str] = mapped_column(Text, nullable=False)
    justification_pt: Mapped[str | None] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    upgrade_project: Mapped["UpgradeProject"] = relationship("UpgradeProject")

    def __repr__(self) -> str:
        return (
            f"<DimensionLift up={self.upgrade_project_id} "
            f"{self.dimension} {self.source_archive_score}->{self.upgrade_score}>"
        )


class FacetValue(db.Model):
    """Historical facet value for a single-select non-probe facet."""

    __tablename__ = "facet_values"
    __table_args__ = (
        Index(
            "idx_facet_values_active",
            "archive_id",
            "facet",
            sqlite_where=db.text(_ACTIVE_ONLY),
            postgresql_where=db.text(_ACTIVE_ONLY),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    archive_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("archives.id"), nullable=False
    )
    facet: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    set_by: Mapped[str | None] = mapped_column(String)
    set_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime)
    superseded_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("facet_values.id")
    )

    archive: Mapped["Archive"] = relationship("Archive")
    superseded_by: Mapped["FacetValue | None"] = relationship(
        "FacetValue", remote_side="FacetValue.id"
    )

    def __repr__(self) -> str:
        return f"<FacetValue archive={self.archive_id} {self.facet}={self.value}>"
