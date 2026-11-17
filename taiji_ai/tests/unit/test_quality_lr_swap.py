"""P4.06: the left/right swap flag: a pair whose two labels jump onto each other's place (T-QLT-10).

Layers are built by hand: a still person (shoulders and hips fix the torso at 200 px) in which the two joints of one
pair change places at the rows of ``flips``; every other joint is still, so only that pair can make an event. A flip of
the pair is a *crossed jump*: both labels move by their separation and land on the other's previous place. A swap is two
flips (in and out); the flag only warns, nothing is corrected."""

from __future__ import annotations

import numpy as np
import pytest

from helpers.synth import make_sequence
from taiji_ai.pose.skeleton import IDX, LR_PAIRS, NUM_JOINTS
from taiji_ai.quality import QualityError
from taiji_ai.quality.lr_swap import (
    ENTER,
    EVENT_OUTCOME_NAMES,
    EXIT,
    UNPAIRED,
    SwapParams,
    detect_lr_swaps,
)
from taiji_ai.quality.mask import LOW_CONF, OK, apply_mask

FPS = 30.0
TORSO = 200.0
ANKLES = (IDX["LAnkle"], IDX["RAnkle"])
WRISTS = (IDX["LWrist"], IDX["RWrist"])
PAIR_INDEX = {pair: i for i, pair in enumerate(LR_PAIRS)}
A0 = (300.0, 500.0)


# --- builders ---------------------------------------------------------------------------------------------------------
def still_person(n: int):
    """Shoulders (y = 100) and hips (y = 300) make a torso of 200 px; every other joint sits on its own spot."""
    kp = np.zeros((n, NUM_JOINTS, 2))
    for j in range(NUM_JOINTS):
        kp[:, j] = (50.0 + 12.0 * j, 700.0 + 3.0 * j)
    kp[:, IDX["LShoulder"]] = (200.0, 100.0)
    kp[:, IDX["RShoulder"]] = (260.0, 100.0)
    kp[:, IDX["LHip"]] = (210.0, 300.0)
    kp[:, IDX["RHip"]] = (250.0, 300.0)
    return kp, np.zeros((n, NUM_JOINTS), np.uint8), np.arange(n) / FPS


def flipped(n: int, flips=(), pair=ANKLES, sep: float = 100.0, t=None):
    """The pair stands 100 px apart (0.5 torso) and changes places at every row of ``flips`` (swapped between two)."""
    kp, reason, clock = still_person(n)
    a, b = pair
    rows = np.arange(n)
    swapped = np.searchsorted(np.asarray(flips, dtype=int), rows, side="right") % 2 == 1
    left = np.where(swapped[:, None], (A0[0] + sep, A0[1]), A0)
    right = np.where(swapped[:, None], A0, (A0[0] + sep, A0[1]))
    kp[:, a], kp[:, b] = left, right
    return kp, reason, clock if t is None else t


def detect(kp, reason, t, **kw):
    params = kw.pop("params", None)
    return detect_lr_swaps(kp, reason, t, params, **kw)


def hide(kp, reason, row: int, joint: int) -> None:
    kp[row, joint] = np.nan
    reason[row, joint] = LOW_CONF


def rows_of(mask: np.ndarray, joint: int) -> list[int]:
    return np.flatnonzero(mask[:, joint]).tolist()


def table_rows(table) -> list[tuple[int, int, float, int]]:
    return list(zip(table.pair.tolist(), table.row.tolist(), table.t_s.tolist(), table.outcome.tolist(), strict=True))


# --- the constants ----------------------------------------------------------------------------------------------------
def test_t_qlt_10_the_defaults_are_the_proposals_and_the_outcomes_are_named():
    p = SwapParams()
    assert (p.min_jump, p.max_cross_ratio, p.max_dt_s, p.max_swap_s, p.pairs) == (0.2, 0.5, 0.25, 0.5, LR_PAIRS)
    assert EVENT_OUTCOME_NAMES == ("enter", "exit", "unpaired") and (ENTER, EXIT, UNPAIRED) == (0, 1, 2)


