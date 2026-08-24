"""Archive model — one row per institution or collection.

Standards-aware identifiers (Handle, DOI, ARK, VIAF, ISNI, Wikidata,
GeoNames) are first-class fields per the standards conformance plan
in ``docs/standards.md``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .joins import archive_periods, archive_record_types, archive_themes
from .mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from .vocabularies import InstitutionalType, Period, RecordType, Theme


class Archive(TimestampMixin, db.Model):
    """One archive institution or collection."""

    __tablename__ = "archives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    name_pt: Mapped[str | None] = mapped_column(String)

    # Standards-aware identifiers
    handle_prefix: Mapped[str | None] = mapped_column(String)
    doi: Mapped[str | None] = mapped_column(String)
    ark_identifier: Mapped[str | None] = mapped_column(String)
    viaf_id: Mapped[str | None] = mapped_column(String)
    isni_id: Mapped[str | None] = mapped_column(String)
    wikidata_qid: Mapped[str | None] = mapped_column(String)
    geonames_primary_id: Mapped[int | None] = mapped_column(Integer)

    # Institutional info
    institutional_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("institutional_types.id"), nullable=False
    )
    home_country_code: Mapped[str] = mapped_column(String, nullable=False, default="BR")
    home_state_code: Mapped[str | None] = mapped_column(String)
    home_city: Mapped[str | None] = mapped_column(String)

    # Access
    canonical_url: Mapped[str] = mapped_column(String, nullable=False)
    catalog_url: Mapped[str | None] = mapped_column(String)
    contact_email: Mapped[str | None] = mapped_column(String)

    # Standards conformance (populated as verified)
    oai_pmh_base_url: Mapped[str | None] = mapped_column(String)
    ead_finding_aid_url: Mapped[str | None] = mapped_column(String)
    iiif_manifest_root: Mapped[str | None] = mapped_column(String)

    # Descriptions
    description_en: Mapped[str | None] = mapped_column(Text)
    description_pt: Mapped[str | None] = mapped_column(Text)
    curatorial_rarity_notes: Mapped[str | None] = mapped_column(Text)
    prior_use_note: Mapped[str | None] = mapped_column(Text)
    stated_scope: Mapped[str | None] = mapped_column(Text)

    # Editorial state
    no_digital_content: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Nullable = not yet reviewed. Enforced editorially, not in SQL.
    fair_use_eligible: Mapped[bool | None] = mapped_column(Boolean)
    caveat_emptor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Provenance
    survey_source: Mapped[str | None] = mapped_column(String)
    survey_row: Mapped[int | None] = mapped_column(Integer)

    # Relationships
    institutional_type: Mapped["InstitutionalType"] = relationship(
        "InstitutionalType", lazy="joined"
    )
    periods: Mapped[list["Period"]] = relationship(
        "Period", secondary=archive_periods, order_by="Period.sort_order"
    )
    record_types: Mapped[list["RecordType"]] = relationship(
        "RecordType", secondary=archive_record_types, order_by="RecordType.sort_order"
    )
    themes: Mapped[list["Theme"]] = relationship(
        "Theme", secondary=archive_themes, order_by="Theme.sort_order"
    )

    def __repr__(self) -> str:
        return f"<Archive {self.slug}>"
