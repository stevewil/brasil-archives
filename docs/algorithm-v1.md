# Scoring Algorithm — v1

**Status:** Draft. First pass complete (Pass 1 — dimension design). Pass 2 (calibration on the six Mipibu-fit archives) and Pass 3 (application to the full 50-archive survey) still to run.

**Date:** 2026-08-24

**Purpose:** Grade Brazilian digital archives on their fitness for Mipibu-style pipeline treatment, using a mix of scored dimensions (frame-neutral, comparable across archives) and facets (frame-dependent, filterable but not scored).

**Standards positioning:** This algorithm is `brasil-archives`-specific. The federation contract (see `docs/federation-v1.md`) and the standards adopted by the project (see `docs/standards.md`) are separate concerns. The scoring dimensions reward archives whose delivery *conforms* to standards (OAI-PMH, IIIF, controlled authorities), but the dimensions themselves are project-authored.

## Design principles

1. **Score frame-neutral properties; facet frame-dependent ones.** If a value judgment depends on the researcher's period, subfield, or methodological frame (e.g., which record types are "important," which themes are "significant"), it becomes a facet rather than a score. Scores are reserved for properties every serious researcher benefits from equally.

2. **Real-world tested where possible.** Anchors are calibrated against the actual Mipibu build against LABIM/UFRN, not against abstract archival theory. See Dimension 5 (Pipeline Ingestion Readiness) for the strongest example.

3. **Transparent, auditable, per-dimension.** Each archive carries per-dimension scores with a written justification, not just a composite. The composite (aggregation deferred to Pass 2) sits on top of the transparent breakdown.

4. **Do not predict the future.** Where a proposed dimension required forecasting institutional durability, growth, or continued scholarly attention, we replaced the score with observable facets refreshed by a periodic probe. See Dimensions dropped from scoring.

5. **Do not reward existing attention.** Prior scholarly use was demoted from a scored dimension to a facet, because our project's mission includes surfacing neglected archives. A scoring system that rewards attention would undermine that.

## Fundamental floor

**Fair use / uso justo for scholarly work.** Every archive on the public site must clear this eligibility criterion. Archives that cannot are tracked internally to avoid duplicate research but are not published to the public interface.

## Scored dimensions (all 0–10)

Eight dimensions, each with defined anchor points. Present-tense observable; educatively calibrated where noted; auditable via a written per-archive justification.

### Dimension 1 — Accessibility

**What it measures:** How easily a researcher can reach individual documents.

- **10** — Anonymous open direct download (e.g., BCZM/UFRN newspaper directory)
- **8** — Anonymous browsing through a viewer (e.g., Jornais de Sergipe DSpace; TJMA restored processes)
- **6** — Free registration then full access (e.g., FamilySearch)
- **4** — Catalog/thumbnails only; source requires request/appointment/payment
- **2** — Finding aid or metadata only; documents in-person only
- **1** — Web presence but no online catalog; in-person only
- **0** — No public digital presence

### Dimension 2 — Provenance and curatorial quality (transcription tier at 9–10)

**What it measures:** Quality of descriptive and contextual metadata attached to each digital object, plus the categorical jump when transcription is present.

- **10** — Full verified transcription plus complete archival description
- **9** — Partial or unverified transcription (print OCR with known error rates, or manuscript subset transcription)
- **7** — Full ISAD(G)-complete description, no transcription
- **6** — Strong descriptive metadata but missing some ISAD(G) elements
- **5** — Basic metadata: title and date reliable; fonds/creator inconsistent
- **4** — Minimal metadata: filenames only, no fonds structure
- **2** — Undescribed image bundles
- **1** — Orphaned scans
- **0** — No metadata at all

Ranks 3 and 8 intentionally reserved as buffer zones between tiers.

### Dimension 3 — Corpus completeness within scope

**What it measures:** Given the scope the archive claims for itself, how much of that scope is digitally represented.

- **10** — Complete or near-complete digital coverage (>90%) of stated scope
- **8** — Substantially complete (60–90%) with disclosed gaps
- **6** — Partial coverage (30–60%)
- **4** — Sparse coverage (10–30%)
- **2** — Token coverage (<10%)
- **1** — Digitization exists but almost nothing published
- **0** — Nothing digitized, or nothing published from what's digitized