# --- T-QLT-10a: SYN-08 ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("noise", [0.0, 1.0])
def test_t_qlt_10a_syn_08_the_suspect_rows_are_exactly_the_swap_mask_and_the_jumps_are_at_the_four_rows(noise: float):
    seq = make_sequence("SYN-08", seed=3, noise_px=noise)
    mask = apply_mask(seq.kp, seq.score)
    r = detect_lr_swaps(mask.keypoints, mask.reason, seq.t_sec)
    swapped = np.asarray(seq.truth["lr_swap_mask"])
    assert np.array_equal(r.frame_suspect, swapped)  # rows 20 to 22 and 50 to 52
    assert np.flatnonzero(r.events.any(axis=1)).tolist() == [20, 23, 50, 53]
    kp_true = np.asarray(seq.kp_true, dtype=np.float64)
    torso = float(
        np.median(np.linalg.norm((kp_true[:, 5] + kp_true[:, 6]) / 2 - (kp_true[:, 11] + kp_true[:, 12]) / 2, axis=-1))
    )
    for p, (a, b) in enumerate(LR_PAIRS):
        separation = float(np.linalg.norm(kp_true[:, a] - kp_true[:, b], axis=-1).mean()) / torso
        if separation >= 0.25:  # far enough apart: flagged on exactly the swapped rows, both joints
            for joint in (a, b):
                assert np.array_equal(r.suspect[:, joint], swapped), (p, joint)
            assert np.flatnonzero(r.events[:, p]).tolist() == [20, 23, 50, 53]
        elif separation <= 0.15:  # closer than min_jump: a swap that nothing can see, and nothing is flagged
            assert not r.suspect[:, [a, b]].any() and not r.events[:, p].any(), p
    assert not r.suspect[:, [IDX["Nose"], IDX["Head"], IDX["Neck"], IDX["Hip"]]].any()  # joints that are in no pair
    assert r.torso_px == pytest.approx(torso, rel=0.02)


# --- T-QLT-10b: no false alarms ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["SYN-05", "SYN-06", "SYN-07"])
@pytest.mark.parametrize("noise", [0.0, 1.0])
def test_t_qlt_10b_a_clip_without_a_swap_has_no_event(name: str, noise: float):
    seq = make_sequence(name, seed=5, noise_px=noise)
    mask = apply_mask(seq.kp, seq.score)
    r = detect_lr_swaps(mask.keypoints, mask.reason, seq.t_sec)
    assert not r.events.any() and not r.suspect.any() and len(r.table) == 0
    assert np.isfinite(r.torso_px)


def test_t_qlt_10b_two_limbs_that_cross_smoothly_are_not_a_swap_however_fast():
    kp, reason, t = still_person(60)
    a, b = ANKLES
    x = np.arange(60) * 10.0  # 10 px a row (0.05 torso): far under the jump of 40 px
    kp[:, a] = np.stack([100.0 + x, np.full(60, 500.0)], axis=1)
    kp[:, b] = np.stack([700.0 - x, np.full(60, 500.0)], axis=1)  # they meet at row 30
    assert not detect(kp, reason, t).events.any()
    fast = np.arange(60) * 30.0  # 30 px a row (0.15 torso): the labels pass each other, still no jump of 40 px
    kp[:, a] = np.stack([100.0 + fast, np.full(60, 500.0)], axis=1)
    kp[:, b] = np.stack([1900.0 - fast, np.full(60, 500.0)], axis=1)
    assert not detect(kp, reason, t).events.any()


