# ADR-0001: Two-axis aggregation for the eight scored dimensions

- **Status:** accepted, 2026-08-24 · **re-examined by
  [ADR-0002](adr-0002-axis-re-examination.md), 2026-08-29** — the 4-4
  partition was re-tested against 21 scored archives and **held**; the
  quadrant threshold was lowered 28 → 26; the motivating "no archive high
  on both axes" claim was found not to survive Pass 3 (the axes co-vary,
  r ≈ 0.68) and is superseded by ADR-0002 §"Finding 1".
- **Deciders:** Steve Williams
- **Consulted:** the six-archive Pass 2 calibration set (LABIM/UFRN, INTERPI, TJMA, BCZM/UFRN, Jornais de Sergipe, Nupem)
- **Supersedes:** v0 placeholder aggregation (naive sum only) documented in `docs/algorithm-v1.md §Aggregation`.
- **Referenced by:** `docs/algorithm-v1.md §Aggregation`, `docs/scenario-driven-federation-model.md`.

## Context

`docs/algorithm-v1.md` scores each candidate archive on eight independent dimensions on a 0–10 scale. Pass 1 deliberately deferred any aggregation past a naive sum (0–80), on the grounds that we did not yet have real per-archive scores to observe how the dimensions co-vary.

Pass 2 scored six calibration archives (see `configs/calibration/pass2.yaml`). Two observations emerged:

1. **The naive sum ties archives that should not tie.** LABIM/UFRN and INTERPI both scored 57/80 but reached that total in opposite ways — LABIM through pipeline readiness (accessibility, finding aids, scale) and INTERPI through research value (provenance, uniqueness, linkage). The Pass 1 dimensions were chosen to be independent axes of value, so collapsing them to one scalar destroys exactly the information we spent Pass 1 building.
2. **The tension between the two clusters is empirically real.** The four "pipeline" dimensions (accessibility, finding_aids, pipeline_ingestion_readiness, scale) measure what it costs us to reach material. The four "research" dimensions (provenance_curatorial, corpus_completeness, uniqueness_non_duplication, linkage_potential) measure what that material is worth once reached. Across the six calibration archives, no archive was uniformly high on both — one axis dominated in every case.

The v0 naive sum still has utility (single sortable column, works when only some dimensions are scored, preserves Pass 1 outputs), so removing it would be gratuitous churn. The question is what to add alongside it.

## Decision

Add a **two-axis view** to the algorithm and expose it in the UI, keeping the naive sum as a labeled legacy column.

### Axis membership

```python
AXES = {
    "pipeline": (
        "accessibility",
        "finding_aids",
        "pipeline_ingestion_readiness",
        "scale",
    ),
    "research": (
        "provenance_curatorial",
        "corpus_completeness",
        "uniqueness_non_duplication",
        "linkage_potential",
    ),
}
AXIS_MAX = 40  # len(members) * 10
```

Each axis is an unweighted sum of its four member dimensions. An import-time assertion enforces that `set(pipeline) ∪ set(research) == set(DIMENSIONS)` and that the two sets are disjoint. Any change to that partition is a code review event, not a config edit.

### Quadrant label

The two axes get a coarse label at threshold **28/40** using inclusive comparison (`pipeline >= 28`, `research >= 28`):

- `High pipeline / High research`
- `High pipeline / Low research`
- `Low pipeline / High research`
- `Low pipeline / Low research`
- `n.a.` when either axis is `None` (i.e., that axis has zero dimension scores recorded)

The 28/40 threshold anchors on average anchor score 7 per dimension. In the Pass 1 anchor table, 7 is the "uniformly usable for scholarship" mark on nearly every dimension; picking a lower threshold (say 24 = anchor 6) risks classifying archives as "high" when they are only workable-with-effort, and the label is meant to be a stronger claim than that. The threshold is not part of the persisted data model; it is a display parameter of `quadrant_label`.

The quadrant is a **label**, not a rank. Two archives in the same quadrant are not ordered by the label; they are ordered by whichever axis is being sorted.

### UI surfacing

- **List page** (`archives/list.html`): columns `Pipeline` (X/40) and `Research` (X/40) alongside `Naive sum` (X/80). Sort options: `name`, `score` (naive sum), `pipeline`, `research`. Axis sorts rank `NULL` totals last.
- **Detail page** (`archives/detail.html`): a "Score profile" card at the top with both axis totals, the members that contributed, the quadrant label, and the naive sum in a smaller legacy row.

### `scholarly_access_practical` facet (companion to this decision)