### Dimension 4 — Finding aids and indexes

**What it measures:** Search and browse mechanisms that let a researcher locate specific documents before viewing them.

- **10** — Full-text search + faceted browse + machine-readable index (OAI-PMH, API, CSV export)
- **9** — Full-text search + faceted browse, no machine-readable export
- **7** — Faceted browse and metadata search, no full-text
- **6** — Basic metadata search or well-organized browse hierarchy
- **4** — Filename-only search or flat listing
- **3** — Downloadable finding-aid PDFs only
- **2** — Institutional catalog exists but doesn't index digital objects
- **1** — Only a general institutional description; no item-level search
- **0** — No search or browse mechanism

### Dimension 5 — Pipeline ingestion readiness (Mipibu-baseline)

**What it measures:** How close the archive is to being ingestible by a Mipibu-shape pipeline. Grounded in the real technical properties that made the Mipibu build against LABIM/UFRN work.

**Five baseline properties:**

1. **Individually addressable documents** — one URL per document, resolvable and stable
2. **Direct file access** — the URL returns the file (PDF, JPG, TIFF), not a JS viewer wrapper
3. **Adequate image resolution** — ≥150 dpi for readable text; ≥300 dpi preferred for masters
4. **Per-document isolation** — one document per file, not multiple documents bundled
5. **Enumerable structure** — either a sequential ID pattern, a machine-readable index, or a documented API (OAI-PMH, REST, sitemap, XML feed, or directory listing) that lets a pipeline discover documents systematically. Documented APIs and OAI-PMH count fully. OAI-PMH conformance per `docs/standards.md` is the preferred form.

**Anchor scale:**

- **10** — All five baseline properties met
- **8** — Four of five properties met, one manageable gap
- **6** — Three of five properties met, moderate pipeline work required
- **4** — Two of five properties met, fundamental gaps
- **2** — One property met
- **1** — Content online in some form but no baseline property cleanly met
- **0** — No pipeline-ingestible content

Highly objective — each property is testable with a browser and curl.

### Dimension 6 — Uniqueness / non-duplication

**What it measures:** Whether this archive holds material not already available digitally elsewhere. Frame-neutral in the useful sense, though it carries first-to-digital bias worth flagging.

- **10** — Only known digital source for its material
- **8** — Effectively unique for practical purposes; technical duplicates exist but no competing digitization at comparable scope/quality
- **6** — Partial overlap with other digital sources
- **4** — Substantially duplicated by better sources; still useful as backup
- **2** — Largely duplicated; redundant except in edge cases
- **1** — Fully duplicated, no distinct digital value
- **0** — Duplicative to the point of noise

**Known bias:** Rewards first-to-digital, not best-in-digital. Scores may drift downward over time as more archives digitize the same material. Documented; not corrected in v1.

### Dimension 7 — Scale (absolute size)

**What it measures:** Absolute digital holdings in normalized page-equivalents.

- **10** — 50,000+ page-equivalents
- **8** — 10,000–50,000
- **6** — 1,000–10,000
- **4** — 100–1,000
- **2** — 10–100
- **1** — <10
- **0** — Nothing digitized

Roughly log-scaled. Distinct from Dimension 3 (Completeness): Scale measures raw size; Completeness measures fulfillment ratio. A large-but-sparse archive scores high on Scale, low on Completeness; a small-but-complete archive is the opposite. Both matter; interaction handled at aggregation time.

Unit heterogeneity acknowledged — pages of newspaper, items of judicial, hours of audiovisual. Each archive carries a `size_unit_note` to make the score auditable.

### Dimension 8 — Linkage potential

**What it measures:** How well this archive's content connects to other archives via named entities, controlled vocabularies, and standardized identifiers. Distinct from Dimension 5's API/enumerability property, which is about *fetching*; this is about *connecting once fetched*.

