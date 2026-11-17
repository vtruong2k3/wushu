"""T-MET-09a to 09d: the pauses of a joint group, ``V_G < τ`` for at least ``d_min`` (P5.07).

``find_pauses`` is tested on hand-made series (every rule re-derived by hand and, for a few hundred random series, by a
plain loop that does not share a line with it); ``group_speed`` with ``pause_tau`` and ``pause_min_s`` is tested on a
layer whose hands move, stop, move, stop and move again, with every expected number derived from the layer's own
keypoints. A pause is a maximal run of measured rows with ``V < τ`` that lasts ``n × step >= d_min``, the interval
``[t_first, t_last + step)``; a row that is not measured ends a run.
"""

from __future__ import annotations

import dataclasses
import math
import statistics
from typing import Any

import numpy as np
import pytest

from helpers.metric_layers import body, cells, drop, edited, exact_layer
from taiji_ai.metrics import MetricError
from taiji_ai.metrics.series import MetricSeries, build_series
from taiji_ai.metrics.tempo import Pause, find_pauses, group_speed
from taiji_ai.quality.layers_io import PoseFiltered

STEP = 0.1  # the step of the hand-made series (s)
TAU = 1.0


# --- hand-made series -------------------------------------------------------------------------------------------------
def series_of(values: list[float | None], reasons: list[int] | None = None, step: float = STEP) -> MetricSeries:
    """A series whose rows are the given values (``None`` is NaN and gets the reason 2 unless ``reasons`` says)."""
    v = np.array([math.nan if x is None else float(x) for x in values], dtype=np.float64)
    r = np.array([0 if not math.isnan(x) else 2 for x in v] if reasons is None else reasons, dtype=np.uint8)
    return build_series(
        metric_name="speed_hands", metric_version="1", units="body_lengths_per_s",
        recording_id="00000000-0000-4000-8000-000000000507", camera_id="camA", view_category="front",
        t_sec=np.arange(len(v)) * step, values=v, reason=r,
        step_s=step if len(v) >= 2 else None,
    )  # fmt: skip


def spans(pauses: tuple[Pause, ...]) -> list[tuple[int, int]]:
    return [(p.first_row, p.last_row) for p in pauses]


# --- T-MET-09a: the rules of a pause ----------------------------------------------------------------------------------
def test_t_met_09a_a_run_of_slow_measured_rows_is_a_pause_with_its_interval_and_length():
    (p,) = find_pauses(series_of([5, 0.5, 0.5, 0.5, 5]), tau=TAU, min_pause_s=0.3)
    assert (p.first_row, p.last_row) == (1, 3)
    assert p.t_start == pytest.approx(0.1) and p.t_end == pytest.approx(0.4)  # [t_first, t_last + step)
    assert p.duration_s == pytest.approx(0.3) and (p.cut_before, p.cut_after) == (False, False)


def test_t_met_09a_the_threshold_is_strict_a_speed_equal_to_tau_is_not_slow():
    assert find_pauses(series_of([5, 1.0, 1.0, 1.0, 5]), tau=1.0, min_pause_s=0.3) == ()
    assert spans(find_pauses(series_of([5, 0.999999, 1.0, 0.999999, 5]), tau=1.0, min_pause_s=0.1)) == [(1, 1), (3, 3)]
    assert spans(find_pauses(series_of([5, 1.0, 1.0, 1.0, 5]), tau=1.0000001, min_pause_s=0.3)) == [(1, 3)]


def test_t_met_09a_the_minimum_duration_is_inclusive_to_a_nanosecond_and_a_whole_number_of_steps():
    three = series_of([5, 0.5, 0.5, 0.5, 5])
    assert spans(find_pauses(three, tau=TAU, min_pause_s=0.3)) == [(1, 3)]  # exactly d_min counts
    assert spans(find_pauses(three, tau=TAU, min_pause_s=0.3 + 5e-10)) == [(1, 3)]  # inside the 1e-9 s tolerance
    assert find_pauses(three, tau=TAU, min_pause_s=0.3 + 5e-9) == ()  # a few nanoseconds over is over
    assert find_pauses(three, tau=TAU, min_pause_s=0.31) == ()
    two = series_of([5, 0.5, 0.5, 5, 5])
    assert find_pauses(two, tau=TAU, min_pause_s=0.3) == ()  # two steps are 0.2 s
    assert spans(find_pauses(two, tau=TAU, min_pause_s=0.2)) == [(1, 2)]
    assert spans(find_pauses(series_of([5, 0.5, 5]), tau=TAU, min_pause_s=0.01)) == [(1, 1)]  # one step is 0.1 s


