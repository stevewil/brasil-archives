# Parallel large-job session — 2026-08-27

**Goal:** consume a large token budget before the reset by running the four
deferred large jobs as autonomous worktree agents in parallel, while the
orchestrator clears small deck items inline.

`main` at `4ad89ad` (code `4f59d27`), baseline 170 passed / 4 skipped.

---

## Parallel agents — ALL COMPLETE

| # | Job | Branch | Commit | Tests | Status |
|---|-----|--------|--------|-------|--------|
| A | **Quarterly health probe runner** (`TODO.md` §6) | `feature/probe-runner` | `0c1c84d` | 213p/4s | ✅ done |
| B | **Phase 3 standards-native output** (`standards.md` §Phase 3) | `feature/standards-output` | `9311900` | 215p/4s | ✅ done |
| C | **Pass 3 scoring** (`TODO.md` §5) | `feature/pass3-scoring` | `3a21e07` | data only | ✅ DRAFT — not loaded, awaiting Steve's review |
| D | **Povos OAI-PMH endpoint** (`TODO.md` §2 / Track B) | povos `feature/oai-pmh` | `92c02b0` | 134p | ✅ done — built from spec (mipibu's pkg was on origin/main; local checkout stale) |

### Integration verified

Branch `integration/parallel-jobs` = A+B+C merged (zero file overlap, clean
merge). Migration chain `ca94209a1f1b → d7f1a2b3c4d5` applies clean,
`flask db check` clean. Full suite **258 passed, 4 skipped**. `/oai` endpoint
live-verified — all 6 verbs + error codes, 79-archive `ListRecords`.
`python -m scripts.probe` CLI works. Local dev DB reset to `ca94209a1f1b`
(main's head); an orphan `archives.last_probed_at` column remains until A
merges (harmless).

### Recommended merge order into `main`

1. `feature/probe-runner` — owns migration `d7f1a2b3c4d5`, must land first
2. `feature/standards-output` — no migration, independent
3. inline docs: `docs/vocabularies.md` (new), this file, `algorithm-v1.md` (2× "(TBD)" → dropped)
4. `feature/pass3-scoring` — **only after Steve reviews the 8 borderline calls** in `docs/pass3-scoring-notes.md`, then `python -m scripts.load_calibration configs/calibration/pass3.yaml`
5. povos `feature/oai-pmh` — separate repo; merge + deploy independently

## Orchestrator inline items

- [x] `docs/vocabularies.md` — written from `configs/vocabularies/*.yaml` + code single-selects + probe facets; `algorithm-v1.md` "(TBD)" pointers dropped. **Uncommitted on main.**
- [ ] `size_unit_note` facet decision (`TODO.md` §0) — **recommendation: add a `Text` column on `Archive`** (parallels `curatorial_rarity_notes` / `prior_use_note`). Held pending A's migration landing, so the two migrations chain rather than fork.
- [ ] `LICENSE` + `LICENSING.md` — left alone; README + `algorithm-v1.md` deliberately defer to "before public release" and the split is Steve's legal call.
- [ ] Deploy UI-polish Tracks 1+3 to cPanel — Steve-side (cPanel terminal).

## Ecosystem cleanup

- `git -C c:\DEV\mipibu pull` — local checkout 5 commits behind, missing the entire `app/oai/` package (only on `origin/main`, commit `9d9ed99`).
- `git -C c:\DEV\povos-indigenas-rn` — agent pulled it current before working; `feature/oai-pmh` branch is local, unpushed.
- Agent dev servers left running on :9000 and :5051 → killed. Agent worktrees → removed.

## Notes for whoever merges

- A and B genuinely don't touch the same files (verified `git diff --name-only` intersection is empty).
- A's `set_probe_facet_value` in `app/services/scoring.py` mirrors the existing `set_facet_value` supersede-and-insert history path — same pattern, new `PROBE_FACETS` dict.
- B serves `Archive` rows only over OAI, **not** `AggregatedRecord` (deliberate — "index not mirror", per `scenario-driven-federation-model.md`). Public filter chokepoint: `app/oai/queries.py::_public_filter`.
- C's `pass3.yaml` validated: 15 archives, 8 dims each, all facet/tag values are real vocab slugs, no slug collision with `pass2.yaml`. 13 of 15 land Low/Low pipeline/research.
