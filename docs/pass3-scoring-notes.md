# Pass 3 scoring notes

**Status:** Reviewed by Steve 2026-08-28 — see "Review outcome" below.
Ready to load.

**Date:** 2026-08-27 (scored), 2026-08-28 (reviewed)
**Scored by:** `calibration/pass3`

---

## Review outcome (2026-08-28)

All eight borderline calls resolved **option A** (keep the drafted approach).
Changes applied to `configs/calibration/pass3.yaml`:

| # | Call | Decision | YAML change |
|---|------|----------|-------------|
| 1 | Scale = digitized vs. published volume | **A — digitized-volume basis** (Pass 2 TJMA precedent). Flagged as a known tension in `algorithm-v1.md` for the ADR-0001 review. | none |
| 2 | EAP703 accessibility contingency | **A — confirmed live**, `accessibility 6 → 8`. eap.bl.uk restored post-2023 attack; pages resolve + are search-indexed with real content (re-checked 2026-08-28). Pipeline axis 31 → 33, stays High/High. | `t1r6` accessibility 6→8; dropped the "contingent on catalogue live" flags |
| 3 | APEB indexes — finding aids scored as data | **A — leave as High pipeline / Low research.** They're scaffolding, not sources. Watch in the ADR-0001 threshold re-exam. | none |
| 4 | Atas da Câmara — transcription tier | **A — keep `provenance_curatorial 9`.** Anchor language ("partial or unverified transcription, print OCR") fits. | none |
| 5 | APEJE + APEPI — unreachable, not weak | **A — publish with floor scores** + `scholarly_access_practical = only-via-federation`. | `t1r10`, `t1r47` gain the facet |
| 6 | Cúria de Maceió — nothing online | **A — keep in the scored catalog** (scans exist, sample published via CPDHis; consistent with call 1). | none |
| 7 | `scholarly_access_practical` | **A — set it** for the clear `only-via-federation` cases: APEJE, APEPI, all 3 FamilySearch collections. | `t1r10`, `t1r37`, `t1r39`, `t1r43`, `t1r47` gain the facet |
| 8 | FamilySearch `institutional_type` | **A — keep `third-party-hosted`.** | none |

Net: EAP703 moves from "low confidence, contingent" to a firm High/High.
Everything else scored as drafted. `algorithm-v1.md` §"Aggregation" gains a
Scale-basis note for the ADR-0001 re-examination.

---
**Method:** desk scoring against `docs/algorithm-v1.md` anchors +
`docs/nordeste-digital-archives-survey.md` Table 1 + live site inspection
via WebFetch / WebSearch on 2026-08-27. Where a site could not be reached
this session, the dimension is scored conservatively and flagged.

## Scope and selection

Pass 3 targets 12–15 pipeline-viable archives from the survey not already
in `pass2.yaml`. The six Pass 2 anchors (TJMA t1r1, INTERPI t1r2, BCZM
t1r3, Jornais de Sergipe t1r4, Nupem t1r5, LABIM t1r8) are excluded. No
Pass 3 slug collides with Pass 2 (checked).

15 archives, all from survey Table 1 (`no_digital_content = False`).
Selection follows the brief: **Nordeste first (RN, PE, BA)**,
**ecclesiastical sources included** (4 of 15), **resource-poor archives
kept, not filtered** (Cúria de Maceió, APEPI, EAP703-blocked all scored).
State spread: RN×2, PE×2, BA×4, AL×2, MA×2, CE×1, PI×2.

Deliberately **not** picked this pass, and why:
- FamilySearch civil-registration collections for PE/PI/PB (survey rows
  35, 42, 44) — already heavily indexed, low marginal value; one RN civil
  set (t1r43) is scored as the linkage exemplar.
- APES photographic fundo (t1r19), Villa Digital / FUNDAJ (t1r21), Acervo
  Saturnino de Brito (t1r30) — iconographic / engineering, weak Mipibu
  fit; can come in a Pass 4.
- Memorial MP-RN (t1r29), Biblioteca Benedito Leite (t1r22), TRE-MA
  (t1r24) — thin leads needing manual inspection first.

## Cross-cutting scoring decisions Steve should ratify

