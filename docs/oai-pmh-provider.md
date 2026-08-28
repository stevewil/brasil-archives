# OAI-PMH provider + EAG output — design & runbook

**Status:** Implemented. `docs/standards.md` Phase 3 ("Standards-native output").
**Date:** 2026-08-27
**Endpoint:** `GET`/`POST` `/oai` (OAI-PMH 2.0)
**Per-institution EAG:** `GET /archives/<slug>/eag.xml`
**Blueprint:** `app/oai/` — public, read-only, **not** admin-gated.
**Spec:** <https://www.openarchives.org/OAI/openarchivesprotocol.html>

> This is brasil-archives' first standards-native *output* surface. The
> harvesting *client* (what brasil-archives uses to pull from upgrade
> projects) is separate — `app/services/oai_client.py`. The provider's
> package structure deliberately mirrors mipibu's `app/oai/` (the
> reference provider in this ecosystem) so a shared package can be
> extracted later if a third provider appears.

---

## 1. What the provider exposes, and why

### Records = `Archive` rows only

brasil-archives' OAI feed disseminates **one record kind: `Archive` rows** —
the project's own ISDIAH-level descriptions of Brazilian archival
institutions. That is the metadata brasil-archives *authors* and is the
authoritative source for.

**`AggregatedRecord` rows are deliberately NOT exposed.** Those are
harvested *from* upgrade projects (mipibu, and future explorers) via their
own OAI endpoints. Re-serving them from `/oai` would:

- make brasil-archives a **mirror** rather than an index, contradicting
  `docs/scenario-driven-federation-model.md` ("federation as an index, not
  a mirror");
- **misattribute provenance** — the origin repository for those records is
  the upgrade project, which already serves them over OAI-PMH with correct
  `oai:` identifiers in its own namespace. A harvester that wants mipibu's
  case records should harvest `mipibu.from-bottom-to.top/oai` directly.

So there is exactly one identifier kind:

```
oai:brasil-archives.from-bottom-to.top:archive:<slug>
```

e.g. `oai:brasil-archives.from-bottom-to.top:archive:labim-ufrn`. The host
name is configurable (`OAI_REPOSITORY_IDENTIFIER`) but must stay stable
once registered.

### Public bar

`/oai` is a public redistribution surface, so it applies the project's
`uso justo` floor (`docs/handoff/2026-08-27-master.md` §2). An `Archive`
row is disseminated unless:

- `caveat_emptor = true` (the fatal-flaw bucket), or
- `fair_use_eligible = false` (explicitly ruled ineligible).

Rows **not yet reviewed** (`fair_use_eligible IS NULL`) and rows with
`no_digital_content = true` **are** included — an ISDIAH description of an
institution that holds nothing online yet is still valid catalog data.
This filter lives in one place: `app/oai/queries.py::_public_filter`.

### Sets

One record kind, partitioned along the slices a harvester is most likely
to want a slice of. Sets are **flat** (no nesting):

| setSpec pattern         | example                    | meaning                                   |
|-------------------------|----------------------------|-------------------------------------------|
| `state:<CODE>`          | `state:RN`                 | archives whose `home_state_code` = CODE   |
| `itype:<slug>`          | `itype:federal-university` | archives of that institutional type       |
| `content:digital`       | —                          | `no_digital_content = false`              |
| `content:no-digital`    | —                          | `no_digital_content = true`               |

`ListSets` only emits sets that actually have ≥1 public archive. Each set
carries two `<setName>` children (`xml:lang="pt"` and `"en"`) per
OAI-PMH §2.6.

### Datestamps & deleted records

- **granularity:** `YYYY-MM-DD` (day-level).
- **record datestamp:** `date(Archive.updated_at)`; floor `2024-01-01` for
  the (rare) row with a null timestamp.
- **`earliestDatestamp`:** `min(date(updated_at))` over public rows, or the
  floor if the catalog is empty.
- **`deletedRecord`: `no`.** `schema-v1` has no soft-delete — an archive
  row is either present or hard-deleted. If a soft-delete/tombstone column
  is added later, switch this to `transient` or `persistent` and emit
  `<header status="deleted">`.

---

## 2. Verbs & formats

All six OAI-PMH 2.0 verbs are implemented:

`Identify`, `ListMetadataFormats`, `ListSets`, `ListIdentifiers`,
`ListRecords`, `GetRecord`.

| metadataPrefix | namespace | notes |
|----------------|-----------|-------|
| `oai_dc` | `http://www.openarchives.org/OAI/2.0/oai_dc/` | required by the spec; DC 1.1 mapping below |
| `eag`   | `http://www.archivesportaleurope.net/Portal/profiles/eag_2012/` | EAG 2012 — the ISDIAH-native format; see §4 |

Error codes emitted: `badVerb`, `badArgument`, `badResumptionToken`,
`cannotDisseminateFormat`, `idDoesNotExist`, `noRecordsMatch`. (HTTP
status is always `200` for protocol errors, per §3.6.) Response
`Content-Type` is `text/xml; charset=utf-8`.

### `oai_dc` mapping (`Archive` → Dublin Core 1.1)

| DC element      | Source |
|-----------------|--------|
| `dc:identifier` | the OAI identifier; then `canonical_url`; then `catalog_url` (if different); then resolvable authority URIs built from `wikidata_qid` / `viaf_id` / `isni_id` / `doi` / `geonames_primary_id` |
| `dc:title`      | `name` (`xml:lang="en"`) and `name_pt` (`xml:lang="pt"`, if different) |
| `dc:description`| `description_en` (`en`), `description_pt` (`pt`), then `stated_scope` |
| `dc:publisher`  | `name` (the institution publishes its own holdings) |
| `dc:type`       | `"Collection"` (DCMI Type) + the institutional-type label (`en` + `pt`) |
| `dc:subject`    | one per record type + one per theme, each in `en` and `pt` |
| `dc:coverage`   | spatial: `home_city, home_state_code, home_country_code` joined; then temporal: one per period tag (`label (start/end)`) |
| `dc:relation`   | `oai_pmh_base_url`, `ead_finding_aid_url`, `iiif_manifest_root`, then the `primary_url` of every upgrade project whose `source_archive_id` is this archive |
| `dc:source`     | `survey_source` |
| `dc:language`   | `pt` (the described holdings are Portuguese-language) |
| `dc:date`       | `date(updated_at)` |
| `dc:rights`     | fixed statement: catalog metadata is CC BY-SA 4.0; rights in the holdings rest with the institution |

Bilingual PT/EN is carried via `xml:lang` on the repeated elements, which
`oai_dc.xsd` (through `dc:SimpleLiteral`) permits.

---

## 3. Resumption tokens

Design copied from mipibu's provider: **stateless, self-describing
base64url-encoded JSON**. No server-side cursor table, so a cPanel
Passenger restart mid-harvest is safe.

Token payload:

```json
{ "v": 1, "prefix": "oai_dc", "set": "state:RN" | null,
  "from": "YYYY-MM-DD" | null, "until": "YYYY-MM-DD" | null,
  "cursor": <int offset>, "total": <int count at issue time> }
```

- **Page size:** `OAI_PAGE_SIZE` (default **100**), applied to
  `ListRecords` and `ListIdentifiers`.
- **Ordering:** `ORDER BY archives.slug` — stable, so paging can't skip or
  double-count.
- **Emission (§3.5):** a single-page result emits **no** `<resumptionToken>`
  element; a multi-page result emits one with `completeListSize` + `cursor`
  attributes and the next token as text, and an **empty** element (attrs
  only) on the final page.
- `resumptionToken` is exclusive with every other argument → `badArgument`
  if combined. A token that won't decode, or carries an unknown
  `metadataPrefix`, → `badResumptionToken`. The live `total` in the
  response is authoritative; the token's copy is advisory only.
- `ListSets` is **not** paginated (the set space is tiny); a
  `resumptionToken` on `ListSets` → `badResumptionToken`.

---

## 4. EAG 2012 mapping

**EAG** (Encoded Archival Guide) is the ISDIAH-aligned XML schema for
describing institutions with archival holdings — the institution-level
companion to EAD. Namespace
`http://www.archivesportaleurope.net/Portal/profiles/eag_2012/`, schema
v0.6 (2020-10-19), maintained by the Archives Portal Europe Foundation
Working Group on Standards. Reference:
<https://www.archivesportaleurope.net/tools/for-content-providers/standards/eag/>
and the schema at
<http://www.archivesportaleurope.net/Portal/profiles/eag_2012.xsd>.

Served two ways, **identical content**:

- **Standalone:** `GET /archives/<slug>/eag.xml` — the stable per-institution
  URL. 404 for unknown slugs and for archives that fail the public bar.
- **In OAI:** `metadataPrefix=eag` on `ListRecords` / `GetRecord`.

### Element mapping (`Archive` → `<eag>`)

| EAG path | Source |
|----------|--------|
| `@audience` | `"external"` |
| `control/recordId` | `BR-<archive.id>` — the schema restricts `recordId` to a country code + short token, so the id is synthetic |
| `control/otherRecordId` | the full `oai:…:archive:<slug>` identifier (unrestricted element) |
| `control/maintenanceAgency/agencyCode` \| `agencyName` | `BR-brasil-archives` \| `brasil-archives` |
| `control/maintenanceStatus` | `derived` |
| `control/maintenanceHistory/maintenanceEvent` | machine event, `eventType=derived`, `eventDateTime` = record datestamp |
| `control/conventionDeclaration` | EAG + ISDIAH citations |
| `archguide/identity/repositorid/@countrycode` \| `@repositorycode` | `home_country_code` (upper) \| `BR-<slug>` |
| `archguide/identity/autform` (`xml:lang="por"`) | `name_pt` (falls back to `name`) |
| `archguide/identity/parform` (`xml:lang="eng"`) | `name` (if different from autform) |
| `archguide/identity/repositoryType` | mapped from institutional-type slug where a confident EAG enumeration exists (university → *University and research archives*, church → *Church and religious archives*, court → *Specialised government archives*, …); omitted otherwise |
| `desc/repositories/repository/repositoryName` | `name_pt` |
| `…/geogarea` | `"South America"` (schema enum; mandatory) |
| `…/location/@localType` | `"visitors address"` |
| `…/location/country` | `"Brazil"` for `BR` |
| `…/location/municipalityPostalcode` | `home_city, home_state_code` joined (`"—"` if both null — the element is schema-mandatory) |
| `…/email/@href` | `mailto:<contact_email>` (omitted if unknown) |
| `…/webpage/@href` | `canonical_url`; a second `webpage` for `catalog_url` if different |
| `…/holdings/descriptiveNote/p` | `description_en` + `stated_scope` folded together (`xml:lang="eng"`) |
| `…/timetable/opening` | placeholder pointing to the institution's own site |
| `…/access/@question` | `"yes"` + a `restaccess` note deferring to the institution |
| `…/accessibility/@question` | `"no"` + a "not recorded in the catalog" note |
| `…/descriptiveNote/p` (`xml:lang="por"`) | `description_pt` |
| `relations/resourceRelation` (`@resourceRelationType="other"`, `@href`) | one per upgrade project derived from this archive |

### EAG mapping decisions worth knowing

1. **`timetable` / `access` / `accessibility` are schema-mandatory** but the
   catalog does not hold opening hours or physical-access data. Rather than
   emit invalid EAG, the serializer writes honest placeholder text and a
   conservative `question` value (`access="yes"`, `accessibility="no"`),
   each with a note saying to consult the institution directly. If those
   facets are ever added to `schema-v1`, wire them here.
2. **`recordId` is synthetic** (`BR-<id>`) because the EAG `recordId`
   pattern rejects long slugs with dots. The real, stable identifier lives
   in `otherRecordId` and matches the OAI identifier exactly.
3. **`repositoryType` is best-effort.** Only slugs with an unambiguous EAG
   enumeration are mapped; anything else omits the element rather than
   guess.
4. **No full XSD validation in tests.** `lxml`/`xmlschema` are not
   dependencies. `tests/test_eag.py` asserts the structure `eag_2012.xsd`
   requires (namespace, root, mandatory elements, element order, name
   mapping). Validate against the live schema before a registry submission
   (see §6).

---

## 5. Configuration

| key | default | purpose |
|-----|---------|---------|
| `OAI_REPOSITORY_NAME` | `brasil-archives — Catálogo de arquivos digitais brasileiros` | `<repositoryName>` in `Identify` |
| `OAI_REPOSITORY_IDENTIFIER` | `brasil-archives.from-bottom-to.top` | host part of every `oai:` identifier + the `<oai-identifier>` block — **keep stable once registered** |
| `OAI_ADMIN_EMAIL` | `stevewil@gmail.com` | `<adminEmail>` |
| `OAI_PAGE_SIZE` | `100` | records per `ListRecords`/`ListIdentifiers` page |

The provider is registered in `app/__init__.py` and **CSRF-exempted**
(it accepts POST per the spec, has no forms and no session). No Alembic
migration — Phase 3 is serialization only, it reads existing tables.

---

## 6. Registry-registration runbook

Registration makes the repository discoverable to harvesters. It is a
**manual external step** — do it once, after the endpoint is live at its
production URL.

### Prerequisites

1. `/oai` is reachable at the **stable public HTTPS URL**
   `https://brasil-archives.from-bottom-to.top/oai` (this is the value in
   `OAI_REPOSITORY_IDENTIFIER` and in `<baseURL>` — they must agree).
2. The DB has real content (≥ a few dozen `Archive` rows).
3. `?verb=Identify` returns `<repositoryName>`, `<baseURL>`,
   `<protocolVersion>2.0</protocolVersion>`, `<adminEmail>`,
   `<earliestDatestamp>`, `<deletedRecord>`, `<granularity>`.

### Step 1 — validate conformance

Run the **OAI-PMH Validator & Data Provider Registration** service at the
Open Archives Initiative:

- URL: <https://www.openarchives.org/Register/ValidateSite>
- Enter `https://brasil-archives.from-bottom-to.top/oai`.
- It runs the full compliance suite: all six verbs, resumption-token
  paging (`ListRecords`/`ListIdentifiers` must page cleanly), error
  handling (`badVerb`, `badArgument`, `cannotDisseminateFormat`,
  `idDoesNotExist`), UTC `responseDate`, `oai_dc` well-formedness against
  `oai_dc.xsd`, and datestamp granularity.
- Fix any failures and re-run until it reports **"Site is compliant"**.
  Common gotchas for this provider: make sure the production DB is large
  enough that the validator exercises a real resumption token (set
  `OAI_PAGE_SIZE` low temporarily if the catalog is small), and that the
  server's clock is UTC-correct.

### Step 2 — register with the OAI registry

- On the same page, after a successful validation, use **"Register as a
  Data Provider"**. You must supply the base URL, the admin email
  (`OAI_ADMIN_EMAIL`), and confirm ownership via the email address in the
  `Identify` response.
- Once accepted, the repository is listed at
  <https://www.openarchives.org/Register/BrowseSites> and is picked up by
  aggregators that crawl the OAI registry.

### Step 3 — register with domain aggregators (optional, as they come online)

- **BASE (Bielefeld Academic Search Engine)** — the largest OAI harvester.
  Submit at <https://www.base-search.net/about/en/suggest.php> with the
  base URL. No pre-validation form; BASE harvests `oai_dc`.
- **A future Brazilian national archival aggregator / DIBRARQ** — when one
  exists, submit the same base URL. Because records are ISDIAH-shaped and
  `eag` is offered as a second `metadataPrefix`, such an aggregator can
  pull richer EAG directly.
- **OpenArchives / OpenAIRE / CORE** — only relevant if brasil-archives
  starts describing scholarly outputs; not applicable to an institution
  catalog today.

### Step 4 — record the registration

Add an entry to this file's change log with the date, the registry, and
the confirmation/reference number, so a later session knows it's done and
doesn't double-register.

### Ongoing

- Registries re-poll `Identify` periodically; keep the endpoint up and the
  `<baseURL>` unchanged.
- If `OAI_REPOSITORY_IDENTIFIER` or the public host ever changes, that is a
  **new repository** from a harvester's point of view — you must
  re-validate and re-register, and existing harvest state elsewhere is
  invalidated. Avoid.

---

## 7. Open questions for the user

1. **Public bar for `/oai`.** Current rule: exclude `caveat_emptor` and
   `fair_use_eligible = false`; include not-yet-reviewed and
   no-digital-content rows. Is that the right cut for a bulk
   redistribution surface, or should `/oai` be stricter (only
   `fair_use_eligible = true`) or looser (mirror the `/archives/` list
   view, which currently shows everything)?
2. **A `harvested` passthrough set.** If a future Brazilian national
   aggregator explicitly wants the *union* of everything brasil-archives
   knows about (including `AggregatedRecord` rows harvested from upgrade
   projects), we could add an opt-in set/format that passes those through
   with clear provenance. Deliberately not built now (mirror-vs-index).
   Build it only on a concrete request.
3. **`eag` vs `eag_dc` naming.** We advertise the EAG format under
   `metadataPrefix=eag`. Some aggregators expect `eag` to mean a specific
   profile. Confirm no clash when registering with a Brazilian aggregator.
4. **EAC-CPF.** `docs/standards.md` Phase 3 also lists "serve authority
   records as EAC-CPF where applicable". brasil-archives has no
   person/corporate authority records of its own yet (only identifier
   fields on `Archive`), so this was not built. Revisit when authority
   data exists.
5. ~~**`repositoryType` coverage.**~~ **Resolved 2026-08-28** — the map in
   `app/oai/eag.py` had invented slugs (`university`, `national-archive`,
   `diocese`, …) that never matched. Rewritten against the real
   `configs/vocabularies/institutional_types.yaml` — all 11 slugs covered,
   `third-party-hosted` / `special-thematic` → `"Other"`.

---

## Change log

- **2026-08-27** — Initial implementation. OAI-PMH 2.0 provider (`/oai`,
  all six verbs, `oai_dc` + `eag` formats, stateless resumption tokens),
  per-institution EAG 2012 at `/archives/<slug>/eag.xml`. Not yet
  registered with any registry (runbook §6 pending a production URL).
