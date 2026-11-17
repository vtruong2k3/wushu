"""P4.07: the quality chain wired in its order, and what its report says about data with a known answer
(T-QLT-11h to 11k).

``run_quality_arrays`` must be exactly the six stages called by hand in the order of DEC-0046 and DEC-0049: mask, the
swap flag and Hampel (both on the mask layer), the gap layer with the swap mask as ``blocked``, the uniform grid, the
Butterworth filter. The report is then read against the synthetic sequences of the project (SYN-05 to SYN-08) and
against the tracker scene.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from helpers.quality_fixtures import build_f1, clean
from helpers.synth import make_sequence
from helpers.track_build import FPS as SCENE_FPS
from helpers.track_build import HOME_X, resolve, stands
from taiji_ai.pose.skeleton import IDX, LR_PAIRS, NUM_JOINTS
from taiji_ai.quality import QualityError
from taiji_ai.quality.chain import QualityParams, run_quality, run_quality_arrays
from taiji_ai.quality.filters import ButterworthParams, HampelParams, hampel_outliers, lowpass_grid, torso_length_px
from taiji_ai.quality.gaps import BLOCKED, FILLED, GapParams, interpolate_gaps
from taiji_ai.quality.lr_swap import SwapParams, detect_lr_swaps
from taiji_ai.quality.mask import MaskParams, apply_mask
from taiji_ai.quality.resample import ResampleParams, resample_gaps
from taiji_ai.track.state import TRACKED

FPS30 = 30.0


def by_hand(kp, score, t, *, tracked=None, fraction=0.01):
    """The six stages in the order of the plan, one after the other."""
    mask = apply_mask(kp, score, tracked)
    torso = torso_length_px(mask.keypoints, mask.reason)
    swap = detect_lr_swaps(mask.keypoints, mask.reason, t, torso_px=torso)
    hampel = hampel_outliers(mask.keypoints, mask.reason, t, HampelParams(scale_floor_px=fraction * torso))
    gaps = interpolate_gaps(hampel.keypoints, hampel.reason, t, blocked=swap.blocked)
    grid = resample_gaps(gaps, t)
    return mask, swap, hampel, gaps, grid, lowpass_grid(grid)


def same(a, b) -> bool:
    return a.dtype == b.dtype and a.shape == b.shape and np.array_equal(a, b, equal_nan=a.dtype.kind == "f")


# --- T-QLT-11h: the chain is the stages -------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "scenario, kwargs", [("SYN-08", {"noise_px": 1.0}), ("SYN-06", {"noise_px": 1.0}), ("SYN-07", {})]
)
def test_t_qlt_11h_the_chain_is_the_six_stages_in_order_bit_for_bit(scenario, kwargs):
    seq = make_sequence(scenario, seed=3, **kwargs)
    r = run_quality_arrays(seq.kp, seq.score, seq.t_sec)
    mask, swap, hampel, gaps, grid, filt = by_hand(seq.kp, seq.score, seq.t_sec)
    assert same(r.mask.keypoints, mask.keypoints) and same(r.mask.reason, mask.reason)
    assert same(r.swap.suspect, swap.suspect) and same(r.swap.events, swap.events)
    assert same(r.hampel.keypoints, hampel.keypoints) and same(r.hampel.outlier, hampel.outlier)
    assert same(r.gaps.keypoints, gaps.keypoints) and same(r.gaps.interpolated, gaps.interpolated)
    assert same(r.gaps.reason, gaps.reason) and np.array_equal(r.gaps.gaps.outcome, gaps.gaps.outcome)
    assert same(r.grid.keypoints, grid.keypoints) and same(r.grid.reason, grid.reason)
    assert same(r.filtered.keypoints, filt.keypoints) and same(r.filtered.filtered, filt.filtered)
    assert same(r.filtered.interpolated, filt.interpolated) and same(r.filtered.reason, filt.reason)
    assert r.torso_px == torso_length_px(mask.keypoints, mask.reason)


def test_t_qlt_11h_the_swap_mask_is_given_to_the_gap_layer_as_blocked():
    seq = make_sequence("SYN-08", seed=3, noise_px=0.0)  # swaps in rows 20 to 22 and 50 to 52
    score = np.array(seq.score, copy=True)
    joint = IDX["RShoulder"]
    score[24:26, joint] = 0.1  # a hole right after the jump back, and one far from any swap
    score[80:82, joint] = 0.1
    r = run_quality_arrays(seq.kp, score, seq.t_sec)
    table = r.gaps.gaps
    # Hampel has made the swapped cells of rows 20 to 22 (and the row between the swap and the hole, whose window is
    # mostly swapped) holes too, so the hole of rows 24 and 25 is the tail of a longer gap: find the gap that holds it
    near = np.flatnonzero((table.joint == joint) & (table.start <= 24) & (table.end >= 25))
    far = np.flatnonzero((table.joint == joint) & (table.start == 80))
    assert len(near) == 1 and len(far) == 1
    assert table.outcome[near[0]] == BLOCKED and table.outcome[far[0]] == FILLED
    assert not r.gaps.interpolated[24:26, joint].any() and r.gaps.interpolated[80:82, joint].all()
    seg = r.report.intervals[0]
    assert seg.gaps.gaps.blocked >= 1 and seg.gaps.cells.filled >= 2


def test_t_qlt_11h_the_swap_flag_reads_the_mask_layer_not_the_layer_after_hampel():
    seq = make_sequence("SYN-08", seed=3, noise_px=0.0, swap_ranges=((40, 41),))  # one row: Hampel would hide it
    r = run_quality_arrays(seq.kp, seq.score, seq.t_sec)
    assert np.flatnonzero(r.swap.events.any(axis=1)).tolist() == [40, 41]
    assert np.flatnonzero(r.swap.frame_suspect).tolist() == [40]
    assert r.hampel.outlier[40].any()  # Hampel did turn the swapped labels of that row into holes
    assert r.report.warnings == (f"lr_swap_suspect@{seq.t_sec[40]:.2f}-{seq.t_sec[41]:.2f}",)


def test_t_qlt_11h_hampel_reads_the_mask_layer_and_the_floor_is_a_share_of_the_torso():
    seq = make_sequence("SYN-05", seed=3, noise_px=1.0)
    r = run_quality_arrays(seq.kp, seq.score, seq.t_sec)
    mask = apply_mask(seq.kp, seq.score)
    torso = torso_length_px(mask.keypoints, mask.reason)
    assert r.torso_px == torso and r.params.hampel.scale_floor_px == pytest.approx(0.01 * torso)
    assert r.hampel.params.scale_floor_px == pytest.approx(0.01 * torso)


def test_t_qlt_11h_the_layers_stay_apart_and_nothing_given_is_changed():
    t, kp, score, tracked, in_segment = build_f1()
    before = (kp.copy(), score.copy(), t.copy(), tracked.copy(), in_segment.copy())
    r = run_quality_arrays(kp, score, t, tracked=tracked, in_segment=in_segment)
    assert all(
        np.array_equal(a, b, equal_nan=True) for a, b in zip((kp, score, t, tracked, in_segment), before, strict=True)
    )
    assert r.mask.reason is not r.gaps.reason and r.filtered.keypoints is not r.grid.keypoints
    assert not np.array_equal(r.mask.keypoints, r.filtered.keypoints, equal_nan=True)  # the layers are different ones
    for a in (r.mask.keypoints, r.hampel.keypoints, r.gaps.keypoints, r.grid.keypoints, r.filtered.keypoints):
        assert not a.flags.writeable


def test_t_qlt_11h_filtered_on_source_is_the_grid_layer_on_the_rows():
    seq = make_sequence("SYN-05", seed=1, noise_px=1.0)
    r = run_quality_arrays(seq.kp, seq.score, seq.t_sec)
    on_source = r.filtered_on_source()
    assert on_source.shape == seq.kp.shape and r.grid.gridmap.identity
    assert np.array_equal(on_source, r.filtered.keypoints, equal_nan=True)
    vfr = make_sequence("SYN-07", seed=1)
    rv = run_quality_arrays(vfr.kp, vfr.score, vfr.t_sec)
    back = rv.filtered_on_source()
    assert back.shape == vfr.kp.shape and not rv.grid.gridmap.identity
    assert np.isfinite(back).mean() > 0.95  # a few rows after the last grid time have no value


def test_t_qlt_11h_a_stage_error_names_the_stage():
    seq = make_sequence("SYN-05", seed=0)
    with pytest.raises(QualityError, match="^mask: "):
        run_quality_arrays(seq.kp.astype(np.int32), seq.score, seq.t_sec)
    backwards = np.array(seq.t_sec[::-1], copy=True)
    with pytest.raises(QualityError, match="^lr_swap: "):
        run_quality_arrays(seq.kp, seq.score, backwards)


def test_t_qlt_11h_the_parameters_reach_their_stage():
    t, kp, score = clean(40)
    score[10:13, 9] = 0.1  # 3 rows: the anchors (rows 9 and 13) are 0.133 s apart, so the default 150 ms bridges it
    bridged = run_quality_arrays(kp, score, t).report.intervals[0]
    assert bridged.bridged == 3
    strict = QualityParams(gaps=GapParams(max_gap_s=0.1))
    refused = run_quality_arrays(kp, score, t, params=strict).report.intervals[0]
    assert refused.bridged == 0 and refused.gaps.gaps.too_long == 1
    strict_mask = QualityParams(mask=MaskParams(tau_kp=0.99))
    all_out = run_quality_arrays(kp, score, t, params=strict_mask).report.intervals[0]
    assert all_out.observed == 0 and all_out.missing_by_reason.low_conf == 40 * NUM_JOINTS
    slow = QualityParams(filter=ButterworthParams(cutoff_hz=20.0))  # above the Nyquist frequency of 15 Hz
    skipped = run_quality_arrays(kp, score, t, params=slow)
    assert skipped.report.intervals[0].filtered == 0 and "filter_skipped_above_nyquist" in skipped.report.warnings


# --- T-QLT-11i: data with a known answer ------------------------------------------------------------------------------
def test_t_qlt_11i_syn06_the_short_gap_is_bridged_and_the_long_one_stays_nan():
    seq = make_sequence("SYN-06", seed=1, noise_px=0.0)
    short, long = (g for g in seq.truth["gaps"])
    assert short["kind"] == "short" and long["kind"] == "long"
    r = run_quality_arrays(seq.kp, seq.score, seq.t_sec)
    seg = r.report.intervals[0]
    n_short = short["n_missing"] * len(short["joints"])
    n_long = long["n_missing"] * len(long["joints"])
    assert seg.gaps.cells.filled == n_short and seg.gaps.gaps.filled == len(short["joints"])
    assert seg.gaps.cells.too_long == n_long and seg.gaps.gaps.too_long == len(long["joints"])
    assert seg.bridged == n_short and seg.missing == n_long
    assert seg.missing_by_reason.non_finite == n_long and seg.unobserved_by_reason.non_finite == n_short + n_long
    for joint in long["joints"]:  # the long gap is NaN in the final layer, the short one has values
        j = IDX[joint]
        assert np.isnan(r.filtered.keypoints[long["frames"][0] : long["frames"][1] + 1, j]).all()
        assert np.isfinite(r.filtered.keypoints[short["frames"][0] : short["frames"][1] + 1, j]).all()
    assert r.report.warnings == ()


def test_t_qlt_11i_syn08_the_warning_has_the_times_of_the_swap_and_the_swapped_rows_are_suspect():
    seq = make_sequence("SYN-08", seed=3, noise_px=0.0)  # swaps in rows 20 to 22 and 50 to 52
    r = run_quality_arrays(seq.kp, seq.score, seq.t_sec)
    t = seq.t_sec
    assert r.report.warnings == (
        f"lr_swap_suspect@{t[20]:.2f}-{t[23]:.2f}",  # events at row 20 (enter) and row 23 (exit): blocked 20 to 23
        f"lr_swap_suspect@{t[50]:.2f}-{t[53]:.2f}",
    )
    assert np.array_equal(r.swap.frame_suspect, seq.truth["lr_swap_mask"])
    seg = r.report.intervals[0]
    # a pair is flagged when both of its labels jump by 0.2 torso: which joints that is comes from the layer; the
    # rows are known: 3 swapped rows (suspect) and 4 rows with the event rows (blocked) in each of the two swaps
    flagged = [j for j in range(NUM_JOINTS) if r.swap.suspect[:, j].any()]
    assert flagged and len(flagged) % 2 == 0 and len(flagged) <= 2 * len(LR_PAIRS)
    for j, joint in enumerate(seg.joints):
        assert (joint.suspect, joint.blocked) == ((6, 8) if j in flagged else (0, 0)), joint.joint
    assert seg.suspect == 6 * len(flagged) and seg.blocked == 8 * len(flagged)


def test_t_qlt_11i_syn05_has_no_warning_and_syn07_has_grid_resampled():
    syn05 = make_sequence("SYN-05", seed=1, noise_px=1.0)
    r5 = run_quality_arrays(syn05.kp, syn05.score, syn05.t_sec)
    assert r5.report.warnings == () and r5.report.timeline.resampled is False
    syn07 = make_sequence("SYN-07", seed=1)
    r7 = run_quality_arrays(syn07.kp, syn07.score, syn07.t_sec)
    assert r7.report.warnings == ("grid_resampled",) and r7.report.timeline.resampled is True
    seg = r7.report.intervals[0]
    assert seg.rows == r7.report.timeline.grid_rows and seg.source_rows == len(syn07.t_sec) and seg.mixed_rows > 0


# --- T-QLT-11j: the tracker scene -------------------------------------------------------------------------------------
def scene():
    """The performer appears at frame 10 and is away from frame 40 to 99; the margins of the segment are kept."""
    return resolve(
        {0: stands(HOME_X, first=10, absent=[(40, 100)]), 1: stands(1500)},
        160,
        at_t_sec=20 / SCENE_FPS,
        segment_start_pos=5,
    )


def test_t_qlt_11j_the_scene_the_margins_are_not_in_the_segment_and_the_absence_is_not_tracked():
    run = scene()
    target = run.target
    inside = np.flatnonzero(target.in_segment)
    assert inside.tolist() == list(range(inside[0], inside[-1] + 1))  # contiguous
    r = run_quality(target)
    seg = r.report.intervals[0]
    assert seg.rows == len(inside) and seg.rows < target.n_frames and seg.cells == seg.rows * 26
    not_tracked = int(((target.status != TRACKED) & target.in_segment).sum())
    assert not_tracked > 0 and seg.not_tracked_frames == not_tracked
    assert seg.missing_by_reason.not_tracked == not_tracked * 26
    tracked_in = int(((target.status == TRACKED) & target.in_segment).sum())
    assert seg.usable_frames == tracked_in  # a still performer: every tracked frame has its joints
    assert r.report.warnings == ()


def test_t_qlt_11j_the_loss_at_the_start_is_open_start_and_the_one_in_the_middle_is_never_fill():
    run = scene()
    target = run.target
    r = run_quality(target)
    seg = r.report.intervals[0]
    rows = np.arange(target.n_frames)
    tracked = target.status == TRACKED
    first, last = int(rows[tracked][0]), int(rows[tracked][-1])
    in_seg = target.in_segment
    start_rows = int((in_seg & (rows < first)).sum())  # before the performer is there
    middle_rows = int((in_seg & ~tracked & (rows > first) & (rows < last)).sum())
    end_rows = int((in_seg & (rows > last)).sum())
    assert start_rows > 0 and middle_rows > 0
    assert seg.gaps.gaps.open_start == 26 and seg.gaps.cells.open_start == 26 * start_rows
    assert seg.gaps.gaps.never_fill == 26 and seg.gaps.cells.never_fill == 26 * middle_rows
    assert seg.gaps.cells.open_end == 26 * end_rows
    assert seg.bridged == 0


def test_t_qlt_11j_run_quality_is_run_quality_arrays_on_the_arrays_of_the_track():
    run = scene()
    target = run.target
    a = run_quality(target)
    b = run_quality_arrays(
        target.keypoints, target.scores, target.t_sec, tracked=target.status == TRACKED, in_segment=target.in_segment
    )
    assert a.report == b.report and same(a.filtered.keypoints, b.filtered.keypoints)


def test_t_qlt_11j_a_swap_put_into_the_take_is_a_warning_inside_the_segment_only():
    run = scene()
    target = run.target
    kp = target.keypoints.copy()
    left, right = IDX["LAnkle"], IDX["RAnkle"]
    rows = np.flatnonzero(target.status == TRACKED)
    first = int(rows[rows < 40][5])
    for row in range(first, first + 3):
        kp[row, [left, right]] = kp[row, [right, left]]
    r = run_quality(dataclasses.replace(target, keypoints=kp))
    t = target.t_sec
    assert r.report.warnings == (f"lr_swap_suspect@{t[first]:.2f}-{t[first + 3]:.2f}",)


# --- T-QLT-11k: the floor and the parameters in the report ------------------------------------------------------------
def test_t_qlt_11k_a_fraction_of_the_torso_gives_the_floor_in_pixels_and_the_report_states_it():
    t, kp, score = clean(40)  # torso 150 px
    r = run_quality_arrays(kp, score, t, params=QualityParams(hampel_floor_fraction=0.02))
    assert r.params.hampel.scale_floor_px == pytest.approx(3.0)
    assert r.report.params.hampel.scale_floor_px == pytest.approx(3.0) and r.report.params.hampel.floor_fraction == 0.02
    assert r.report.timeline.torso_px == 150.0


def test_t_qlt_11k_none_uses_the_floor_of_hampel_as_it_is():
    t, kp, score = clean(40)
    params = QualityParams(hampel=HampelParams(scale_floor_px=3.5), hampel_floor_fraction=None)
    r = run_quality_arrays(kp, score, t, params=params)
    assert r.report.params.hampel.scale_floor_px == 3.5 and r.report.params.hampel.floor_fraction is None
    assert r.report.warnings == ()  # the torso was measurable: nothing to warn about


def test_t_qlt_11k_a_layer_without_a_torso_uses_the_fixed_floor_and_says_so():
    t, kp, score = clean(40)
    score[:, IDX["LShoulder"]] = 0.1  # the torso cannot be measured in any row
    r = run_quality_arrays(kp, score, t)
    assert np.isnan(r.torso_px) and r.report.timeline.torso_px is None
    assert r.report.params.hampel.scale_floor_px == 2.0  # HampelParams' default, used as it is
    assert r.report.params.hampel.floor_fraction == 0.01  # as configured; the warning says it was not used
    assert r.report.warnings == ("torso_unmeasured",)
    assert not r.swap.events.any()


def test_t_qlt_11k_the_parameters_of_every_stage_are_in_the_report_as_used():
    t, kp, score = clean(40)
    params = QualityParams(
        mask=MaskParams(tau_kp=0.4, essential=(5, 6, 11, 12), min_essential_fraction=0.75),
        swap=SwapParams(min_jump=0.3, max_cross_ratio=0.4, max_dt_s=0.2, max_swap_s=0.6, pairs=((5, 6), (11, 12))),
        hampel=HampelParams(window=5, n_sigma=4.0, min_observed=4, max_half_span_s=0.3),
        hampel_floor_fraction=0.02,
        gaps=GapParams(max_gap_s=0.2, never_fill=(3, 4)),
        resample=ResampleParams(grid_hz=None, max_step_s=0.2, uniform_tol_s=0.002),
        filter=ButterworthParams(cutoff_hz=5.0, order=2, padlen=9),
    )
    p = run_quality_arrays(kp, score, t, params=params).report.params.model_dump(mode="json")
    assert p["mask"] == {"tau_kp": 0.4, "essential": [5, 6, 11, 12], "min_essential_fraction": 0.75}
    assert p["swap"] == {
        "min_jump": 0.3,
        "max_cross_ratio": 0.4,
        "max_dt_s": 0.2,
        "max_swap_s": 0.6,
        "pairs": [[5, 6], [11, 12]],
    }
    assert p["hampel"]["window"] == 5 and p["hampel"]["n_sigma"] == 4.0 and p["hampel"]["min_observed"] == 4
    assert p["hampel"]["max_half_span_s"] == 0.3 and p["hampel"]["floor_fraction"] == 0.02
    assert p["hampel"]["scale_floor_px"] == pytest.approx(3.0)
    assert p["gaps"] == {"max_gap_s": 0.2, "never_fill": [3, 4]}
    assert p["resample"] == {"grid_hz": None, "max_step_s": 0.2, "uniform_tol_s": 0.002}
    assert p["filter"] == {"cutoff_hz": 5.0, "order": 2, "padlen": 9}


def test_t_qlt_11k_the_default_parameters_are_the_defaults_of_the_stages():
    t, kp, score = clean(40)
    p = run_quality_arrays(kp, score, t).report.params
    assert p.mask.tau_kp == 0.3 and p.mask.min_essential_fraction == 0.5 and p.gaps.max_gap_s == 0.15
    assert p.hampel.window == 7 and p.hampel.n_sigma == 3.0 and p.hampel.floor_fraction == 0.01
    assert p.filter.cutoff_hz == 6.0 and p.filter.order == 4 and p.filter.padlen is None
    assert p.swap.min_jump == 0.2 and p.resample.grid_hz is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"hampel_floor_fraction": -0.01},
        {"hampel_floor_fraction": float("nan")},
        {"hampel_floor_fraction": float("inf")},
        {"hampel_floor_fraction": True},
        {"hampel_floor_fraction": "0.01"},
        {"mask": HampelParams()},
        {"swap": MaskParams()},
        {"hampel": None},
        {"gaps": ButterworthParams()},
        {"resample": GapParams()},
        {"filter": ResampleParams()},
    ],
)
def test_t_qlt_11k_wrong_quality_parameters_are_refused(kwargs):
    with pytest.raises(QualityError):
        QualityParams(**kwargs)


def test_t_qlt_11k_a_zero_fraction_is_the_rule_of_w6_as_written():
    t, kp, score = clean(40)
    r = run_quality_arrays(kp, score, t, params=QualityParams(hampel_floor_fraction=0.0))
    assert r.params.hampel.scale_floor_px == 0.0 and r.report.params.hampel.scale_floor_px == 0.0


def test_t_qlt_11k_quality_params_is_a_value_with_the_defaults_of_the_plan():
    d = QualityParams()
    assert d.hampel_floor_fraction == 0.01 and d.mask == MaskParams() and d.filter == ButterworthParams()
    assert d.swap == SwapParams() and d.hampel == HampelParams() and d.gaps == GapParams()
    assert d.resample == ResampleParams() and d == QualityParams()


def test_t_qlt_11h_the_parameters_object_must_be_a_quality_params():
    t, kp, score = clean(5)
    with pytest.raises(QualityError, match="params"):
        run_quality_arrays(kp, score, t, params=HampelParams())  # type: ignore[arg-type]


def test_t_qlt_11k_the_filter_warning_is_given_exactly_when_the_cutoff_is_not_below_the_nyquist_frequency():
    t = np.arange(40) * 0.5  # 2 Hz exactly: the Nyquist frequency is 1 Hz
    kp, score = clean(40)[1:]
    at = run_quality_arrays(kp, score, t, params=QualityParams(filter=ButterworthParams(cutoff_hz=1.0)))
    assert "filter_skipped_above_nyquist" in at.report.warnings and at.report.intervals[0].filtered == 0
    below = run_quality_arrays(kp, score, t, params=QualityParams(filter=ButterworthParams(cutoff_hz=0.9)))
    assert "filter_skipped_above_nyquist" not in below.report.warnings and below.report.intervals[0].filtered > 0


def test_t_qlt_11h_the_event_rows_block_a_gap_too_not_only_the_suspect_rows():
    seq = make_sequence("SYN-08", seed=3, noise_px=0.0, swap_ranges=((40, 41),))  # events at rows 40 and 41, suspect 40
    score = np.array(seq.score, copy=True)
    joint = IDX["RShoulder"]
    score[42:44, joint] = 0.1  # a hole whose anchor before it is row 41: an event row, not a suspect row
    r = run_quality_arrays(seq.kp, score, seq.t_sec)
    assert r.swap.blocked[41, joint] and not r.swap.suspect[41, joint]
    table = r.gaps.gaps
    hole = np.flatnonzero((table.joint == joint) & (table.start == 42))
    assert len(hole) == 1 and table.outcome[hole[0]] == BLOCKED
    assert not r.gaps.interpolated[42:44, joint].any()


def test_t_qlt_11h_filtered_on_source_gives_no_value_to_a_row_that_had_none_even_between_two_grid_values():
    # 40 rows at 1/30 s, a burst of 24 rows at 1/150 s (finer than the grid), 40 rows at 1/30 s; the median step is
    # 1/30 s, so the grid is coarser than the rows in the burst. Row 46 is not the target's (never bridged) and lies
    # between two grid times that are both copies of rows with values: a mix of them would invent a value for it.
    t = np.concatenate([np.arange(40) / 30.0, 39 / 30.0 + np.arange(1, 25) / 150.0])
    t = np.concatenate([t, t[-1] + np.arange(1, 41) / 30.0])
    n = len(t)
    kp, score = clean(n)[1:]
    tracked = np.ones(n, dtype=bool)
    tracked[46] = False
    r = run_quality_arrays(kp, score, t, tracked=tracked)
    assert r.grid.gridmap.resampled and r.grid.gridmap.step_s == pytest.approx(1 / 30)
    on_source = r.filtered_on_source()
    assert np.isnan(on_source[46]).all()  # no value at the source
    assert np.isfinite(on_source[45]).all() and np.isfinite(on_source[47]).all()


def test_t_qlt_11h_an_invalid_interval_is_refused_before_any_stage_runs():
    t, kp, score = clean(10)
    with pytest.raises(QualityError, match="interval name"):  # the keypoints are wrong too: the interval comes first
        run_quality_arrays(kp.astype(np.int32), score, t, intervals={"a b": (0.0, 1.0)})


def test_t_qlt_11h_the_resample_swap_and_hampel_parameters_reach_their_stage():
    first = np.arange(20) / FPS30
    t = np.concatenate([first, first[-1] + 0.4 + np.arange(20) / FPS30])  # a pause of 0.4 s
    n = len(t)
    kp, score = clean(n)[1:]
    stalled = run_quality_arrays(kp, score, t).report.intervals[0]
    assert stalled.missing_by_reason.no_frame == 11 * NUM_JOINTS
    tolerant = QualityParams(resample=ResampleParams(max_step_s=0.5))
    bridged = run_quality_arrays(kp, score, t, params=tolerant).report.intervals[0]
    assert bridged.missing == 0 and bridged.mixed_rows == 11
    coarse = QualityParams(resample=ResampleParams(grid_hz=15.0))
    assert run_quality_arrays(kp, score, t, params=coarse).report.timeline.step_s == pytest.approx(1 / 15)
    t2, kp2, score2 = clean(40)
    for left, right in LR_PAIRS:
        kp2[10:12, [left, right]] = kp2[10:12, [right, left]]
    assert run_quality_arrays(kp2, score2, t2).report.warnings  # 100 px = 0.67 torso: a swap
    blind = QualityParams(swap=SwapParams(min_jump=0.9))
    assert run_quality_arrays(kp2, score2, t2, params=blind).report.warnings == ()
    t3, kp3, score3 = clean(40)
    kp3[20, 0, 1] += 80.0  # a spike of 80 px at a floor of 1.5 px
    assert run_quality_arrays(kp3, score3, t3).report.intervals[0].unobserved_by_reason.outlier == 1
    deaf = QualityParams(hampel=HampelParams(n_sigma=100.0))
    assert run_quality_arrays(kp3, score3, t3, params=deaf).report.intervals[0].unobserved_by_reason.outlier == 0