def test_t_qlt_10b_a_label_that_jumps_alone_a_limb_that_moves_fast_alone_and_a_jump_elsewhere_are_not_swaps():
    kp, reason, t = flipped(40)
    a, b = ANKLES
    alone = kp.copy()
    alone[10:, a] = (A0[0], A0[1] + 150.0)  # one label jumps away and stays: a flicker, not a swap
    assert not detect(alone, reason, t).events.any()
    fast = kp.copy()
    fast[10:, a] = (A0[0] + 60.0, A0[1])  # 60 px, over the limit, but the other label does not move
    assert not detect(fast, reason, t).events.any()
    elsewhere = kp.copy()
    elsewhere[10:, a] = (A0[0], A0[1] + 100.0)  # both jump 100 px in the same direction: not onto each other's place
    elsewhere[10:, b] = (A0[0] + 100.0, A0[1] + 100.0)
    assert not detect(elsewhere, reason, t).events.any()


# --- T-QLT-10c: the boundaries ----------------------------------------------------------------------------------------
def test_t_qlt_10c_a_jump_of_exactly_min_jump_is_an_event_and_one_hair_less_is_not():
    for sep, expected in ((40.0, True), (39.99, False), (80.0, True)):
        kp, reason, t = flipped(30, flips=(10,), sep=sep)
        r = detect(kp, reason, t)
        assert bool(r.events[:, PAIR_INDEX[ANKLES]].any()) is expected, sep
    kp, reason, t = flipped(30, flips=(10,), sep=30.0)
    assert (
        not detect(kp, reason, t).events.any() and detect(kp, reason, t, params=SwapParams(min_jump=0.14)).events.any()
    )


def crossing_past(c: float):
    """Row 9: a at (300, 500), b at (400, 500). Row 10: a lands c px past b's old place, b c px past a's old place."""
    kp, reason, t = still_person(20)
    a, b = ANKLES
    kp[:, a] = A0
    kp[:, b] = (400.0, 500.0)
    kp[10:, a] = (400.0 + c, 500.0)
    kp[10:, b] = (300.0 - c, 500.0)
    return kp, reason, t


def test_t_qlt_10c_a_landing_at_exactly_max_cross_ratio_of_the_move_counts_and_a_hair_more_does_not():
    assert detect(*crossing_past(100.0)).events[10, PAIR_INDEX[ANKLES]]  # cross 100, stay 200: 0.5 exactly
    assert not detect(*crossing_past(101.0)).events.any()  # 101 / 201 = 0.5025
    assert detect(*crossing_past(101.0), params=SwapParams(max_cross_ratio=0.6)).events[10, PAIR_INDEX[ANKLES]]
    assert not detect(*crossing_past(100.0), params=SwapParams(max_cross_ratio=0.49)).events.any()


def test_t_qlt_10c_the_two_rows_may_be_at_most_max_dt_s_apart():
    for step, expected in ((0.25, True), (0.25 + 1e-7, False)):
        kp, reason, t = flipped(30, flips=(10,))
        t = t.copy()
        t[10:] += step - 1.0 / FPS  # the interval between rows 9 and 10
        assert bool(detect(kp, reason, t).events.any()) is expected, step
    kp, reason, t = flipped(30, flips=(10,))
    t = t.copy()
    t[10:] += 0.5 - 1.0 / FPS
    assert not detect(kp, reason, t).events.any()
    assert detect(kp, reason, t, params=SwapParams(max_dt_s=0.6)).events.any()


@pytest.mark.parametrize(("row", "joint"), [(9, 15), (10, 15), (9, 16), (10, 16)])
def test_t_qlt_10c_a_cell_that_is_not_observed_makes_no_event(row: int, joint: int):
    kp, reason, t = flipped(30, flips=(10,))
    assert detect(kp, reason, t).events.any()
    hide(kp, reason, row, joint)
    assert not detect(kp, reason, t).events.any()


def test_t_qlt_10c_a_layer_without_a_torso_has_no_event_and_the_scale_can_be_given():
    kp, reason, t = flipped(30, flips=(10,))
    for row in range(30):
        hide(kp, reason, row, IDX["LShoulder"])
    r = detect(kp, reason, t)
    assert np.isnan(r.torso_px) and not r.events.any() and len(r.table) == 0
    given = detect(kp, reason, t, torso_px=200.0)
    assert given.torso_px == 200.0 and given.events.any()


