"""BuildJob / BuildReport — the archive-miner work queue.

The miner (``packages/archive-miner``) runs *outside* this app — on the dev
box or a cloud runner — because a corpus build is a long, resumable job and
cPanel cannot host a persistent worker (harness doc §4.3). This app owns the
**queue and the status surface**: ``/admin/builds`` enqueues a job and reads
its progress; the worker claims ``queued`` rows, heartbeats, checkpoints, and
writes progress back here.

One ``BuildJob`` is a run of a stage state machine
(``triage → enumerate → fetch → structure → [ocr] → extract → freeze →
deploy``). ``checkpoint`` is an opaque per-stage cursor so a pause or crash
resumes mid-stage. The mined data itself lives in a per-corpus ``build``
schema in the corpus cluster, not here.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    pass

# --- kind: what the job does -----------------------------------------------
KIND_BUILD = "build"      # a new corpus from an archives row
KIND_SYNC = "sync"        # re-run against an existing project's manifest

# --- construction mode (harness doc §3) ----------------------------------
MODE_A = "A"              # metadata audit (DSpace / AtoM / OAI-PMH)
MODE_B = "B"              # assembly from catalogs + literature
MODE_C = "C"              # OCR-first (pile of page images)

# --- stages (the fixed spine) -------------------------------------------
STAGES: tuple[str, ...] = (
    "triage", "enumerate", "fetch", "structure", "ocr", "extract",
    "freeze", "deploy",
)

# --- status ------------------------------------------------------------
ST_QUEUED = "queued"
ST_RUNNING = "running"
ST_PAUSE_REQUESTED = "pause_requested"   # operator asked; worker will stop cleanly
ST_PAUSED = "paused"
ST_BLOCKED = "blocked_on_human"          # ambiguity / rights / confidence gate
ST_DONE = "done"
ST_FAILED = "failed"
ST_CANCELLED = "cancelled"

ACTIVE_STATUSES = frozenset({ST_QUEUED, ST_RUNNING, ST_PAUSE_REQUESTED})
TERMINAL_STATUSES = frozenset({ST_DONE, ST_FAILED, ST_CANCELLED})


class BuildJob(TimestampMixin, db.Model):
    """One archive-miner job."""

    __tablename__ = "build_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    kind: Mapped[str] = mapped_column(String, nullable=False, default=KIND_BUILD)
    construction_mode: Mapped[str | None] = mapped_column(String)

    # Exactly one is the anchor: a source archive (build) or a project (sync).
    archive_slug: Mapped[str | None] = mapped_column(String, index=True)
    project_slug: Mapped[str | None] = mapped_column(String, index=True)

    stage: Mapped[str] = mapped_column(String, nullable=False, default="triage")
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=ST_QUEUED, index=True
    )

    # Opaque per-stage resume cursor; {stage: {...}} written by the handler.
    checkpoint: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {done, total, unit, rate_per_min} for the current stage.
    progress: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Freeform build options (scope filters, adapter hints, model overrides).
    options: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    budget_usd: Mapped[float | None] = mapped_column(Numeric(10, 4))
    spent_usd: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)

    # The corpus-cluster database holding this job's ``build`` schema. Just a
    # name; the worker resolves credentials from its own config.
    build_db_name: Mapped[str | None] = mapped_column(String)

    worker_id: Mapped[str | None] = mapped_column(String)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    eta_at: Mapped[datetime | None] = mapped_column(DateTime)

    operator_note: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)

    reports: Mapped[list["BuildReport"]] = relationship(
        "BuildReport", back_populates="job", cascade="all, delete-orphan",
        order_by="BuildReport.at",
    )

    @property
    def anchor(self) -> str:
        return self.project_slug or self.archive_slug or f"job-{self.id}"

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<BuildJob id={self.id} {self.kind} {self.anchor} "
            f"stage={self.stage} status={self.status}>"
        )


class BuildReport(db.Model):
    """A point-in-time snapshot of a job's status.

    Written every ~30 min while a job runs (and on every stage transition), so
    the admin UI can show history and the >1h management report has a trail.
    """

    __tablename__ = "build_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("build_jobs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=db.func.current_timestamp()
    )
    stage: Mapped[str] = mapped_column(String, nullable=False)
    # The full status dict at this moment (see archive_miner.report.status).
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Optional natural-language paragraph (a cheap-model summary).
    summary: Mapped[str | None] = mapped_column(Text)

    job: Mapped["BuildJob"] = relationship("BuildJob", back_populates="reports")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BuildReport job={self.job_id} at={self.at} stage={self.stage}>"
