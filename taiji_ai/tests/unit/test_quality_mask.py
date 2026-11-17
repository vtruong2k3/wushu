"""P4.01: the mask layer: low-confidence keypoints become NaN, poor frames ``frame_invalid`` (T-QLT-01, T-QLT-02).

Arrays are built by hand: no video, no model. Joint ``j`` of frame ``t`` sits at ``(100 + t, 200 + j)`` pixels, so every
value that survives the mask can be checked against the input at the same place. The essential joints of W6 are
``ESSENTIAL`` of ``pose/skeleton.py`` (ten); five of them usable is still a valid frame, four is not.
"""

from __future__ import annotations

import numpy as np
import pytest

from taiji_ai.audit import signals as audit_signals
from taiji_ai.pose.skeleton import ESSENTIAL, NUM_JOINTS
from taiji_ai.quality import QualityError
from taiji_ai.quality.mask import (
    FRAME_INVALID,
    LOW_CONF,
    NON_FINITE,
    NOT_TRACKED,
    OK,
    OUTLIER,
    REASON_NAMES,
    TAU_KP,
    MaskParams,
    apply_mask,
)

OTHERS = tuple(j for j in range(NUM_JOINTS) if j not in ESSENTIAL)


def pose(frames: int = 1, score: float = 0.9, dtype=np.float32) -> tuple[np.ndarray, np.ndarray]:
    """Finite keypoints and one score for every joint of every frame."""
    kp = np.zeros((frames, NUM_JOINTS, 2), dtype)
    kp[..., 0] = 100.0 + np.arange(frames)[:, None]
    kp[..., 1] = 200.0 + np.arange(NUM_JOINTS)[None, :]
    return kp, np.full((frames, NUM_JOINTS), score, dtype)