# --- T-QLT-10d: the pairing -------------------------------------------------------------------------------------------
def test_t_qlt_10d_two_events_are_an_enter_and_an_exit_and_the_rows_between_are_suspect():
    kp, reason, t = flipped(40, flips=(10, 13))
    r = detect(kp, reason, t)
    a, b = ANKLES
    p = PAIR_INDEX[ANKLES]
    assert np.flatnonzero(r.events[:, p]).tolist() == [10, 13]
    assert rows_of(r.suspect, a) == rows_of(r.suspect, b) == [10, 11, 12]  # the exit row is right again: not suspect
    assert [row[1] for row in table_rows(r.table)] == [10, 13] and r.table.outcome.tolist() == [ENTER, EXIT]
    blocked = r.blocked
    assert rows_of(blocked, a) == rows_of(blocked, b) == [10, 11, 12, 13]  # but the jump row is not to be trusted
    assert blocked.sum() == 8 and r.frame_suspect.nonzero()[0].tolist() == [10, 11, 12]


def test_t_qlt_10d_exactly_max_swap_s_pairs_and_a_hair_more_does_not():
    kp, reason, t = flipped(60, flips=(10, 25))  # 15 rows at 30 fps: 0.5 s
    r = detect(kp, reason, t)
    assert r.table.outcome.tolist() == [ENTER, EXIT] and rows_of(r.suspect, ANKLES[0]) == list(range(10, 25))
    kp, reason, t = flipped(60, flips=(10, 26))  # 0.5333 s
    r = detect(kp, reason, t)
    assert r.table.outcome.tolist() == [UNPAIRED, UNPAIRED] and not r.suspect.any()
    assert detect(kp, reason, t, params=SwapParams(max_swap_s=0.6)).table.outcome.tolist() == [ENTER, EXIT]


def test_t_qlt_10d_the_limit_between_two_events_is_inclusive_to_a_nanosecond_whatever_the_float_rounding():
    for extra, expected in ((5e-10, [ENTER, EXIT]), (1e-8, [UNPAIRED, UNPAIRED])):
        kp, reason, t = flipped(60, flips=(10, 25))
        t = t.copy()
        t[25:] += (t[10] + 0.5 + extra) - t[25]  # the two jumps are 0.5 s plus a hair apart
        assert detect(kp, reason, t).table.outcome.tolist() == expected, extra


def test_t_qlt_10d_unpaired_events_mark_their_row_and_no_interval():
    kp, reason, t = flipped(60, flips=(20,))
    r = detect(kp, reason, t)
    a, b = ANKLES
    assert r.table.outcome.tolist() == [UNPAIRED] and not r.suspect.any()
    assert np.flatnonzero(r.events[:, PAIR_INDEX[ANKLES]]).tolist() == [20]
    assert rows_of(r.blocked, a) == rows_of(r.blocked, b) == [20]


def test_t_qlt_10d_three_and_four_events_are_taken_greedily_in_time_order():
    a = ANKLES[0]
    r = detect(*flipped(60, flips=(10, 13, 40)))
    assert r.table.outcome.tolist() == [ENTER, EXIT, UNPAIRED] and rows_of(r.suspect, a) == [10, 11, 12]
    r = detect(*flipped(60, flips=(10, 13, 16, 19)))
    assert r.table.outcome.tolist() == [ENTER, EXIT, ENTER, EXIT]
    assert rows_of(r.suspect, a) == [10, 11, 12, 16, 17, 18]  # two intervals, the rows between them are not suspect
    r = detect(*flipped(60, flips=(10, 13, 20)))  # 13 is an exit and is consumed: 20 is alone although it is near
    assert r.table.outcome.tolist() == [ENTER, EXIT, UNPAIRED]


