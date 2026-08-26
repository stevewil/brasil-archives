"""OAI-PMH harvest runner — orchestrates client + extractors + DB writes.

See ``docs/harvest-design.md`` for the full contract. Highlights:

* One HarvestRun row per invocation.
* Per-record upsert keyed by (project, oai_identifier, prefix); SHA-256
  of raw XML is the change-detection oracle.
* Per-record failures write HarvestError rows and let the run continue.
* HTTP-level failures (protocol, HTTP, resumption) abort the run and mark
  it ``failed``; the partial rows already written stay.
* Dry-run mode: exercise everything except DB writes; returns a summary.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable
from xml.etree import ElementTree as ET

from sqlalchemy import select

from ..extensions import db
from ..models import (
    AggregatedRecord,
    HarvestError,
    HarvestRun,
    UpgradeProject,
)
from ..models.harvest_error import PHASE_EXTRACT, PHASE_PARSE, PHASE_UPSERT
from ..models.harvest_run import (
    SOURCE_OAI_PMH,
    STATUS_FAILED,
    STATUS_OK,
    STATUS_PARTIAL,
    STATUS_RUNNING,
)
from . import oai_client
from .oai_extractors import extract as extract_metadata


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public results dataclass
# ---------------------------------------------------------------------------
@dataclass
class HarvestSummary:
    """Result of one harvest invocation (returned by ``run_harvest``)."""
    upgrade_project_id: int | None
    project_slug: str
    metadata_prefix: str
    status: str
    records_seen: int = 0
    records_upserted: int = 0
    records_unchanged: int = 0
    error_count: int = 0
    harvest_run_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    notes: str | None = None
    dry_run: bool = False
    errors: list[str] = field(default_factory=list)

    def exit_code(self) -> int:
        """0=ok, 1=partial, 2=failed. CLI uses this."""
        if self.status == STATUS_OK:
            return 0
        if self.status == STATUS_PARTIAL:
            return 1
        return 2


# ---------------------------------------------------------------------------
# Exceptions raised only inside this module (not part of the public API)
# ---------------------------------------------------------------------------
class HarvestConfigError(Exception):
    """Project isn't configured for OAI-PMH harvest (no base URL etc)."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_project(slug: str) -> UpgradeProject:
    stmt = select(UpgradeProject).where(UpgradeProject.slug == slug)
    proj = db.session.execute(stmt).scalar_one_or_none()
    if proj is None:
        raise HarvestConfigError(f"No upgrade project with slug={slug!r}")
    return proj


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _validate_prefix(project: UpgradeProject, prefix: str) -> None:
    supported = _parse_csv(project.supported_metadata_formats)
    if supported and prefix not in supported:
        raise HarvestConfigError(
            f"Project {project.slug!r} does not advertise prefix {prefix!r} "
            f"(supported: {supported})"
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def run_harvest(
    project_slug: str,
    metadata_prefix: str = "oai_dc",
    from_: str | None = None,
    until: str | None = None,
    set_: str | None = None,
    dry_run: bool = False,
    max_pages: int | None = None,
) -> HarvestSummary:
    """Harvest one project's OAI-PMH endpoint into aggregated_records."""
    summary = HarvestSummary(
        upgrade_project_id=None,
        project_slug=project_slug,
        metadata_prefix=metadata_prefix,
        status=STATUS_RUNNING,
        started_at=_now(),
        dry_run=dry_run,
    )

    try:
        project = _load_project(project_slug)
        summary.upgrade_project_id = project.id
        _validate_prefix(project, metadata_prefix)

        base_url = project.oai_pmh_base_url
        if not base_url:
            raise HarvestConfigError(
                f"Project {project.slug!r} has no oai_pmh_base_url; "
                "use run_static_harvest for static exports."
            )
    except HarvestConfigError as exc:
        summary.status = STATUS_FAILED
        summary.notes = str(exc)
        summary.finished_at = _now()
        summary.errors.append(str(exc))
        log.error("harvest config error: %s", exc)
        return summary

    # Persist the HarvestRun row up front (unless dry-run) so per-record
    # errors have something to reference.
    run: HarvestRun | None = None
    if not dry_run:
        run = HarvestRun(
            upgrade_project_id=project.id,
            metadata_prefix=metadata_prefix,
            started_at=summary.started_at,
            status=STATUS_RUNNING,
            records_seen=0,
            records_upserted=0,
            records_unchanged=0,
            error_count=0,
            from_ts=from_,
            until_ts=until,
            source=SOURCE_OAI_PMH,
        )
        db.session.add(run)
        db.session.commit()
        summary.harvest_run_id = run.id

    try:
        for record in oai_client.iterate_records(
            base_url, metadata_prefix,
            from_=from_, until=until, set_=set_,
            max_pages=max_pages,
        ):
            summary.records_seen += 1
            _process_record(
                project=project,
                metadata_prefix=metadata_prefix,
                record=record,
                summary=summary,
                run=run,
                dry_run=dry_run,
            )
    except oai_client.OaiError as exc:
        summary.status = STATUS_FAILED
        summary.notes = f"OAI protocol/HTTP failure: {exc}"
        summary.errors.append(str(exc))
        log.error("harvest aborted for %s (%s): %s",
                  project_slug, metadata_prefix, exc)
    else:
        summary.status = (
            STATUS_PARTIAL if summary.error_count > 0 else STATUS_OK
        )

    summary.finished_at = _now()

    if run is not None:
        run.status = summary.status
        run.finished_at = summary.finished_at
        run.records_seen = summary.records_seen
        run.records_upserted = summary.records_upserted
        run.records_unchanged = summary.records_unchanged
        run.error_count = summary.error_count
        if summary.notes:
            run.notes = summary.notes
        db.session.commit()

    log.info(
        "harvest %s prefix=%s dry_run=%s status=%s seen=%d upserted=%d "
        "unchanged=%d errors=%d",
        project_slug, metadata_prefix, dry_run, summary.status,
        summary.records_seen, summary.records_upserted,
        summary.records_unchanged, summary.error_count,
    )
    return summary


# ---------------------------------------------------------------------------
# Per-record processing
# ---------------------------------------------------------------------------
def _process_record(
    *,
    project: UpgradeProject,
    metadata_prefix: str,
    record: ET.Element,
    summary: HarvestSummary,
    run: HarvestRun | None,
    dry_run: bool,
) -> None:
    """Extract, upsert, or record an error for one <record>."""
    # ---- Phase 1: parse header ----
    try:
        oai_id, datestamp, set_specs = oai_client.record_header_fields(record)
        if not oai_id or not datestamp:
            raise ValueError("missing identifier or datestamp in <header>")
    except Exception as exc:
        _log_error(
            run=run, summary=summary, phase=PHASE_PARSE,
            oai_identifier=None, message=str(exc),
            record=record, dry_run=dry_run,
        )
        return

    # ---- Phase 2: extract ----
    payload = oai_client.record_metadata_element(record)
    if payload is None:
        _log_error(
            run=run, summary=summary, phase=PHASE_EXTRACT,
            oai_identifier=oai_id, message="record has no <metadata> child",
            record=record, dry_run=dry_run,
        )
        return
    try:
        extracted = extract_metadata(metadata_prefix, payload)
    except Exception as exc:
        _log_error(
            run=run, summary=summary, phase=PHASE_EXTRACT,
            oai_identifier=oai_id, message=f"extractor failure: {exc}",
            record=record, dry_run=dry_run,
        )
        return

    raw_xml = oai_client.record_to_xml(record)
    raw_sha = _sha256(raw_xml)

    if dry_run:
        # Count as upsert so the dry run gives an accurate preview.
        summary.records_upserted += 1
        return

    # ---- Phase 3: upsert ----
    assert run is not None
    try:
        _upsert(
            project_id=project.id,
            metadata_prefix=metadata_prefix,
            oai_identifier=oai_id,
            datestamp=datestamp,
            set_specs=set_specs,
            raw_xml=raw_xml,
            raw_sha=raw_sha,
            extracted=extracted,
            run=run,
            summary=summary,
        )
    except Exception as exc:  # DB-level failure — record and continue
        db.session.rollback()
        _log_error(
            run=run, summary=summary, phase=PHASE_UPSERT,
            oai_identifier=oai_id, message=f"db upsert failure: {exc}",
            record=record, dry_run=dry_run,
        )


def _upsert(
    *,
    project_id: int,
    metadata_prefix: str,
    oai_identifier: str,
    datestamp: str,
    set_specs: list[str],
    raw_xml: str,
    raw_sha: str,
    extracted: dict,
    run: HarvestRun,
    summary: HarvestSummary,
) -> None:
    stmt = select(AggregatedRecord).where(
        AggregatedRecord.upgrade_project_id == project_id,
        AggregatedRecord.oai_identifier == oai_identifier,
        AggregatedRecord.metadata_prefix == metadata_prefix,
    )
    existing = db.session.execute(stmt).scalar_one_or_none()
    now = _now()

    if existing is None:
        row = AggregatedRecord(
            upgrade_project_id=project_id,
            oai_identifier=oai_identifier,
            metadata_prefix=metadata_prefix,
            datestamp=datestamp,
            set_specs_json=json.dumps(set_specs, ensure_ascii=False),
            raw_xml=raw_xml,
            raw_xml_sha256=raw_sha,
            extracted_json=json.dumps(extracted, ensure_ascii=False),
            harvest_run_id=run.id,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.session.add(row)
        db.session.commit()
        summary.records_upserted += 1
        return

    if existing.raw_xml_sha256 == raw_sha:
        existing.last_seen_at = now
        db.session.commit()
        summary.records_unchanged += 1
        return

    # Content changed — full refresh; preserve first_seen_at.
    existing.datestamp = datestamp
    existing.set_specs_json = json.dumps(set_specs, ensure_ascii=False)
    existing.raw_xml = raw_xml
    existing.raw_xml_sha256 = raw_sha
    existing.extracted_json = json.dumps(extracted, ensure_ascii=False)
    existing.harvest_run_id = run.id
    existing.last_seen_at = now
    db.session.commit()
    summary.records_upserted += 1


def _log_error(
    *,
    run: HarvestRun | None,
    summary: HarvestSummary,
    phase: str,
    oai_identifier: str | None,
    message: str,
    record: ET.Element,
    dry_run: bool,
) -> None:
    summary.error_count += 1
    summary.errors.append(f"[{phase}] {oai_identifier or '?'}: {message}")
    log.warning("harvest per-record error phase=%s id=%s: %s",
                phase, oai_identifier, message)
    if dry_run or run is None:
        return

    try:
        excerpt = oai_client.record_to_xml(record)[:2000]
    except Exception:  # pragma: no cover
        excerpt = None

    err = HarvestError(
        harvest_run_id=run.id,
        phase=phase,
        oai_identifier=oai_identifier,
        message=message,
        xml_excerpt=excerpt,
    )
    db.session.add(err)
    db.session.commit()


# ---------------------------------------------------------------------------
# Convenience helpers used by the CLI
# ---------------------------------------------------------------------------
def list_harvestable_projects() -> list[UpgradeProject]:
    """Return every UpgradeProject with an OAI-PMH endpoint configured."""
    stmt = (
        select(UpgradeProject)
        .where(UpgradeProject.oai_pmh_base_url.is_not(None))
        .order_by(UpgradeProject.slug)
    )
    return list(db.session.execute(stmt).scalars())
