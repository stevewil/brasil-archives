"""Seed the composite ``archives`` row for the povos-indigenas-rn corpus.

``upgrade_projects.source_archive_id`` is NOT NULL, but povos's corpus is
assembled from several institutional holdings (AHU / CRL / UFRN) rather
than a single fonds in the Nordeste survey. This adds one ``Archive`` row
that stands for that composite, so
``configs/upgrade_projects/povos-indigenas-rn.yaml`` has a
``source_archive_slug`` to resolve against.

Idempotent: safe to re-run (upserts by slug).

Usage::

    .venv/Scripts/python -m scripts.seed_povos_archive
    .venv/Scripts/python -m scripts.seed_povos_archive --dry-run

See ``docs/integrations/povos-indigenas-rn.md`` §3 for context.
"""
from __future__ import annotations

import argparse

from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import Archive, InstitutionalType

SLUG = "povos-indigenas-rn-corpus"
INSTITUTIONAL_TYPE_SLUG = "research-project"

_DESCRIPTION_EN = (
    "Composite corpus assembled from AHU (Arquivo Histórico Ultramarino / "
    "Projeto Resgate), CRL (Center for Research Libraries — Brazilian "
    "Government Documents Digitization Project), and UFRN portal holdings. "
    "Not a single fonds: the 'archive' here is the assembled evidence base "
    "surfaced by the povos-indigenas-rn corpus explorer, which curates and "
    "audits colonial and imperial documents bearing on the Indigenous "
    "peoples of Rio Grande do Norte."
)
_DESCRIPTION_PT = (
    "Corpus composto reunido a partir de acervos do AHU (Arquivo Histórico "
    "Ultramarino / Projeto Resgate), da CRL (Center for Research Libraries — "
    "Brazilian Government Documents Digitization Project) e do portal da "
    "UFRN. Não é um fundo único: o 'arquivo' aqui é a base de evidências "
    "reunida e auditada pelo explorador de corpus povos-indigenas-rn, "
    "voltada a documentos coloniais e imperiais sobre os povos indígenas "
    "do Rio Grande do Norte."
)
_STATED_SCOPE = (
    "Colonial administrative correspondence (AHU) and imperial provincial "
    "reports (CRL) mentioning Indigenous peoples of RN, plus UFRN portal "
    "essays and academic works. ~40 documents, ~1623–1889."
)


def _fields(itype_id: int) -> dict:
    return {
        "name": "Povos Indígenas do RN — corpus",
        "name_pt": "Povos Indígenas do RN — corpus",
        "institutional_type_id": itype_id,
        "home_country_code": "BR",
        "home_state_code": "RN",
        "canonical_url": "https://povos-indigenas-rn.from-bottom-to.top",
        "description_en": _DESCRIPTION_EN,
        "description_pt": _DESCRIPTION_PT,
        "stated_scope": _STATED_SCOPE,
        "no_digital_content": False,
        "fair_use_eligible": True,
        "caveat_emptor": False,
        "survey_source": None,
        "survey_row": None,
    }


def run(*, dry_run: bool = False) -> str:
    itype = db.session.scalar(
        select(InstitutionalType).where(InstitutionalType.slug == INSTITUTIONAL_TYPE_SLUG)
    )
    if itype is None:
        raise SystemExit(
            f"institutional type '{INSTITUTIONAL_TYPE_SLUG}' not found — "
            "run `python -m scripts.load_vocabularies` first."
        )

    existing = db.session.scalar(select(Archive).where(Archive.slug == SLUG))
    fields = _fields(itype.id)
    if existing is None:
        db.session.add(Archive(slug=SLUG, **fields))
        action = "added"
    else:
        for key, value in fields.items():
            setattr(existing, key, value)
        action = "updated"

    if dry_run:
        db.session.rollback()
        return f"would have {action} {SLUG}"
    db.session.commit()
    row = db.session.scalar(select(Archive).where(Archive.slug == SLUG))
    return f"{action} {SLUG} (id={row.id})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        print(run(dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