def test_t_qlt_10d_pairs_and_joints_are_independent():
    kp, reason, t = flipped(60, flips=(10, 13), pair=ANKLES)
    kp2, _, _ = flipped(60, flips=(30, 34), pair=WRISTS)
    kp[:, list(WRISTS)] = kp2[:, list(WRISTS)]
    r = detect(kp, reason, t)
    assert rows_of(r.suspect, ANKLES[0]) == rows_of(r.suspect, ANKLES[1]) == [10, 11, 12]
    assert rows_of(r.suspect, WRISTS[0]) == rows_of(r.suspect, WRISTS[1]) == [30, 31, 32, 33]
    assert np.flatnonzero(r.events[:, PAIR_INDEX[WRISTS]]).tolist() == [30, 34]
    others = [j for j in range(NUM_JOINTS) if j not in ANKLES + WRISTS]
    assert not r.suspect[:, others].any() and not r.blocked[:, others].any()
    assert r.table.pair.tolist() == sorted(r.table.pair.tolist())  # ordered by pair, then row


# --- T-QLT-10e: scale and clock ---------------------------------------------------------------------------------------
def test_t_qlt_10e_the_events_do_not_depend_on_the_units_or_the_origin():
    kp, reason, t = flipped(60, flips=(10, 13, 30))
    base = detect(kp, reason, t)
    for other in (detect(kp * 3.0, reason, t), detect(kp + 1000.0, reason, t), detect(kp, reason, t + 123.456)):
        assert np.array_equal(other.events, base.events) and np.array_equal(other.suspect, base.suspect)
        assert other.table.outcome.tolist() == base.table.outcome.tolist()
    assert detect(kp * 3.0, reason, t).torso_px == pytest.approx(3.0 * base.torso_px)


@pytest.mark.parametrize("k", [0.5, 2.0])
def test_t_qlt_10e_a_clock_scaled_by_k_with_the_two_times_scaled_by_k_gives_the_same_flags(k: float):
    kp, reason, t = flipped(60, flips=(10, 13, 30))
    base = detect(kp, reason, t)
    params = SwapParams(max_dt_s=0.25 * k, max_swap_s=0.5 * k)
    other = detect(kp, reason, t * k, params=params)
    assert np.array_equal(other.events, base.events) and np.array_equal(other.suspect, base.suspect)


def test_t_qlt_10e_rows_of_a_variable_frame_rate_are_judged_by_seconds_and_the_scale_can_be_given():
    kp, reason, t = flipped(40, flips=(10, 13))
    slow = t.copy()
    slow[10:] += 0.3  # a pause of 0.33 s at the jump into the swap: the two rows are too far apart to compare
    r = detect(kp, reason, slow)
    assert np.flatnonzero(r.events[:, PAIR_INDEX[ANKLES]]).tolist() == [13] and r.table.outcome.tolist() == [UNPAIRED]
    kp, reason, t = flipped(40, flips=(10, 13), sep=30.0)  # 0.15 of the torso of 200 px
    assert not detect(kp, reason, t).events.any()
    assert detect(kp, reason, t, torso_px=100.0).events.any()  # 0.3 of a torso of 100 px


# --- T-QLT-10f: the result --------------------------------------------------------------------------------------------
def test_t_qlt_10f_inputs_are_not_changed_outputs_are_new_and_read_only_and_no_value_is_in_the_result():
    kp, reason, t = flipped(40, flips=(10, 13))
    kp = kp.astype(np.float32)
    before = (kp.copy(), reason.copy(), t.copy())
    r = detect(kp, reason, t)
    for given, kept in zip((kp, reason, t), before, strict=True):
        assert np.array_equal(given, kept)
    assert not hasattr(r, "keypoints") and not hasattr(r, "reason")  # a warning: no value, no reason is returned
    for arr in (
        r.events,
        r.suspect,
        r.blocked,
        r.frame_suspect,
        r.table.pair,
        r.table.row,
        r.table.t_s,
        r.table.jump,
        r.table.outcome,
    ):
        assert not any(np.shares_memory(arr, x) for x in (kp, reason, t))
    for arr in (
        r.events,
        r.suspect,
        r.blocked,
        r.frame_suspect,
        r.table.pair,
        r.table.row,
        r.table.t_s,
        r.table.jump,
        r.table.outcome,
    ):
        assert not arr.flags.writeable
    assert r.events.dtype == bool and r.suspect.dtype == bool and r.events.shape == (40, len(LR_PAIRS))
    assert (
        r.suspect.shape == (40, NUM_JOINTS) and r.blocked.shape == (40, NUM_JOINTS) and r.frame_suspect.shape == (40,)
    )
    assert r.table.pair.dtype == np.int16 and r.table.row.dtype == np.int32 and r.table.t_s.dtype == np.float64
    assert r.table.jump.dtype == np.float32 and r.table.outcome.dtype == np.uint8
    with pytest.raises(ValueError, match="read-only"):
        r.suspect[0, 0] = True


