"""UpgradeProject model — a registered federation participant.

Per ``docs/federation-v1.md``, upgrade projects register via YAML under
``configs/upgrade_projects/<slug>.yaml`` and expose OAI-PMH (required)
plus optional IIIF Content Search / EAD / EAC-CPF endpoints.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .joins import upgrade_project_periods, upgrade_project_record_types
from .mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from .archive import Archive
    from .federation_cache import FederationCache
    from .vocabularies import Period, RecordType


class UpgradeProject(TimestampMixin, db.Model):
    """A registered upgrade project (e.g. Mipibu)."""

    __tablename__ = "upgrade_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    name_pt: Mapped[str | None] = mapped_column(String)

    # Source
    source_archive_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("archives.id"), nullable=False
    )
    scope_description_en: Mapped[str] = mapped_column(Text, nullable=False)
    scope_description_pt: Mapped[str | None] = mapped_column(Text)
    approximate_document_count: Mapped[int | None] = mapped_column(Integer)
    approximate_page_equivalents: Mapped[int | None] = mapped_column(Integer)

    # Delivery
    primary_url: Mapped[str] = mapped_column(String, nullable=False)
    source_repo: Mapped[str | None] = mapped_column(String)
    # Enforced editorially: in-development | beta | stable | deprecated
    delivery_status: Mapped[str] = mapped_column(String, nullable=False)

    # Federation contract (see docs/federation-v1.md)
    federation_contract_version: Mapped[str] = mapped_column(
        String, nullable=False, default="v1"
    )
    # Federation-v1 JSON contract endpoint (Phase 2). See mipibu
    # /api/{health,schema,records,records/<id>}. Nullable because a
    # project may register with OAI-PMH only (or static exports only).
    json_api_base_url: Mapped[str | None] = mapped_column(String)
    oai_pmh_base_url: Mapped[str | None] = mapped_column(String)
    iiif_search_endpoint: Mapped[str | None] = mapped_column(String)
    ead_export_url: Mapped[str | None] = mapped_column(String)
    eac_cpf_export_url: Mapped[str | None] = mapped_column(String)
    # Comma-separated lists (kept simple for v1; move to join tables if needed)
    supported_metadata_formats: Mapped[str | None] = mapped_column(String)
    supported_authorities: Mapped[str | None] = mapped_column(String)

    # License and contact
    code_license: Mapped[str | None] = mapped_column(String)
    data_license: Mapped[str | None] = mapped_column(String)
    attribution_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    contact_email: Mapped[str | None] = mapped_column(String)
    maintainer: Mapped[str | None] = mapped_column(String)

    # Provenance
    yaml_source: Mapped[str | None] = mapped_column(String)

    # Relationships
    source_archive: Mapped["Archive"] = relationship("Archive")
    periods: Mapped[list["Period"]] = relationship(
        "Period", secondary=upgrade_project_periods, order_by="Period.sort_order"
    )
    record_types: Mapped[list["RecordType"]] = relationship(
        "RecordType",
        secondary=upgrade_project_record_types,
        order_by="RecordType.sort_order",
    )
    cache_entries: Mapped[list["FederationCache"]] = relationship(
        "FederationCache",
        back_populates="upgrade_project",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<UpgradeProject {self.slug}>"
