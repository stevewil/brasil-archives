#!/usr/bin/env python
"""Command-line harvester for OAI-PMH endpoints.

Usage::

    python scripts/harvest.py --list
    python scripts/harvest.py --project mipibu
    python scripts/harvest.py --project mipibu --format oai_ead
    python scripts/harvest.py --project mipibu --since 2026-08-01
    python scripts/harvest.py --project mipibu --dry-run

Exit codes: 0=ok, 1=partial, 2=failed, 64=usage.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Repo root on sys.path when invoked as a script from anywhere.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from wsgi import app  # noqa: E402
from app.services import harvest  # noqa: E402


EXIT_USAGE = 64


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="harvest.py",
        description="OAI-PMH harvester for brasil-archives",
    )
    parser.add_argument(
        "--project", "-p",
        help="Upgrade project slug (e.g. 'mipibu').",
    )
    parser.add_argument(
        "--format", "-f",
        dest="metadata_prefix",
        default="oai_dc",
        help="metadataPrefix (default: oai_dc).",
    )
    parser.add_argument(
        "--since",
        dest="from_",
        help="Selective harvest: OAI 'from' date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--until",
        help="Selective harvest: OAI 'until' date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--set",
        dest="set_",
        help="Selective harvest: OAI setSpec.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse but skip DB writes.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        help="Cap the number of ListRecords pages (for smoke testing).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List projects with an OAI-PMH endpoint configured and exit.",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress INFO-level logging.",
    )
    return parser.parse_args(argv)


def _configure_logging(quiet: bool) -> None:
    level = logging.WARNING if quiet else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _print_project_list() -> None:
    with app.app_context():
        projects = harvest.list_harvestable_projects()
    if not projects:
        print("No projects with oai_pmh_base_url configured.")
        return
    header = f"{'SLUG':20s}  {'FORMATS':20s}  BASE_URL"
    print(header)
    print("-" * len(header))
    for p in projects:
        print(
            f"{p.slug:20s}  {(p.supported_metadata_formats or ''):20s}  "
            f"{p.oai_pmh_base_url}"
        )


def _print_summary(summary: harvest.HarvestSummary) -> None:
    started = summary.started_at.isoformat() if summary.started_at else "-"
    finished = summary.finished_at.isoformat() if summary.finished_at else "-"
    print()
    print("=" * 60)
    print(f"Project:         {summary.project_slug}")
    print(f"Prefix:          {summary.metadata_prefix}")
    print(f"Status:          {summary.status}")
    print(f"Run ID:          {summary.harvest_run_id}")
    print(f"Started:         {started}")
    print(f"Finished:        {finished}")
    print(f"Records seen:    {summary.records_seen}")
    print(f"  upserted:      {summary.records_upserted}")
    print(f"  unchanged:     {summary.records_unchanged}")
    print(f"  errors:        {summary.error_count}")
    if summary.dry_run:
        print("(DRY RUN — no rows written)")
    if summary.notes:
        print(f"Notes:           {summary.notes}")
    if summary.errors:
        print("First few errors:")
        for line in summary.errors[:5]:
            print(f"  - {line}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _configure_logging(args.quiet)

    if args.list:
        _print_project_list()
        return 0

    if not args.project:
        print("error: --project is required (or use --list)", file=sys.stderr)
        return EXIT_USAGE

    with app.app_context():
        summary = harvest.run_harvest(
            project_slug=args.project,
            metadata_prefix=args.metadata_prefix,
            from_=args.from_,
            until=args.until,
            set_=args.set_,
            dry_run=args.dry_run,
            max_pages=args.max_pages,
        )

    _print_summary(summary)
    return summary.exit_code()


if __name__ == "__main__":
    sys.exit(main())