def test_t_qlt_10f_the_table_has_pair_row_time_jump_and_outcome_of_every_event_ordered_by_pair_then_row():
    kp, reason, t = flipped(80, flips=(10, 13, 50), pair=WRISTS)
    kp2, _, _ = flipped(80, flips=(20, 23), pair=ANKLES)
    kp[:, list(ANKLES)] = kp2[:, list(ANKLES)]
    r = detect(kp, reason, t)
    pairs = r.table.pair.tolist()
    assert pairs == sorted(pairs) and set(pairs) == {PAIR_INDEX[WRISTS], PAIR_INDEX[ANKLES]}
    wrists = [
        (int(row), int(o))
        for p, row, o in zip(r.table.pair, r.table.row, r.table.outcome, strict=True)
        if p == PAIR_INDEX[WRISTS]
    ]
    assert wrists == [(10, ENTER), (13, EXIT), (50, UNPAIRED)]
    assert np.allclose(r.table.t_s, t[r.table.row]) and np.allclose(r.table.jump, 0.5)  # 100 px of a torso of 200 px
    assert len(r.table) == 5


def test_t_qlt_10f_zero_one_and_two_rows():
    for n in (0, 1, 2):
        kp, reason, t = still_person(n)
        r = detect(kp, reason, t)
        assert r.events.shape == (n, len(LR_PAIRS)) and not r.events.any() and len(r.table) == 0
        assert r.suspect.shape == (n, NUM_JOINTS) and r.frame_suspect.shape == (n,)
    kp, reason, t = flipped(2, flips=(1,))
    assert detect(kp, reason, t).events[1, PAIR_INDEX[ANKLES]]  # the second row is the first that can be compared


# --- T-QLT-10g: bad input ---------------------------------------------------------------------------------------------
def good():
    return flipped(40, flips=(10, 13))


def with_half_value():
    kp, reason, t = good()
    reason[3, 4] = LOW_CONF  # a value with a reason that is not ok
    return kp, reason, t


def with_nan_and_ok():
    kp, reason, t = good()
    kp[3, 4] = np.nan
    return kp, reason, t


def with_equal_times():
    kp, reason, t = good()
    t = t.copy()
    t[5] = t[4]
    return kp, reason, t


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: (good()[0].astype(np.int32), *good()[1:]), "keypoints"),
        (lambda: (good()[0][:, :, 0], *good()[1:]), "keypoints"),
        (lambda: (good()[0], good()[1].astype(np.int64), good()[2]), "reason"),
        (lambda: (good()[0], good()[1][:-1], good()[2]), "reason"),
        (lambda: (*good()[:2], (good()[2] * 30).astype(np.int64)), "t_sec"),
        (lambda: (*good()[:2], good()[2][:-1]), "t_sec"),
        (with_equal_times, "strictly increasing"),
        (with_nan_and_ok, "NaN"),
        (with_half_value, "not ok"),
    ],
)
def test_t_qlt_10g_bad_arrays_are_refused_naming_the_argument(make, message: str):
    kp, reason, t = make()
    with pytest.raises(QualityError, match=message):
        detect_lr_swaps(kp, reason, t)


