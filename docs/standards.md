# Standards conformance

**Status:** Statement of intent. Implementation phased.
**Date:** 2026-08-24

## Purpose

`brasil-archives` is a **federated open metadata infrastructure for Brazilian digital archives**. As such, it does not invent bespoke exchange formats where established archival standards already exist. This document names which standards the project intends to conform to, at what level, and in what phase.

The intent is threefold:

1. **Legitimacy** — position the project inside the existing archival-standards community rather than outside it.
2. **Interoperability** — allow `brasil-archives` to be harvested by existing federations (DPLA, Europeana, DIBRARQ, any future Brazilian national aggregator) and to harvest from existing archives and upgrade projects that expose standard interfaces.
3. **Portability** — protect against lock-in. Data described in ISAD(G) / Dublin Core / EAD is portable to any conforming platform; data described in a bespoke format is trapped.

## Standards we adopt

### Description standards (what an archive or record looks like)

- **ISAD(G) — General International Standard Archival Description.** ICA-published. Foundational hierarchical archival description. Referenced in the scoring algorithm (Dimension 2, Provenance and curatorial quality). `brasil-archives` describes archives at the fonds/collection level using ISAD(G) elements.
- **ISAAR(CPF) — International Standard Archival Authority Record — Corporate bodies, Persons, Families.** ICA-published. Used for describing the *creators* of archival materials.
- **ISDIAH — International Standard for Describing Institutions with Archival Holdings.** ICA-published. This is exactly the level `brasil-archives` operates at — describing the institutions that hold digital archives. Native fit.
- **Dublin Core / DCMI Terms.** Lightweight metadata, widely used, especially in DSpace deployments (several of our surveyed archives). Used as a floor exchange format when richer standards aren't available.
- **RiC-CM and RiC-O — Records in Contexts (Conceptual Model / Ontology).** ICA's newer, RDF-based conceptual model. Aspirational for `brasil-archives`; adopt as a serialization output when the LOD ecosystem for Brazilian archives matures.

### Encoding standards (how the description is serialized)

- **EAG — Encoded Archival Guide.** XML schema for describing institutions with archival holdings. Companion to EAD, published by PARES (Spain). Native output format for `brasil-archives`'s own descriptions of Brazilian archival institutions.
- **EAD — Encoded Archival Description.** XML schema for finding aids. `brasil-archives` doesn't produce finding aids at the item level, but consumes EAD from archives and upgrade projects that expose it.
- **EAC-CPF — Encoded Archival Context.** XML schema for authority records (persons, corporate bodies, families). Companion to EAD. Consumed for cross-archival person and institution linkage.

### Harvesting and federation standards (how machines exchange metadata)

- **OAI-PMH — Open Archives Initiative Protocol for Metadata Harvesting.** Primary harvest protocol. `brasil-archives` consumes OAI-PMH from source archives and upgrade projects; `brasil-archives` also publishes its own catalog via OAI-PMH so it can be harvested by others.
- **IIIF Content Search API.** Standard for federated full-text search across image-based digital objects. Consumed for cross-corpus search across upgrade projects. Serving IIIF Content Search is the responsibility of individual upgrade projects, not of `brasil-archives` itself.
- **ResourceSync.** Successor/companion to OAI-PMH for larger-scale sync. Not required for `brasil-archives`'s scale in v1; adopt if we outgrow OAI-PMH.
- **Web Annotation Data Model (W3C).** Standard for annotations on digital objects. Aspirational.

### Identifier and authority standards

- **Handle System / DOI.** Persistent identifiers. LABIM/UFRN already uses Handles. `brasil-archives` records the Handle prefix or DOI where an archive publishes them.
- **ARK — Archival Resource Key.** Persistent identifier framework common in archives and libraries. Recorded where present.
- **VIAF — Virtual International Authority File.** Federated person and corporate-body authority. `brasil-archives` records VIAF IDs for institutions where they exist.
- **GeoNames.** Place-name identifiers. Recorded for the geographic scope of each archive.
- **Wikidata Q-numbers.** Increasingly the LOD backbone for cross-referencing entities. Recorded as available.
- **ISNI — International Standard Name Identifier.** Person and organization identifier, ISO-standardized. Recorded where present.

## Conformance levels by phase

We adopt these standards in phases rather than trying to be fully conformant on day one.

### Phase 1 — Design and initial build (current)

- Design the data model with fields for standards-aware identifiers (Handle, VIAF, GeoNames, Wikidata) from the start
- Design the export data model as ISAD(G) / ISDIAH compatible
- Do not yet serve OAI-PMH or EAG output
- Do not yet harvest via OAI-PMH
- Populate identifier fields opportunistically as we score archives

### Phase 2 — Standards-native input

