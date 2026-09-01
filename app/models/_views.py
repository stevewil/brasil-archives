"""Read-only ORM models over the cross-source ``*_all`` UNION views.

These map ``public.aggregated_records_all`` / ``harvest_runs_all`` /
``harvest_errors_all`` — the union of every ``src_<slug>`` schema on
Postgres, or a JOIN over the single shared tables on SQLite (see
``app/services/sources.py::rebuild_source_views``).

They live on a **separate declarative base**, deliberately kept out of
``db.metadata``:

* ``db.create_all()`` / ``db.drop_all()`` never touch them (the views are
  built by ``rebuild_source_views``, not DDL from metadata).
* Alembic autogenerate never sees them.

Query them through ``db.session`` like any mapped class — the Session's
engine binding is what matters, not which metadata owns the table.

No relationships: use ``upgrade_project_id`` for a join or ``source_slug``
(the real ``UpgradeProject.slug``) as the cheap attribution key.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ViewBase(DeclarativeBase):
    """Isolated registry for the read-only view models."""


class AggregatedRecordView(ViewBase):
    __tablename__ = "aggregated_records_all"
    __table_args__ = {"info": {"is_view": True}}

    # composite PK: id is only unique within one src_<slug> schema
    source_slug: Mapped[str] = mapped_column(primary_key=True)
    id: Mapped[int] = mapped_column(primary_key=True)

    upgrade_project_id: Mapped[int]
    oai_identifier: Mapped[str]
    metadata_prefix: Mapped[str]
    datestamp: Mapped[str]
    set_specs_json: Mapped[str]
    raw_xml: Mapped[str]
    raw_xml_sha256: Mapped[str]
    extracted_json: Mapped[str]
    harvest_run_id: Mapped[int]
    first_seen_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]


class HarvestRunView(ViewBase):
    __tablename__ = "harvest_runs_all"
    __table_args__ = {"info": {"is_view": True}}

    source_slug: Mapped[str] = mapped_column(primary_key=True)
    id: Mapped[int] = mapped_column(primary_key=True)

    upgrade_project_id: Mapped[int]
    metadata_prefix: Mapped[str]
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    status: Mapped[str]
    records_seen: Mapped[int]
    records_upserted: Mapped[int]
    records_unchanged: Mapped[int]
    error_count: Mapped[int]
    from_ts: Mapped[str | None]
    until_ts: Mapped[str | None]
    source: Mapped[str]
    notes: Mapped[str | None]


class HarvestErrorView(ViewBase):
    __tablename__ = "harvest_errors_all"
    __table_args__ = {"info": {"is_view": True}}

    source_slug: Mapped[str] = mapped_column(primary_key=True)
    id: Mapped[int] = mapped_column(primary_key=True)

    harvest_run_id: Mapped[int]
    phase: Mapped[str]
    oai_identifier: Mapped[str | None]
    message: Mapped[str]
    xml_excerpt: Mapped[str | None]