@pytest.mark.parametrize("bad", [0.0, -0.2, float("nan"), float("inf"), True, "0.2", None])
def test_t_qlt_10g_a_wrong_min_jump_is_refused(bad):
    with pytest.raises(QualityError, match="min_jump"):
        SwapParams(min_jump=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [0.0, -0.5, 1.5, float("nan"), True, "0.5", None])
def test_t_qlt_10g_a_wrong_cross_ratio_is_refused(bad):
    with pytest.raises(QualityError, match="max_cross_ratio"):
        SwapParams(max_cross_ratio=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [0.0, -0.25, float("nan"), float("inf"), True, "0.25", None])
def test_t_qlt_10g_a_wrong_time_limit_is_refused(bad):
    with pytest.raises(QualityError, match="max_dt_s"):
        SwapParams(max_dt_s=bad)  # type: ignore[arg-type]
    with pytest.raises(QualityError, match="max_swap_s"):
        SwapParams(max_swap_s=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad",
    [(), ((1, 1),), ((1, 2), (2, 3)), ((0, 26),), ((1, 2, 3),), "ab", ((True, 2),), ((1.5, 2),), ((-1, 2),), None, 5],
)
def test_t_qlt_10g_wrong_pairs_are_refused(bad):
    with pytest.raises(QualityError, match="pairs"):
        SwapParams(pairs=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [0.0, -200.0, float("nan"), float("inf"), True, "200"])
def test_t_qlt_10g_a_wrong_scale_is_refused(bad):
    kp, reason, t = good()
    with pytest.raises(QualityError, match="torso_px"):
        detect_lr_swaps(kp, reason, t, torso_px=bad)  # type: ignore[arg-type]


def test_t_qlt_10g_the_parameters_that_were_used_travel_with_the_result_and_other_pairs_are_allowed():
    kp, reason, t = good()
    params = SwapParams(min_jump=0.3, max_cross_ratio=1.0, max_dt_s=0.5, max_swap_s=1.0, pairs=((15, 16), (9, 10)))
    r = detect_lr_swaps(kp, reason, t, params)
    assert r.params == params and r.events.shape == (40, 2) and r.events[:, 0].any() and not r.events[:, 1].any()
    assert detect_lr_swaps(kp, reason, t).params == SwapParams()
    assert SwapParams(pairs=[[1, 2], [3, 4]]).pairs == ((1, 2), (3, 4))
    assert (
        SwapParams(min_jump=np.float32(0.25)).min_jump == 0.25 and SwapParams(max_cross_ratio=1).max_cross_ratio == 1.0
    )


# --- the differential test: the rules written the slow way ------------------------------------------------------------
def oracle(kp, reason, t, params: SwapParams, torso: float):
    n = len(t)
    pairs = params.pairs
    events = np.zeros((n, len(pairs)), bool)
    jump = np.full((n, len(pairs)), np.nan)
    observed = reason == OK
    for p, (a, b) in enumerate(pairs):
        for row in range(1, n):
            if not (observed[row, a] and observed[row - 1, a] and observed[row, b] and observed[row - 1, b]):
                continue
            if t[row] - t[row - 1] > params.max_dt_s + 1e-9:
                continue
            stay_a = float(np.hypot(*(kp[row, a].astype(float) - kp[row - 1, a])))
            stay_b = float(np.hypot(*(kp[row, b].astype(float) - kp[row - 1, b])))
            cross_a = float(np.hypot(*(kp[row, a].astype(float) - kp[row - 1, b])))
            cross_b = float(np.hypot(*(kp[row, b].astype(float) - kp[row - 1, a])))
            limit = params.min_jump * torso
            if (
                stay_a >= limit
                and stay_b >= limit
                and cross_a <= params.max_cross_ratio * stay_a
                and cross_b <= params.max_cross_ratio * stay_b
            ):
                events[row, p] = True
                jump[row, p] = min(stay_a, stay_b) / torso
    suspect = np.zeros((n, NUM_JOINTS), bool)
    table = []
    for p, (a, b) in enumerate(pairs):
        rows = np.flatnonzero(events[:, p])
        i = 0
        while i < len(rows):
            if i + 1 < len(rows) and t[rows[i + 1]] - t[rows[i]] <= params.max_swap_s + 1e-9:
                suspect[rows[i] : rows[i + 1], a] = True
                suspect[rows[i] : rows[i + 1], b] = True
                table.append((p, int(rows[i]), ENTER, jump[rows[i], p]))
                table.append((p, int(rows[i + 1]), EXIT, jump[rows[i + 1], p]))
                i += 2
            else:
                table.append((p, int(rows[i]), UNPAIRED, jump[rows[i], p]))
                i += 1
    return events, suspect, table