- Import Dublin Core / OAI-PMH data from source archives that expose it (BCZM/UFRN, Jornais de Sergipe, LABIM/UFRN)
- Add EAD import for archives that expose finding aids in EAD
- Retain provenance of imported metadata separately from `brasil-archives`-authored metadata (per Mipibu principle: original always preserved separately from interpretation)

### Phase 3 — Standards-native output

- Serve `brasil-archives`'s own catalog as OAI-PMH — **done** (`/oai`,
  provider blueprint `app/oai/`; see `docs/oai-pmh-provider.md`)
- Serve institution descriptions as EAG XML — **done** (`eag`
  metadataPrefix + `/archives/<slug>/eag.xml`)
- Serve authority records as EAC-CPF where applicable — deferred: no
  authority records of our own yet (see `docs/oai-pmh-provider.md` §7)
- Register with the OAI-PMH registry so we are discoverable — runbook
  written (`docs/oai-pmh-provider.md` §6); pending a production URL

### Phase 4 — Federation

- Consume IIIF Content Search API from registered upgrade projects (starting with Mipibu once retrofit)
- Aggregate cross-corpus search results in the `brasil-archives` UI
- Provide coverage-gap analysis: what periods, places, and record types are not yet covered by any upgrade project

### Phase 5 — LOD publication

- Publish RiC-O RDF alongside the primary formats
- Provide a SPARQL endpoint (or contribute to an existing one)
- Cross-reference to Wikidata, VIAF, GeoNames at RDF level

### Phase 6 — Community and certification

- Engage with archival standards bodies and Brazilian archival community per project timeline
- Consider CoreTrustSeal certification as a longer-term legitimacy marker
- Contribute back to standards development where our experience is relevant

## What we deliberately do not adopt

Naming what we deliberately do not do is as important as naming what we do.

- **We do not invent a bespoke `brasil-archives` API for federation.** If OAI-PMH and IIIF Content Search cover the use case, we use them. We do not add a proprietary REST API alongside them.
- **We do not host archive content.** `brasil-archives` is a catalog. Content lives at the archive itself, or in an upgrade project's own delivery system. We link out and describe, we do not deliver.
- **We do not require upgrade projects to use a specific technology stack.** An upgrade project can be Flask, Django, Rails, Ruby-on-Rails, PHP, or bespoke; if it speaks OAI-PMH and (optionally) IIIF Content Search, it can register.
- **We do not use MARC.** MARC is a library standard, not an archival one. Even though many Brazilian institutions have library and archival functions bundled, `brasil-archives` operates at the archival level and uses archival standards.

## References

Authoritative specifications, in order of first mention:

- ISAD(G): [International Council on Archives — ISAD(G) second edition](https://www.ica.org/en/isadg-general-international-standard-archival-description-second-edition)
- ISAAR(CPF): [ICA — ISAAR(CPF)](https://www.ica.org/en/isaar-cpf-international-standard-archival-authority-record-corporate-bodies-persons-and-families-2nd)
- ISDIAH: [ICA — ISDIAH](https://www.ica.org/en/isdiah-international-standard-describing-institutions-archival-holdings)
- Dublin Core: [DCMI Terms](https://www.dublincore.org/specifications/dublin-core/dcmi-terms/)
- RiC-CM/RiC-O: [ICA EGAD — Records in Contexts](https://www.ica.org/en/records-in-contexts-conceptual-model)
- EAG: [PARES — EAG schema](https://eag.readthedocs.io/)
- EAD: [Library of Congress — EAD](https://www.loc.gov/ead/)
- EAC-CPF: [Library of Congress — EAC-CPF](https://eac.staatsbibliothek-berlin.de/)
- OAI-PMH: [Open Archives Initiative — Protocol for Metadata Harvesting](https://www.openarchives.org/pmh/)
- IIIF Content Search API: [IIIF — Content Search API 2.0](https://iiif.io/api/search/2.0/)
- Web Annotation: [W3C Web Annotation Data Model](https://www.w3.org/TR/annotation-model/)
- Handle System: [Handle System — Corporation for National Research Initiatives](https://www.handle.net/)
- ARK: [ARK Alliance](https://arks.org/)
- VIAF: [Virtual International Authority File](https://viaf.org/)
- GeoNames: [GeoNames](https://www.geonames.org/)
- Wikidata: [Wikidata](https://www.wikidata.org/)
- ISNI: [ISNI International Agency](https://isni.org/)

## Change log

- **2026-08-24** — Initial statement of intent. Phase 1 in progress.
- **2026-08-27** — Phase 3 standards-native output implemented: OAI-PMH 2.0
  provider at `/oai` (`oai_dc` + `eag` formats) and per-institution EAG
  2012 at `/archives/<slug>/eag.xml`. See `docs/oai-pmh-provider.md`.
