# ADR-0002: Re-examining the two-axis aggregation after Pass 3

- **Status:** **Accepted, 2026-08-29** — R1 + R2 + R3 all adopted.
- **Date:** 2026-08-29
- **Deciders:** Steve Williams
- **Amends:** [ADR-0001](adr-0001-two-axis-aggregation.md) (does not replace it —
  the two-axis view and the naive sum both stand).
- **Trigger:** ADR-0001 §"Open follow-ups": *"After Pass 3 (roughly 12–15
  archives) we should re-examine whether the 4-4 partition still fits and
  whether the 28 threshold still separates 'uniformly usable' from the
  middle band."*

## Data

21 archives now carry all 8 dimension scores: the 6 Pass 2 anchors +
15 Pass 3 (`configs/calibration/{pass2,pass3}.yaml`). All analysis below is
over that set. Reproduce with the script in this file's git history / re-run
against the live DB.

### Finding 1 — the axes co-vary; they are **not** a trade-off

ADR-0001's motivating claim was *"across the six calibration archives, no
archive was uniformly high on both — one axis dominated in every case."*
**That does not survive Pass 3.**

| metric | value |
|---|---|
| Pearson r, pipeline total vs research total (n=21) | **+0.68** |
| quadrant distribution at threshold 28 | HH **2** · HL **5** · LH **1** · LL **13** |

The two axes share a strong latent factor — call it *archive resourcing*.
Well-funded institutions (federal universities, large state digitisation
projects) score decently on both; resource-poor archives score low on both.
13 of 21 land in Low/Low. There is no fundamental cost/value tension; there
is a common "how much has this archive invested" signal.

**This does not make the two axes useless.** Six archives sit off the
diagonal, and they are exactly the ones where a single scalar misleads:

| archive | pipeline | research | why the split matters |
|---|---|---|---|
| INTERPI | 24 | 33 | rich transcription + provenance, viewer-locked delivery |
| LABIM/UFRN | 31 | 26 | DSpace, ingestible; descriptive metadata thinner |
| BCZM/UFRN | 32 | 21 | open PDF tree, near-zero item metadata |
| TJMA | 28 | 22 | large + browsable, metadata-thin |
| Jornais de Sergipe | 28 | 24 | DSpace, title-level metadata only |
| APEB finding-aid indexes (IA) | 29 | 27 | machine-readable scaffolding, not primary sources |

The naive sum ties INTERPI (57) and LABIM (57); the axes correctly separate
them. **Keep the two-axis view** — but replace ADR-0001's "no archive high
on both" language with: *"the axes co-vary (r ≈ 0.68 over 21 archives) —
both track archive resourcing — but ~30% of archives diverge enough that a
single scalar would mislead."*

### Finding 2 — the research axis is not internally coherent

Cronbach's α (internal consistency of each 4-dimension axis):

| axis | α | reading |
|---|---|---|
| pipeline | **0.66** | acceptable — the four dimensions hang together |
| research | **0.49** | poor — the four dimensions do not measure one thing |

Inside "research":

- `provenance_curatorial` ↔ `linkage_potential`: r = +0.57 (a real
  "metadata quality" cluster).
- `uniqueness_non_duplication`: r ≤ 0.34 with **everything**, mean 7.7,
  sd 1.5 — nearly a constant in the Nordeste (almost every archive is the
  only digital copy of its material). It barely discriminates.
- `corpus_completeness`: correlates with the *pipeline* dimensions
  (`accessibility` +0.69, `pipeline_ingestion_readiness` +0.64,
  `finding_aids` +0.53) and **not** with its research axis-mates
  (`provenance` +0.20, `uniqueness` +0.06, `linkage` +0.16). Behaviourally
  it is a pipeline dimension — a complete collection got that way through
  the same investment that produces good delivery.

Inside "pipeline":

- `accessibility` ↔ `pipeline_ingestion_readiness`: r = +0.80 (the core).
- `scale`: r ≈ 0.0–0.24 with every other dimension. Genuinely orthogonal —
  a huge archive is not necessarily accessible, described, or ingestible.
  `scale` dilutes the pipeline signal but is conceptually a "raw size"
  member, not a category error.

### Finding 3 — the quadrant threshold is defensible but exclusive

