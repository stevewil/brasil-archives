"""FederationCache model — 15-minute cache for federation-v1 responses.

Per Phase 2 of the federation prototype, brasil-archives calls upgrade
projects' /api/ endpoints on demand. Each unique (upgrade_project,
endpoint, query-params) triple is cached for 15 minutes. If the upstream
is unreachable, the last cached entry is served with a `stale=True`
flag by the federation service.

See ``docs/federation-v1.md`` and ``app/services/federation.py``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db

if TYPE_CHECKING:  # pragma: no cover
    from .upgrade_project import UpgradeProject


class FederationCache(db.Model):
    """One cached federation-v1 HTTP response."""

    __tablename__ = "federation_cache"
    # Per-source schema — see AggregatedRecord / docs/project-schema-design.md.
    __table_args__ = (
        UniqueConstraint(
            "upgrade_project_id",
            "cache_key",
            name="uq_federation_cache_project_key",
        ),
        {"schema": "source"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upgrade_project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("upgrade_projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    # sha256 of (endpoint + '?' + sorted-normalized query string).
    # 64 hex chars for sha256; column sized loosely.
    cache_key: Mapped[str] = mapped_column(String, nullable=False)

    # Short human-readable endpoint slug: 'health' | 'schema' | 'records'
    # | 'record'. Not tied to URL structure, so future endpoints don't
    # force a schema change.
    endpoint: Mapped[str] = mapped_column(String, nullable=False)

    # Full URL for debugging and audit.
    request_url: Mapped[str] = mapped_column(String, nullable=False)

    # Serialized JSON body from the upstream response. Stored as TEXT
    # rather than JSON so SQLite portability stays clean; the service
    # layer json.loads on read.
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)

    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Sidecar identifiers pulled from federation responses when known.
    # federation_contract_version comes from any envelope; corpus_version
    # comes from /api/health.
    contract_version: Mapped[str | None] = mapped_column(String)
    corpus_version: Mapped[str | None] = mapped_column(String)

    upgrade_project: Mapped["UpgradeProject"] = relationship(
        "UpgradeProject",
        back_populates="cache_entries",
    )

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return True if this cache entry has passed its expires_at."""
        current = now or datetime.now(timezone.utc)
        # SQLite hands back naive datetimes; normalize both sides.
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return current >= expires

    def __repr__(self) -> str:
        return (
            f"<FederationCache project={self.upgrade_project_id} "
            f"endpoint={self.endpoint} expires_at={self.expires_at.isoformat()}>"
        )
