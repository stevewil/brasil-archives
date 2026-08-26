"""HarvestError model — one row per per-record failure during a harvest.

See ``docs/harvest-design.md`` §Data model. HTTP-level failures abort a
run without producing error rows; per-record failures are logged here
and the run continues.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db

if TYPE_CHECKING:  # pragma: no cover
    from .harvest_run import HarvestRun


# Phase strings — enforced editorially in the service layer.
PHASE_PARSE = "parse"
PHASE_EXTRACT = "extract"
PHASE_UPSERT = "upsert"


class HarvestError(db.Model):
    """One per-record error during a harvest run."""

    __tablename__ = "harvest_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    harvest_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("harvest_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phase: Mapped[str] = mapped_column(String, nullable=False)
    oai_identifier: Mapped[str | None] = mapped_column(String)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    xml_excerpt: Mapped[str | None] = mapped_column(Text)

    run: Mapped["HarvestRun"] = relationship("HarvestRun", back_populates="errors")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<HarvestError run={self.harvest_run_id} phase={self.phase} "
            f"id={self.oai_identifier}>"
        )
