# Licensing

This repository is licensed in two parts: the **software** and the
project's **curated data**. They are not the same and not under the same
license.

| | License | Covers |
|---|---|---|
| **Source code** | [MIT](LICENSE) | Everything in the repo except the data listed below |
| **Curated data** | [CC BY 4.0](LICENSE-CC-BY-4.0.txt) | The Nordeste digital archives survey and the controlled vocabularies |

> **TL;DR for reusers.** Build on the code freely — keep the MIT notice.
> If you reuse the *survey* or the *vocabularies*, **credit the Brasil
> Archives Project, link back, and note any changes you made.** That's it —
> no share-alike, no restrictions on how you use it.

## What is "the code"

All application source, tests, migrations, scripts, deployment helpers, and
documentation prose. Reuse under the [MIT License](LICENSE): keep the
copyright and permission notice, and it's yours to use, modify, and
redistribute, including commercially.

## What is "the curated data"

Licensed [CC BY 4.0](LICENSE-CC-BY-4.0.txt) — attribution only:

- **The Nordeste digital archives survey** —
  `docs/nordeste-digital-archives-survey.md` and the rows loaded from it by
  `scripts/load_survey.py`: which institutions exist, their URLs,
  institutional types, states, and the "no digital content" / fair-use
  eligibility judgments. This is the project's own compiled research — the
  underlying facts are not ours, but the selection, the descriptions, and
  the eligibility calls are.
- **The controlled vocabularies** — `configs/vocabularies/*.yaml` (periods,
  record types, themes, institutional types) as a curated bilingual set.

When you extract, redistribute, or build on this, CC BY 4.0 applies:
**attribute**, **link to the license**, and **indicate if you changed
anything**. Nothing more — you may use it commercially, adapt it, and
license your adaptation however you like.

### Suggested attribution

> Survey data from the Brasil Archives Project
> (https://brasil-archives.from-bottom-to.top), used under CC BY 4.0.

## Not yet public — the scoring output

The eight per-dimension scores, the two-axis totals and quadrant labels,
and the evaluative facets (`licensing_posture`, `stated_roadmap`,
`scholarly_access_practical`) and their curatorial notes are **not exposed
on the public site** and are not covered by either license above. When the
project is confident enough in these judgments to publish them, this
section will name their license (expected: CC BY 4.0, same as the survey).

## What is *not* covered by anything here

- **Harvested partner records.** The `aggregated_records` table holds
  Dublin Core harvested by OAI-PMH from partner corpus explorers (mipibu,
  povos-indigenas-rn). Those carry their **own** licenses, set by each
  partner — the Brasil Archives Project is an index of them, not their
  licensor. See each partner's `/api/schema`.
- **The archives' own holdings.** This project catalogs *metadata about*
  Brazilian digital archives; it never contains their documents, images, or
  transcriptions. Each source archive's content is governed entirely by
  that archive's own terms — follow the `canonical_url` / `catalog_url`.
  Listing an archive is a scholarly fair-use *eligibility judgment*
  (README §"Fundamental floor"), not a grant of any right in its content.
- **Fonts and any future third-party vendored asset** — their own licenses.

## A request, not a license term

We *ask* — but do not add as a binding condition — that reusers of the
survey do not use it for surveillance, or to drive mass reproduction of a
source archive's holdings in violation of that archive's terms of use. This
stays a request because turning it into a condition would make the data no
longer openly licensed, which would block legitimate scholarly aggregation.

## Contributions

Unless you state otherwise, contributions are licensed inbound = outbound:
code under the [MIT License](LICENSE), survey/vocabulary contributions
under [CC BY 4.0](LICENSE-CC-BY-4.0.txt).

## History

The code/data split was planned from the start (`docs/algorithm-v1.md`
§Licensing) and finalized 2026-08-29. Two earlier ideas were dropped: a
share-alike (CC BY-SA) data license — unnecessary friction for a project
that exists to be reused by resource-poor scholars — and a RAIL-style
responsible-use license term, which would have failed the open-data
definition. The concerns they addressed are handled by the fair-use floor,
by keeping the scoring output non-public until it is trustworthy, and by
the request above.