def with_essential_usable(n: int, other: float = 0.9, low: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    """One frame: the first ``n`` essential joints score 0.9, the other essential ones ``low``; the rest ``other``."""
    kp, sc = pose(1, other)
    sc[0, list(ESSENTIAL)] = low
    sc[0, list(ESSENTIAL[:n])] = 0.9
    return kp, sc


# --- the constants of W6 ------------------------------------------------------------------------------------------
def test_t_qlt_01_the_defaults_are_the_values_of_w6():
    p = MaskParams()
    assert (p.tau_kp, p.essential, p.min_essential_fraction) == (0.3, ESSENTIAL, 0.5)
    assert len(ESSENTIAL) == 10 and TAU_KP == 0.3
    assert REASON_NAMES == ("ok", "low_conf", "non_finite", "not_tracked", "frame_invalid", "outlier")
    codes = (OK, LOW_CONF, NON_FINITE, NOT_TRACKED, FRAME_INVALID, OUTLIER)
    assert [REASON_NAMES[c] for c in codes] == list(REASON_NAMES) and OUTLIER == 5


def test_t_qlt_01_the_mask_never_emits_the_outlier_code_that_the_hampel_stage_adds():
    rng = np.random.default_rng(4)
    for _ in range(20):
        kp = rng.uniform(0, 1000, (30, NUM_JOINTS, 2)).astype(np.float32)
        sc = rng.uniform(-0.5, 1.5, (30, NUM_JOINTS)).astype(np.float32)
        kp[rng.random(kp.shape) < 0.05] = np.nan
        sc[rng.random(sc.shape) < 0.05] = np.inf
        out = apply_mask(kp, sc, rng.random(30) < 0.7)
        assert out.reason.max() <= FRAME_INVALID and not (out.reason == OUTLIER).any()


def test_t_qlt_01e_the_audit_evaluates_the_values_the_product_ships():
    assert audit_signals.TAU_KP == TAU_KP
    assert audit_signals.ESSENTIAL == MaskParams().essential


# --- T-QLT-01a: the score rule --------------------------------------------------------------------------------------
def test_t_qlt_01a_a_score_under_tau_is_nan_with_low_conf_and_everything_else_is_untouched():
    kp, sc = pose(1)
    sc[0, 0], sc[0, 1], sc[0, 2] = 0.29, 0.31, 0.95
    out = apply_mask(kp, sc)
    assert out.reason[0, 0] == LOW_CONF and np.isnan(out.keypoints[0, 0]).all()
    for j in (1, 2, 3, 10):
        assert out.reason[0, j] == OK
        assert np.array_equal(out.keypoints[0, j], kp[0, j])  # the exact input values
    assert np.array_equal(out.scores, sc)  # scores are carried as they are


def test_t_qlt_01a_a_score_equal_to_tau_is_kept():
    kp, sc = pose(1, 0.9)
    sc[0, 4] = 0.5
    out = apply_mask(kp, sc, params=MaskParams(tau_kp=0.5))
    assert out.reason[0, 4] == OK and np.array_equal(out.keypoints[0, 4], kp[0, 4])
    sc[0, 4] = np.nextafter(np.float32(0.5), np.float32(0.0))  # the float just under
    assert apply_mask(kp, sc, params=MaskParams(tau_kp=0.5)).reason[0, 4] == LOW_CONF


def test_t_qlt_01a_the_default_tau_keeps_a_stored_score_of_0_3():
    kp, sc = pose(1, 0.9, np.float32)
    sc[0, 7] = np.float32(0.3)  # a float32 score as the model files hold it
    assert apply_mask(kp, sc).reason[0, 7] == OK
    kp64, sc64 = pose(1, 0.9, np.float64)
    sc64[0, 7] = 0.3
    assert apply_mask(kp64, sc64).reason[0, 7] == OK


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
@pytest.mark.parametrize("tau", [0.1, 0.2, 0.3, 0.45, 0.6, 0.7, 0.85, 0.9, 0.95])
def test_t_qlt_01a_a_stored_score_equal_to_tau_is_kept_whatever_tau_is(tau: float, dtype):
    # float32(0.7) is a little under 0.7 as a double: the comparison must be made in the precision of the scores
    kp, sc = pose(1, 0.99, dtype)
    sc[0, 4] = dtype(tau)
    out = apply_mask(kp, sc, params=MaskParams(tau_kp=tau))
    assert out.reason[0, 4] == OK and np.array_equal(out.keypoints[0, 4], kp[0, 4])


def test_t_qlt_01a_scores_are_not_range_checked_or_clipped():
    kp, sc = pose(1)
    sc[0, 0], sc[0, 1] = -0.5, 1.5
    out = apply_mask(kp, sc)
    assert out.reason[0, 0] == LOW_CONF  # a negative score is under tau
    assert out.reason[0, 1] == OK and out.scores[0, 1] == np.float32(1.5)  # above 1 is kept as it is


def test_t_qlt_01a_tau_zero_keeps_every_finite_score_and_tau_one_only_a_score_of_one():
    kp, sc = pose(1, 0.0)
    sc[0, 0] = -1e-6
    zero = apply_mask(kp, sc, params=MaskParams(tau_kp=0.0, essential=(1,), min_essential_fraction=1.0))
    assert zero.reason[0, 0] == LOW_CONF and (zero.reason[0, 1:] == OK).all()
    kp, sc = pose(1, 0.999)
    sc[0, 1] = 1.0
    one = apply_mask(kp, sc, params=MaskParams(tau_kp=1.0, essential=(1,), min_essential_fraction=1.0))
    assert one.reason[0, 1] == OK and (np.delete(one.reason[0], 1) == LOW_CONF).all()


# --- T-QLT-01b: the other reasons, the order of reasons, and the layers --------------------------------------------
@pytest.mark.parametrize(
    "bad",
    ["nan_x", "nan_y", "inf_x", "nan_score", "inf_score", "nan_both_with_score_zero"],
)
def test_t_qlt_01b_a_value_that_is_not_finite_is_non_finite_and_not_low_conf(bad: str):
    kp, sc = pose(1)
    if bad == "nan_x":
        kp[0, 3, 0] = np.nan
    elif bad == "nan_y":
        kp[0, 3, 1] = np.nan
    elif bad == "inf_x":
        kp[0, 3, 0] = np.inf
    elif bad == "nan_score":
        sc[0, 3] = np.nan
    elif bad == "inf_score":
        sc[0, 3] = -np.inf
    else:
        kp[0, 3, :] = np.nan  # what SYN-06 gap_mode="nan" makes: NaN coordinates and a score of 0
        sc[0, 3] = 0.0
    out = apply_mask(kp, sc)
    assert out.reason[0, 3] == NON_FINITE and np.isnan(out.keypoints[0, 3]).all()
    assert (np.delete(out.reason[0], 3) == OK).all()


def test_t_qlt_01b_a_frame_that_is_not_the_targets_is_not_tracked_even_when_its_numbers_look_good():
    kp, sc = pose(3)
    sc[1, 2] = 0.01  # also a low score: the frame reason comes first
    out = apply_mask(kp, sc, np.array([True, False, True]))
    assert (out.reason[1] == NOT_TRACKED).all() and np.isnan(out.keypoints[1]).all()
    assert (out.reason[[0, 2]] == OK).all() and np.array_equal(out.keypoints[[0, 2]], kp[[0, 2]])
    assert not out.frame_invalid[1] and out.n_essential_valid[1] == 0  # absent, not invalid
    assert out.tracked.tolist() == [True, False, True] and out.usable.tolist() == [True, False, True]


def test_t_qlt_01b_the_first_reason_that_applies_wins():
    kp, sc = pose(2)
    kp[1, 0, :] = np.nan
    sc[1, 0] = 0.0  # not finite and low: non_finite
    sc[1, 1] = 0.0  # low only
    out = apply_mask(kp, sc, np.array([True, True]))
    assert out.reason[1, 0] == NON_FINITE and out.reason[1, 1] == LOW_CONF


def test_t_qlt_01b_the_inputs_are_not_changed_and_the_outputs_are_new_read_only_arrays():
    kp, sc = pose(4)
    sc[2, :] = 0.0  # a frame that the mask blanks completely
    tracked = np.array([True, True, True, False])
    kp_before, sc_before, tr_before = kp.copy(), sc.copy(), tracked.copy()
    for a in (kp, sc, tracked):
        a.setflags(write=False)  # a mask that wrote into its input would raise
    out = apply_mask(kp, sc, tracked)
    assert np.array_equal(kp, kp_before) and np.array_equal(sc, sc_before) and np.array_equal(tracked, tr_before)
    for name in ("keypoints", "scores", "reason", "tracked", "n_essential_valid", "frame_invalid"):
        array = getattr(out, name)
        assert not array.flags.writeable, name
    assert not np.shares_memory(out.keypoints, kp) and not np.shares_memory(out.scores, sc)
    assert not np.shares_memory(out.tracked, tracked)


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_t_qlt_01b_the_dtype_of_the_input_is_kept(dtype):
    kp, sc = pose(2, dtype=dtype)
    out = apply_mask(kp, sc)
    assert out.keypoints.dtype == dtype and out.scores.dtype == dtype
    assert out.reason.dtype == np.uint8 and out.frame_invalid.dtype == bool and out.tracked.dtype == bool


@pytest.mark.parametrize("seed", range(12))
def test_t_qlt_01_invariants_on_random_input(seed: int):
    """No value is made, nothing is NaN without a reason, nothing is kept that a rule excludes (AC3, AC4)."""
    rng = np.random.default_rng(seed)
    t = 300
    kp = rng.uniform(0, 1000, (t, NUM_JOINTS, 2)).astype(np.float32)
    sc = rng.uniform(-0.2, 1.2, (t, NUM_JOINTS)).astype(np.float32)
    kp[rng.random((t, NUM_JOINTS)) < 0.05] = np.nan
    kp[rng.random((t, NUM_JOINTS)) < 0.01, 0] = np.inf
    sc[rng.random((t, NUM_JOINTS)) < 0.05] = np.nan
    sc[rng.random(t) < 0.15] = rng.uniform(0.0, 0.4)  # frames with a poor score everywhere
    tracked = rng.random(t) < 0.8
    out = apply_mask(kp, sc, tracked)

    kept = out.reason == OK
    assert np.array_equal(np.isfinite(out.keypoints).all(-1), kept)  # NaN exactly where there is a reason
    assert np.array_equal(out.keypoints[kept], kp[kept])  # a kept value is the input value
    assert np.isfinite(sc[kept]).all() and (sc[kept] >= TAU_KP).all()  # a kept joint has a good score
    assert (out.reason[~tracked] == NOT_TRACKED).all() and (out.reason[tracked] != NOT_TRACKED).all()
    assert (out.reason[out.frame_invalid] != OK).all()  # an invalid frame keeps no joint
    assert not (out.frame_invalid & ~tracked).any()
    ess_ok = np.isfinite(kp[:, list(ESSENTIAL)]).all(-1) & np.isfinite(sc[:, list(ESSENTIAL)])
    ess_ok &= sc[:, list(ESSENTIAL)] >= TAU_KP
    expected_n = np.where(tracked, ess_ok.sum(-1), 0)
    assert np.array_equal(out.n_essential_valid, expected_n)
    assert np.array_equal(out.frame_invalid, tracked & (expected_n < 5))  # 5 of 10 is still valid
    assert np.array_equal(out.usable, tracked & (expected_n >= 5))


# --- T-QLT-01c: parameters, shapes, empty input --------------------------------------------------------------------
@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"tau_kp": float("nan")}, "tau_kp"),
        ({"tau_kp": -0.1}, "tau_kp"),
        ({"tau_kp": 1.1}, "tau_kp"),
        ({"tau_kp": float("inf")}, "tau_kp"),
        ({"essential": ()}, "essential"),
        ({"essential": (5, 5)}, "essential"),
        ({"essential": (26,)}, "essential"),
        ({"essential": (-1,)}, "essential"),
        ({"essential": (1.5,)}, "essential"),
        ({"essential": (True,)}, "essential"),
        ({"min_essential_fraction": 0.0}, "min_essential_fraction"),
        ({"min_essential_fraction": 1.1}, "min_essential_fraction"),
        ({"min_essential_fraction": float("nan")}, "min_essential_fraction"),
    ],
)
def test_t_qlt_01c_wrong_parameters_are_refused_naming_the_field(kwargs: dict, field: str):
    with pytest.raises(QualityError, match=field):
        MaskParams(**kwargs)


