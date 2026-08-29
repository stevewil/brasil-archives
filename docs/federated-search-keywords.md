# Federated search — keyword cheat sheet

For operators and curious visitors of `GET /search` (see
[`federated-search.md`](federated-search.md)). It searches the **harvested
`oai_dc` records** from partner corpora — not the web, not full text, just
the Dublin Core we last pulled. If a plausible term returns nothing, the
corpus probably doesn't cover it: these two corpora are narrow by design.

Matching is accent- and case-insensitive, so `sesmaria` = `Sesmaria`,
`indios` = `índios`.

Counts below were taken **2026-08-29** against 508 mipibu + 145 povos
`oai_dc` records. Re-mine after a harvest with:

```
python -m scripts.harvest --project <slug>          # refresh
# then, in a shell:  the snippet at the bottom of this file
```

---

## Mipibu — São José de Mipibu judicial corpus

**What it is:** cartório (registry) records from one Rio Grande do Norte
town — criminal proceedings ~1872–1926 and probate/wills ~1855–1926.
Portuguese only. Years present in metadata span **1862–2018** (later dates
are digitization/catalog stamps, not document dates).

**Case-type subjects** (`dc:subject`):

| term | ~hits | |
|---|---|---|
| `sumário crime` | 86 | criminal summary proceeding |
| `habeas corpus` | 19 | |
| `apelação` | 16 | appeal |
| `autoamento` | 10 | |
| `traslado` | 9 | certified copy |
| `recurso` | 7 | |
| `corpo de delito` | 5 | forensic examination |
| `auto de exame e vistoria` | 4 | |
| `sumário de culpa` | 4 | |
| `inquérito policial` | 4 | |

**Offence types** (normalized `dc:type`, English slugs):
`physical_assault` (41), `theft` (41), `homicide` (27), `bodily_harm` (11),
`verbal_offence_injuria` (5), `abuse_of_authority` (4), `infanticide` (4),
`property_damage` (4). Portuguese words also work: `furto` (39),
`homicídio` (27), `ofensas físicas`, `lesões corporais`.

**Productive free-text:** `crime`, `furto`, `homicídio`, `cavalo` (10 —
horse theft), `habeas`, `apelação`, `traslado`.

---

## Povos Indígenas do RN — Indigenous history corpus

**What it is:** colonial administrative correspondence (AHU / Projeto
Resgate) and imperial provincial reports (CRL) bearing on the Indigenous
peoples of Rio Grande do Norte, plus UFRN portal essays and academic
works. Years span **1675–2021** (colonial docs 1675–1823; scholarship
recent).

**Ethnonym / people subjects** (`dc:subject`):

| term | ~hits |
|---|---|
| `índios` | 74 (free-text) / 22 (subject) |
| `Potiguara` | 21 |
| `Canindé` | ~6 |
| `Paiacu` (also `Paiaku`, `Paiacú`) | ~9 |
| `Janduí` | 4 |
| `Tapuia` / `Tarairiú` | ~6 |
| `Caboré` / `Caboré-Açu` | 4 |
| `Caboclos` | ~4 |

**Document types** (`dc:type`): `colonial_manuscript` (30),
`imperial_report` (10), `colonial_ethnonym` (5),
`contemporary_self_identified` (5), plus academic:
`dissertacao` (18), `tcc` (4), `artigo` (3), `tese` (1), `livro_guia` (3).
Portuguese: `dissertação` (18), `manuscrito colonial`.

**Productive free-text:** `aldeia` (24 — mission village), `sesmaria` (4 —
colonial land grant), `capitão-mor` (34), `Conselho Ultramarino` (16),
`capitania`, `Natal`, `Assú` / `Açu`, `guerra dos bárbaros`.

---

## Things that return nothing (and why)

- **`escravo` / slavery terms** — neither corpus is indexed on this. Mipibu
  is post-1870 small-town crime; povos is Indigenous-focused colonial
  admin. Enslaved people appear *in* documents but not in the DC subjects.
- **Other Brazilian states, other archives** — only these two towns/themes
  are federated so far.
- **English terms** — metadata is Portuguese. Exception: the normalized
  offence-type slugs above (`theft`, `homicide`, …).
- **Full-text phrases from inside a document** — we only harvested
  catalog-level DC, not OCR/transcription. That is Phase 4 (IIIF Content
  Search fan-out).

---

## Re-mining after a harvest

```python
from app import create_app
from app.extensions import db
from app.models import AggregatedRecord, UpgradeProject
from collections import Counter
import json

app = create_app()
with app.app_context():
    for p in db.session.query(UpgradeProject).order_by(UpgradeProject.name):
        recs = db.session.query(AggregatedRecord).filter_by(
            upgrade_project_id=p.id, metadata_prefix="oai_dc").all()
        subj, typ, years = Counter(), Counter(), []
        for r in recs:
            c = json.loads(r.extracted_json).get("canonical", {})
            for s in c.get("subjects") or []: subj[s.strip()] += 1
            for t in c.get("types") or []: typ[str(t).strip()] += 1
            years += [y for y in (c.get("year_start"), c.get("year_end")) if y]
        print(p.name, len(recs), min(years, default="?"), "-", max(years, default="?"))
        print("  subjects:", subj.most_common(15))
        print("  types:   ", typ.most_common(12))
```

Keep `SAMPLE_QUERIES` in `app/services/federated_search.py` in sync with
whatever stays productive here.