def test_t_met_09a_the_length_is_n_steps_whatever_the_step_is():
    for step in (1 / 30, 0.05, 0.25):
        (p,) = find_pauses(series_of([5, 0.5, 0.5, 0.5, 0.5, 5], step=step), tau=TAU, min_pause_s=3.5 * step)
        assert p.duration_s == pytest.approx(4 * step, rel=1e-12)
        assert p.t_start == pytest.approx(step) and p.t_end == pytest.approx(5 * step)


def test_t_met_09a_a_row_that_is_not_measured_ends_a_run_and_is_never_slow():
    pauses = find_pauses(series_of([0.5, 0.5, 0.5, None, 0.5, 0.5, 0.5]), tau=TAU, min_pause_s=0.3)
    assert spans(pauses) == [(0, 2), (4, 6)]  # a hole is not bridged and not read as slow
    assert find_pauses(series_of([5, None, None, None, 5]), tau=TAU, min_pause_s=0.1) == ()
    assert find_pauses(series_of([None, None, None]), tau=TAU, min_pause_s=0.1) == ()
    assert spans(find_pauses(series_of([0.5, 0.5, None, 0.5, 0.5, 0.5]), tau=TAU, min_pause_s=0.3)) == [(3, 5)]


def test_t_met_09a_several_pauses_come_in_time_order_and_the_series_edges_are_not_cuts():
    values = [0.5] * 3 + [5] + [0.5] * 4 + [5] + [0.5] * 3
    pauses = find_pauses(series_of(values), tau=TAU, min_pause_s=0.3)
    assert spans(pauses) == [(0, 2), (4, 7), (9, 11)]
    assert [(p.cut_before, p.cut_after) for p in pauses] == [(False, False)] * 3  # series edges are no holes
    assert [p.t_start for p in pauses] == pytest.approx([0.0, 0.4, 0.9])
    assert [p.t_end for p in pauses] == pytest.approx([0.3, 0.8, 1.2])
    (whole,) = find_pauses(series_of([0.5] * 6), tau=TAU, min_pause_s=0.3)
    assert (whole.first_row, whole.last_row, whole.t_start) == (0, 5, 0.0) and whole.t_end == pytest.approx(0.6)
    assert find_pauses(series_of([5, 5, 5, 5]), tau=TAU, min_pause_s=0.1) == ()


def test_t_met_09a_the_threshold_and_the_minimum_may_be_any_real_number_and_a_pause_is_read_only():
    series = series_of([5, 0.5, 0.5, 0.5, 5])
    for tau, d_min in ((1, 0.3), (np.float32(1.0), np.float64(0.3)), (np.int64(1), 0.3), (1.0, 0.25)):
        found = find_pauses(series, tau=tau, min_pause_s=d_min)
        assert spans(found) == [(1, 3)], (tau, d_min)
        assert all(type(x) is float for x in (found[0].t_start, found[0].t_end))  # plain floats, whatever went in
    with pytest.raises(dataclasses.FrozenInstanceError):
        found[0].first_row = 0  # type: ignore[misc]


def test_t_met_09a_a_series_with_fewer_than_two_rows_has_no_pause():
    assert find_pauses(series_of([]), tau=TAU, min_pause_s=0.1) == ()
    assert find_pauses(series_of([None], reasons=[21]), tau=TAU, min_pause_s=0.01) == ()


@pytest.mark.parametrize("code", [1, 2, 3, 4, 5, 6])
def test_t_met_09a_a_pose_loss_next_to_a_pause_cuts_it_on_that_side(code):
    before = find_pauses(series_of([None, 0.5, 0.5, 0.5, 5], reasons=[code, 0, 0, 0, 0]), tau=TAU, min_pause_s=0.3)
    assert [(p.cut_before, p.cut_after) for p in before] == [(True, False)]
    after = find_pauses(series_of([5, 0.5, 0.5, 0.5, None], reasons=[0, 0, 0, 0, code]), tau=TAU, min_pause_s=0.3)
    assert [(p.cut_before, p.cut_after) for p in after] == [(False, True)]
    both = find_pauses(series_of([None, 0.5, 0.5, 0.5, None], reasons=[code, 0, 0, 0, code]), tau=TAU, min_pause_s=0.3)
    assert [(p.cut_before, p.cut_after) for p in both] == [(True, True)]


