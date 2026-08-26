"""Load the Nordeste digital archives survey into the ``archives`` table.

Parses ``nordeste-digital-archives-survey.md`` — Table 1 (50 pipeline-
viable rows) and Table 2 (~30 no-content rows) — and produces one
``Archive`` row per entry. Idempotent by generated ``slug``.

Design choices for Phase 1:

- Extract raw survey fields into descriptive/scope columns; do not
  attempt structured Pass 2 tagging (record types, periods, themes)
  here — that lives in the scoring UI.
- Normalize the survey's "Institution type" text to
  :class:`InstitutionalType` slugs via a small mapping table.
- Preserve the primary URL as a plain URL (parsed out of the survey's
  markdown link). Everything else stays as-is in Portuguese/mixed text.
- Every archive gets ``survey_source`` and ``survey_row`` for
  provenance.

Usage::

    .venv/bin/python -m scripts.load_survey
    .venv/bin/python -m scripts.load_survey --survey <path> --dry-run
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import Archive, InstitutionalType

# The survey doc lives in the repo at docs/nordeste-digital-archives-survey.md.
# An earlier default pointed at an out-of-repo project-files path that only
# existed in a specific authoring environment; this default resolves inside
# any checkout of brasil-archives.
DEFAULT_SURVEY = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "nordeste-digital-archives-survey.md"
)

# Survey column indices (0-based, after stripping empty edges).
TABLE1_HEADERS = (
    "num", "state", "institution_pt", "institution_type", "city",
    "primary_url", "example_url", "record_types_text", "digital_level",
    "url_addressability", "est_corpus_size", "time_period_text",
    "handwriting_era", "access_tos", "mipibu_fit", "priority_notes",
    "source_of_lead",
)
TABLE2_HEADERS = (
    "state", "institution_pt", "institution_type", "city",
    "url", "available_content", "source_of_finding",
)

# Institution-type text → InstitutionalType.slug.
# The survey uses free-form text; we normalize with a case-insensitive
# substring match against these patterns (evaluated in order).
INSTITUTION_TYPE_MAP: tuple[tuple[str, str], ...] = (
    ("special/thematic", "special-thematic"),
    ("state archive", "state-archive"),
    ("state court", "state-court"),
    ("tribunal", "state-court"),
    ("federal university", "federal-university"),
    ("state university", "state-university"),
    ("university", "federal-university"),  # default university → federal
    ("municipal", "municipal"),
    ("diocesan", "diocesan"),
    ("ecclesiastical", "diocesan"),
    ("research project", "research-project"),
    ("third-party", "third-party-hosted"),
    ("individual", "individual"),
    ("national", "national"),
)


@dataclass
class SurveyRow:
    """Parsed row from either survey table."""

    table: int                    # 1 or 2
    survey_row: int               # 1-based row number within the table
    state: str
    institution_pt: str
    institution_type_text: str
    city: str
    primary_url: str              # extracted URL, plain
    description_pt: str           # what's available online (Table 2) or scope+notes (Table 1)
    stated_scope: str | None      # richer stated scope for Table 1
    curatorial_notes: str | None  # Priority notes (Table 1)
    source_of_lead: str           # provenance citation
    time_period_text: str | None  # free-text time span (Table 1)
    no_digital_content: bool


# --------------------------------------------------------------------------- #
# Parsing


MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _first_url(text: str) -> str:
    """Return the first URL found in ``text``, or the trimmed text itself.

    The survey stores primary URLs as ``[label](https://...)`` markdown.
    Some Table 2 entries have the archive institution's URL wrapped the
    same way, or occasionally as a bare URL.
    """
    m = MD_LINK_RE.search(text)
    if m:
        return m.group(2).strip()
    return text.strip()


def _strip_row_cells(line: str) -> list[str]:
    """Split a markdown table row on ``|`` and strip whitespace."""
    if not line.startswith("|") or not line.rstrip().endswith("|"):
        raise ValueError(f"Not a markdown table row: {line!r}")
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return cells


def _slugify(text: str) -> str:
    """ASCII lowercase-hyphen slug. Preserves numbers; drops punctuation."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_ = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_ = ascii_.lower()
    ascii_ = re.sub(r"[^a-z0-9]+", "-", ascii_).strip("-")
    return ascii_ or "archive"


def _map_institution_type(text: str) -> str:
    lowered = text.lower()
    for pattern, slug in INSTITUTION_TYPE_MAP:
        if pattern in lowered:
            return slug
    return "special-thematic"  # safe default; editable later


def _parse_int_or_none(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def parse_survey(markdown: str) -> list[SurveyRow]:
    """Return the concatenated list of Table 1 and Table 2 rows."""
    lines = markdown.splitlines()
    rows: list[SurveyRow] = []

    # Table 1 — rows begin with '| <num> |' where <num> is an integer.
    # Table 2 — rows begin with '| <STATE> |' where STATE is a 2-letter code.
    table_state = 0  # 0=before, 1=inside T1, 2=inside T2, 3=after
    table1_seq = 0
    table2_seq = 0

    for raw in lines:
        if raw.startswith("## Table 1"):
            table_state = 1
            continue
        if raw.startswith("## Table 2"):
            table_state = 2
            continue
        if raw.startswith("## ") and table_state in (1, 2):
            table_state = 3
            continue
        if not raw.strip().startswith("|"):
            continue
        # Skip header and separator rows
        if re.match(r"^\|\s*(#|State)\s*\|", raw, re.IGNORECASE):
            continue
        if re.match(r"^\|\s*[-:| ]+\|\s*$", raw):
            continue

        try:
            cells = _strip_row_cells(raw)
        except ValueError:
            continue

        if table_state == 1 and len(cells) == len(TABLE1_HEADERS):
            table1_seq += 1
            data = dict(zip(TABLE1_HEADERS, cells))
            rows.append(
                SurveyRow(
                    table=1,
                    survey_row=table1_seq,
                    state=data["state"],
                    institution_pt=data["institution_pt"],
                    institution_type_text=data["institution_type"],
                    city=data["city"],
                    primary_url=_first_url(data["primary_url"]),
                    description_pt=data["record_types_text"],
                    stated_scope=data["est_corpus_size"] or None,
                    curatorial_notes=data["priority_notes"] or None,
                    source_of_lead=data["source_of_lead"],
                    time_period_text=data["time_period_text"] or None,
                    no_digital_content=False,
                )
            )
        elif table_state == 2 and len(cells) == len(TABLE2_HEADERS):
            table2_seq += 1
            data = dict(zip(TABLE2_HEADERS, cells))
            rows.append(
                SurveyRow(
                    table=2,
                    survey_row=table2_seq,
                    state=data["state"],
                    institution_pt=data["institution_pt"],
                    institution_type_text=data["institution_type"],
                    city=data["city"],
                    primary_url=_first_url(data["url"]),
                    description_pt=data["available_content"],
                    stated_scope=None,
                    curatorial_notes=None,
                    source_of_lead=data["source_of_finding"],
                    time_period_text=None,
                    no_digital_content=True,
                )
            )

    return rows


# --------------------------------------------------------------------------- #
# Upsert


def _slug_for(row: SurveyRow) -> str:
    """Deterministic archive slug: <state>-<short-institution>-t<table>r<row>.

    Suffix guarantees survey uniqueness even for edge cases where two
    entries share an institution name (Table 1 vs. Table 2 for TJMA).
    """
    short = _slugify(row.institution_pt)[:60].strip("-")
    return f"{row.state.lower()}-{short}-t{row.table}r{row.survey_row}"


def upsert_rows(
    rows: Iterable[SurveyRow],
    *,
    type_lookup: dict[str, int],
    survey_source_name: str,
) -> tuple[int, int]:
    inserted = updated = 0
    for row in rows:
        slug = _slug_for(row)
        it_slug = _map_institution_type(row.institution_type_text)
        it_id = type_lookup.get(it_slug)
        if it_id is None:
            raise ValueError(
                f"Unknown institutional_type '{it_slug}' for row {row.survey_row} "
                f"({row.institution_pt}). Load vocabularies first."
            )

        payload = {
            "slug": slug,
            "name": row.institution_pt,
            "name_pt": row.institution_pt,
            "institutional_type_id": it_id,
            "home_country_code": "BR",
            "home_state_code": row.state,
            "home_city": row.city or None,
            "canonical_url": row.primary_url,
            "description_pt": row.description_pt or None,
            "curatorial_rarity_notes": row.curatorial_notes,
            "stated_scope": row.stated_scope,
            "no_digital_content": row.no_digital_content,
            "survey_source": survey_source_name,
            "survey_row": row.survey_row,
        }

        existing = db.session.scalar(select(Archive).where(Archive.slug == slug))
        if existing is None:
            db.session.add(Archive(**payload))
            inserted += 1
        else:
            dirty = False
            for k, v in payload.items():
                if getattr(existing, k) != v:
                    setattr(existing, k, v)
                    dirty = True
            if dirty:
                updated += 1
    return inserted, updated


def load(survey_path: Path, *, dry_run: bool = False) -> tuple[int, int, int]:
    """Load the survey. Returns ``(rows_parsed, inserted, updated)``."""
    markdown = survey_path.read_text(encoding="utf-8")
    rows = parse_survey(markdown)

    type_lookup = {
        row.slug: row.id for row in db.session.scalars(select(InstitutionalType)).all()
    }
    if not type_lookup:
        raise RuntimeError(
            "institutional_types table is empty; run scripts.load_vocabularies first."
        )

    ins, upd = upsert_rows(
        rows, type_lookup=type_lookup, survey_source_name=survey_path.name
    )

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()

    return len(rows), ins, upd


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--survey", type=Path, default=DEFAULT_SURVEY)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.survey.exists():
        raise SystemExit(f"Survey file not found: {args.survey}")

    app = create_app()
    with app.app_context():
        parsed, ins, upd = load(args.survey, dry_run=args.dry_run)

    verb = "would have" if args.dry_run else "did"
    print(
        f"survey rows parsed: {parsed}; "
        f"{verb} insert {ins}, update {upd} archive rows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