def test_t_qlt_01c_the_boundaries_of_the_parameters_are_allowed():
    MaskParams(tau_kp=0.0)
    MaskParams(tau_kp=1.0)
    MaskParams(min_essential_fraction=1.0)
    MaskParams(essential=(0,), min_essential_fraction=0.01)
    MaskParams(essential=tuple(range(NUM_JOINTS)))
    numpy_ints = MaskParams(essential=(np.int64(5), np.int64(6)))  # numpy integers are integers, stored as plain ints
    assert numpy_ints.essential == (5, 6) and all(type(j) is int for j in numpy_ints.essential)
    assert MaskParams(essential=[5, 6]).essential == (5, 6)  # a list becomes a tuple: the parameters stay hashable
    assert MaskParams(essential=[5, 6]) == MaskParams(essential=(5, 6)) and hash(MaskParams()) == hash(MaskParams())


@pytest.mark.parametrize(
    ("change", "name"),
    [
        ("kp_joints", "keypoints"),
        ("kp_last", "keypoints"),
        ("kp_2d", "keypoints"),
        ("sc_joints", "scores"),
        ("sc_frames", "scores"),
        ("kp_int", "keypoints"),
        ("sc_int", "scores"),
        ("tr_int", "tracked"),
        ("tr_len", "tracked"),
        ("tr_2d", "tracked"),
    ],
)
def test_t_qlt_01c_wrong_shapes_and_types_are_refused_naming_the_array(change: str, name: str):
    kp, sc = pose(3)
    tracked: np.ndarray = np.ones(3, bool)
    if change == "kp_joints":
        kp = kp[:, :25]
    elif change == "kp_last":
        kp = np.zeros((3, NUM_JOINTS, 3), np.float32)
    elif change == "kp_2d":
        kp = kp[:, :, 0]
    elif change == "sc_joints":
        sc = sc[:, :25]
    elif change == "sc_frames":
        sc = sc[:2]
    elif change == "kp_int":
        kp = kp.astype(np.int32)
    elif change == "sc_int":
        sc = (sc * 100).astype(np.int32)
    elif change == "tr_int":
        tracked = np.ones(3, np.int8)
    elif change == "tr_len":
        tracked = np.ones(4, bool)
    elif change == "tr_2d":
        tracked = np.ones((3, 1), bool)
    with pytest.raises(QualityError, match=name):
        apply_mask(kp, sc, tracked)