@pytest.mark.parametrize("code", [16, 17, 18, 19, 20, 21, 22])
def test_t_met_09a_a_boundary_of_the_protocol_or_of_the_track_does_not_cut_a_pause(code):
    series = series_of([None, 0.5, 0.5, 0.5, None], reasons=[code, 0, 0, 0, code])
    pauses = find_pauses(series, tau=TAU, min_pause_s=0.3)
    assert [(p.cut_before, p.cut_after) for p in pauses] == [(False, False)]  # 16 to 22 are boundaries, not losses


def test_t_met_09a_only_the_row_next_to_a_pause_cuts_it():
    values = [None, 5, 0.5, 0.5, 0.5, 5, None]  # a hole two rows away from the pause is not next to it
    pauses = find_pauses(series_of(values, reasons=[2, 0, 0, 0, 0, 0, 2]), tau=TAU, min_pause_s=0.3)
    assert [(p.cut_before, p.cut_after) for p in pauses] == [(False, False)]


def reference_pauses(values: list[float], reasons: list[int], step: float, tau: float, d_min: float) -> list[tuple]:
    """The same rule, written as a plain scan with a state, for the random series."""
    out: list[tuple] = []
    start = None
    for k in range(len(values) + 1):
        slow = k < len(values) and reasons[k] == 0 and values[k] < tau
        if slow and start is None:
            start = k
        if not slow and start is not None:
            n = k - start
            if n * step >= d_min - 1e-9:
                before = start > 0 and 1 <= reasons[start - 1] <= 6
                after = k < len(values) and 1 <= reasons[k] <= 6
                out.append((start, k - 1, start * step, k * step, before, after))
            start = None
    return out


def test_t_met_09a_three_hundred_random_series_agree_with_a_plain_scan():
    rng = np.random.default_rng(507)
    seen = 0
    for _ in range(300):
        n = int(rng.integers(2, 40))
        step = float(rng.choice([1 / 30, 0.05, 0.1]))
        codes = rng.choice([2, 3, 4, 5, 6, 16, 18, 22], size=n)
        lost = rng.random(n) < 0.2
        values = np.where(lost, np.nan, rng.uniform(0.0, 2.0, size=n))
        reasons = [int(c) if bad else 0 for c, bad in zip(codes, lost, strict=True)]
        tau, d_min = float(rng.uniform(0.3, 1.5)), float(rng.choice([0.01, 0.1, 0.2, 0.35]))
        series = series_of([None if math.isnan(x) else x for x in values], reasons=reasons, step=step)
        got = [(p.first_row, p.last_row, p.t_start, p.t_end, p.cut_before, p.cut_after) for p in
               find_pauses(series, tau=tau, min_pause_s=d_min)]  # fmt: skip
        want = reference_pauses(list(values), reasons, step, tau, d_min)
        assert len(got) == len(want)
        for g, w in zip(got, want, strict=True):
            assert g[:2] == w[:2] and g[4:] == w[4:]
            assert g[2] == pytest.approx(w[2], abs=1e-9) and g[3] == pytest.approx(w[3], abs=1e-9)
        seen += len(got)
    assert seen > 100  # the comparison saw a good number of pauses, not 300 empty answers


# --- a layer whose hands move, stop, move, stop and move again ------------------------------------------------------
G = 60
SEG = (5, 55)  # 50 rows of the segment, five margin rows on each side
KNOT_ROWS = [0, 20, 32, 40, 50, 59]
KNOT_X = [0.0, 100.0, 100.0, 140.0, 140.0, 185.0]  # px: 5 px per row (1 trunk length per second at 150 px) or still
TAU_LAYER = 0.25  # body lengths per second: above the 0 of the still rows, below the 0.5 of the rows at a corner
D_MIN = 0.3
# the still rows are the grid rows 21 to 31 and 41 to 49 (both neighbours are still); the rows 20, 32, 40 and 50 are
# corner rows (one neighbour still, one moving: 0.5 body lengths per second). In the series (row - 5): 16 to 26 and
# 36 to 44.
PAUSE_ROWS = [(16, 26), (36, 44)]


