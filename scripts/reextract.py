#!/usr/bin/env python
"""Re-run the OAI extractors over already-harvested records.

A normal ``scripts/harvest.py`` run only refreshes ``extracted_json`` when
the record's raw XML changed (sha guard in ``app/services/harvest.py``).
When the *extractor* changes instead — a new canonical field, a mapping
fix — existing rows keep their stale derived data until the provider
happens to re-emit them.

This script closes that gap: it walks ``aggregated_records``, re-parses
the stored ``raw_xml``, re-runs ``extract_metadata`` for its prefix, and
writes back any row whose ``extracted_json`` actually changed. No network.

Usage::

    python -m scripts.reextract --list
    python -m scripts.reextract --project povos-indigenas-rn
    python -m scripts.reextract                       # every project
    python -m scripts.reextract --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from wsgi import app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import AggregatedRecord, UpgradeProject  # noqa: E402
from app.services import oai_client  # noqa: E402
from app.services.oai_extractors import extract as extract_metadata  # noqa: E402

EXIT_USAGE = 64


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="reextract.py",
        description="Re-run OAI extractors over stored raw_xml.",
    )
    p.add_argument("--project", "-p", help="Upgrade project slug; omit for all.")
    p.add_argument(
        "--format", "-f", dest="metadata_prefix",
        help="Restrict to one metadataPrefix (e.g. oai_dc).",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Report what would change without writing.",
    )
    p.add_argument("--list", action="store_true", help="List projects and exit.")
    return p.parse_args(argv)


def _metadata_element(raw_xml: str) -> ET.Element | None:
    """The <oai_dc:dc> / <ead> child inside a stored <record> string."""
    try:
        record = ET.fromstring(raw_xml)
    except ET.ParseError:
        return None
    return oai_client.record_metadata_element(record)


def _reextract(project: UpgradeProject, prefix: str | None, dry_run: bool) -> tuple[int, int, int]:
    q = db.session.query(AggregatedRecord).filter(
        AggregatedRecord.upgrade_project_id == project.id
    )
    if prefix:
        q = q.filter(AggregatedRecord.metadata_prefix == prefix)

    seen = changed = failed = 0
    for rec in q.yield_per(200):
        seen += 1
        element = _metadata_element(rec.raw_xml)
        if element is None:
            failed += 1
            continue
        try:
            fresh = extract_metadata(rec.metadata_prefix, element)
        except Exception as exc:  # noqa: BLE001 — report and move on
            print(f"  !! {rec.oai_identifier}: {exc}")
            failed += 1
            continue
        fresh_json = json.dumps(fresh, ensure_ascii=False)
        if fresh_json == rec.extracted_json:
            continue
        changed += 1
        if not dry_run:
            rec.extracted_json = fresh_json
    if not dry_run:
        db.session.commit()
    return seen, changed, failed


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    with app.app_context():
        if args.list:
            for p in db.session.query(UpgradeProject).order_by(UpgradeProject.slug):
                n = db.session.query(AggregatedRecord).filter_by(
                    upgrade_project_id=p.id
                ).count()
                print(f"{p.slug:24s} {n:5d} records")
            return 0

        projects = db.session.query(UpgradeProject).order_by(UpgradeProject.slug)
        if args.project:
            projects = projects.filter(UpgradeProject.slug == args.project)
        projects = list(projects)
        if not projects:
            print(f"No project matches {args.project!r}", file=sys.stderr)
            return EXIT_USAGE

        total_seen = total_changed = total_failed = 0
        for project in projects:
            seen, changed, failed = _reextract(
                project, args.metadata_prefix, args.dry_run
            )
            total_seen += seen
            total_changed += changed
            total_failed += failed
            print(
                f"{project.slug:24s} seen={seen:5d} "
                f"{'would change' if args.dry_run else 'changed'}={changed:5d} "
                f"failed={failed:3d}"
            )

        print("-" * 48)
        print(
            f"{'TOTAL':24s} seen={total_seen:5d} "
            f"{'would change' if args.dry_run else 'changed'}={total_changed:5d} "
            f"failed={total_failed:3d}"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
