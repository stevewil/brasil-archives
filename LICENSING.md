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

## Where the non-public data lives

The scored judgments above, the harvested partner records, and all catalog
metadata live in a **PostgreSQL database on the production host's own
`localhost`** — the cPanel account that runs the site. The database is not
reachable over the network: no public port, no REST / Data-API layer, no
anonymous credential. The only ways in are the application itself (via
`DATABASE_URL`, which is secret) and an SSH shell on the host.

On the public site the scored judgments are withheld by two independent
environment flags — `BRASIL_ARCHIVES_ADMIN` and
`BRASIL_ARCHIVES_PUBLIC_SCORES`, both unset on the public deployment;
`app/visibility.py` enforces it. The catalog and federated search work
without them.

**Off-site backup.** A weekly `pg_dump` of the whole database — the
non-public tables included — is encrypted on the host (AES-256-GCM) before
it leaves, and stored in a private object-storage bucket. The encryption
key lives only in the host's environment file and a password manager; it
is the sole access boundary on that copy. See
`scripts/backup_to_wasabi.py` and `docs/wasabi-backup.md`.

(A cloud-hosted Postgres was prepared for this data but the host's network
cannot reach it, so the local database above is what shipped. There is
therefore no anon-key / Data-API surface to keep locked down.)

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
