"""Load controlled vocabularies from YAML into the database.

Idempotent: each vocabulary row is keyed by ``slug``. Re-running updates
labels and sort orders without duplicating rows. Vocabularies never
get destructively cleared — deprecated entries should be soft-handled
in a follow-up (out of scope for Phase 1).

Usage::

    .venv/bin/python -m scripts.load_vocabularies
    .venv/bin/python -m scripts.load_vocabularies --dry-run
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from app import create_app
from app.extensions import db
from app.models import InstitutionalType, Period, RecordType, Theme

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs" / "vocabularies"

# Maps YAML filename → (SQLAlchemy model, required-fields tuple).
LOADERS: dict[str, tuple[type[db.Model], tuple[str, ...]]] = {
    "periods.yaml": (Period, ("slug", "label_en", "label_pt", "sort_order")),
    "institutional_types.yaml": (
        InstitutionalType,
        ("slug", "label_en", "label_pt", "sort_order"),
    ),
    "record_types.yaml": (
        RecordType,
        ("slug", "label_en", "label_pt", "category", "sort_order"),
    ),
    "themes.yaml": (
        Theme,
        ("slug", "label_en", "label_pt", "category", "sort_order"),
    ),
}


def _load_yaml(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Vocabulary file missing: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or []
    if not isinstance(data, list):
        raise ValueError(f"{path.name} must be a YAML list, got {type(data).__name__}")
    return data


def _upsert(model: type[db.Model], rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Insert or update vocabulary rows keyed by ``slug``.

    Returns ``(inserted, updated)``.
    """
    inserted = updated = 0
    for row in rows:
        slug = row.get("slug")
        if not slug:
            raise ValueError(f"{model.__tablename__} row missing slug: {row!r}")
        existing = db.session.query(model).filter_by(slug=slug).one_or_none()
        if existing is None:
            db.session.add(model(**row))
            inserted += 1
        else:
            dirty = False
            for k, v in row.items():
                if getattr(existing, k) != v:
                    setattr(existing, k, v)
                    dirty = True
            if dirty:
                updated += 1
    return inserted, updated


def load_all(dry_run: bool = False) -> dict[str, tuple[int, int]]:
    """Load every vocabulary file and return per-file (inserted, updated)."""
    results: dict[str, tuple[int, int]] = {}
    for filename, (model, required) in LOADERS.items():
        rows = _load_yaml(CONFIG_DIR / filename)
        for row in rows:
            missing = [f for f in required if f not in row]
            if missing:
                raise ValueError(
                    f"{filename} row {row.get('slug', '<no slug>')} missing: {missing}"
                )
        results[filename] = _upsert(model, rows)
    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate but do not commit.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        results = load_all(dry_run=args.dry_run)

    verb = "would have" if args.dry_run else "did"
    for filename, (ins, upd) in results.items():
        print(f"{filename}: {verb} insert {ins}, update {upd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