The two-axis view answers *how strong is this archive on the pipeline vs. research dimensions*. It does **not** answer *who has to build the pipeline*. The BCZM PDF tree scores well on accessibility (public, no auth, stable URLs) but scholarly workflows over it require our tooling to enumerate, cross-reference, and cite the underlying records — the archive itself does not expose that surface.

To capture that observation without inventing a ninth scoring dimension, we add a single-select facet with four values:

- `well-supported` — the archive itself supports scholarly workflows (search across record types, enumerate, cite stably, retrieve in bulk).
- `usable-with-effort` — reachable with scripting effort but no federation companion needed.
- `only-via-federation` — practical scholarly access requires a federation companion app (Mipibu-shape).
- `not-yet-assessed` — default.

This facet is annotation, not scoring. It informs the scenario-driven federation model (see `docs/scenario-driven-federation-model.md`) by identifying archives where federation tooling is the practical access surface.

## Consequences

### Positive

- **The tie problem disappears.** LABIM/UFRN and INTERPI now sit in opposite quadrants even though their naive sums are identical. The list page can be sorted along either axis to answer either question directly.
- **Partial scoring keeps working.** An archive with only some dimensions scored returns partial axis sums (not `None`) unless the axis is entirely empty, matching the same lenient behavior the naive sum has.
- **The two axes are cheap to compute.** Each is a `SUM(CASE WHEN dimension IN (...) THEN score END)` in the list query; the detail page reuses `axis_scores()` on the already-loaded archive id.
- **The axis membership is guarded.** The import-time partition check means a future contributor cannot silently drop a dimension into "pipeline" and out of "research"; the tests will fail on load.
- **Backward compatibility is preserved.** The naive sum stays sortable and stays on the detail card. Pass 1 outputs remain valid; no scores need to be re-recorded.

### Negative / accepted trade-offs

- **Two axes are still an opinionated compression.** The Pass 1 dimensions were designed to be independent; forcing them into two clusters imposes structure the data may eventually push back on. We accept this because the two clusters *do* correspond to a real cost/value split observed in the six calibration archives, and because the naive sum remains available as an unopinionated baseline.
- **The 28 threshold is arbitrary within a defensible range.** Any threshold between 24 and 32 could be justified; 28 is the "uniformly usable" anchor. The threshold is a display parameter and can be revisited without changing stored data.
- **The 4-4 split is not proven optimal.** A 5-3 or 3-5 split might match the data better, and later scoring passes may show a dimension belongs in the other cluster. Because AXES lives in code and is a small table, revisiting the partition is a well-scoped code change.

### Open follow-ups

- ~~After Pass 3 … re-examine whether the 4-4 partition still fits and whether the 28 threshold still separates "uniformly usable" from the middle band.~~ **Done — [ADR-0002](adr-0002-axis-re-examination.md), 2026-08-29.** Partition held; threshold 28 → 26; research-axis coherence flagged for a Pass 4 review.
- If a future archive scores fully on one axis and zero on the other, revisit whether the quadrant label should degrade to an explicit "one-axis only" tier. **Still open** — no such archive yet (closest: APEJE, 10 pipeline / 19 research).
- ~~The `scholarly_access_practical` facet needs at least one calibration archive labeled `only-via-federation` before it is meaningful.~~ **Done** — Pass 3 labels 5 (APEJE, APEPI, and the three FamilySearch collections).

## Implementation

- Service layer: `app.services.scoring.AXES`, `AXIS_MAX`, `AXIS_LABELS`, `axis_score`, `axis_scores`, `quadrant_label`.
- Import-time invariant: `assert set(pipeline) | set(research) == set(DIMENSIONS)`.
- List route: two SUM(CASE) subqueries, extra `sort=pipeline` and `sort=research` options, NULLs sorted last.
- Detail route: passes `axes`, `axis_labels`, `axis_max`, `axis_members`, `quadrant` to template.
- Templates: axis columns on the list, axis card on the detail.
- Facet: `scholarly_access_practical` in `SINGLE_SELECT_FACETS`, `FacetForm`, `facets.html`, `detail.html`, edit route.
- Tests: `tests/test_scoring_axes.py` for service-layer contracts + facet registration; `tests/test_archives_blueprint.py` extended for column rendering, sort ordering, and facet form/persistence.

## References

- `configs/calibration/pass2.yaml` — the six-archive calibration set that motivated the change.
- `docs/algorithm-v1.md §Aggregation` — updated pointer to this ADR.
- `docs/scenario-driven-federation-model.md` — companion design doc; uses the axes and the `scholarly_access_practical` facet to prioritize which archives need federation companion apps.
