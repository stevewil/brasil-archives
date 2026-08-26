"""Static-export fallback for projects that publish an OAI-PMH-style
XML file (via ``oai_dc_export_url`` or ``ead_export_url``) but do NOT
expose a live OAI-PMH endpoint.

Contract: the referenced URL returns an XML document whose root
contains one or more ``<record>`` elements in the OAI-PMH 2.0 namespace
— i.e. what a ``ListRecords`` response would look like without the
outer verb envelope. Records are processed with the same extractor +
upsert pipeline as ``harvest.py``.

See ``docs/harvest-design.md`` §Static-export fallback.
"""
from __future__ import annotations

import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from sqlalchemy import select

from ..extensions import db
from ..models import HarvestRun, UpgradeProject
from ..models.harvest_run import (
    SOURCE_STATIC_EXPORT,
    STATUS_FAILED,
    STATUS_OK,
    STATUS_PARTIAL,
    STATUS_RUNNING,
)
from . import oai_client
from .harvest import (
    HarvestConfigError,
    HarvestSummary,
    _now,
    _process_record,
)


log = logging.getLogger(__name__)


def _fetch_body(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": oai_client.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=oai_client.HTTP_TIMEOUT_SECONDS) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise oai_client.OaiHTTPError(f"HTTP {exc.code} from {url}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise oai_client.OaiHTTPError(f"Network error for {url}: {exc.reason}") from exc


def _extract_records(root: ET.Element) -> list[ET.Element]:
    """Find <record> elements anywhere in the tree (namespace-aware)."""
    records = root.findall(f".//{{{oai_client.OAI_NS}}}record")
    if records:
        return records
    # Fall back to a namespace-agnostic search — some static exports drop
    # the OAI-PMH namespace decl entirely.
    return [el for el in root.iter() if el.tag.rsplit("}", 1)[-1] == "record"]


def run_static_harvest(
    project_slug: str,
    metadata_prefix: str,
    export_url: str | None = None,
    dry_run: bool = False,
) -> HarvestSummary:
    """Harvest one project from a static XML export."""
    summary = HarvestSummary(
        upgrade_project_id=None,
        project_slug=project_slug,
        metadata_prefix=metadata_prefix,
        status=STATUS_RUNNING,
        started_at=_now(),
        dry_run=dry_run,
    )

    stmt = select(UpgradeProject).where(UpgradeProject.slug == project_slug)
    project = db.session.execute(stmt).scalar_one_or_none()
    if project is None:
        summary.status = STATUS_FAILED
        summary.notes = f"No upgrade project with slug={project_slug!r}"
        summary.errors.append(summary.notes)
        summary.finished_at = _now()
        return summary
    summary.upgrade_project_id = project.id

    # Resolve URL: explicit > oai_dc_export_url > ead_export_url.
    url = export_url
    if url is None:
        if metadata_prefix == "oai_dc":
            url = project.oai_dc_export_url
        elif metadata_prefix == "oai_ead":
            url = project.ead_export_url
    if not url:
        summary.status = STATUS_FAILED
        summary.notes = (
            f"Project {project_slug!r} has no static export URL for "
            f"prefix {metadata_prefix!r}"
        )
        summary.errors.append(summary.notes)
        summary.finished_at = _now()
        return summary

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
            source=SOURCE_STATIC_EXPORT,
            notes=f"static export: {url}",
        )
        db.session.add(run)
        db.session.commit()
        summary.harvest_run_id = run.id

    try:
        body = _fetch_body(url)
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise oai_client.OaiParseError(
                f"Malformed static export XML from {url}: {exc}"
            ) from exc

        for record in _extract_records(root):
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
        summary.notes = f"Static export fetch/parse failure: {exc}"
        summary.errors.append(str(exc))
        log.error("static harvest aborted for %s: %s", project_slug, exc)
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

    return summary