def test_t_qlt_01c_no_frames_gives_empty_arrays_and_no_crash():
    out = apply_mask(np.empty((0, NUM_JOINTS, 2), np.float32), np.empty((0, NUM_JOINTS), np.float32))
    assert out.keypoints.shape == (0, NUM_JOINTS, 2) and out.reason.shape == (0, NUM_JOINTS)
    assert out.tracked.shape == out.frame_invalid.shape == out.n_essential_valid.shape == out.usable.shape == (0,)


def test_t_qlt_01c_one_frame_and_tracked_none_means_every_frame_is_the_targets():
    kp, sc = pose(1)
    out = apply_mask(kp, sc)
    assert out.tracked.tolist() == [True] and (out.reason == OK).all() and out.usable.tolist() == [True]
    assert out.params == MaskParams()
    custom = MaskParams(tau_kp=0.95)
    strict = apply_mask(kp, sc, params=custom)
    assert strict.params is custom  # the parameters used travel with the result
    assert (strict.reason == LOW_CONF).all() and strict.frame_invalid[0]  # every score is under 0.95


# --- T-QLT-02a: the frame rule ------------------------------------------------------------------------------------
@pytest.mark.parametrize("usable", range(11))
def test_t_qlt_02a_a_frame_is_invalid_when_fewer_than_half_of_the_essential_joints_are_usable(usable: int):
    kp, sc = with_essential_usable(usable)
    out = apply_mask(kp, sc)
    assert out.n_essential_valid[0] == usable
    assert bool(out.frame_invalid[0]) is (usable < 5)  # 5 of 10 is valid, 4 of 10 is not
    assert bool(out.usable[0]) is (usable >= 5)