def pause_layer(
    *, segment: tuple[int, int] | None = SEG, knots: tuple[list[int], list[float]] = (KNOT_ROWS, KNOT_X)
) -> PoseFiltered:
    base = exact_layer(body(G, 400.0, trunk=150.0), segment=segment)
    kp = base.keypoints.astype(np.float64)
    x = np.interp(np.arange(G), *knots)
    for joint in (9, 10):  # both hands: the median of the group is each of them
        kp[:, joint, 0] += x
    return edited(base, keypoints=kp)


def step_of(layer: PoseFiltered) -> float:
    return float(layer.meta.timeline.step_s)


def run(layer: PoseFiltered, **kwargs: Any):
    args: dict[str, Any] = {"group": "hands", "flags": {}, "camera_id": "camA", "view_category": "front"}
    args.update(kwargs)
    return group_speed(layer, **args)


def stat(result, name: str) -> float | None:
    (s,) = [s for s in result.summary.statistics if s.name == name]
    return s.value


def at(layer: PoseFiltered, s: int) -> float:
    return float(layer.t_grid[SEG[0] + s])


def trunk_px(row: np.ndarray) -> float:
    p = row.astype(np.float64)
    sx, sy = (p[5, 0] + p[6, 0]) / 2.0, (p[5, 1] + p[6, 1]) / 2.0
    hx, hy = (p[11, 0] + p[12, 0]) / 2.0, (p[11, 1] + p[12, 1]) / 2.0
    return math.hypot(sx - hx, sy - hy)


def profile_of(layer: PoseFiltered) -> list[float]:
    """V of the hands at the rows of the segment, from the keypoints of the layer, with a plain loop."""
    rows = list(range(SEG[0], SEG[1]))
    scale = statistics.median(trunk_px(layer.keypoints[g]) for g in rows)
    out = []
    for g in rows:
        speeds = []
        for joint in (9, 10):
            a, b = layer.keypoints[g - 1, joint].astype(np.float64), layer.keypoints[g + 1, joint].astype(np.float64)
            dt = float(layer.t_grid[g + 1] - layer.t_grid[g - 1])
            speeds.append(math.hypot(b[0] - a[0], b[1] - a[1]) / dt / scale)
        out.append(statistics.median(speeds))
    return out


# --- T-MET-09b: group_speed with pauses -------------------------------------------------------------------------------
def test_t_met_09b_the_two_stops_of_the_hands_are_two_pauses_with_their_own_times_and_numbers():
    layer = pause_layer()
    v = profile_of(layer)
    assert [round(v[s], 6) for s in (15, 16, 26, 27, 35, 36, 44, 45)] == [0.5, 0.0, 0.0, 0.5, 0.5, 0.0, 0.0, 0.5]
    out = run(layer, pause_tau=TAU_LAYER, pause_min_s=D_MIN)
    step = step_of(layer)
    pauses = [e for e in out.summary.events if e.kind == "pause"]
    assert len(pauses) == len(out.summary.events) == 2
    for event, (first, last) in zip(pauses, PAUSE_ROWS, strict=True):
        assert event.t_start == pytest.approx(at(layer, first), abs=1e-9)
        assert event.t_end == pytest.approx(at(layer, last) + step, abs=1e-9)
        assert event.value is None and event.uses_threshold is True
    assert stat(out, "pause_count") == 2.0
    assert stat(out, "pause_total_s") == pytest.approx((11 + 9) * step, rel=1e-12)
    assert stat(out, "pause_longest_s") == pytest.approx(11 * step, rel=1e-12)
    assert stat(out, "pause_cut_count") == 0.0


def test_t_met_09b_the_longest_pause_is_the_longest_and_not_the_first():
    # still from the row 20 to 30 and from 40 to 52: the pauses last 9 rows (series 16 to 24) and then 11 (36 to 46)
    layer = pause_layer(knots=([0, 20, 30, 40, 52, 59], [0.0, 100.0, 100.0, 140.0, 140.0, 175.0]))
    out = run(layer, pause_tau=TAU_LAYER, pause_min_s=D_MIN)
    assert spans(find_pauses(out.series, tau=TAU_LAYER, min_pause_s=D_MIN)) == [(16, 24), (36, 46)]
    step = step_of(layer)
    assert stat(out, "pause_longest_s") == pytest.approx(11 * step) and stat(out, "pause_total_s") == pytest.approx(
        20 * step
    )
    assert [e.t_start for e in out.summary.events] == pytest.approx([at(layer, 16), at(layer, 36)])


