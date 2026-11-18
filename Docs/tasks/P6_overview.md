# Phase 6 — the comparison with a reference: lanes, shared contracts, proposed dependency changes

Written 2026-11-17 with the plans of P6.02 to P6.07, so that the tasks of Phase 6 can be done in parallel by two agents
(or one agent in a shorter order) without two of them editing the same file or guessing an interface. This file is not a
task: each task keeps its own `Docs/tasks/<ID>.md`. **The dependency changes in §2 need the maintainer's confirmation**
(they change the plan, AGENTS.md §4.1); until then the plan's own order holds.

## 1. The chain and what each step needs

Appendix C and W8 of `TECH_WORKFLOW_V1.md`: frame features (C.1) → masked cost (C.2) → constrained DTW (C.3, C.4: path and
distance `D`) → local tempo along the path and per-unit deviation on the reference timeline (C.4) → "normal band" from the
coach's reference takes (C.5); guards decide whether two segments may be compared at all (W8); a check on UMONS shows the
whole chain on real data (out of domain).

| Task | Output | Needs, really | Plan row says |
| ---- | ------ | ------------- | ------------- |
| P6.01 features | `compare/features.py` | P5.02 | P5.02 |
| P6.02 masked cost | `compare/cost.py` (the plan row says `compare/dtw.py`, shared with P6.03: split so that two lanes never edit one file) | P6.01 (`FrameFeatures`) | P6.01 |
| P6.03a DTW core (new sub-task) | `compare/dtw.py` | **only the cost-matrix contract** (§3.2): it runs on any matrix | P6.02 (as P6.03) |
| P6.03b alignment of two segments (new sub-task) | `compare/align.py` | P6.02, P6.03a | P6.02 (as P6.03) |
| P6.04 local tempo and deviation | `compare/tempo_ratio.py` | P6.03b (path of real features; its golden test needs the whole chain) | P6.03 |
| P6.05 guards | `compare/guards.py` | **P6.01** (coverage of the features) and the ontology; not the DTW | P6.03 |
| P6.06 normal band | `compare/reference_band.py` | **P6.03a** (`DtwResult`: the distances and the settings they were made with); not the tempo | P6.04 |
| P6.07 UMONS check | `bench/umons_compare.py`, `tools/umons_compare.py`, `Docs/reports/p6_umons_check.md` | P6.03b, P4.08 | P6.03, P4.08 |

## 2. Proposed dependency changes (to confirm)

1. **Split P6.03 (1 day) into P6.03a (0.5 day: the DTW algorithm on a cost matrix) and P6.03b (0.5 day: two segments
   aligned through features, cost and DTW, with the golden tests of SYN-10 and SYN-11).** P6.03a then depends on nothing but
   the contract of §3.2.
2. **P6.05 depends on P6.01** instead of P6.03 (a guard reads the segments' descriptions and the features' coverage).
3. **P6.06 depends on P6.03a** instead of P6.04 (a band is made of distances).
4. **P6.02 writes `compare/cost.py`** instead of `compare/dtw.py`.

Recorded as a `DEC-NNNN` and a dated note on the rows of `IMPLEMENTATION_PLAN_V1.md` when confirmed.

## 3. Shared contracts (fixed now; a change is made in this file first, then in the tasks)

### 3.1 Frame features (P6.01, `Docs/tasks/P6.01.md` §1.5)

