"""Join tables for multi-select facets.

These are declared as Core ``Table`` objects rather than ORM classes
because they carry no columns beyond the composite primary key.
"""
from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, Table

from ..extensions import db


metadata = db.metadata


archive_periods = Table(
    "archive_periods",
    metadata,
    Column("archive_id", Integer, ForeignKey("archives.id"), primary_key=True),
    Column("period_id", Integer, ForeignKey("periods.id"), primary_key=True),
)

archive_record_types = Table(
    "archive_record_types",
    metadata,
    Column("archive_id", Integer, ForeignKey("archives.id"), primary_key=True),
    Column("record_type_id", Integer, ForeignKey("record_types.id"), primary_key=True),
)

archive_themes = Table(
    "archive_themes",
    metadata,
    Column("archive_id", Integer, ForeignKey("archives.id"), primary_key=True),
    Column("theme_id", Integer, ForeignKey("themes.id"), primary_key=True),
)

upgrade_project_periods = Table(
    "upgrade_project_periods",
    metadata,
    Column("upgrade_project_id", Integer, ForeignKey("upgrade_projects.id"), primary_key=True),
    Column("period_id", Integer, ForeignKey("periods.id"), primary_key=True),
)

upgrade_project_record_types = Table(
    "upgrade_project_record_types",
    metadata,
    Column("upgrade_project_id", Integer, ForeignKey("upgrade_projects.id"), primary_key=True),
    Column("record_type_id", Integer, ForeignKey("record_types.id"), primary_key=True),
)
