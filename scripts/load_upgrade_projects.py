"""Load upgrade projects from ``configs/upgrade_projects/*.yaml``.

Each YAML file registers one upgrade project per docs/federation-v1.md.
The loader:

- Resolves ``source_archive_*`` fields to a real Archive row.
- Upserts the UpgradeProject by ``slug``.
- Associates period and record-type tags via join tables.
- Creates one DimensionLift row per entry in ``lifts:`` (idempotent by
  ``(upgrade_project_id, dimension)``: existing lift for a dimension is
  updated in place).

Usage::

    .venv/bin/python -m scripts.load_upgrade_projects
    .venv/bin/python -m scripts.load_upgrade_projects --dry-run
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import (
    Archive,
    DimensionLift,
    Period,
    RecordType,
    UpgradeProject,
)
from app.services.sources import ensure_source_schema, rebuild_source_views

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs" / "upgrade_projects"


def _resolve_source_archive(cfg: dict[str, Any]) -> Archive:
    """Look up the source Archive using one of the accepted keys."""
    if slug := cfg.get("source_archive_slug"):
        row = db.session.scalar(select(Archive).where(Archive.slug == slug))
        if row is None:
            raise ValueError(f"source_archive_slug '{slug}' not found in archives table")
        return row

    survey = cfg.get("source_archive_survey")
    if isinstance(survey, dict) and "table" in survey and "row" in survey:
        # Survey row uniqueness is enforced by (survey_source, survey_row) plus
        # the table indicator baked into the slug (t1r8, etc.).
        needle = f"t{int(survey['table'])}r{int(survey['row'])}"
        rows = db.session.scalars(
            select(Archive).where(Archive.slug.like(f"%-{needle}"))
        ).all()
        if not rows:
            raise ValueError(
                f"source_archive_survey {survey} did not match any archive; "
                "run scripts.load_survey first."
            )
        if len(rows) > 1:
            raise ValueError(
                f"source_archive_survey {survey} matched {len(rows)} archives: "
                + ", ".join(r.slug for r in rows)
            )
        return rows[0]

    if name := cfg.get("source_archive_name_match"):
        rows = db.session.scalars(
            select(Archive).where(Archive.name_pt.ilike(f"%{name}%"))
        ).all()
        if len(rows) != 1:
            raise ValueError(
                f"source_archive_name_match '{name}' matched {len(rows)} archives; "
                "expected exactly one."
            )
        return rows[0]

    raise ValueError(
        "Upgrade project config must specify source_archive_slug, "
        "source_archive_survey, or source_archive_name_match."
    )


def _resolve_slugs(model: type[db.Model], slugs: list[str]) -> list[Any]:
    """Look up vocabulary rows by slug; raise on any miss."""
    if not slugs:
        return []
    rows = db.session.scalars(select(model).where(model.slug.in_(slugs))).all()
    found = {r.slug for r in rows}
    missing = [s for s in slugs if s not in found]
    if missing:
        raise ValueError(
            f"{model.__tablename__} slugs not found: {missing}. "
            "Load vocabularies first."
        )
    return rows


def _upsert_project(cfg: dict[str, Any], yaml_path: Path) -> UpgradeProject:
    slug = cfg["slug"]
    scope = cfg.get("scope") or {}
    delivery = cfg.get("delivery") or {}
    federation = cfg.get("federation") or {}
    license_ = cfg.get("license") or {}
    maintainer = cfg.get("maintainer") or {}
    approx = scope.get("approximate_size") or {}

    source = _resolve_source_archive(cfg)

    def _csv_or_none(items: list[str] | None) -> str | None:
        if not items:
            return None
        return ",".join(items)

    payload: dict[str, Any] = {
        "slug": slug,
        "name": cfg["name"],
        "name_pt": cfg.get("name_pt"),
        "source_archive_id": source.id,
        "scope_description_en": scope.get("description_en", "").strip(),
        "scope_description_pt": (scope.get("description_pt") or "").strip() or None,
        "approximate_document_count": approx.get("document_count"),
        "approximate_page_equivalents": approx.get("page_equivalents"),
        "primary_url": delivery["primary_url"],
        "source_repo": delivery.get("source_repo"),
        "delivery_status": delivery.get("status", "in-development"),
        "federation_contract_version": federation.get("contract_version", "v1"),
        "json_api_base_url": federation.get("json_api_base_url"),
        "oai_pmh_base_url": federation.get("oai_pmh_base_url"),
        "iiif_search_endpoint": federation.get("iiif_search_endpoint"),
        "ead_export_url": federation.get("ead_export_url"),
        "eac_cpf_export_url": federation.get("eac_cpf_export_url"),
        "supported_metadata_formats": _csv_or_none(
            federation.get("supported_metadata_formats")
        ),
        "supported_authorities": _csv_or_none(federation.get("supported_authorities")),
        "code_license": license_.get("code"),
        "data_license": license_.get("data"),
        "attribution_required": bool(license_.get("attribution_required", True)),
        "contact_email": maintainer.get("contact_email"),
        "maintainer": maintainer.get("name"),
        "yaml_source": yaml_path.name,
    }

    existing = db.session.scalar(
        select(UpgradeProject).where(UpgradeProject.slug == slug)
    )
    if existing is None:
        project = UpgradeProject(**payload)
        db.session.add(project)
        db.session.flush()  # populate id for tag associations
    else:
        for k, v in payload.items():
            setattr(existing, k, v)
        project = existing

    # Tag associations (multi-select). Replace-in-place semantics.
    project.periods = _resolve_slugs(Period, scope.get("period_tags") or [])
    project.record_types = _resolve_slugs(RecordType, scope.get("record_types") or [])
    return project


def _upsert_lifts(project: UpgradeProject, lifts: dict[str, dict[str, Any]]) -> int:
    """Idempotent lift upsert. Returns number of rows touched."""
    touched = 0
    for dimension, data in (lifts or {}).items():
        existing = db.session.scalar(
            select(DimensionLift).where(
                DimensionLift.upgrade_project_id == project.id,
                DimensionLift.dimension == dimension,
            )
        )
        payload = {
            "upgrade_project_id": project.id,
            "dimension": dimension,
            "source_archive_score": int(data["source_archive_score"]),
            "upgrade_score": int(data["upgrade_score"]),
            "justification_en": (data.get("justification_en") or "").strip(),
            "justification_pt": (data.get("justification_pt") or None),
        }
        if existing is None:
            db.session.add(DimensionLift(**payload))
        else:
            for k, v in payload.items():
                setattr(existing, k, v)
        touched += 1
    return touched


def load(
    yaml_dir: Path | None = None,
    *,
    dry_run: bool = False,
    skip_schema_sync: bool = False,
) -> dict[str, int]:
    """Load every YAML under ``yaml_dir``. Returns counts per project.

    ``yaml_dir`` defaults to :data:`CONFIG_DIR` — resolved at call time
    so tests can monkeypatch the module-level constant.

    After the upsert (unless ``dry_run`` or ``skip_schema_sync``), stamps a
    ``src_<slug>`` Postgres schema for each registered source and rebuilds
    the cross-source ``*_all`` views — so onboarding a partner stays one
    command. Both are no-ops on SQLite. See docs/partner-schema-design.md.
    """
    if yaml_dir is None:
        yaml_dir = CONFIG_DIR
    counts: dict[str, int] = {}
    slugs: list[str] = []
    for path in sorted(yaml_dir.glob("*.yaml")):
        with path.open(encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        project = _upsert_project(cfg, path)
        lifts_touched = _upsert_lifts(project, cfg.get("lifts") or {})
        counts[cfg.get("slug", path.stem)] = lifts_touched
        slugs.append(cfg.get("slug", path.stem))

    if dry_run:
        db.session.rollback()
        return counts

    db.session.commit()
    if not skip_schema_sync:
        for slug in slugs:
            ensure_source_schema(db.engine, slug)
        rebuild_source_views(db.engine, slugs)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-schema-sync",
        action="store_true",
        help="upsert the rows but don't stamp src_<slug> schemas / rebuild views",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        counts = load(
            dry_run=args.dry_run, skip_schema_sync=args.skip_schema_sync
        )

    verb = "would have" if args.dry_run else "did"
    for slug, lifts in counts.items():
        print(f"{slug}: upsert project, {verb} touch {lifts} dimension lift(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