def random_case(seed: int):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(0, 70))
    fps = float(rng.uniform(10.0, 60.0))
    steps = rng.uniform(0.8, 1.2, n) / fps
    steps[rng.random(n) < 0.05] *= 10.0  # a pause
    t = np.cumsum(steps) + float(rng.uniform(0.0, 5.0))
    kp = np.cumsum(rng.normal(0.0, 3.0, (n, NUM_JOINTS, 2)), axis=0) + rng.uniform(100.0, 600.0, (1, NUM_JOINTS, 2))
    pair_choices = list(LR_PAIRS)
    for a, b in pair_choices:
        if rng.random() < 0.6 and n > 3:
            flips = np.sort(rng.choice(np.arange(1, n), size=int(rng.integers(1, min(6, n))), replace=False))
            swapped = np.searchsorted(flips, np.arange(n), side="right") % 2 == 1
            ka, kb = kp[:, a].copy(), kp[:, b].copy()
            kp[swapped, a], kp[swapped, b] = kb[swapped], ka[swapped]
    reason = np.zeros((n, NUM_JOINTS), np.uint8)
    holes = rng.random((n, NUM_JOINTS)) < 0.06
    reason[holes] = LOW_CONF
    kp[holes] = np.nan
    chosen = rng.choice(len(LR_PAIRS), size=int(rng.integers(1, len(LR_PAIRS) + 1)), replace=False)
    params = SwapParams(
        min_jump=float(rng.choice([0.05, 0.1, 0.2, 0.4])),
        max_cross_ratio=float(rng.choice([0.25, 0.5, 1.0])),
        max_dt_s=float(rng.choice([0.1, 0.25, 0.5])),
        max_swap_s=float(rng.choice([0.1, 0.3, 0.5, 1.0])),
        pairs=tuple(LR_PAIRS[int(i)] for i in sorted(chosen)),
    )
    return kp.astype(np.float32 if seed % 2 else np.float64), reason, t, params, float(rng.uniform(80.0, 300.0))


@pytest.mark.parametrize("seed", range(200))
def test_t_qlt_10_diff_the_module_equals_the_slow_rules(seed: int):
    kp, reason, t, params, torso = random_case(seed)
    r = detect_lr_swaps(kp, reason, t, params, torso_px=torso)
    events, suspect, table = oracle(kp, reason, t, params, torso)
    assert np.array_equal(r.events, events) and np.array_equal(r.suspect, suspect)
    assert [
        (int(p), int(row), int(o)) for p, row, o in zip(r.table.pair, r.table.row, r.table.outcome, strict=True)
    ] == [(p, row, o) for p, row, o, _ in table]
    assert np.allclose(r.table.jump, [j for *_, j in table], rtol=1e-5)
    assert np.allclose(r.table.t_s, t[r.table.row]) and r.params == params and r.torso_px == torso
    cells = suspect.copy()
    for p, (a, b) in enumerate(params.pairs):
        cells[:, a] |= events[:, p]
        cells[:, b] |= events[:, p]
    assert np.array_equal(r.blocked, cells) and np.array_equal(r.frame_suspect, suspect.any(axis=1))
    used = sorted({j for pair in params.pairs for j in pair})
    assert not r.suspect[:, [j for j in range(NUM_JOINTS) if j not in used]].any()  # only the joints of the pairs
    assert not r.events[:1].any()  # the first row has no row before it