- **10** — Controlled authorities (VIAF, GeoNames, LOD linkage) per `docs/standards.md`, standard identifiers (Handle, ARK, DOI), dense in extractable named entities. Aspirational; no current shortlist archive reaches this.
- **8** — Rich structured metadata with consistent controlled vocabulary for at least one of place/person/institution; content dense in named entities extractable with modest work
- **6** — Structured metadata for one entity type; content dense in names but requires transcription
- **5** — High-linkage content in principle, but metadata-thin delivery; requires full pipeline work first
- **4** — Moderately name-dense content; minimal metadata
- **3** — Content name-sparse or unsuited to entity extraction
- **2** — Content atomic and non-linkable
- **1** — No extractable entities
- **0** — No linkage potential

## Facet fields (not scored)

Twelve fields. Some human-tagged, some probe-updated, some free text.

### Human-tagged facets

- **Time period** — 12-tag vocabulary, multi-select: Pre-colonial | Early Colonial 1500–1700 | Late Colonial/Pombaline 1700–1808 | Joanine 1808–1822 | Independence & First Reign 1822–1831 | Regency 1831–1840 | Second Reign/Império 1840–1889 | Old Republic 1889–1930 | Vargas 1930–1945 | Second Republic 1945–1964 | Military Dictatorship 1964–1985 | New Republic 1985–present. Burns/Skidmore periodization, Colonial subdivided.
- **Licensing posture** — single-select: `redistribution-friendly` / `citation-only` / `bulk-restricted`. Internal-only; not scored, not surfaced on public site.
- **Record type** — multi-select from vocabulary (Judicial, Notarial and land, Ecclesiastical, Administrative and legislative, Demographic and census, Slavery and post-abolition, Press and periodicals, Photographic and iconographic, Personal and institutional papers, Manuscripts and books, Audiovisual). Full vocabulary in `docs/vocabularies.md`.
- **Themes** — multi-select from vocabulary (provisional; refine after tagging shortlist). Full vocabulary in `docs/vocabularies.md`.
- **Curatorial rarity notes** — free text. Room for observations like "holds one of three known copies of the 1611 visita pastoral to Pernambuco."
- **Institutional type** — single-select: `national` / `federal-university` / `state-university` / `state-court` / `state-archive` / `municipal` / `diocesan` / `research-project` / `individual` / `third-party-hosted`.
- **Stated roadmap** — single-select: `published-and-active` / `published-but-unmet` / `informal` / `none` / `not-applicable`.
- **Prior use note** — free text. Concise description of the main scholarly uses to date.

### Probe-updated facets

Refreshed quarterly by a scheduled probe. Each carries a `last_probed` timestamp.

- **Web operations health** — single-select: `healthy` / `degraded` / `at-risk` / `down`. Composited from HTTPS + cert validity, HTTP status on canonical and interior URLs, robots.txt fetch.
- **External preservation** — single-select: `preserved` / `home-page-only` / `unpreserved`. From Wayback CDX coverage of domain and interior URL sample.
- **Growth signal** — single-select: `active` (new content in last 12 months) / `slow` (new content in last 24 months) / `stalled` / `wound-down` / `unknown`. From Wayback CDX diff and directory-listing comparison against 12- and 24-month prior snapshots.
- **Prior use signal** — single-select: `foundational` / `established` / `emerging` / `unused` / `unknown`. Best-effort from CrossRef / Semantic Scholar / Google Scholar; human-editable when probe misses Portuguese-language scholarship.

## Dropped from scoring

Dimensions initially proposed but demoted or removed. Each carries a rationale so future reviewers can revisit.

- **Historical depth** — became the time-period facet. Rationale: frame-dependent value judgment (age-as-value bias); national-period historian holds 19c documents as more valuable than colonial for their frame, so scoring would encode one frame's preferences.
- **Licensing-as-score** — became the licensing facet + `LICENSING.md` (deferred). Rationale: over-scoring licensing hurts the individual researcher who is protected by fair use; per-archive licensing scoring conflates two different questions (individual UX vs. downstream reuse posture).
- **Institutional stability** — became three facets (institutional type + web ops health + external preservation). Rationale: stability is a claim about the future; we can only measure the present. Facets record what's observable; probe keeps them current.
- **Growth trajectory** — became two facets (growth signal + stated roadmap). Rationale: same as institutional stability; growth is future-facing prediction dressed as measurement.
- **Prior scholarly use** — became two facets (prior use signal + prior use note). Rationale: scoring would reward already-noticed archives, cutting against the project's mission of surfacing neglected material.
- **Record type importance** — became the record type facet. Rationale: no frame-neutral hierarchy of record types exists.
- **Thematic significance** — became the themes facet. Rationale: thematic value is question-driven; every frame elevates different themes.