At threshold 28, only **2** archives (EAP703, Atas da Câmara) ever reach
High/High. "Low research" spans the entire 15–27 band — for a catalog whose
mission is surfacing neglected-but-valuable archives, that label reads more
pessimistically than intended.

| threshold | HH | HL | LH | LL | anchor meaning |
|---|---|---|---|---|---|
| 24 | 7 | 4 | 0 | 10 | avg dimension 6 — "workable with effort" |
| **26** | **4** | **3** | **1** | **13** | avg 6.5 |
| 28 (current) | 2 | 5 | 1 | 13 | avg 7 — "uniformly usable" |
| 30 | 0 | 4 | 1 | 16 | avg 7.5 |

Axis medians: pipeline 24, research 22. Threshold 26 sits just above both
medians and makes "High/High" a bucket of 4 (EAP703, Atas, LABIM,
APEB-indexes) rather than 2.

### Closed follow-up

ADR-0001 §"Open follow-ups" wanted *"at least one calibration archive
labeled `only-via-federation`"* before `scholarly_access_practical` was
meaningful. **Done** — Pass 3 labels 5 (APEJE, APEPI, and the three
FamilySearch collections). That follow-up is closed.

## Recommendations

Three decisions, independent. Each is a small change.

### R1 — Keep the 4-4 partition; do **not** move dimensions

`corpus_completeness` behaves like pipeline (r ≈ 0.65) and `scale` behaves
like nothing, but:

- moving dimensions to chase correlation on 21 data points is overfitting;
- `corpus_completeness` is *conceptually* a research-value question ("is the
  collection whole enough to rely on?") — its pipeline correlation is a
  resourcing confound, not a mis-categorisation;
- `scale` is weak in either axis; there is no better home.

**Action:** none to the code. Update ADR-0001's axis-membership section to
cite this ADR and record that the partition was re-tested and held.

### R2 — Record the research axis's weak coherence; flag two future moves

**Action:** amend `docs/algorithm-v1.md` §Aggregation with the α = 0.49
finding and two items for a Pass 4 review (do not act now):

1. **`uniqueness_non_duplication`** — near-constant (mean 7.7, sd 1.5) and
   uncorrelated with everything. Consider demoting it from the research
   axis to a standalone flag (like `scholarly_access_practical`): it is a
   yes/no-ish property, not a graded one, at least in this corpus.
2. **Split "research" conceptually** into *metadata quality*
   (`provenance_curatorial` + `linkage_potential`, α would be ~0.7) and
   *collection substance* (`corpus_completeness` + `scale`). Only worth
   doing if it earns its complexity — a 2-2-2-2 four-axis view, or a
   weighted research sum, are both heavier than the current model.

### R3 — Lower the quadrant threshold from 28 to 26

**Recommended.** 26 = anchor 6.5, still meaningfully above the field median,
and it makes "High/High" a non-trivial bucket. ADR-0001 itself says *"any
threshold between 24 and 32 could be justified."*

**Action:** `app.services.scoring.quadrant_label` default `threshold: int = 28`
→ `26`; update the docstring and `docs/algorithm-v1.md`; the four
`test_scoring_axes.py` / blueprint assertions that check specific quadrant
labels need re-checking (LABIM 31/26 and APEB-indexes 29/27 move
Low→High on research; BCZM 32/21 does not).

**Alternative (conservative):** keep 28, and relabel the UI — "High/Low"
becomes "Strong pipeline" / "Below the top tier on research" so the label
is not read as "low value." No threshold change, but more template churn.

### What is explicitly *not* recommended

- **Weighted axes.** Weights fit to 21 archives would overfit; the equal
  sum is the honest baseline.
- **Dropping the two-axis view.** The 6 off-diagonal archives justify it.
- **A one-axis-only tier** (ADR-0001 follow-up #2). No archive is fully one
  axis — the closest is APEJE (10 pipeline / 19 research). Keep deferred.

## Consequences if adopted (R1 + R2 + R3)

- One constant change (`threshold` 28 → 26) + ~4 test assertions.
- Two doc updates (ADR-0001 pointer, `algorithm-v1.md` §Aggregation).
- No re-scoring, no schema change, no data migration.
- The quadrant labels of 2 archives change (LABIM, APEB-indexes → High
  research); everything else is stable.
- ADR-0001 stays "accepted"; this ADR is its recorded re-examination.