def test_t_qlt_02a_an_invalid_frame_is_nan_in_all_26_joints_and_each_joint_keeps_its_most_specific_reason():
    kp, sc = with_essential_usable(4)  # six essential joints low_conf, the other 16 joints perfect
    out = apply_mask(kp, sc)
    assert np.isnan(out.keypoints).all()
    assert (out.reason[0, list(ESSENTIAL[4:])] == LOW_CONF).all()  # excluded by the score rule first
    assert (out.reason[0, list(ESSENTIAL[:4])] == FRAME_INVALID).all()  # usable joints of an invalid frame
    assert (out.reason[0, list(OTHERS)] == FRAME_INVALID).all()


def test_t_qlt_02a_a_non_finite_joint_of_an_invalid_frame_keeps_non_finite():
    kp, sc = with_essential_usable(3)
    kp[0, ESSENTIAL[9], :] = np.nan
    out = apply_mask(kp, sc)
    assert out.reason[0, ESSENTIAL[9]] == NON_FINITE and out.frame_invalid[0]


def test_t_qlt_02a_only_the_essential_joints_decide():
    kp, sc = with_essential_usable(10, other=0.0)  # all ten essential perfect, the other 16 joints with score 0
    out = apply_mask(kp, sc)
    assert not out.frame_invalid[0] and (out.reason[0, list(OTHERS)] == LOW_CONF).all()
    assert np.array_equal(out.keypoints[0, list(ESSENTIAL)], kp[0, list(ESSENTIAL)])  # the essential joints are intact
    assert np.isnan(out.keypoints[0, list(OTHERS)]).all()
    kp, sc = with_essential_usable(4, other=1.0)  # 16 perfect other joints do not save a frame with four essential
    assert apply_mask(kp, sc).frame_invalid[0]


