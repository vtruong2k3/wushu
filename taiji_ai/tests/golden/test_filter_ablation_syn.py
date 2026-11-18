"""T-MET-13 and 13b: the cut-off ablation on the generator, through the real chain (P5.08).

The truth of ``tests/helpers/synth.py`` comes from the continuous model: the speed of a still joint is 0, the pauses are
the stretches where the analytic speed is below ``tau`` (``slow_intervals``), the hip range is 2A. Each run goes through
the chain once per cut-off, only ``cutoff_hz`` changing (4, 6, 8 Hz and no filter). Only the claims that **hold** are
asserted, with margins from the measured numbers (``tests/helpers/ablation_sweep.py`` prints the tables; the
task file P5.08 section 5 has them): the speed floor rises with the cut-off and with the noise, a slow movement is not
touched by any cut-off, at a ``tau`` near the floor a lower cut-off finds more of the pauses, at a ``tau`` above it all
agree at 1 px of noise, a sharp onset costs 4 Hz more than a frame, and the hip range hardly depends on the cut-off.
"""

from __future__ import annotations

import pytest

from helpers.ablation_sweep import ABSOLUTE_TAU, clip, floor, hip_error, pauses
from helpers.synth import TOLERANCES
from taiji_ai.bench.filter_ablation import ALL_CUTOFFS, NO_FILTER_HZ, check_invariants

SEEDS = (1, 2, 3, 4, 5)
RANGE_TOL = TOLERANCES["SYN-02"]["range_relative_error"]  # 5 %
CUT4, CUT6, CUT8 = 4.0, 6.0, 8.0


def right(scenario: str, noise: float, seeds=SEEDS, **kwargs) -> list[int]:
    """Per cut-off, the number of seeds in which the pause count is the true one."""
    rows = {s: pauses(scenario, s, noise, **kwargs) for s in seeds}
    return [sum(rows[s][hz].found == rows[s][hz].truth for s in seeds) for hz in ALL_CUTOFFS]


# --- the floor of the speed of a joint that does not move ------------------------------------------------------------
def test_t_met_13_the_floor_of_a_still_joint_rises_with_the_cutoff_and_with_the_noise():
    f1, f2 = floor(1.0), floor(2.0)
    for quantity in ("median", "p95", "maximum"):  # measured at 1 px: 0.040, 0.066, 0.094, 0.127 for the median
        values = [getattr(f1[hz], quantity) for hz in ALL_CUTOFFS]
        assert values == sorted(values) and len(set(values)) == 4, quantity
    assert f1[CUT4].median < 0.75 * f1[CUT6].median  # measured 0.61: 4 Hz takes a third off the floor of 6 Hz
    assert f1[NO_FILTER_HZ].median > 1.5 * f1[CUT6].median  # measured 1.92: the 6 Hz filter halves the floor
    for hz in ALL_CUTOFFS:  # white noise: the floor is proportional to it (measured 1.98 to 2.02 for twice the noise)
        assert 1.7 < f2[hz].median / f1[hz].median < 2.3, hz
    assert f1[CUT6].maximum < ABSOLUTE_TAU  # the 0.3 per second of the pause tests clears the 6 Hz floor at 1 px (0.18)


# --- the pauses ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("scenario", ["SYN-05", "SYN-07"])
def test_t_met_13_without_noise_a_slow_movement_is_not_touched_by_any_cutoff(scenario):
    rows = pauses(scenario, 1, 0.0)
    errors = [rows[hz].boundary_steps for hz in ALL_CUTOFFS]
    assert all(rows[hz].found == rows[hz].truth for hz in ALL_CUTOFFS) and None not in errors
    assert max(errors) - min(errors) < 0.05 and max(errors) <= 1.0  # measured 0.51 and 0.53, one frame allowed


@pytest.mark.parametrize("scenario", ["SYN-05", "SYN-07"])
def test_t_met_13_at_one_pixel_and_a_tau_near_the_floor_a_lower_cutoff_finds_more_of_the_pauses(scenario):
    counts = right(scenario, 1.0)  # measured: SYN-05 5, 2, 1, 0 and SYN-07 5, 3, 0, 1 of 5 seeds
    assert counts[0] == 5  # 4 Hz finds the right number of pauses in every seed
    assert counts[0] > counts[1] >= counts[2]  # 6 Hz loses some and 8 Hz more
    assert counts[3] <= 1  # without a filter the noise breaks the pauses up and almost none is found
    assert right(scenario, 2.0)[0] < 5  # at 2 px even 4 Hz does not find them all at that tau (measured 0 and 3)