def test_t_met_09b_a_measured_run_that_the_minimum_valid_duration_made_21_has_no_pause_and_the_others_stay():
    layer = pause_layer()
    windows = [(at(layer, 14), at(layer, 28)), (at(layer, 35), at(layer, 46))]  # series rows 14 to 27 and 35 to 45
    both = run(layer, intervals=windows, pause_tau=TAU_LAYER, pause_min_s=D_MIN)
    assert spans(find_pauses(both.series, tau=TAU_LAYER, min_pause_s=D_MIN)) == PAUSE_ROWS
    short = run(layer, intervals=windows, min_valid_s=0.4, pause_tau=TAU_LAYER, pause_min_s=D_MIN)
    assert short.series.reason[35:46].tolist() == [21] * 11  # 11 rows last 0.367 s: not a valid run, so no pause in it
    assert spans(find_pauses(short.series, tau=TAU_LAYER, min_pause_s=D_MIN)) == [PAUSE_ROWS[0]]
    assert (
        len(short.summary.events) == 1 and stat(short, "pause_count") == 1.0 and stat(short, "pause_cut_count") == 0.0
    )


def test_t_met_09b_the_same_pauses_are_found_by_find_pauses_on_the_series_and_by_a_plain_scan():
    layer = pause_layer()
    series = run(layer, pause_tau=TAU_LAYER, pause_min_s=D_MIN).series
    pauses = find_pauses(series, tau=TAU_LAYER, min_pause_s=D_MIN)
    assert spans(pauses) == PAUSE_ROWS
    reference = reference_pauses(profile_of(layer), [0] * 50, step_of(layer), TAU_LAYER, D_MIN)
    assert [(a, b) for a, b, *_ in reference] == PAUSE_ROWS


def test_t_met_09b_the_minimum_keeps_the_longer_pause_and_a_longer_minimum_keeps_none_but_counts_zero():
    layer = pause_layer()
    step = step_of(layer)
    one = run(layer, pause_tau=TAU_LAYER, pause_min_s=0.35)  # 11 steps are 0.367 s, 9 steps 0.3 s
    assert stat(one, "pause_count") == 1.0 and stat(one, "pause_longest_s") == pytest.approx(11 * step)
    none = run(layer, pause_tau=TAU_LAYER, pause_min_s=0.4)
    assert none.summary.events == () and none.summary.evidence == "sufficient"
    # the measured rows last 1.67 s, so a pause of 0.4 s could have been seen: a measured 0, not a missing number
    assert [stat(none, n) for n in ("pause_count", "pause_total_s", "pause_longest_s", "pause_cut_count")] == [0.0] * 4


def test_t_met_09b_a_threshold_above_every_speed_makes_the_whole_measured_stretch_one_pause():
    layer = pause_layer()
    out = run(layer, pause_tau=5.0, pause_min_s=D_MIN)
    (event,) = out.summary.events
    assert event.t_start == pytest.approx(at(layer, 0)) and event.t_end == pytest.approx(at(layer, 49) + step_of(layer))
    assert stat(out, "pause_count") == 1.0 and stat(out, "pause_total_s") == pytest.approx(50 * step_of(layer))
    assert run(layer, pause_tau=1e-6, pause_min_s=D_MIN).series.reason.tolist() == [0] * 50  # a stop is exactly 0


def test_t_met_09b_the_profile_the_reasons_and_the_first_four_numbers_do_not_depend_on_the_pause_arguments():
    layer = pause_layer()
    plain, asked = run(layer), run(layer, pause_tau=TAU_LAYER, pause_min_s=D_MIN)
    assert np.array_equal(plain.series.values, asked.series.values, equal_nan=True)
    assert np.array_equal(plain.series.reason, asked.series.reason)
    assert np.array_equal(plain.series.t_sec, asked.series.t_sec)
    assert asked.summary.statistics[:4] == plain.summary.statistics
    a, b = plain.series.header.model_dump(), asked.series.header.model_dump()
    for key in ("pause_tau", "pause_min_s"):
        assert a["parameters"].pop(key) is None and b["parameters"].pop(key) is not None
    assert a == b  # everything else of the header is the same