`FrameFeatures`: `t_sec (N,)` real clock, `values (N, U, 2)` float64 (a position in trunk lengths from the mid-hip, or
`(sin φ, cos φ)`), `valid (N, U)`, `reason (N, U)` uint8, `bridged (N, U)`, `units` (each a `FeatureUnit(kind, name,
joints)`: positions first, then angles), `scale_px`, `scale_rows`, `scale_s`, `roll_deg`, `step_s`, `recording_id`,
`data_sources`, `version`, and the two echoes of the optional arguments that decided which features are values,
`min_scale_s` and `min_segment_length` (trailing fields, default `None`). `frame_features(layer, *, roll_deg=0.0, joints=DEFAULT_JOINTS, segments=DEFAULT_SEGMENTS,
min_scale_s=None, min_segment_length=None)`: the last argument (added 2026-11-17 after finding R1 of P6.01: a limb segment
that is very short in the image, a forearm pointing at the camera, has an arbitrary direction) is a minimum length in trunk
lengths for the **angle** units, `None` (none applied) by default; a segment below it is invalid with the reason 24
`short_segment`. The reasons of a feature are `FeatureReason`: 0 valid, 1 to 6 and 19 as in `MissingReason`, 23
`zero_length`, 24 `short_segment`. A consumer (P6.02, P6.05) reads only `valid`, `values`, `units`, `t_sec` and the
provenance, so the added argument changes none of them.

### 3.2 Cost matrix (P6.02 produces, P6.03a and P6.03b read)

- `CostMatrix`: `values (n, m)` float64, **axis 0 the query** (rows `i`), **axis 1 the reference** (columns `k`); `+inf`
  where fewer than `min_visible` units are valid in both frames, never NaN; `n_common (n, m)` int16, the units valid in
  both; `units` (the names, equal in both feature sets: a difference is refused); `weights` as used; `min_visible`.
- A unit's distance is the Euclidean norm of the difference of its two 2-vectors: a position in trunk lengths, an angle as
  the chord `‖(sin a, cos a) − (sin b, cos b)‖ = 2 |sin((a − b) / 2)|` (0 to 2). The cell is the **weighted mean** over the
  units valid in both, `Σ w_u d_u / Σ w_u` (Appendix C.2 read so that `D` does not grow with the number of units).
- P6.03a accepts any `(n, m)` float64 array with finite values and `+inf` (a `CostMatrix` or its `values`), so it can be
  built and tested on hand-made matrices.

### 3.3 DTW result (P6.03a produces; P6.03b, P6.04, P6.06, P6.07 read)

- `dtw(cost, *, band, step) -> DtwResult` (open-begin and open-end are not in the first version: P6.03a Q4).
- `DtwResult`: `path (L, 2)` int64 pairs `(i, k)` (query row, reference row), monotone, every step one of the pattern's;
  `distance` `D = Σ c(path) / L` (Appendix C.4) or `None` when there is no finite path; `status` `ok` or `no_path`;
  `accumulated` (the DP's cost at the end) and `normalised` (by the pattern's normaliser); `params` (`band`, `step`, `n`,
  `m`) echoed, so that P6.06 can refuse to put distances made with different settings in one band.
