"""Controlled vocabularies.

Stored as tables so entries can be edited without schema migrations.
Populated by ``scripts/load_vocabularies.py`` from YAML files in
``configs/vocabularies/``.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db


class Period(db.Model):
    """A period tag (Burns/Skidmore 12-tag scheme)."""

    __tablename__ = "periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    label_en: Mapped[str] = mapped_column(String, nullable=False)
    label_pt: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    start_year: Mapped[int | None] = mapped_column(Integer)
    end_year: Mapped[int | None] = mapped_column(Integer)

    def __repr__(self) -> str:
        return f"<Period {self.slug}>"


class RecordType(db.Model):
    """A record-type tag (judicial, ecclesiastical, notarial, etc.)."""

    __tablename__ = "record_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    label_en: Mapped[str] = mapped_column(String, nullable=False)
    label_pt: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:
        return f"<RecordType {self.slug}>"


class Theme(db.Model):
    """A thematic tag. Provisional flag from algorithm-v1.md."""

    __tablename__ = "themes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    label_en: Mapped[str] = mapped_column(String, nullable=False)
    label_pt: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    provisional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<Theme {self.slug}>"


class InstitutionalType(db.Model):
    """Institutional-type facet (university, tribunal, church, state, etc.)."""

    __tablename__ = "institutional_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    label_en: Mapped[str] = mapped_column(String, nullable=False)
    label_pt: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:
        return f"<InstitutionalType {self.slug}>"