def test_t_met_09b_without_the_arguments_only_the_profile_is_output_and_no_threshold_is_claimed():
    out = run(pause_layer())
    s = out.summary
    assert s.events == () and [x.name for x in s.statistics] == [
        "segment_duration_s", "speed_median", "speed_cv", "bridged_rows",
    ]  # fmt: skip
    assert s.threshold_source is None and not any(x.uses_threshold for x in s.statistics)
    assert s.parameters["pause_tau"] is None and s.parameters["pause_min_s"] is None


def test_t_met_09b_the_threshold_is_labelled_unsigned_and_the_result_is_experimental_never_conclusive():
    s = run(pause_layer(), pause_tau=TAU_LAYER, pause_min_s=D_MIN).summary
    assert s.threshold_source == "unsigned_config" and s.record_status == "experimental" and s.conclusive is False
    assert [x.name for x in s.statistics] == [
        "segment_duration_s", "speed_median", "speed_cv", "bridged_rows",
        "pause_count", "pause_total_s", "pause_longest_s", "pause_cut_count",
    ]  # fmt: skip
    assert [x.units for x in s.statistics[4:]] == ["count", "s", "s", "count"]
    assert [x.uses_threshold for x in s.statistics] == [False] * 4 + [True] * 4
    assert s.parameters["pause_tau"] == TAU_LAYER and s.parameters["pause_min_s"] == D_MIN


def test_t_met_09b_a_pause_next_to_a_row_the_pose_lost_is_cut_and_counted_as_cut():
    layer = pause_layer()
    k, r, _ = cells(layer)
    for joint in (9, 10):
        drop(
            k, r, 33, joint, 2
        )  # the rows 32 and 34 lose both hands: the series row 27, just after pause 1, has no value
        drop(k, r, 19, joint, 4)  # ... and the rows 18 and 20: the series row 15 (just before pause 1) has none
    out = run(edited(layer, keypoints=k, reason=r), pause_tau=TAU_LAYER, pause_min_s=D_MIN)
    assert out.series.reason[15] == 4 and out.series.reason[27] == 2
    pauses = find_pauses(out.series, tau=TAU_LAYER, min_pause_s=D_MIN)
    assert spans(pauses) == PAUSE_ROWS  # the pauses themselves are unchanged
    assert [(p.cut_before, p.cut_after) for p in pauses] == [(True, True), (False, False)]
    assert stat(out, "pause_count") == 2.0 and stat(out, "pause_cut_count") == 1.0


def test_t_met_09b_a_row_outside_the_coachs_intervals_is_a_boundary_and_does_not_cut():
    layer = pause_layer()
    out = run(layer, intervals=[(at(layer, 0), at(layer, 27))], pause_tau=TAU_LAYER, pause_min_s=D_MIN)
    assert out.series.reason[27] == 16 and out.series.reason[26] == 0  # the first row outside is next to pause 1
    assert stat(out, "pause_count") == 1.0 and stat(out, "pause_cut_count") == 0.0
    (event,) = out.summary.events
    assert event.t_end == pytest.approx(at(layer, 26) + step_of(layer))


# --- T-MET-09d: nothing is a 0 that nobody measured; no evidence gives no number --------------------------------------
def test_t_met_09d_when_no_run_of_measured_rows_lasts_the_minimum_the_pause_numbers_are_null_not_zero():
    layer = pause_layer()
    short = [(at(layer, 0), at(layer, 3))]  # three measured rows, 0.1 s; the rest is outside the interval
    out = run(layer, intervals=short, pause_tau=TAU_LAYER, pause_min_s=D_MIN)
    assert out.summary.evidence == "sufficient" and out.summary.events == ()
    assert [stat(out, n) for n in ("pause_count", "pause_total_s", "pause_longest_s", "pause_cut_count")] == [None] * 4
    assert stat(out, "speed_median") is not None  # the profile's numbers are there: only the pause numbers are not
    assert out.summary.threshold_source == "unsigned_config"  # the null numbers are still threshold outputs
    seen = run(layer, intervals=short, pause_tau=TAU_LAYER, pause_min_s=0.05)  # a pause of 0.05 s could have been seen
    assert stat(seen, "pause_count") == 0.0 and stat(seen, "pause_longest_s") == 0.0


