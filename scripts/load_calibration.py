"""Load Pass 2 calibration scores from configs/calibration/*.yaml.

Idempotent: re-running supersedes prior active rows for each
(archive, dimension) or (archive, facet) tuple through the service
layer's supersede semantics (see app/services/scoring.py). Identical
inputs no-op — see set_facet_value's guard.

Usage:
    export FLASK_APP=wsgi.py
    .venv/bin/python -m scripts.load_calibration
    .venv/bin/python -m scripts.load_calibration --path configs/calibration/pass2.yaml
    .venv/bin/python -m scripts.load_calibration --dry-run

Direct Archive columns handled here (not by the scoring service):
    - fair_use_eligible (bool)
    - curatorial_rarity_notes (text)
    - prior_use_note (text)
    - institutional_type (via slug lookup)

Single-select facets handled through set_facet_value:
    - licensing_posture
    - stated_roadmap

Multi-select tags handled through set_archive_tags:
    - periods, record_types, themes

Unknown YAML keys are reported but ignored so future extensions can be
added to the YAML before the loader supports them.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import Archive, DIMENSIONS, InstitutionalType
from app.services.scoring import (
    SINGLE_SELECT_FACETS,
    record_score,
    set_archive_tags,
    set_facet_value,
)


DEFAULT_PATH = Path("configs/calibration/pass2.yaml")

# Archive columns the loader is allowed to touch directly.
_DIRECT_ARCHIVE_TEXT_FIELDS = {
    "curatorial_rarity_notes",
    "prior_use_note",
}
_DIRECT_ARCHIVE_BOOL_FIELDS = {
    "fair_use_eligible",
}

# Facet keys we understand in the YAML that are Archive-column-backed
# (not FacetValue rows). Kept separate from SINGLE_SELECT_FACETS so we
# can route them correctly.
_ARCHIVE_BACKED_FACET_KEYS = (
    _DIRECT_ARCHIVE_TEXT_FIELDS
    | _DIRECT_ARCHIVE_BOOL_FIELDS
    | {"institutional_type"}
)

# YAML facet keys we simply don't have a home for yet. We warn once
# per key rather than fail so YAML can stay expressive.
_KNOWN_UNSUPPORTED_FACETS = {"size_unit_note"}


@dataclass
class LoadReport:
    archives_processed: int = 0
    scores_written: int = 0
    scores_unchanged: int = 0
    facets_written: int = 0
    facets_unchanged: int = 0
    archive_fields_updated: int = 0
    tags_updated: int = 0
    warnings: list[str] = field(default_factory=list)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _resolve_institutional_type(slug: str) -> InstitutionalType:
    itype = db.session.scalar(
        select(InstitutionalType).where(InstitutionalType.slug == slug)
    )
    if itype is None:
        raise ValueError(f"Unknown institutional_type slug: {slug!r}")
    return itype


def _apply_archive_backed_facets(
    archive: Archive,
    facets: dict[str, Any],
    report: LoadReport,
) -> None:
    """Set Archive-column-backed values from the YAML facets block."""
    for key, value in facets.items():
        if key not in _ARCHIVE_BACKED_FACET_KEYS:
            continue

        if key == "institutional_type":
            itype = _resolve_institutional_type(str(value))
            if archive.institutional_type_id != itype.id:
                archive.institutional_type_id = itype.id
                report.archive_fields_updated += 1
            continue

        if key in _DIRECT_ARCHIVE_BOOL_FIELDS:
            new_val = bool(value) if value is not None else None
            if getattr(archive, key) != new_val:
                setattr(archive, key, new_val)
                report.archive_fields_updated += 1
            continue

        # Text field.
        new_val = str(value).strip() if value else None
        if getattr(archive, key) != new_val:
            setattr(archive, key, new_val)
            report.archive_fields_updated += 1


def _apply_single_select_facets(
    archive: Archive,
    facets: dict[str, Any],
    scored_by: str,
    report: LoadReport,
) -> None:
    for facet, value in facets.items():
        if facet in _ARCHIVE_BACKED_FACET_KEYS:
            continue
        if facet not in SINGLE_SELECT_FACETS:
            if facet in _KNOWN_UNSUPPORTED_FACETS:
                report.warn(
                    f"{archive.slug}: facet '{facet}' has no storage yet; "
                    "carried in YAML only."
                )
            else:
                report.warn(f"{archive.slug}: unknown facet {facet!r}; skipped.")
            continue

        before = _active_facet_value(archive.id, facet)
        result = set_facet_value(
            archive=archive,
            facet=facet,
            value=str(value) if value is not None else "",
            note=None,
            set_by=scored_by,
        )
        after = result.value if result is not None else ""
        if before == after:
            report.facets_unchanged += 1
        else:
            report.facets_written += 1


def _active_facet_value(archive_id: int, facet: str) -> str:
    from app.models import FacetValue

    row = db.session.scalar(
        select(FacetValue).where(
            FacetValue.archive_id == archive_id,
            FacetValue.facet == facet,
            FacetValue.superseded_at.is_(None),
        )
    )
    return row.value if row is not None else ""


def _apply_scores(
    archive: Archive,
    scores: dict[str, Any],
    scored_by: str,
    report: LoadReport,
) -> None:
    from app.services.scoring import active_scores

    prior = active_scores(archive.id)
    for dim, payload in scores.items():
        if dim not in DIMENSIONS:
            report.warn(f"{archive.slug}: unknown dimension {dim!r}; skipped.")
            continue

        score_val = int(payload["score"])
        just_en = (payload.get("justification_en") or "").strip() or None
        just_pt = (payload.get("justification_pt") or "").strip() or None

        existing = prior.get(dim)
        if (
            existing is not None
            and existing.score == score_val
            and (existing.justification_en or None) == just_en
            and (existing.justification_pt or None) == just_pt
            and (existing.scored_by or None) == (scored_by or None)
        ):
            report.scores_unchanged += 1
            continue

        record_score(
            archive=archive,
            dimension=dim,
            score=score_val,
            justification_en=just_en,
            justification_pt=just_pt,
            scored_by=scored_by,
        )
        report.scores_written += 1


def _apply_tags(
    archive: Archive,
    tags: dict[str, Any],
    report: LoadReport,
) -> None:
    if not tags:
        return
    set_archive_tags(
        archive=archive,
        period_slugs=list(tags.get("periods") or []),
        record_type_slugs=list(tags.get("record_types") or []),
        theme_slugs=list(tags.get("themes") or []),
    )
    report.tags_updated += 1


def load_calibration(path: Path, *, dry_run: bool = False) -> LoadReport:
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)

    if not isinstance(doc, dict) or "archives" not in doc:
        raise ValueError(f"{path}: top-level 'archives' list required.")

    scored_by = str(doc.get("scored_by") or "calibration/pass2").strip()
    entries = doc["archives"] or []
    report = LoadReport()

    for entry in entries:
        slug = entry["slug"]
        archive = db.session.scalar(select(Archive).where(Archive.slug == slug))
        if archive is None:
            report.warn(f"Archive not found for slug {slug!r}; skipped entry.")
            continue

        _apply_archive_backed_facets(archive, entry.get("facets") or {}, report)
        _apply_single_select_facets(
            archive, entry.get("facets") or {}, scored_by, report
        )
        _apply_scores(archive, entry.get("scores") or {}, scored_by, report)
        _apply_tags(archive, entry.get("tags") or {}, report)
        report.archives_processed += 1

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute writes and roll back; report counts and warnings.",
    )
    args = parser.parse_args(argv)

    app = create_app()
    with app.app_context():
        report = load_calibration(args.path, dry_run=args.dry_run)

    tag = " (dry-run)" if args.dry_run else ""
    print(f"Loaded calibration from {args.path}{tag}")
    print(f"  archives processed:      {report.archives_processed}")
    print(f"  scores written:          {report.scores_written}")
    print(f"  scores unchanged:        {report.scores_unchanged}")
    print(f"  facets written:          {report.facets_written}")
    print(f"  facets unchanged:        {report.facets_unchanged}")
    print(f"  archive fields updated:  {report.archive_fields_updated}")
    print(f"  tag sets replaced:       {report.tags_updated}")
    if report.warnings:
        print("  warnings:")
        for w in report.warnings:
            print(f"    - {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