1. **Scale on digitized-but-not-public holdings.** Pass 2 scored TJMA
   `scale = 10` citing "~2.5M images digitized overall" even though only
   ~10,000 processos are public. Pass 3 follows that precedent: APEPI
   (`scale 10`, 450k+ pages digitized, ~5% online), Cúria de Maceió
   (`scale 8`, 38-município baptism corpus, ~nothing online). If you'd
   rather Scale track **published** volume only, these three drop hard
   (APEPI 10→2, Cúria 8→1) and it changes the ADR-0001 re-examination.

2. **`scholarly_access_practical` not set.** `pass2.yaml` never sets this
   facet, so to "match the shape precisely" Pass 3 omits it too. But
   several Pass 3 archives are textbook `only-via-federation` candidates
   — APEJE (robots-blocked), EAP703 (if still catalogue-down), the three
   FamilySearch collections (ToS blocks bulk work; diocesan-copy route
   needed). Consider setting it when these land.

3. **FamilySearch `pipeline_ingestion_readiness = 2`.** Scored low
   because the ToS prohibition on systematic downloading is the binding
   constraint, not the technology. If the project pursues the
   Arquidiocese de Natal precedent (diocese gets its own image copy),
   the *diocesan copy* would be a different, higher-scoring archive.

4. **Internet Archive items scored as archives.** Atas da Câmara (t1r17)
   and the APEB index volumes (t1r18) are IA uploads, not institutional
   portals. They score very high on the pipeline axis (IA gives stable
   IDs, direct files, an API) — arguably the scoring rewards "someone put
   it on IA" more than institutional merit. Defensible (the algorithm is
   frame-neutral about delivery) but worth a conscious nod.

---

## Per-archive notes

### 1. APEB — Salvador notary books, EAP703 (British Library) — `t1r6`
- **In scope:** survey's own verdict — "the single richest Nordeste
  notarial corpus digitized anywhere": Salvador livros de notas
  1664–1911, incl. cartas de alforria and slave bills of sale. BA focus,
  slavery/notarial content, exactly Mipibu-shaped.
- **Evidence:** `eap.bl.uk/project/EAP703`, `/collection/EAP703-1-2`,
  BL archives search (WebSearch, 2026-08-27). Counts: 1,326 files /
  ~304,497 TIFF images, 1664–1911 (BL catalogue text via search result).
- **Uncertainty flags:**
  - The survey (Aug 2026) recorded the BL catalogue **offline since the
    Oct 2023 cyber-attack**. On 2026-08-27 `eap.bl.uk/archive-file/EAP703-*`
    and collection pages are **indexed by search engines again**,
    suggesting partial restoration — but direct WebFetch of item/collection
    pages returned **empty** this session, so image viewing could not be
    confirmed.
  - `accessibility 6` and `pipeline_ingestion_readiness 8` are the
    **contingent** scores. If the catalogue+viewer are confirmed live:
    accessibility → 8 (pipeline axis 31 → 33, stays High/High). If
    confirmed still dead: pipeline_ingestion_readiness → 1–2, accessibility
    → 2, and it collapses to Low pipeline / High research.
- **Borderline call for Steve:** verify EAP703 live status directly
  before this score is trusted — it swings the widest of any Pass 3 entry.

### 2. APEM — SIAPEM "Acervo Digital" — `t1r7`
- **In scope:** MA state archive; the Câmara Municipal de São Luís fundo
  (1645–1973) and Secretaria do Governo (1728–1914) are administrative
  series in the target period. Enumerable integer fundo IDs.
- **Evidence:** `apem.cultura.ma.gov.br/siapem/index.php` (WebFetch,
  2026-08-27). Fundos and date spans confirmed; an inventário-analítico
  (RDC-Arq) series is present.