def test_t_met_09d_the_minimum_is_met_by_a_run_that_lasts_it_to_a_nanosecond_and_not_by_a_shorter_one():
    layer = pause_layer()
    step = step_of(layer)
    short = [(at(layer, 0), at(layer, 3))]
    assert stat(run(layer, intervals=short, pause_tau=TAU_LAYER, pause_min_s=3 * step), "pause_count") == 0.0
    assert stat(run(layer, intervals=short, pause_tau=TAU_LAYER, pause_min_s=3 * step + 5e-10), "pause_count") == 0.0
    assert stat(run(layer, intervals=short, pause_tau=TAU_LAYER, pause_min_s=3 * step + 5e-9), "pause_count") is None


def test_t_met_09d_with_no_evidence_all_eight_numbers_are_null_and_there_is_no_event():
    layer = pause_layer()
    out = run(layer, flags={"perspective_shift": True}, pause_tau=TAU_LAYER, pause_min_s=D_MIN)
    s = out.summary
    assert s.evidence == "insufficient_evidence" and s.insufficient_reason == "interval_flagged"
    assert len(s.statistics) == 8 and all(x.value is None for x in s.statistics) and s.events == ()
    assert s.threshold_source == "unsigned_config"
    nothing = run(edited(layer, grid_in_segment=np.zeros(G, dtype=bool)), pause_tau=TAU_LAYER, pause_min_s=D_MIN)
    assert nothing.summary.insufficient_reason == "no_frame" and len(nothing.summary.statistics) == 8
    assert all(x.value is None for x in nothing.summary.statistics)


def test_t_met_09d_a_group_that_does_not_move_is_one_pause_over_the_measured_rows():
    out = run(pause_layer(), group="feet", pause_tau=0.05, pause_min_s=D_MIN)
    (event,) = out.summary.events
    layer = pause_layer()
    assert event.t_start == pytest.approx(at(layer, 0)) and event.t_end == pytest.approx(at(layer, 49) + step_of(layer))
    assert stat(out, "pause_count") == 1.0 and stat(out, "speed_median") == 0.0
    assert out.summary.metric_name == "speed_feet"


# --- T-MET-09c: refusals ----------------------------------------------------------------------------------------------
BAD_VALUES = [0, 0.0, -1.0, float("nan"), float("inf"), -float("inf"), True, "0.25", [0.25], None]


@pytest.mark.parametrize("bad", BAD_VALUES, ids=[repr(b) for b in BAD_VALUES])
def test_t_met_09c_a_bad_threshold_or_minimum_is_refused_naming_the_argument(bad):
    layer = pause_layer()
    if bad is not None:  # None alone is "not asked": it is refused only as half of a pair, below
        with pytest.raises(MetricError, match="pause_tau"):
            run(layer, pause_tau=bad, pause_min_s=D_MIN)
        with pytest.raises(MetricError, match="pause_min_s"):
            run(layer, pause_tau=TAU_LAYER, pause_min_s=bad)
        with pytest.raises(MetricError, match="tau"):
            find_pauses(run(layer).series, tau=bad, min_pause_s=D_MIN)
        with pytest.raises(MetricError, match="min_pause_s"):
            find_pauses(run(layer).series, tau=TAU_LAYER, min_pause_s=bad)


def test_t_met_09c_one_argument_without_the_other_is_refused_and_both_none_is_the_profile_only():
    layer = pause_layer()
    with pytest.raises(MetricError, match="pause_tau and pause_min_s"):
        run(layer, pause_tau=TAU_LAYER)
    with pytest.raises(MetricError, match="pause_tau and pause_min_s"):
        run(layer, pause_min_s=D_MIN)
    assert run(layer, pause_tau=None, pause_min_s=None).summary.events == ()


def test_t_met_09c_the_arguments_are_checked_even_when_no_row_is_measured_and_a_non_series_is_refused():
    layer = pause_layer()
    with pytest.raises(MetricError, match="pause_tau"):
        run(layer, intervals=[], pause_tau=-1.0, pause_min_s=D_MIN)  # every row is outside: nothing would use them
    with pytest.raises(MetricError, match="pause_min_s"):
        run(edited(layer, grid_in_segment=np.zeros(G, dtype=bool)), pause_tau=TAU_LAYER, pause_min_s=0.0)
    with pytest.raises(MetricError, match="series"):
        find_pauses("not a series", tau=TAU_LAYER, min_pause_s=D_MIN)  # type: ignore[arg-type]
    with pytest.raises(MetricError, match="series"):
        find_pauses(None, tau=TAU_LAYER, min_pause_s=D_MIN)  # type: ignore[arg-type]