@pytest.mark.parametrize("scenario", ["SYN-05", "SYN-07"])
def test_t_met_13_at_a_tau_above_the_floor_every_cutoff_finds_the_pauses_at_one_pixel(scenario):
    assert right(scenario, 1.0, share=None, tau=ABSOLUTE_TAU) == [5, 5, 5, 5]  # the floor at 1 px is 0.18 at most


def test_t_met_13_at_two_pixels_the_floor_of_8_hz_and_of_no_filter_passes_tau_and_the_pauses_fragment():
    # measured SYN-05, tau 0.3: 5, 5, 1, 2 of 5 seeds right; 8 Hz finds three pauses where there are two in 4 seeds
    counts = right("SYN-05", 2.0, share=None, tau=ABSOLUTE_TAU)
    assert counts[0] == counts[1] == 5 and counts[2] <= 2 and counts[3] <= 3
    found_8hz = [pauses("SYN-05", s, 2.0, share=None, tau=ABSOLUTE_TAU)[CUT8].found for s in SEEDS]
    assert sum(found_8hz) > 2 * len(SEEDS)  # more pauses than the truth: the floor of 8 Hz (0.38 at most) crosses tau


# --- the cost of a low cut-off: a sharp onset ------------------------------------------------------------------------
def boundary(ramp: float) -> dict[float, float]:
    rows = pauses("SYN-05", 1, 0.0, ramp_s=ramp)
    assert all(r.found == r.truth and r.boundary_steps is not None for r in rows.values())
    return {hz: float(rows[hz].boundary_steps) for hz in ALL_CUTOFFS}  # type: ignore[arg-type]


def test_t_met_13_a_sharp_onset_costs_4_hz_more_than_a_frame_and_6_and_8_hz_do_not():
    slow = boundary(0.2)  # the default ramp of the generator: the same at every cut-off
    assert max(slow.values()) - min(slow.values()) < 0.05
    for ramp in (0.1, 0.02):  # measured 1.75 and 2.15 steps at 4 Hz, 0.75 and 1.15 at 6 and 8 Hz and without a filter
        e = boundary(ramp)
        assert e[CUT4] >= e[CUT6] + 0.5, ramp  # 4 Hz smears the onset by at least half a step more than 6 Hz
        assert e[CUT4] > 1.5  # more than a frame and a half
        assert e[CUT6] <= 1.5 and abs(e[CUT6] - e[CUT8]) < 0.05 and abs(e[CUT6] - e[NO_FILTER_HZ]) < 0.05
    e = boundary(0.05)  # measured 1.38 at 4, 6 and 8 Hz and 0.69 without a filter: any of them smooths such an onset
    assert e[CUT6] - e[NO_FILTER_HZ] >= 0.5 and abs(e[CUT4] - e[CUT6]) < 0.05


# --- the hip range ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("variant", ["A", "B"])
def test_t_met_13_the_hip_range_is_within_the_tolerance_at_every_cutoff_and_hardly_depends_on_it(variant):
    seeds = (1, 2, 3)
    for noise in (0.0, 1.0, 2.0):
        rows = {s: hip_error(s, noise, variant) for s in seeds}
        for s in seeds:
            assert all(abs(e) <= RANGE_TOL for e in rows[s].values()), (noise, s)  # measured at most 3.07 % of 5 %
            filtered = [rows[s][hz] for hz in (CUT4, CUT6, CUT8)]
            assert max(filtered) - min(filtered) < 0.02, (noise, s)  # the three cut-offs differ by under 2 points
        if noise == 0.0:
            for s in seeds:  # without noise the range is the sampling error of 30 fps (-2.1 %) at every cut-off
                values = list(rows[s].values())
                assert max(values) - min(values) < 1e-4 and values[0] == pytest.approx(
                    -0.021, abs=1e-3
                )  # to 0.01 point


# --- the invariants --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("scenario", "noise"), [("SYN-05", 1.0), ("SYN-07", 0.0), ("SYN-02", 2.0), ("SYN-01", 1.0)])
def test_t_met_13b_the_grid_reasons_flags_and_segment_are_the_same_at_every_cutoff_and_only_no_filter_is_unfiltered(
    scenario, noise
):
    _, layers = clip(scenario, 1, noise)
    check_invariants(layers)  # the grid, the reasons, the interpolation flags and the segment: identical
    assert list(layers) == list(ALL_CUTOFFS)
    assert not layers[NO_FILTER_HZ].filtered.any()  # a cut-off above Nyquist: the stage is skipped, no run is filtered
    for hz in (CUT4, CUT6, CUT8):
        assert layers[hz].filtered.any() and layers[hz].filtered.shape == layers[CUT6].filtered.shape
    assert layers[CUT4].filtered.sum() == layers[CUT6].filtered.sum() == layers[CUT8].filtered.sum()  # the same runs
