#!/usr/bin/env python
"""Command-line runner for the quarterly health probe.

Usage::

    python -m scripts.probe --list
    python -m scripts.probe --all
    python -m scripts.probe --archive bczm-ufrn
    python -m scripts.probe --archive bczm-ufrn --archive interpi --dry-run
    python -m scripts.probe --all --include-upgrade-projects

``--dry-run`` collects every signal, composites the four probe-fed facets
and prints them, but writes nothing (no ProbeResult row, no facet update,
no ``last_probed_at`` stamp).

Exit codes: 0=all ok, 1=at least one run partial (a signal failed),
2=at least one run failed / target not found, 64=usage.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from wsgi import app  # noqa: E402
from app.services import probe  # noqa: E402


EXIT_USAGE = 64


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="probe.py",
        description="Quarterly health probe for brasil-archives",
    )
    parser.add_argument(
        "--all", action="store_true", help="Probe every archive.",
    )
    parser.add_argument(
        "--archive", "-a", action="append", default=[], metavar="SLUG",
        help="Probe this archive slug (repeatable).",
    )
    parser.add_argument(
        "--upgrade-project", "-u", action="append", default=[], metavar="SLUG",
        help="Probe this upgrade-project slug (repeatable).",
    )
    parser.add_argument(
        "--include-upgrade-projects", action="store_true",
        help="With --all, also probe every registered upgrade project.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Collect + composite + print, but write nothing.",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List probe targets and exit.",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress INFO-level logging.",
    )
    return parser.parse_args(argv)


def _configure_logging(quiet: bool) -> None:
    logging.basicConfig(
        level=logging.WARNING if quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _print_targets(include_ups: bool) -> None:
    with app.app_context():
        archives, ups = probe.list_probe_targets(
            include_upgrade_projects=include_ups
        )
    print(f"{'KIND':18s}  {'SLUG':28s}  URL")
    print("-" * 72)
    for a in archives:
        print(f"{'archive':18s}  {a.slug:28s}  {a.canonical_url}")
    for u in ups:
        print(f"{'upgrade_project':18s}  {u.slug:28s}  {u.primary_url}")


def _print_summary(s: probe.ProbeSummary) -> None:
    print()
    print("=" * 60)
    print(f"Target:              {s.target_kind}/{s.target_slug}")
    print(f"Status:              {s.status}")
    print(f"ProbeResult id:      {s.probe_result_id}")
    print(f"web_ops_health:      {s.web_ops_health}")
    print(f"external_preservation: {s.external_preservation}")
    print(f"growth_signal:       {s.growth_signal}")
    print(f"prior_use_signal:    {s.prior_use_signal}")
    if s.dry_run:
        print("(DRY RUN — nothing written)")
    if s.notes:
        print(f"Notes:               {s.notes}")
    if s.signal_errors:
        print("Signal errors:")
        for line in s.signal_errors[:8]:
            print(f"  - {line}")


def _worst_exit(summaries: list[probe.ProbeSummary]) -> int:
    if not summaries:
        return EXIT_USAGE
    return max(s.exit_code() for s in summaries)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _configure_logging(args.quiet)

    if args.list:
        _print_targets(args.include_upgrade_projects or bool(args.upgrade_project))
        return 0

    if not (args.all or args.archive or args.upgrade_project):
        print(
            "error: pass --all, --archive SLUG, or --upgrade-project SLUG "
            "(or --list)",
            file=sys.stderr,
        )
        return EXIT_USAGE

    summaries: list[probe.ProbeSummary] = []
    with app.app_context():
        if args.all:
            summaries.extend(
                probe.run_all_probes(
                    include_upgrade_projects=args.include_upgrade_projects,
                    dry_run=args.dry_run,
                )
            )
        for slug in args.archive:
            archive = probe.load_archive(slug)
            if archive is None:
                print(f"error: no archive with slug {slug!r}", file=sys.stderr)
                summaries.append(
                    probe.ProbeSummary(
                        target_kind="archive", target_slug=slug, status="failed",
                        notes="target not found",
                    )
                )
                continue
            summaries.append(
                probe.run_probe(archive=archive, dry_run=args.dry_run)
            )
        for slug in args.upgrade_project:
            up = probe.load_upgrade_project(slug)
            if up is None:
                print(f"error: no upgrade project with slug {slug!r}", file=sys.stderr)
                summaries.append(
                    probe.ProbeSummary(
                        target_kind="upgrade_project", target_slug=slug,
                        status="failed", notes="target not found",
                    )
                )
                continue
            summaries.append(
                probe.run_probe(upgrade_project=up, dry_run=args.dry_run)
            )

    for s in summaries:
        _print_summary(s)

    ok = sum(1 for s in summaries if s.status == "ok")
    partial = sum(1 for s in summaries if s.status == "partial")
    failed = sum(1 for s in summaries if s.status == "failed")
    print()
    print(f"{len(summaries)} target(s): {ok} ok, {partial} partial, {failed} failed")
    return _worst_exit(summaries)


if __name__ == "__main__":
    sys.exit(main())
