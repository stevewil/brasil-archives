# Controlled vocabularies

Reference for every controlled vocabulary used by the scoring algorithm and
the facet system. This document is descriptive — the **source of truth** is:

- **YAML-loaded vocabularies** (`configs/vocabularies/*.yaml` → DB tables via
  `python -m scripts.load_vocabularies`): time periods, record types, themes,
  institutional types.
- **Code-defined single-selects** (`app/services/scoring.py`
  `SINGLE_SELECT_FACETS`): licensing posture, stated roadmap, scholarly
  access practical.
- **Probe-fed single-selects** (`docs/algorithm-v1.md` §"Probe-updated
  facets"; written by the quarterly probe): web operations health, external
  preservation, growth signal, prior use signal.

If a vocabulary changes, edit the YAML/code above and update this file to
match. Slugs are stable identifiers; labels are display-only and bilingual.

---

## Human-tagged facets

### Time period — multi-select

Burns/Skidmore 12-tag periodization, Colonial subdivided. Source:
`configs/vocabularies/periods.yaml`. Multi-select on archives and upgrade
projects.

| slug | EN | PT | span |
|------|----|----|------|
| `pre-colonial` | Pre-colonial | Pré-colonial | –1500 |
| `early-colonial-1500-1700` | Early Colonial | Colônia — período inicial | 1500–1700 |
| `late-colonial-pombaline-1700-1808` | Late Colonial / Pombaline | Colônia — período pombalino | 1700–1808 |
| `joanine-1808-1822` | Joanine | Período joanino | 1808–1822 |
| `independence-first-reign-1822-1831` | Independence & First Reign | Independência e Primeiro Reinado | 1822–1831 |
| `regency-1831-1840` | Regency | Regência | 1831–1840 |
| `second-reign-imperio-1840-1889` | Second Reign / Império | Segundo Reinado / Império | 1840–1889 |
| `old-republic-1889-1930` | Old Republic | República Velha | 1889–1930 |
| `vargas-1930-1945` | Vargas | Era Vargas | 1930–1945 |
| `second-republic-1945-1964` | Second Republic | Segunda República | 1945–1964 |
| `military-dictatorship-1964-1985` | Military Dictatorship | Ditadura Militar | 1964–1985 |
| `new-republic-1985-present` | New Republic | Nova República | 1985– |

### Record type — multi-select

Source: `configs/vocabularies/record_types.yaml`. `category` groups related
types for faceted browse.

| slug | EN | PT | category |
|------|----|----|----------|
| `judicial` | Judicial records | Documentos judiciais | judicial |
| `notarial-land` | Notarial and land records | Documentos cartoriais e fundiários | notarial |
| `ecclesiastical` | Ecclesiastical records | Documentos eclesiásticos | ecclesiastical |
| `administrative-legislative` | Administrative and legislative records | Documentos administrativos e legislativos | administrative |
| `demographic-census` | Demographic and census records | Documentos demográficos e censitários | demographic |
| `slavery-post-abolition` | Slavery and post-abolition records | Documentos sobre escravidão e pós-abolição | slavery |
| `press-periodicals` | Press and periodicals | Imprensa e periódicos | press |
| `photographic-iconographic` | Photographic and iconographic material | Material fotográfico e iconográfico | iconographic |
| `personal-institutional-papers` | Personal and institutional papers | Arquivos pessoais e institucionais | papers |
| `manuscripts-books` | Manuscripts and books | Manuscritos e livros | manuscripts |
| `audiovisual` | Audiovisual material | Material audiovisual | audiovisual |

### Themes — multi-select (provisional)

Source: `configs/vocabularies/themes.yaml`. **All entries provisional** —
to be refined after Pass 2/3 tagging. `category` groups for browse.

| slug | EN | PT | category |
|------|----|----|----------|
| `slavery-freedom` | Slavery and freedom | Escravidão e liberdade | population |
| `indigenous-peoples` | Indigenous peoples | Povos indígenas | population |
| `migration-diaspora` | Migration and diaspora | Migração e diáspora | population |
| `family-kinship` | Family and kinship | Família e parentesco | population |
| `land-property` | Land and property | Terra e propriedade | economy |
| `commerce-trade` | Commerce and trade | Comércio | economy |
| `labor-work` | Labor and work | Trabalho | economy |
| `rural-agrarian` | Rural and agrarian history | História rural e agrária | economy |
| `religious-life` | Religious life | Vida religiosa | culture |
| `education-literacy` | Education and literacy | Educação e alfabetização | culture |
| `public-health-medicine` | Public health and medicine | Saúde pública e medicina | society |
| `crime-punishment` | Crime and punishment | Crime e punição | society |
| `gender-women` | Gender and women | Gênero e mulheres | society |
| `urban-history` | Urban history | História urbana | society |
| `politics-power` | Politics and power | Política e poder | politics |
| `state-formation` | State formation | Formação do Estado | politics |
| `environment-climate` | Environment and climate | Meio ambiente e clima | environment |

### Institutional type — single-select

Source: `configs/vocabularies/institutional_types.yaml`. Stored directly on
`Archive.institutional_type_id` (not a `FacetValue` row).

| slug | EN | PT |
|------|----|----|
| `national` | National institution | Instituição nacional |
| `federal-university` | Federal university | Universidade federal |
| `state-university` | State university | Universidade estadual |
| `state-court` | State court / tribunal | Tribunal de justiça estadual |
| `state-archive` | State archive | Arquivo público estadual |
| `municipal` | Municipal institution | Instituição municipal |
| `diocesan` | Diocesan / ecclesiastical | Diocesano / eclesiástico |
| `research-project` | Research project | Projeto de pesquisa |
| `individual` | Individual scholar or collector | Pesquisador ou colecionador individual |
| `third-party-hosted` | Third-party hosted | Hospedado por terceiros |
| `special-thematic` | Special / thematic collection | Coleção especial / temática |

### Licensing posture — single-select

Source: `app/services/scoring.py` `SINGLE_SELECT_FACETS`. Internal-only — not
scored, not surfaced on the public site.

| value | meaning |
|-------|---------|
| `redistribution-friendly` | Content may be redistributed (open license or public domain) |
| `citation-only` | Cite-and-link only; no bulk redistribution |
| `bulk-restricted` | Bulk retrieval or republishing restricted; downstream reusers must preserve this flag |

### Stated roadmap — single-select

| value | meaning |
|-------|---------|
| `published-and-active` | Public roadmap exists and is being met |
| `published-but-unmet` | Public roadmap exists but milestones are slipping |
| `informal` | Direction stated informally (blog, talk) but no published plan |
| `none` | No stated direction |
| `not-applicable` | Roadmap concept doesn't apply (e.g. a closed/complete collection) |

### Scholarly access practical — single-select

Annotates the accessibility dimension: does the archive's own access surface
support scholarly workflows, or does practical access require our federation
tooling? Not a scoring dimension. See
`docs/adr-0001-two-axis-aggregation.md` §"Related facet".

| value | meaning |
|-------|---------|
| `well-supported` | Search across record types, enumeration, stable citations, bulk retrieval all work on the archive's own site |
| `usable-with-effort` | Scholarly access possible but awkward — partial search, no enumeration, unstable URLs |
| `only-via-federation` | Practical scholarly access requires a Mipibu-style companion app / our federation tooling |
| `not-yet-assessed` | Not yet evaluated |

---

## Probe-updated facets

Refreshed quarterly by the scheduled probe (`docs/algorithm-v1.md`
§"Ongoing infrastructure"). Each carries a `last_probed` timestamp;
human-editable when the probe misses Portuguese-language evidence.

### Web operations health — single-select

Composited from HTTPS + cert validity, HTTP status on canonical and interior
URLs, robots.txt fetch.

`healthy` / `degraded` / `at-risk` / `down`

### External preservation — single-select

From Wayback CDX coverage of the domain and an interior URL sample.

`preserved` / `home-page-only` / `unpreserved`

### Growth signal — single-select

From Wayback CDX diff and directory-listing comparison against 12- and
24-month prior snapshots.

`active` (new content in last 12 months) / `slow` (new content in last 24
months) / `stalled` / `wound-down` / `unknown`

### Prior use signal — single-select

Best-effort from CrossRef / Semantic Scholar / Google Scholar.

`foundational` / `established` / `emerging` / `unused` / `unknown`

---

## Free-text facets (no vocabulary)

Stored directly on `Archive` as `Text` columns; audit trails for the reader,
not controlled values.

- **`curatorial_rarity_notes`** — e.g. "holds one of three known copies of
  the 1611 visita pastoral to Pernambuco."
- **`prior_use_note`** — concise description of main scholarly uses to date.
- **`size_unit_note`** — what unit the archive counts in (processos vs.
  images vs. page-equivalents vs. items), so the Scale dimension score is
  auditable. Stored on `Archive.size_unit_note`; loaded from the
  calibration YAML `facets:` block by `scripts/load_calibration.py`
  alongside `curatorial_rarity_notes` / `prior_use_note`.