## Aggregation

**Status:** deferred to Pass 2. Rationale: we do not yet have evidence of how the eight dimensions co-vary in real archives. Tensions flagged in principle (Scale × Completeness, Uniqueness × Scale) but not observed. Aggregation choices work very differently on real data.

**v0 placeholder:** display per-dimension scores plus a naive sum (0–80). Not authoritative; a placeholder that gives us signal without pre-committing.

**v1 (Pass 2, adopted 2026-08-24) — two-axis view.** After scoring the six-archive calibration set, we adopted a two-axis 4-4 split alongside the naive sum. See `docs/adr-0001-two-axis-aggregation.md` for the full rationale; the summary is:

- **Pipeline axis** (0–40) = accessibility + finding_aids + pipeline_ingestion_readiness + scale. What it costs us to ingest.
- **Research axis** (0–40) = provenance_curatorial + corpus_completeness + uniqueness_non_duplication + linkage_potential. What we get back once we do.
- **Quadrant label** at threshold **26/40** (average anchor ~6.5, just above the field median) using inclusive comparison: `pipeline >= 26 and research >= 26` → "High pipeline / High research", and so on. Unscored archives return `"n.a."`. *(ADR-0001 originally set 28; [ADR-0002](adr-0002-axis-re-examination.md) lowered it after Pass 3 showed 28 admitted only 2 of 21 archives to High/High.)*
- **Naive sum kept** as a legacy 0–80 column on both the list page (sortable) and the detail card. It remains useful when one axis is unscored and it preserves continuity with Pass 1 outputs.
- **Sorting.** The list page offers `sort=name`, `sort=score` (naive sum), `sort=pipeline`, and `sort=research`. Each axis sort ranks NULLs last so partially-scored archives don't crowd the top.

The axis membership table (`app.services.scoring.AXES`) lives in code and is guarded by an import-time sanity check that asserts every dimension in `DIMENSIONS` appears in exactly one axis. Any change to that partition is a code-review event, not a config edit.

**ADR-0002 re-examination (2026-08-29, 21 archives).** The 4-4 partition was
re-tested and kept. Two findings recorded for a Pass 4 review — *do not act
without an ADR*:

- The **research axis is not internally coherent** (Cronbach α ≈ 0.49; the
  pipeline axis is 0.66). `uniqueness_non_duplication` is near-constant
  (mean 7.7, sd 1.5 — almost every Nordeste archive is the only digital
  copy) and uncorrelated with everything; `corpus_completeness` correlates
  with the *pipeline* dimensions (r ≈ 0.65), a resourcing confound rather
  than a mis-categorisation. Pass 4 should consider demoting `uniqueness`
  to a standalone flag and/or splitting research into "metadata quality"
  (provenance + linkage) vs "collection substance" (completeness + scale).
- The two axis totals **co-vary** (r ≈ 0.68) — both track archive
  resourcing; they are not the trade-off ADR-0001 assumed. The split still
  earns its place: ~30% of archives sit off the diagonal (INTERPI, LABIM,
  BCZM, TJMA, Jornais de Sergipe, APEB finding-aid indexes) where a single
  scalar misleads.

**Related facet: `scholarly_access_practical`** (added at the same time). Single-select over `well-supported`, `usable-with-effort`, `only-via-federation`, `not-yet-assessed`. This is *not* a scoring dimension — it annotates whether an archive's own access surface supports scholarly workflows or whether reaching that material practically requires our federation tooling. It complements the pipeline axis by naming *who pays the ingestion cost*.

**Aggregation options still open for later evaluation:**