def test_t_qlt_02a_a_tracked_frame_with_nothing_finite_is_invalid():
    kp, sc = pose(1)
    kp[:] = np.nan
    out = apply_mask(kp, sc, np.array([True]))
    assert out.frame_invalid[0] and out.n_essential_valid[0] == 0 and (out.reason == NON_FINITE).all()


def test_t_qlt_02a_each_frame_is_decided_alone():
    kp, sc = pose(5)
    sc[1, list(ESSENTIAL)] = 0.0  # frame 1 loses every essential joint
    out = apply_mask(kp, sc)
    assert out.frame_invalid.tolist() == [False, True, False, False, False]
    assert (out.reason[[0, 2, 3, 4]] == OK).all() and np.array_equal(out.keypoints[[0, 2]], kp[[0, 2]])


def test_t_qlt_02a_a_custom_list_and_fraction_are_used():
    kp, sc = pose(1, 0.9)
    sc[0, [0, 1]] = 0.1  # of the four joints (0, 1, 2, 3) two are usable
    half = MaskParams(essential=(0, 1, 2, 3), min_essential_fraction=0.5)
    assert not apply_mask(kp, sc, params=half).frame_invalid[0]  # 2 of 4 is valid
    sc[0, 2] = 0.1
    assert apply_mask(kp, sc, params=half).frame_invalid[0]  # 1 of 4 is not
    kp, sc = pose(1, 0.9)
    sc[0, 3] = 0.1
    strict = MaskParams(essential=(0, 1, 2, 3), min_essential_fraction=1.0)
    assert apply_mask(kp, sc, params=strict).frame_invalid[0]  # all four are needed
    assert not apply_mask(kp, sc, params=MaskParams(essential=(0, 1, 2), min_essential_fraction=1.0)).frame_invalid[0]


def test_t_qlt_02a_a_share_that_is_not_an_exact_float_does_not_move_the_boundary():
    # 0.28 of 25 joints is exactly 7 in arithmetic but 7.000000000000001 as a float: 7 usable joints must still pass
    assert 0.28 * 25 > 7
    params = MaskParams(essential=tuple(range(25)), min_essential_fraction=0.28)
    for usable, invalid in ((8, False), (7, False), (6, True)):
        kp, sc = pose(1, 0.9)
        sc[0, usable:25] = 0.1
        out = apply_mask(kp, sc, params=params)
        assert out.n_essential_valid[0] == usable and bool(out.frame_invalid[0]) is invalid, usable


def test_t_qlt_02a_the_score_rule_uses_the_given_tau_not_a_fixed_one():
    kp, sc = pose(1, 0.9)
    sc[0, list(ESSENTIAL)] = 0.5
    assert not apply_mask(kp, sc, params=MaskParams(tau_kp=0.5)).frame_invalid[0]
    assert apply_mask(kp, sc, params=MaskParams(tau_kp=0.6)).frame_invalid[0]