- **Uncertainty flags:** the site is labelled "Acervo Digital" and serves
  instrument PDFs, but **per-item image availability was not confirmed**
  on the pages fetched (matches the survey's "catalog-with-thumbnails to
  full-scans-no-ocr" hedge). `accessibility 4`, `corpus_completeness 2`,
  `scale 4`, `pipeline_ingestion_readiness 4` are all conservative — if
  item-level scans are confirmed viewable, accessibility → 8 and this
  moves toward the middle band.

### 3. Acervo Digital de Fortaleza — `t1r9`
- **In scope:** the only CE Table-1 candidate with a real aggregator; the
  Câmara Municipal de Fortaleza and Instituto Histórico do Ceará slices +
  the 1824-onward hemeroteca are pre-1930 municipal material.
- **Evidence:** `acervo.fortaleza.ce.gov.br/pesquisa` (WebFetch,
  2026-08-27). Nine categories, rich facet search (60+ themes, 100+
  source institutions), downloads without registration. HEMEROTECA
  ~3,454 files 1824–2022 (from the survey's category-listing citation;
  the search page itself shows no counts).
- **Uncertainty flags:** per-item URLs are not exposed (viewer-locked),
  so `pipeline_ingestion_readiness 4` is a "needs reverse-engineering"
  score. Category counts other than HEMEROTECA are unknown — `scale 6`
  and `corpus_completeness 6` are estimates.

### 4. APEJE — Acervo Digital (AtoM) — `t1r10`  ⚠ unreachable
- **In scope:** largest PE state archival holding; PE is a priority
  state; the 19–20c local-periodicals hemeroteca is a strong target on
  paper.
- **Evidence:** `arquivopublico.pe.gov.br` homepage (WebFetch — resolves,
  confirms an "Acervo Digital" link + Hemeroteca section). The AtoM host
  `acervo.arquivopublico.pe.gov.br` **refused connection**
  (ECONNREFUSED 200.238.105.223) this session; the survey recorded it as
  `disallow_by_robots` and calls that "a genuine ToS signal, not a
  transient error."
- **Uncertainty flags:** almost everything. Scores are floor values:
  `accessibility 2`, `corpus_completeness 1`, `finding_aids 3`,
  `pipeline_ingestion_readiness 1`, `scale 4`. Naive 29/80 — near the
  bottom of the pass.
- **Borderline call for Steve:** this is an **access-negotiation**
  archive, not a harvest target. If you'd rather it not sit in the public
  catalog with near-floor scores until someone talks to APEJE, hold it
  back. Otherwise mark `scholarly_access_practical = only-via-federation`.

### 5. CPDHis/UFAL — documentação disponível para download — `t1r12`
- **In scope:** ecclesiastical (Arquivo da Cúria Metropolitana de
  Maceió source material); AL has almost no other digital primary
  sources; the survey calls it "the best partnership opportunity in the
  survey."
- **Evidence:** the ichca.ufal.br download page (WebFetch, 2026-08-27):
  3 manuscript PDFs (1794 testamento; 1847 livro de provisões e
  visitações; 1920–1929 register) + 1 periodical PDF (O Semeador n.1,
  1913) + a Google Drive folder for material "em processamento". >1 TB
  digitized total (survey, CPDHis Guia Geral 2024).
- **Uncertainty flags:** `corpus_completeness 1` and `scale 2` reflect
  that only a handful of items are online. Direct anonymous PDF download
  earns `accessibility 8` (docked from 10 for the Drive hop).

### 6. Arquivo da Cúria Metropolitana de Maceió — `t1r13`  ⚠ not online
- **In scope:** ecclesiastical; parish registers for 38 municipalities;
  the survey keeps it in Table 1 (not Table 2) because "the scans
  demonstrably exist and a small sample is already published via CPDHis."
- **Evidence:** `arquidiocesedemaceio.org.br` **did not resolve**
  (ENOTFOUND) 2026-08-27. Everything is from the survey + the CPDHis
  page. Baptism books 19c–1960s digitized, consultable in-loco only.
- **Uncertainty flags:** the whole entry is near-floor except
  `scale 8` (large digitized-but-unpublished corpus, TJMA precedent) and
  `uniqueness 6` (overlaps FamilySearch AL Church Records, survey row 41).
  Naive **26/80 — the lowest in the pass.**
- **Borderline call for Steve:** (a) does an archive with **nothing**
  browsable online belong in the scored catalog, or on a watch-list?
  (b) `scale 8` on offline material is the single most aggressive Scale
  call in Pass 3 — if you cap Scale to published volume, this goes to 1
  and naive → 19.

### 7. Museu de História do Piauí — UFPI — `t1r14`
- **In scope:** PI university vehicle; clean enumerable URL tree
  (`/acervo/<type>/<title>/<year>`); scanned, unindexed regional press.
- **Evidence:** site homepage + the `jornal-do-piauí/jp-ano-de-1970`
  item page (WebFetch, 2026-08-27). Confirmed: **direct PDF downloads
  via Google Drive, bundled one-PDF-per-month**, inline preview images,
  metadata is month+year only, no OCR.
- **Uncertainty flags:** `corpus_completeness 4` and `scale 4` are
  estimates (no per-title counts). `pipeline_ingestion_readiness 4` —
  property 4 (per-document isolation) fails because a month of issues is
  one PDF; property 1 is year-level not issue-level. A 2025 FINEP grant
  is expanding holdings — revisit.

### 8. APEB — AtoM + Coleção Independência do Brasil na Bahia — `t1r16`  ⚠ host intermittent
- **In scope:** BA priority; the Coleção Independência (Junta Provisória,
  Conselho Interino correspondence 1791–1835) is described to NOBRADE at
  all levels with digitized images — coherent, addressable, in-period.
- **Evidence:** `ba.gov.br/fpc/arquivo-publico-acervo` (WebFetch) +
  WebSearch. AtoM host `atom.fpc.ba.gov.br` **did not resolve**
  (ENOTFOUND) this session and also failed during the original survey —
  but Google has it fully indexed and a 2024 SECULT-BA announcement +
  cached AtoM pages confirm the Independência collection is live there
  (32 bundles/books, 1791–1835). Digitized material is <2% of APEB's
  ~7.4 km.
- **Uncertainty flags:** `accessibility 6` and
  `pipeline_ingestion_readiness 4` are docked for the reachability
  problem; if the host is reliably up, accessibility → 8. `scale 4` is a
  page-equivalent estimate for 32 bundles.

### 9. Atas da Câmara Municipal de Salvador (Internet Archive) — `t1r17`
- **In scope:** survey — "highest signal-to-effort ratio for colonial
  municipal records"; transcribed colonial council minutes, already
  OCR'd, ARK-citable, CC0. One of the survey's three "immediately
  actionable, no negotiation" targets.
- **Evidence:** `archive.org/details/atas-da-camara-volume-v-1669-1684`
  (WebFetch) + WebSearch for the series. Confirmed: djvu.txt full text
  (Tesseract PT OCR), 600 dpi, PDF/JP2, CC0, ARK `ark:/13960/t9j48t96h`.
  IA holds at least vols I (1625–1641), II (1641–1649), V (1669–1684) +
  a 1915 relatório.
- **Uncertainty flags:** `corpus_completeness 6` — exact count of atas
  volumes uploaded to IA was not enumerated ("dozens" per survey).
- **Borderline call for Steve:** `provenance_curatorial 9` puts this in
  the **transcription tier** (algorithm's categorical jump). The text is
  a *published scholarly transcription* (Documentos Históricos series)
  with an IA OCR layer over it — I read that as tier 9 "partial or
  unverified transcription (print OCR with known error rates)". If you
  think print-OCR-of-a-transcription shouldn't cross into the 9–10 band,
  drop to ~6 (research axis 29 → 26, flips to Low research).

### 10. APEB finding-aid indexes on Internet Archive — `t1r18`
- **In scope:** survey — "the highest-value scaffolding in the survey":
  machine-readable indexes to APEB's inventários, testamentos, escrituras,
  cíveis, crime, nascimentos, óbitos. Pairs with EAP703 (entry 1).
- **Evidence:** `archive.org/details/inventa-rios` (WebFetch) — the
  INVENTÁRIOS volume is a digitized 1890 imprint, 4.9 GB @ 300 dpi, ABBYY
  OCR, Public Domain Mark, uploaded by Urano Andrade 2020. Survey lists 8
  further index sets under the same uploader.
- **Uncertainty flags / borderline call for Steve:**
  - **These are finding aids, not primary sources.** `finding_aids 3`
    ("downloadable finding-aid PDFs only") is the honest anchor, but
    `pipeline_ingestion_readiness 8`, `scale 8` and `linkage_potential 8`
    all score the *index volumes themselves* as ingestible data. Decide
    whether an index-only resource should carry those high pipeline/
    linkage scores.
  - **Quadrant is 1 point from flipping:** research axis **27/40**,
    threshold 28. Currently "High pipeline / Low research". If
    `provenance_curatorial` goes 5 → 6 (the indexes *are* descriptive
    metadata, arguably tier 6) it becomes High/High. This is the entry
    most sensitive to the ADR-0001 threshold re-examination.

### 11. Acervo CEPE — Companhia Editora de Pernambuco — `t1r20`
- **In scope:** PE priority; the 19th-century Recife newspaper collection
  (small local titles likely outside Hemeroteca Digital Brasileira) +
  Jesuit property manuscripts with transcriptions; also the delivery
  channel for the CEPE–APEJE digitization agreement, so it will grow.
- **Evidence:** `acervo.cepe.com.br` homepage (WebFetch, 2026-08-27):
  category browse + thumbnail catalogue, collections named (19c Recife
  newspapers, Diário da Manhã 1927–1985, IDHeC papers, Jesuit property
  records with transcriptions).
- **Uncertainty flags:** the **viewing interface and per-item behaviour
  were not verified** past the homepage — `accessibility 6`,
  `pipeline_ingestion_readiness 4`, `scale 6`, `corpus_completeness 4`
  are all provisional. No item or page counts anywhere.

### 12. FamilySearch — RN Catholic Church Records — `t1r37`
- **In scope:** RN priority; ecclesiastical; survey calls it
  "strategically the best FamilySearch entry point" — 1M+ images for the
  Arquidiocese de Natal, **same state and record universe as the Mipibu
  corpus**, and the archdiocese holds an independent public copy (a route
  around the ToS).
- **Evidence:** FamilySearch RN Church Records wiki page (WebFetch —
  confirms dual access: indexed name search + waypoint browse by
  município/paróquia/tipo/anos; "partially indexed, browsable images";
  "contractual limitations" on image access). Image count (1M+ for Natal
  archdiocese, Feb 2019 delivery) and date range 1755–2019 from the
  survey's cited sources. CID 2177294.
- **Uncertainty flags:** `pipeline_ingestion_readiness 2` — ToS is the
  binding constraint. `uniqueness 6` — the images duplicate the diocesan
  copy and the physical originals. `corpus_completeness 6` — interior RN
  dioceses (Mossoró, Caicó) are less complete than Natal.

### 13. FamilySearch — Maranhão Catholic Church Records — `t1r39`
- **In scope:** ecclesiastical; **earliest start date (1673) of any
  Nordeste parish collection**; pairs naturally with the TJMA judicial
  corpus (Pass 2) for São Luís / Alcântara person-and-property linkage.
- **Evidence:** FamilySearch Brazil Church Records wiki (WebFetch —
  "1673–1962", "only partially indexed, but have browsable images").
  Record/image counts **not published** anywhere located.
- **Uncertainty flags:** `corpus_completeness 4` and `scale 8` are both
  estimates (no counts). `scale 8` assumes a state-wide 1673–1962 parish
  collection is in the tens-to-hundreds of thousands of images — plausible
  but unverified.

### 14. FamilySearch — RN Civil Registration — `t1r43`
- **In scope:** RN priority; the survey's designated **linkage exemplar**
  — "civil registration entries can be used to resolve persons named in
  the São José de Mipibu inventários and processos."
- **Evidence:** FamilySearch Brazil Civil Registration wiki (index +
  images, 1803–2020). RN image count **not published**; the comparable PE
  civil set holds ~5.4M images.
- **Uncertainty flags:** `uniqueness 4` — civil registration is heavily
  duplicated/indexed elsewhere; its value here is linkage, not corpus.
  `linkage_potential 7` is the highest of any Pass 3 entry and is the
  whole reason it's scored. `scale 6` is an estimate.

### 15. APEPI — Arquivo Público do Estado do Piauí (Casa Anísio Brito) — `t1r47`  ⚠ site unstable
- **In scope:** survey — "the strongest partnership case in the survey":
  450,000+ pages digitized since 2022, ~5% online, and both UFPI vehicles
  (Nupem, Museu de História do Piauí) already republish APEPI material.
- **Evidence:** `arquivopublico.pi.gov.br/acervo.php` **301-redirects to
  `pi.gov.br`** this session; `pi.gov.br` "Manuscritos Digitais" project
  page + WebSearch (al.pi.leg.br, meionews, G1) confirm 450k+ pages,
  ~5% online, "acesso controlado", Balaiada / Guerra do Paraguai /
  Independência collections.
- **Uncertainty flags:** `accessibility 2`, `finding_aids 2`,
  `pipeline_ingestion_readiness 1` — the institutional site did not serve
  a working catalogue this session. `scale 10` on 450k digitized pages
  (TJMA precedent; ~5% public) — same cap question as entry 6.

---

## Summary table

| # | Archive | Pipeline /40 | Research /40 | Naive /80 | Quadrant | Confidence |
|---|---|---|---|---|---|---|
| 1 | APEB — EAP703 Salvador notary books (BA) | 33 | 29 | 62 | High / High | medium — live confirmed 2026-08-28; viewer not click-tested |
| 2 | APEM — SIAPEM (MA) | 18 | 19 | 37 | Low / Low | low — item image access unverified |
| 3 | Acervo Digital de Fortaleza (CE) | 25 | 21 | 46 | Low / Low | medium |
| 4 | APEJE — AtoM (PE) | 10 | 19 | 29 | Low / Low | **very low** — host unreachable / robots-blocked |
| 5 | CPDHis/UFAL (AL) | 17 | 19 | 36 | Low / Low | medium — small but verified |
| 6 | Arquivo da Cúria Metropolitana de Maceió (AL) | 11 | 15 | 26 | Low / Low | low — nothing online; site down |
| 7 | Museu de História do Piauí (PI) | 22 | 17 | 39 | Low / Low | medium |
| 8 | APEB — AtoM + Coleção Independência (BA) | 20 | 21 | 41 | Low / Low | low — AtoM host intermittent |
| 9 | Atas da Câmara Municipal de Salvador — IA (BA) | 31 | 29 | 60 | High / High | medium-high |
| 10 | APEB finding-aid indexes — IA (BA) | 29 | 27 | 56 | **High / Low** | medium |
| 11 | Acervo CEPE (PE) | 22 | 20 | 42 | Low / Low | low-medium — homepage only |
| 12 | FamilySearch — RN Catholic Church Records | 24 | 23 | 47 | Low / Low | medium |
| 13 | FamilySearch — Maranhão Catholic Church Records | 22 | 23 | 45 | Low / Low | low-medium — no counts |
| 14 | FamilySearch — RN Civil Registration | 20 | 22 | 42 | Low / Low | low-medium |
| 15 | APEPI (PI) | 15 | 19 | 34 | Low / Low | **very low** — site unstable |

Quadrant threshold 28/40 per ADR-0001 (inclusive).

## Borderline calls that most need Steve's review

1. **EAP703 (entry 1) — live-status contingency.** accessibility 6 /
   pipeline 8 assume partial restoration. Confirmed-live → High/High
   firms up and accessibility → 8. Confirmed-dead → collapses to Low
   pipeline / High research. Verify before trusting.
2. **APEB finding-aid indexes (entry 10) — 1 point from High/High**
   (research 27/40) **and** scored as ingestible data despite being
   finding aids, not sources. The single most threshold-sensitive entry
   for the ADR-0001 re-examination.
3. **Atas da Câmara (entry 9) — provenance_curatorial 9** puts it in the
   transcription tier on the strength of a print-OCR'd published
   transcription. If that shouldn't cross into 9–10, it drops to ~6 and
   flips to Low research.
4. **Scale on unpublished holdings** — APEPI (10), Cúria de Maceió (8),
   APEB Independência (4 est.). Follows the Pass 2 TJMA precedent. If
   Scale should track *published* volume, APEPI → 2 and Cúria → 1, which
   materially changes the Pass 3 distribution feeding ADR-0001.
5. **APEJE (entry 4) and APEPI (entry 15)** — near-floor scores driven
   by unreachability, not assessed weakness. Decide: publish with floor
   scores + `only-via-federation`, or hold on a watch-list until access
   is negotiated.
6. **Cúria de Maceió (entry 6)** — naive 26/80, nothing browsable
   online. In the scored catalog or on a watch-list?
7. **`scholarly_access_practical`** — not set anywhere (matching
   `pass2.yaml`). At minimum APEJE, EAP703 (if down), and the three
   FamilySearch collections should be `only-via-federation` when this
   lands.
8. **FamilySearch institutional_type** — set to `third-party-hosted` in
   the YAML (the survey text "FamilySearch collection" maps to
   `special-thematic` by `load_survey`'s default). Confirm which you want.