- Equal-weighted sum, normalized to 0–10
- Weighted sum (weights TBD from Pass 2 intuitions)
- Multiplicative combination (any zero → zero composite)
- Category floors (e.g., Pipeline readiness < 4 caps composite at 5)
- Tiered gates (e.g., must clear Accessibility ≥ 4 to enter the top tier)

## Ongoing infrastructure

**Quarterly probe** — one scheduled cron per archive (or one batch job over all archives). Signals collected per archive:

- HTTPS + cert validity
- HTTP status on canonical URL
- HTTP status on 5–10 sample interior URLs
- Wayback CDX response for domain
- Wayback CDX response for interior URL sample
- robots.txt fetch
- Directory listing or sitemap diff against prior probe (for growth signal)
- CrossRef / Semantic Scholar citation count (for prior use signal)

Probe outputs update the four probe-fed facets and log a `last_probed` timestamp per archive.

## Licensing (deferred until public release)

To be finalized before public release. Planned structure:

- **Code license** — permissive (MIT or Apache 2.0). Encourages other historians and small projects to build on the tooling.
- **Data license** — share-alike (CC-BY-SA 4.0 or similar) with attribution required. Downstream reusers of the derived database must (a) attribute, (b) inherit the license, (c) preserve archive-level `bulk-restricted` flags. Defense against hyperscaler abuse — a downstream service ingesting our data and republishing under permissive terms would be in violation.
- **Optional responsible-use clause** — modeled on RAIL licenses; prohibits use for surveillance, mass-scale republishing of restricted-content archives, or use that violates the ToS of source archives our metadata points to.

Full text lives in `LICENSING.md` when we get closer to public release.

## Change log

- **2026-08-24** — Pass 1 complete. Eight scored dimensions, twelve facets, aggregation deferred. First test scope confirmed as the six Mipibu-fit archives (LABIM/UFRN as anchor + the five survey-listed pipeline-viable archives: TJMA, INTERPI, BCZM/UFRN, Jornais de Sergipe, Nupem).
- **2026-08-24** — Standards positioning added; light cross-references to `docs/standards.md` and `docs/federation-v1.md` inserted. No dimension anchors changed.
- **2026-08-24** — Aggregation moved from v0-placeholder to v1: two-axis view (Pipeline/Research, 4-4 split) adopted alongside the naive sum. Quadrant label at threshold 28/40 (inclusive). New `scholarly_access_practical` facet added; not a scoring dimension. See `docs/adr-0001-two-axis-aggregation.md`.
- **2026-08-28** — Pass 3 loaded: 15 pipeline-viable Nordeste archives (`configs/calibration/pass3.yaml`, `docs/pass3-scoring-notes.md`). 13 of 15 land Low/Low pipeline/research.
  - **Open tension for the ADR-0001 re-examination — Scale basis.** Dimension 7 is scored on *digitally held* volume, not *published* volume, following the Pass 2 TJMA precedent (`scale 10` on ~2.5M images digitized though ~10k processos are public). Pass 3 applies the same to APEPI (`10`, 450k pages digitized / ~5% online), Cúria de Maceió (`8`, corpus digitized / ~nothing online) and APEB–Independência (`4`). If the axis re-examination decides Scale should track published volume, these four scores drop hard and the quadrant distribution shifts. Not changed now (would re-open Pass 2); flagged here.
  - **Threshold sensitivity.** APEB finding-aid indexes (`t1r18`) sit at research axis 27/40 — one point below the 28 threshold — and are scored as ingestible data despite being finding aids. The entry most sensitive to any threshold change.
- **2026-08-29 — [ADR-0002](adr-0002-axis-re-examination.md) accepted** (re-examination over 21 scored archives): 4-4 partition kept; **quadrant threshold 28 → 26** (`quadrant_label` default); research-axis low coherence (α ≈ 0.49) + the `uniqueness`/`corpus_completeness` findings recorded above for Pass 4. Two archives' quadrant labels change (LABIM/UFRN, APEB finding-aid indexes → High research). The Scale-basis tension is *not* resolved by ADR-0002 — it stays flagged for Pass 4. No re-scoring.