- `band` is the Sakoe-Chiba half-width `r` of `|i/(n−1) − k/(m−1)| ≤ r` (a fraction of the length; Appendix C.3); `step`
  is `symmetric1` (unit steps, for the check against an independent implementation) or `symmetricP1` (Sakoe-Chiba P = 1:
  slope between 1/2 and 2, the product's pattern).
- **As built (P6.03a, 2026-11-17; verified by the coordinator):** `compare/dtw.py` exports `STEPS`, `band_mask(n, m,
  band)`, `DtwResult` and `dtw`. (1) **`no_path`** has an empty `(0, 2)` path and `None` for `distance`, `accumulated` and
  `normalised` (the contract named only `distance`). (2) **`distance` is `D`, the plain mean of the cost over the listed
  cells** (Appendix C.4 literally); with `symmetricP1` the `normalised` value is `accumulated / (n + m)` and is **not** `D`:
  P6.06 compares `D` with `D`, made with equal `params`, and never `normalised`. (3) The path lists the middle cell of a
  compound step, so every step of the returned path is `(1, 1)`, `(1, 0)` or `(0, 1)`. (4) **Ties** go to the first
  candidate (`symmetric1`: diagonal, up, left; `symmetricP1`: diagonal step, then from `(i-1, k-2)`, then from `(i-2,
  k-1)`); `D` depends on which tied path is returned, the accumulated cost does not. (5) A matrix of one row or one column
  has no diagonal: with a band below 1 it has no path. (6) `params` is a read-only mapping (`dict(result.params)` for a JSON
  writer). (7) The cost is a floating-point array, or an object whose `.values` is one (a `CostMatrix`); an integer array
  is refused.

### 3.4 Alignment of two segments (P6.03b produces; P6.04, P6.07 read)

`align(reference, query, *, min_visible, band, step="symmetricP1", weights=None) -> Alignment` holding the two
`FrameFeatures`, the `CostMatrix`, the `DtwResult` and `settings` (every setting that changes `D`: feature version and units,
weights, `min_visible`, `band`, `step`, and the features' `min_scale_s` and `min_segment_length`, which must be equal in
the two feature sets or `align` refuses), the fingerprint P6.06 compares: a **non-empty** mapping whose names are short
codes (letters, digits, `_`, `.`, `-`, 1 to 64) and whose values are plain (numbers, strings, tuples, mappings, or
`None` for a minimum that was not applied: "as built" in P6.03b, D2; `min_scale_s` and `min_segment_length` are
`None` when `frame_features` was called without them, never a made-up number). `align`
also offers `Alignment.as_comparison(reference_id, query_id)` giving the `Comparison` of P6.06 (the two segment IDs, `D`,
`settings`), so that P6.06 never imports `align.py`. `Alignment.matched_query_times()` gives, for every
reference row, the mean query time (seconds) of the path cells on that row: P6.04 fits the local tempo to it and P6.07
carries boundaries with it, so the mapping is written once, in P6.03b.

### 3.5 Parameters that have no default

`min_visible` (P6.02), `band` (P6.03a), `min_coverage` (P6.05), `smooth_s` (P6.04): each is a required argument and is
echoed; a value comes from the caller (a configuration now, a signed record later), as `τ` and `d_min` in P5.07 (AGENTS.md
5.5). Appendix C's suggestions (`r` 0.1 to 0.2, 0.5 s) are written in the docs as suggestions, not defaults. Weights
default to 1 for every unit (no unit preferred), as an echoed choice.

## 4. Lanes and order

```text
Wave 1:  P6.01 features (lane A)          ||  P6.03a DTW core (lane B)
Wave 2:  P6.02 cost (lane A)               ||  P6.05 guards (lane B)      ||  P6.06 band (lane B, after P6.05)
Wave 3:  P6.03b alignment (lane A)
Wave 4:  P6.04 tempo and deviation (lane A) ||  P6.07 UMONS check (lane B)
```

With two lanes the critical path is P6.01 → P6.02 → P6.03b → P6.07, about 2.5 days (sequentially about 4.75). With one
agent the same order is still the shortest: no task waits for a task that it does not need.

## 5. Rules for the parallel work

1. **Files:** each task writes only its own module and test files (the table of §1); a change to a shared contract goes
   through §3 first. `compare/__init__.py` (the package docstring and `CompareError`) was written once by the coordinator
   before the lanes started (DEC-0064); a task never edits it, and the coordinator adds a line to its docstring when a
   module closes.
2. **Tracking:** each lane fills its own task file; `TASK_STATUS.md`, `CHANGELOG.md`, `DECISIONS.md` and `BUGS.md` are
   written by one coordinator at a time, and the next free IDs are read again just before writing.
3. **Gate:** one full gate at a time (it runs the whole suite); a lane closes only on a gate run on the tree that holds
   its final code.
4. **Third-party:** `dtaidistance` (Apache-2.0, Appendix C.6) is not installed (`uv.lock`); P6.03a checks against an
   independent naive implementation written in the test, and adding `dtaidistance` as a development dependency is a
   question for the maintainer (P6.03a Q3). Numba is not added.
5. **Data:** P6.07 updates the D12 row of `Docs/DATASET_REGISTRY_TAIJI.md` before it reads a file (AGENTS.md §9.4).
