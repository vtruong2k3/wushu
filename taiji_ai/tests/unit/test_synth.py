"""Unit tests for the synthetic HALPE_26 generator F-SYN (T-SYN-01..04, task P0.07).

The truth of every scenario is checked against an independent computation on the generator's own noise-free output:
Appendix B formulas, a dense (3000 fps) numerical derivative, pose equality between a re-timed query and its
reference, identity bookkeeping of the scene. A truth that merely repeats the generator code would not fail here.
"""

from __future__ import annotations

import hashlib
import random
import warnings
from collections.abc import Mapping

import numpy as np
import pytest

from helpers import synth as S
from taiji_ai.pose.skeleton import GROUND_CANDIDATES, GROUPS, IDX, JOINTS, LR_PAIRS, NUM_JOINTS

DENSE_FPS = 3000.0


# --- helpers (independent of the generator's internals) ---------------------------------------------------------
def mid(kp: np.ndarray, a: str, b: str) -> np.ndarray:
    kp = kp.astype(np.float64)
    return 0.5 * (kp[..., IDX[a], :] + kp[..., IDX[b], :])


def trunk_len(kp: np.ndarray) -> np.ndarray:
    return np.linalg.norm(mid(kp, "LShoulder", "RShoulder") - mid(kp, "LHip", "RHip"), axis=-1)


def theta_deg(kp: np.ndarray) -> np.ndarray:
    """Appendix B2: atan2(x_S - x_H, y_H - y_S), degrees, positive = top leans to the image right."""
    s, h = mid(kp, "LShoulder", "RShoulder"), mid(kp, "LHip", "RHip")
    return np.degrees(np.arctan2(s[..., 0] - h[..., 0], h[..., 1] - s[..., 1]))


def dense_motion(**params):
    """The same continuous motion sampled at 3000 fps (reference for derivatives and re-timing checks)."""
    return S.make_sequence("SYN-05", fps=DENSE_FPS, **params)


def dense_group_speed(dense, idx: np.ndarray, group: str) -> np.ndarray:
    """Appendix B3 group speed (median of joint speeds, Lambda/s) by central difference of the dense positions."""
    kp = dense.kp_true.astype(np.float64)
    v = (kp[idx + 1] - kp[idx - 1]) / (2.0 / DENSE_FPS)
    speed = np.hypot(v[..., 0], v[..., 1]) / dense.truth["scale_px"]
    return np.median(speed[:, list(GROUPS[group])], axis=1)


def build(scenario: str, seed: int = 0, **kw):
    kind = S.SCENARIOS[scenario].kind
    make = {"sequence": S.make_sequence, "pair": S.make_pair, "scene": S.make_scene}[kind]
    return make(scenario, seed=seed, **kw)


def digest(obj, skip: frozenset[str] = frozenset({"seed"})) -> str:
    """Hash of every array / number reachable from a generated object (NaN-safe, order-stable)."""
    h = hashlib.sha256()

    def walk(x) -> None:
        if isinstance(x, np.ndarray):
            h.update(f"{x.dtype}{x.shape}".encode())
            h.update(np.ascontiguousarray(x).tobytes())
        elif isinstance(x, Mapping):
            for k in sorted(x):
                h.update(str(k).encode())
                walk(x[k])
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
        elif hasattr(x, "__dataclass_fields__"):
            for name in sorted(x.__dataclass_fields__):
                if name not in skip:  # e.g. the seed itself must not make two outputs look different
                    walk(getattr(x, name))
        else:
            h.update(repr(x).encode())

    walk(obj)
    return h.hexdigest()


# --- T-SYN-01: shared contract across all registered scenarios ---------------------------------------------------
@pytest.mark.parametrize("scenario_id", list(S.SCENARIOS))
def test_t_syn_01_contract_and_defaults(scenario_id: str):
    spec = S.SCENARIOS[scenario_id]
    obj = build(scenario_id, seed=42)
    assert obj.synthetic is True
    assert obj.generator_version == S.SYNTH_VERSION
    assert obj.scenario == scenario_id
    for key in spec.truth_keys:
        assert key in obj.truth, f"missing truth key {key!r} in {scenario_id}"

    if spec.kind == "sequence":
        assert isinstance(obj, S.SynthSequence)
        sequences = [obj]
    elif spec.kind == "pair":
        assert isinstance(obj, S.SynthPair)
        sequences = [obj.ref, obj.query]
    else:
        assert isinstance(obj, S.SynthScene)
        sequences = []
        assert obj.kp.ndim == 4 and obj.kp.shape[2:] == (NUM_JOINTS, 2) and obj.kp.dtype == np.float32
        assert obj.score.shape == obj.kp.shape[:3] and obj.bbox.shape == (*obj.kp.shape[:2], 4)
        assert obj.t_sec.dtype == np.float64 and obj.t_sec[0] == 0.0 and np.all(np.diff(obj.t_sec) > 0)
        for arr in (obj.kp, obj.score, obj.bbox, obj.t_sec):
            assert not arr.flags.writeable
        pid = obj.truth["person_id"]
        assert pid.shape == obj.kp.shape[:2]
        assert np.array_equal(np.isnan(obj.kp[..., 0, 0]), pid < 0)  # NaN exactly where a slot is empty

    for seq in sequences:
        assert seq.kp.shape[1:] == (NUM_JOINTS, 2) and seq.kp.dtype == np.float32
        assert seq.kp_true.shape == seq.kp.shape and seq.kp_true.dtype == np.float32
        assert seq.score.shape == seq.kp.shape[:2] and seq.score.dtype == np.float32
        assert seq.t_sec.ndim == 1 and seq.t_sec.dtype == np.float64 and len(seq.t_sec) == len(seq.kp)
        assert seq.t_sec[0] == 0.0 and np.all(np.diff(seq.t_sec) > 0.0)
        assert np.all((seq.score >= 0.0) & (seq.score <= 1.0))
        assert np.all(np.isfinite(seq.kp_true))  # the noise-free positions are always observed
        for arr in (seq.kp, seq.score, seq.t_sec, seq.kp_true):
            assert not arr.flags.writeable
        x = seq.kp[..., 0]
        x = x[np.isfinite(x)]
        assert np.all(x >= -50) and np.all(x <= S.IMAGE_SIZE[0] + 50)  # noise may leave the image by a few px

    # F-2: the truth is read-only all the way down: no shared fixture can be corrupted by a test
    def check_read_only(x) -> None:
        if isinstance(x, np.ndarray):
            assert not x.flags.writeable
        elif isinstance(x, Mapping):
            with pytest.raises(TypeError):
                x["__probe__"] = 1
            for v in x.values():
                check_read_only(v)
        elif isinstance(x, (list, set)):
            raise AssertionError(f"mutable container {type(x).__name__} in the truth of {scenario_id}")
        elif isinstance(x, tuple):
            for v in x:
                check_read_only(v)

    check_read_only(obj.truth)
    with pytest.raises(TypeError):
        obj.params["__probe__"] = 1


# --- T-SYN-01b: body conventions ---------------------------------------------------------------------------------
def test_t_syn_01b_body_conventions():
    scale = 220.0
    p = S.neutral_pose(scale_px=scale, facing="camera").astype(np.float64)
    assert abs(float(trunk_len(p)) - scale) < 1e-4
    # facing the camera: the person's left is the image right
    for left, right in (("LShoulder", "RShoulder"), ("LHip", "RHip"), ("LWrist", "RWrist"), ("LAnkle", "RAnkle")):
        assert p[IDX[left], 0] > p[IDX[right], 0]
    away = S.neutral_pose(scale_px=scale, facing="away")
    assert away[IDX["LShoulder"], 0] < away[IDX["RShoulder"], 0]
    assert abs(float(trunk_len(away)) - scale) < 1e-4
    # inside a 1920 x 1080 image, feet on the ground line
    assert np.all((p[:, 0] >= 0) & (p[:, 0] <= S.IMAGE_SIZE[0])) and np.all(
        (p[:, 1] >= 0) & (p[:, 1] <= S.IMAGE_SIZE[1])
    )
    assert abs(float(p[:, 1].max()) - S.GROUND_Y_PX) < 1e-6  # the toes stand on the ground line
    # F-1: adult proportions: hip-to-ankle is 1.6-1.9 x the trunk (the first version used 1.25)
    leg = np.linalg.norm(mid(p, "LHip", "RHip") - mid(p, "LAnkle", "RAnkle"))
    assert 1.6 * scale <= leg <= 1.9 * scale
    # the mirrored (left-right swapped) template equals the "away" one up to the image mirror
    assert S.neutral_pose(scale_px=scale, origin=(100.0, 500.0))[IDX["Hip"]].tolist() == [100.0, 500.0]


def test_t_syn_01c_raise_lower_pose_matches_the_documented_action():
    """The action definition itself (the other truths build on it): at phase 0.5 of 'raise_lower'."""
    scale = 200.0
    seq = S.make_sequence("SYN-05", duration=4.0, fps=30.0, pauses=(), scale_px=scale)
    base = seq.kp_true[0].astype(np.float64)  # phase 0: neutral
    half = seq.kp_true[int(round(2.0 * 30.0))].astype(np.float64)  # t = 2.0 s: phase 0.5, no pauses
    d = (half - base) / scale
    assert np.allclose(d[IDX["Hip"]], (0.0, 0.08), atol=1e-4)  # the body drops 0.08 trunk lengths
    assert np.allclose(d[IDX["LShoulder"]], (0.0, 0.08), atol=1e-4)
    assert np.allclose(d[IDX["LKnee"]], (0.0, 0.04), atol=1e-4)
    assert np.allclose(d[IDX["LAnkle"]], (0.0, 0.0), atol=1e-4)  # feet stay put
    assert np.allclose(d[IDX["LWrist"]], (0.0, 0.08 - 1.10), atol=1e-4)  # wrists rise 1.10 relative to the body
    assert np.allclose(d[IDX["LElbow"]], (0.0, 0.08 - 0.55), atol=1e-4)
    assert np.allclose(trunk_len(seq.kp_true), scale, atol=1e-3)  # rigid trunk in every frame
    other = S.make_sequence("SYN-05", duration=4.0, fps=30.0, pauses=(), scale_px=scale, action="open_close")
    do = (other.kp_true[60].astype(np.float64) - other.kp_true[0].astype(np.float64)) / scale
    assert np.allclose(do[IDX["LWrist"]], (0.60, 0.0), atol=1e-4) and np.allclose(
        do[IDX["RWrist"]], (-0.60, 0.0), atol=1e-4
    )
    away = S.make_sequence(
        "SYN-05", duration=4.0, fps=30.0, pauses=(), scale_px=scale, action="open_close", facing="away"
    )
    da = (away.kp_true[60].astype(np.float64) - away.kp_true[0].astype(np.float64)) / scale
    assert np.allclose(da[IDX["LWrist"]], (-0.60, 0.0), atol=1e-4)  # arms open outward whichever way the body faces


# --- T-SYN-02: the truth of every scenario, verified independently ----------------------------------------------
def test_t_syn_02_syn01_still_truth():
    seq = S.make_sequence("SYN-01", seed=1, noise_px=0.0)
    t = seq.truth
    assert t["hip_range"] == 0.0 and t["n_pauses"] == 1
    assert t["pause_intervals"] == ((0.0, float(seq.t_sec[-1])),)
    assert t["pause_frames"] == ((0, len(seq.t_sec) - 1),)
    for g in GROUPS:
        assert np.all(t["speed"][g] == 0.0)
    assert np.all(seq.kp_true == seq.kp_true[0:1])
    noisy = S.make_sequence("SYN-01", seed=1, noise_px=2.0)
    resid = noisy.kp.astype(np.float64) - noisy.kp_true.astype(np.float64)
    assert abs(float(resid.std()) - 2.0) < 0.1  # the noise is what was asked for


def test_t_syn_02_syn02_hip_sine_truth():
    amp, freq = 0.20, 0.5
    seq = S.make_sequence("SYN-02", seed=2, amplitude=amp, freq=freq)
    hip_y = mid(seq.kp_true, "LHip", "RHip")[:, 1]
    assert np.allclose(hip_y, seq.truth["hip_y"], atol=1e-3)
    h = hip_y / seq.truth["scale_px"]
    p95, p5 = np.percentile(h, [95, 5])
    expected = seq.truth["expected_range_p95_p5"]
    assert abs(expected - 2 * amp * np.sin(0.45 * np.pi)) < 1e-12 and seq.truth["nominal_range"] == 2 * amp
    assert abs(float(p95 - p5) - expected) / expected < 0.01
    assert np.allclose(trunk_len(seq.kp_true), seq.truth["scale_px"], atol=1e-3)  # rigid trunk


def test_t_syn_02_syn03_trunk_lean_truth():
    seq = S.make_sequence("SYN-03", seed=3, theta_from=5.0, theta_to=25.0)
    assert np.allclose(theta_deg(seq.kp_true), seq.truth["theta_deg"], atol=1e-4)
    assert abs(float(np.median(theta_deg(seq.kp_true))) - seq.truth["median_theta_deg"]) < 1e-4
    # theta(t) is a function of time, not of the frame count
    fast = S.make_sequence("SYN-03", theta_from=5.0, theta_to=25.0, fps=60.0)
    assert np.allclose(fast.truth["theta_deg"][::2], seq.truth["theta_deg"], atol=1e-6)
    const = S.make_sequence("SYN-03", theta_deg=-12.5)
    assert np.allclose(theta_deg(const.kp_true), -12.5, atol=1e-4)


def test_t_syn_02_syn04_camera_roll_truth():
    beta = 7.5
    seq = S.make_sequence("SYN-04", seed=4, roll_deg=beta, theta_deg=10.0)
    line = np.asarray(seq.truth["vertical_line"], dtype=np.float64)  # two image points of a true vertical
    line_angle = float(np.degrees(np.arctan2(line[0, 0] - line[1, 0], line[1, 1] - line[0, 1])))
    assert abs(line_angle - beta) < 1e-3
    raw = theta_deg(seq.kp_true)
    assert np.allclose(raw, 10.0 + beta, atol=1e-3) and np.allclose(seq.truth["theta_raw_deg"], raw, atol=1e-3)
    assert np.allclose(raw - beta, seq.truth["theta_body_deg"], atol=1e-3)  # what the metric must recover
    assert np.allclose(trunk_len(seq.kp_true), seq.truth["scale_px"], atol=1e-3)


PAUSES = ((1.0, 1.6), (2.8, 3.4))


def test_t_syn_02_syn05_pauses_and_speed_truth():
    seq = S.make_sequence("SYN-05", seed=5, duration=5.0, pauses=PAUSES, ramp_s=0.2)
    t, truth = seq.t_sec, seq.truth
    assert truth["pause_intervals"] == PAUSES and truth["n_pauses"] == 2
    for (p0, p1), (f0, f1) in zip(truth["pause_intervals"], truth["pause_frames"], strict=True):
        assert p0 - 1e-9 <= t[f0] and t[f1] <= p1 + 1e-9 and (f1 - f0) >= 15
        assert np.all(seq.kp_true[f0 : f1 + 1] == seq.kp_true[f0])  # bit-identical inside a pause
        for g in GROUPS:
            assert np.all(truth["speed"][g][f0 : f1 + 1] == 0.0), g  # exactly zero, edges included
    moving = (t > 0.1) & (t < 0.7)
    assert np.all(truth["speed"]["hands"][moving] > 0.1)
    assert truth["speed"]["hands"].max() > 0.3  # not a vector of zeros
    assert np.all(np.diff(truth["phase"]) >= 0.0) and abs(truth["phase"][0]) < 1e-12 and truth["phase"][-1] < 1.0

    # the truth is the derivative of the continuous model: compare with a dense central difference
    dense = dense_motion(duration=5.0, pauses=PAUSES, ramp_s=0.2)
    k = np.arange(1, len(t))
    idx = np.rint(t[k] * DENSE_FPS).astype(int)
    assert np.allclose(dense.t_sec[idx], t[k])
    for g in GROUPS:
        assert np.allclose(truth["speed"][g][k], dense_group_speed(dense, idx, g), atol=3e-3), g


def test_t_syn_02_group_speed_is_the_median_of_the_joint_speeds():
    """Appendix B3: one fast joint among four must not move the group speed (median, not mean).

    The scenarios move the joints of each group together, so only a direct check can tell the median from the mean.
    """
    vel = np.zeros((3, NUM_JOINTS, 2))
    vel[:, IDX["LAnkle"], 0] = 400.0  # 2 Lambda/s at Lambda = 200 px
    one_fast = S._group_speeds(vel, 200.0)
    assert np.all(one_fast["feet"] == 0.0)  # median of (2, 0, 0, 0)
    assert np.all(one_fast["hands"] == 0.0)
    vel[:, IDX["RAnkle"], 0] = 400.0
    vel[:, IDX["LHeel"], 0] = 400.0
    assert np.allclose(S._group_speeds(vel, 200.0)["feet"], 2.0)  # median of (2, 2, 2, 0); the mean would be 1.5


def test_t_syn_02_syn05_motion_does_not_depend_on_the_frame_rate():
    a = S.make_sequence("SYN-05", fps=30.0)
    b = S.make_sequence("SYN-05", fps=60.0)
    assert len(b.t_sec) == 2 * len(a.t_sec)
    assert np.allclose(a.kp_true, b.kp_true[::2], atol=2e-3)
    assert np.allclose(a.truth["speed"]["hands"], b.truth["speed"]["hands"][::2], atol=1e-9)


def test_t_syn_02_syn06_gaps_truth():
    seq = S.make_sequence("SYN-06", seed=6)  # defaults
    t, gaps = seq.t_sec, seq.truth["gaps"]
    assert len(gaps) == 2 and [g["kind"] for g in sorted(gaps, key=lambda g: g["t0"])] == ["long", "short"]
    dt = float(np.median(np.diff(t)))
    for g in gaps:
        i0, i1 = g["frames"]
        # the gap sits in motion: outside every pause and every ramp, so a 'no false pause' test is meaningful
        for p0, p1 in seq.truth["pause_intervals"]:
            assert not (t[i1] >= p0 - 0.2 and t[i0] <= p1 + 0.2), f"gap {g['t0']} touches the pause {p0}-{p1}"
        for name in g["joints"]:
            j = IDX[name]
            assert np.all(np.isnan(seq.kp[i0 : i1 + 1, j])) and np.all(seq.score[i0 : i1 + 1, j] == 0.0)
        assert g["n_missing"] == i1 - i0 + 1 and abs(g["missing_s"] - g["n_missing"] * dt) < 1e-9
        assert g["bridgeable"] is True and abs(g["bridge_s"] - (t[i1 + 1] - t[i0 - 1])) < 1e-9
        assert (g["kind"] == "short") == (g["bridge_s"] <= 0.150) and (g["kind_missing"] == "short") == (
            g["missing_s"] <= 0.150
        )
        assert i0 == int(np.flatnonzero(t >= g["t0"] - 1e-9)[0])  # starts at the requested time, not one frame off
    # NaN exactly where requested (every joint: the union of its gaps), nowhere else; the other joints are untouched
    for j in range(NUM_JOINTS):
        expected = np.zeros(len(t), dtype=bool)
        for g in gaps:
            if JOINTS[j] in g["joints"]:
                expected[g["frames"][0] : g["frames"][1] + 1] = True
        assert np.array_equal(np.isnan(seq.kp[:, j, 0]), expected), JOINTS[j]
        assert np.array_equal(np.isnan(seq.kp[:, j, 1]), expected), JOINTS[j]
    assert np.all(np.isfinite(seq.kp_true))
    # one gap shorter than the limit and one longer, both reported with both definitions (D2)
    custom = S.make_sequence("SYN-06", gaps=((["LWrist"], 2.0, 0.12),), short_gap_s=0.100)
    assert custom.truth["gaps"][0]["kind"] == "long"


def test_t_syn_02_syn06_low_score_mode_keeps_positions_wrong_but_finite():
    seq = S.make_sequence("SYN-06", gap_mode="low_score")
    for g in seq.truth["gaps"]:
        i0, i1 = g["frames"]
        for name in g["joints"]:
            j = IDX[name]
            assert np.all(seq.score[i0 : i1 + 1, j] < 0.3) and np.all(np.isfinite(seq.kp[i0 : i1 + 1, j]))
            err = np.linalg.norm(seq.kp[i0 : i1 + 1, j].astype(np.float64) - seq.kp_true[i0 : i1 + 1, j], axis=-1)
            assert err.mean() > 3.0  # a consumer that ignores the score is visibly wrong


def test_t_syn_02_syn06_edge_gaps():
    first = S.make_sequence("SYN-06", gaps=((["LWrist"], 0.0, 0.2),)).truth["gaps"][0]
    assert first["bridgeable"] is False and first["bridge_s"] is None and first["kind"] == "unbridgeable"
    last_t0 = float(S.cfr_times(5.0, 30.0)[-1]) - 0.1
    last = S.make_sequence("SYN-06", gaps=((["LWrist"], last_t0, 0.5),)).truth["gaps"][0]
    assert last["bridgeable"] is False and last["kind"] == "unbridgeable"


def test_t_syn_02_syn07_vfr_truth():
    seq = S.make_sequence("SYN-07", seed=7)
    t, truth = seq.t_sec, seq.truth
    dt = np.diff(t)
    assert truth["is_vfr"] is True and np.allclose(truth["dt"], dt) and dt.max() / dt.min() > 2.5
    assert abs(truth["dt"][0] - 1 / 30) < 1e-12 and abs(truth["dt"][-1] - 0.1) < 1e-12
    dense = dense_motion(duration=4.0, pauses=((1.0, 1.5),), ramp_s=0.2)
    k = np.arange(1, len(t))
    idx = np.rint(t[k] * DENSE_FPS).astype(int)
    assert np.allclose(dense.t_sec[idx], t[k])
    assert np.allclose(seq.kp_true[k], dense.kp_true[idx], atol=2e-3)  # same motion, sampled irregularly
    for g in GROUPS:
        assert np.allclose(truth["speed"][g][k], dense_group_speed(dense, idx, g), atol=3e-3), g
    assert truth["speed"]["hands"].max() > 0.3
    # a CFR clip without jitter is not reported as VFR
    cfr = S.make_sequence("SYN-07", step_down_at=None)
    assert cfr.truth["is_vfr"] is False
    # jitter: seeded, strictly increasing, VFR
    jit = S.make_sequence("SYN-07", step_down_at=None, jitter_frac=0.3, seed=3)
    assert jit.truth["is_vfr"] is True and np.all(np.diff(jit.t_sec) > 0)


def test_t_syn_02_syn08_lr_swap_truth():
    ranges = ((10, 15), (30, 35))
    seq = S.make_sequence("SYN-08", seed=8, swap_ranges=ranges)
    mask = seq.truth["lr_swap_mask"]
    assert mask.dtype == bool and int(mask.sum()) == 10 and seq.truth["lr_swap_intervals"] == ranges
    assert seq.truth["n_pairs_swapped"] == len(LR_PAIRS) == 11
    perm = np.arange(NUM_JOINTS)
    for a, b in LR_PAIRS:
        perm[a], perm[b] = b, a
    for f in range(len(seq.t_sec)):
        expected = seq.kp_true[f][perm] if mask[f] else seq.kp_true[f]
        assert np.array_equal(seq.kp[f], expected), f"frame {f}"
        assert np.array_equal(seq.score[f], np.full(NUM_JOINTS, seq.params["score_base"], np.float32))
    # the unswapped clip is exactly the same motion
    plain = S.make_sequence("SYN-08", swap_ranges=())
    assert not plain.truth["lr_swap_mask"].any() and np.array_equal(plain.kp, plain.kp_true)


@pytest.mark.parametrize("cam_height_m", [0.6, 1.0, 1.3])
def test_t_syn_02_syn09_pinhole_truth_follows_appendix_b(cam_height_m: float):
    seq = S.make_sequence("SYN-09", seed=9, cam_height_m=cam_height_m)
    kp, t, truth = seq.kp_true.astype(np.float64), seq.t_sec, seq.truth
    length = trunk_len(kp)
    y_h = mid(kp, "LHip", "RHip")[:, 1]
    ref = t < truth["reference_s"]
    lam_take, lam_seg = float(np.median(length[ref])), float(np.median(length))
    h_a = y_h / lam_take  # Appendix B1, variant A
    ground = kp[:, list(GROUND_CANDIDATES), 1].max(axis=1)
    h_b = (ground - y_h) / lam_seg  # Appendix B1, variant B
    assert np.allclose(length, truth["scale_px"], atol=1e-3)
    assert abs(lam_take - truth["lambda_take"]) < 1e-3 and abs(lam_seg - truth["lambda_segment"]) < 1e-3
    assert np.allclose(h_a, truth["expected_hA"], atol=1e-4) and np.allclose(h_b, truth["expected_hB"], atol=1e-4)
    rng_a, rng_b = (float(np.subtract(*np.percentile(h, [95, 5]))) for h in (h_a, h_b))
    assert abs(rng_a - truth["range_A"]) < 1e-4 and abs(rng_b - truth["range_B"]) < 1e-4
    # a real pinhole camera: the person shrinks and the feet move toward the horizon when walking away
    assert length[-1] < 0.9 * length[0] and ground[-1] < ground[0] - 20
    assert abs(np.median(length[ref]) - length[0]) < 1e-3  # standing still during the reference interval
    # the physical hip height never changes: any measured range is a camera artefact, not a body movement
    assert truth["true_hip_height_m"] > 0 and truth["true_hip_height_range_m"] == 0.0
    assert (
        truth["range_A"] > 0 and truth["range_B"] > 0
    )  # both variants are fooled; their order depends on the geometry


def test_t_syn_02_syn10_query_is_the_reference_retimed():
    pair = S.make_pair("SYN-10", seed=10)
    p, truth = pair.params, pair.truth
    dense = S.make_sequence("SYN-05", duration=p["duration"], fps=DENSE_FPS, pauses=(), scale_px=p["scale_px"])
    t_ref, t_q = np.asarray(truth["t_ref_of_query"]), pair.query.t_sec
    assert (
        t_ref[0] == 0.0 and np.all(np.diff(t_ref) > 0.0) and t_ref[-1] < p["duration"] and truth["same_shape"] is True
    )
    expected = np.stack(
        [
            np.stack([np.interp(t_ref, dense.t_sec, dense.kp_true[:, j, c]) for c in (0, 1)], -1)
            for j in range(NUM_JOINTS)
        ],
        1,
    )
    assert np.abs(pair.query.kp_true - expected).max() < 1e-3  # px
    # rate k = d t_query / d t_ref (Appendix C.4), analytic, spans the requested range
    k = np.asarray(truth["rate_k"])
    assert np.allclose(k[1:-1], np.gradient(t_q, t_ref)[1:-1], rtol=5e-3)
    assert (
        abs(k[0] - p["k_start"]) < 1e-9
        and abs(k[-1] - (p["k_start"] + (p["k_end"] - p["k_start"]) * t_ref[-1] / p["duration"])) < 1e-9
    )
    assert abs(truth["query_duration"] - p["duration"] * (p["k_start"] + p["k_end"]) / 2) < 1e-9


def test_t_syn_02_syn10_query_offset_and_scale_leave_the_normalised_shape_unchanged():
    pair = S.make_pair("SYN-10", query_scale=1.2, query_shift_px=(100.0, -20.0))
    p, truth = pair.params, pair.truth
    dense = S.make_sequence("SYN-05", duration=p["duration"], fps=DENSE_FPS, pauses=(), scale_px=p["scale_px"])
    t_ref = np.asarray(truth["t_ref_of_query"])
    ref_at = np.stack(
        [
            np.stack([np.interp(t_ref, dense.t_sec, dense.kp_true[:, j, c]) for c in (0, 1)], -1)
            for j in range(NUM_JOINTS)
        ],
        1,
    )

    def normalised(kp):
        kp = kp.astype(np.float64)
        return (kp - mid(kp, "LHip", "RHip")[:, None, :]) / trunk_len(kp)[:, None, None]

    assert np.allclose(normalised(pair.query.kp_true), normalised(ref_at), atol=2e-4)
    assert abs(float(trunk_len(pair.query.kp_true).mean()) - 1.2 * p["scale_px"]) < 1e-2
    plain = S.make_pair("SYN-10")
    shift = mid(pair.query.kp_true[0:1], "LHip", "RHip") - mid(plain.query.kp_true[0:1], "LHip", "RHip")
    assert truth["query_scale"] == 1.2 and tuple(truth["query_shift_px"]) == (100.0, -20.0)
    assert np.allclose(shift, (100.0, -20.0), atol=1e-2)  # the query hip moves exactly by the shift


def test_t_syn_02_syn11_actions_truth():
    pair = S.make_pair("SYN-11", seed=11)
    ref, other, variant = pair.ref, pair.query, pair.truth["variant"]
    assert pair.truth["same_action"] is False
    assert (pair.truth["action_ref"], pair.truth["action_query"]) == ("raise_lower", "open_close")
    assert variant.params["action"] == "raise_lower" and other.params["action"] == "open_close"

    def distance(a, b):  # mean joint distance in trunk lengths
        n = min(len(a.kp), len(b.kp))
        return float(
            np.linalg.norm(a.kp[:n].astype(np.float64) - b.kp[:n].astype(np.float64), axis=-1).mean()
            / ref.params["scale_px"]
        )

    d_other, d_variant = distance(ref, other), distance(ref, variant)
    assert d_other >= 2.0 * d_variant  # tolerance table: the other action is at least twice as far as the variant
    assert d_other > 0.03 and d_variant > 0.0  # the variant is not a copy, the actions really differ


def test_t_syn_02_syn12_scene_truth():
    scene = S.make_scene("SYN-12", seed=12)
    t, truth = scene.t_sec, scene.truth
    pid, by_person = truth["person_id"], truth["kp_by_person"]
    n_slots = scene.kp.shape[1]
    assert n_slots == truth["n_people"] == 3 and truth["target_id"] == 0

    # identities: a detector returns an unordered list, so the slot index must not be the identity
    present = pid >= 0
    assert np.mean(pid[present] != np.broadcast_to(np.arange(n_slots), pid.shape)[present]) > 0.2
    for ti, si in zip(*np.nonzero(present), strict=True):  # slot content == the identity's noise-free trajectory
        assert np.array_equal(scene.kp[ti, si], by_person[ti, pid[ti, si]])
    assert (
        S.make_scene("SYN-12", seed=1).truth["person_id"].tolist()
        != S.make_scene("SYN-12", seed=2).truth["person_id"].tolist()
    )
    assert (
        S.make_scene("SYN-12", seed=1).truth["person_id"].tolist()
        == S.make_scene("SYN-12", seed=1).truth["person_id"].tolist()
    )

    # absence of the target: no detection with identity 0 inside it, present before and after
    ((a0, a1),) = truth["absent_intervals"]
    inside = (t >= a0) & (t < a1)
    ((f0, f1),) = truth["absent_frames"]
    assert np.array_equal(np.flatnonzero(inside), np.arange(f0, f1 + 1))
    assert not np.any(pid[inside] == 0) and np.all(np.any(pid[~inside] == 0, axis=1))
    assert np.all(np.isnan(by_person[inside, 0])) and not np.any(np.isnan(by_person[~inside, 0]))

    # crossing: recomputed from the boxes of the identities, in the target's presence, before it leaves
    box = {}
    for ident in (0, 1):
        pts = by_person[:, ident]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # the absent target gives all-NaN rows
            box[ident] = np.concatenate([np.nanmin(pts, axis=1) - 20, np.nanmax(pts, axis=1) + 20], axis=-1)
    both = np.all(np.isfinite(box[0]), axis=1) & np.all(np.isfinite(box[1]), axis=1)
    overlap = both & (np.minimum(box[0][:, 2], box[1][:, 2]) > np.maximum(box[0][:, 0], box[1][:, 0]))
    assert overlap.any()
    c0, c1 = truth["crossing_interval"]
    assert abs(c0 - t[np.flatnonzero(overlap)[0]]) < 1.5 / 30 and abs(c1 - t[np.flatnonzero(overlap)[-1]]) < 1.5 / 30
    assert c1 <= a0 + 1e-9, "the crossing must happen while the target is visible"

    # boxes contain their keypoints, trajectory of the target is the documented sway
    for ti, si in zip(*np.nonzero(present), strict=True):
        box_i, pts = scene.bbox[ti, si], scene.kp[ti, si]
        assert np.all(pts[:, 0] >= box_i[0] - 1e-3) and np.all(pts[:, 0] <= box_i[2] + 1e-3)
        assert np.all(pts[:, 1] >= box_i[1] - 1e-3) and np.all(pts[:, 1] <= box_i[3] + 1e-3)
    before = t < a0
    hip_x = by_person[before, 0, IDX["Hip"], 0].astype(np.float64)
    assert np.allclose(hip_x, truth["target_x0_px"] + 15.0 * np.sin(t[before]), atol=1e-2)

    # re-entry offset: the target comes back where it left, or elsewhere when asked to
    moved = S.make_scene("SYN-12", return_offset_px=250.0)
    after = moved.t_sec >= moved.truth["absent_intervals"][0][1]
    shift = moved.truth["kp_by_person"][after, 0, IDX["Hip"], 0] - truth["kp_by_person"][after, 0, IDX["Hip"], 0]
    assert np.allclose(shift, 250.0, atol=1e-2) and moved.truth["return_offset_px"] == 250.0


def test_t_syn_02_syn12_expected_target_lost():
    scene = S.make_scene("SYN-12", absent_s=(1.5, 2.5))
    assert S.expected_target_lost(scene, max_lost_s=0.5) == ((2.0, 2.5),)
    assert S.expected_target_lost(scene.truth, max_lost_s=1.5) == ()  # a 1.0 s absence is shorter than max_lost
    with pytest.raises(ValueError, match="max_lost_s"):
        S.expected_target_lost(scene, max_lost_s=-1.0)


# --- T-SYN-03: determinism and isolation from global RNG state ----------------------------------------------------
@pytest.mark.parametrize("scenario", list(S.SCENARIOS))
def test_t_syn_03_same_seed_same_output_different_seed_different_noise(scenario: str):
    a, b, c = (build(scenario, seed=s, noise_px=1.5) for s in (123, 123, 124))
    assert digest(a) == digest(b)
    assert digest(a) != digest(c)


@pytest.mark.parametrize("scenario", list(S.SCENARIOS))
def test_t_syn_03_global_rng_state_is_untouched(scenario: str):
    np_state, py_state = np.random.get_state(), random.getstate()  # noqa: NPY002
    build(scenario, seed=5, noise_px=1.5)
    after = np.random.get_state()  # noqa: NPY002
    assert np_state[0] == after[0] and np.array_equal(np_state[1], after[1]) and np_state[2:] == after[2:]
    assert random.getstate() == py_state


# --- T-SYN-04: input errors -------------------------------------------------------------------------------------
def test_t_syn_04_unknown_scenario_and_wrong_api():
    with pytest.raises(ValueError, match="Unknown scenario"):
        S.make_sequence("UNKNOWN_SCENARIO")
    with pytest.raises(ValueError, match="is of kind 'pair'"):
        S.make_sequence("SYN-10")
    with pytest.raises(ValueError, match="is of kind 'sequence'"):
        S.make_pair("SYN-01")
    with pytest.raises(ValueError, match="is of kind 'scene'"):
        S.make_sequence("SYN-12")
    with pytest.raises(ValueError, match="seed"):
        S.make_sequence("SYN-01", seed=-1)


# Alternative value for every parameter a scenario accepts (one entry per name; the test below fails when a name is
# missing, so a new parameter has to be added here and has to change the output).
ALT = {
    "fps": 25.0, "scale_px": 180.0, "score_base": 0.8, "facing": "away",
    "amplitude": 0.12, "freq": 0.6, "theta_deg": 7.0, "theta_from": 2.0, "theta_to": 12.0,
    "roll_deg": 6.0, "centre": (900.0, 500.0), "action": "open_close", "ramp_s": 0.3,
    "gaps": ((("LWrist",), 2.0, 0.2),), "gap_mode": "low_score", "short_gap_s": 0.05,
    "fps_nominal": 25.0, "fps_second": 8.0, "step_down_at": 1.5, "jitter_frac": 0.2,
    "swap_ranges": ((10, 13),), "z0_m": 4.5, "depth_ratio": 1.3, "cam_height_m": 0.9, "trunk_m": 0.45,
    "reference_s": 0.8, "k_start": 0.9, "k_end": 1.2, "query_scale": 1.1, "query_shift_px": (10.0, 5.0),
    "variant_k": (0.95, 1.05), "variant_noise_px": 0.5, "n_people": 2, "absent_s": (1.7, 2.5), "cross_s": 0.7,
    "walk_px_s": 350.0, "target_x0_px": 650.0, "return_offset_px": 50.0,
}  # fmt: skip
PAUSES_ALT = {"SYN-07": ((1.0, 1.3),)}


@pytest.mark.parametrize("scenario", list(S.SCENARIOS))
def test_t_syn_04_every_accepted_parameter_changes_the_output(scenario: str):
    """BUG-0020 / BUG-0028: a parameter that is accepted but never read would let a typo-free call run on defaults."""
    spec = S.SCENARIOS[scenario]
    skip = frozenset({"seed", "params"})  # the echoed parameters would make an ignored one look effective
    base = digest(build(scenario), skip)
    for name in spec.default_params:
        if name == "pauses":
            value = PAUSES_ALT.get(scenario, ((1.0, 1.4), (2.8, 3.4)))
        elif name in ("duration", "noise_px"):  # derived from the default so that the value always differs and fits
            value = spec.default_params[name] + (0.5 if name == "duration" else 1.0)
        else:
            value = ALT[name]
        assert value != spec.default_params[name], f"{scenario}.{name}: the alternative equals the default"
        assert digest(build(scenario, **{name: value}), skip) != base, f"{scenario}: parameter {name!r} is ignored"


def test_t_syn_04_unknown_parameter_is_rejected_by_every_api():
    """BUG-0020: a misspelled parameter must not silently fall back to the default."""
    with pytest.raises(TypeError, match="amplitud") as exc:
        S.make_sequence("SYN-02", amplitud=0.5)
    assert "amplitude" in str(exc.value)  # the message lists the accepted names
    with pytest.raises(TypeError, match="k_strat"):
        S.make_pair("SYN-10", k_strat=0.5)
    with pytest.raises(TypeError, match="absent"):
        S.make_scene("SYN-12", absent=(1.0, 2.0))
    with pytest.raises(TypeError, match="swap_range"):  # nested builders (SYN-08 -> SYN-05) reject it too
        S.make_sequence("SYN-08", swap_range=((1, 2),))
    with pytest.raises(TypeError, match="roll"):  # a parameter of another scenario is unknown here
        S.make_sequence("SYN-03", roll_deg=5.0)
    with pytest.raises(TypeError, match="fps"):  # SYN-07 has fps_nominal / fps_second, not fps (BUG-0028)
        S.make_sequence("SYN-07", fps=60.0)


@pytest.mark.parametrize(
    ("scenario", "kwargs", "name"),
    [
        ("SYN-01", {"duration": -1.0}, "duration"),
        ("SYN-01", {"fps": 0.0}, "fps"),
        ("SYN-01", {"scale_px": -5.0}, "scale_px"),
        ("SYN-01", {"noise_px": -1.0}, "noise_px"),
        ("SYN-01", {"score_base": 1.5}, "score_base"),
        ("SYN-01", {"facing": "sideways"}, "facing"),
        ("SYN-02", {"amplitude": 5.0}, "outside the image"),
        ("SYN-05", {"action": "dance"}, "action"),
        ("SYN-05", {"pauses": ((1.0, 2.0), (1.5, 2.5))}, "pauses"),
        ("SYN-05", {"pauses": ((0.1, 0.5),)}, "pauses"),
        ("SYN-05", {"pauses": ((2.0, 1.0),)}, "pauses"),
        ("SYN-05", {"pauses": ((0.5, 4.9),)}, "pauses"),
        ("SYN-06", {"gaps": ((["LWrist"], 9.0, 0.1),)}, "gap"),
        ("SYN-06", {"gaps": ((["LWrist"], 1.0, 0.0),)}, "gap"),
        ("SYN-06", {"gaps": ((["LWrist"], 1.001, 0.01),)}, "no frame"),
        ("SYN-06", {"gaps": ((["Elbowz"], 1.0, 0.1),)}, "joint"),
        ("SYN-06", {"gap_mode": "zero"}, "gap_mode"),
        ("SYN-06", {"short_gap_s": 0.0}, "short_gap_s"),
        ("SYN-07", {"step_down_at": 9.0}, "step_down_at"),
        ("SYN-07", {"jitter_frac": 1.0}, "jitter_frac"),
        ("SYN-07", {"fps_nominal": 0.0}, "fps_nominal"),
        ("SYN-08", {"swap_ranges": ((10, 5),)}, "swap_ranges"),
        ("SYN-08", {"swap_ranges": ((0, 9999),)}, "swap_ranges"),
        ("SYN-09", {"depth_ratio": 0.0}, "depth_ratio"),
        ("SYN-09", {"cam_height_m": 1.5}, "outside the image"),
        ("SYN-04", {"roll_deg": 80.0}, "roll_deg"),
        ("SYN-04", {"scale_px": 500.0}, "outside the image"),
    ],
)
def test_t_syn_04_invalid_values_name_the_parameter(scenario: str, kwargs: dict, name: str):
    with pytest.raises(ValueError, match=name):
        S.make_sequence(scenario, **kwargs)


@pytest.mark.parametrize(
    ("make", "scenario", "kwargs", "name"),
    [
        ("pair", "SYN-10", {"k_start": 0.0}, "k_start"),
        ("pair", "SYN-10", {"k_end": -1.0}, "k_end"),
        ("pair", "SYN-10", {"query_scale": 0.0}, "query_scale"),
        ("scene", "SYN-12", {"absent_s": (3.0, 2.0)}, "absent_s"),
        ("scene", "SYN-12", {"absent_s": (1.0, 9.0)}, "absent_s"),
        ("scene", "SYN-12", {"n_people": 5}, "n_people"),
        ("scene", "SYN-12", {"cross_s": 2.0}, "cross_s"),
        ("scene", "SYN-12", {"absent_s": (1.501, 1.52)}, "absent_s"),  # BUG-0029: no frame inside
    ],
)
def test_t_syn_04_invalid_values_pair_and_scene(make: str, scenario: str, kwargs: dict, name: str):
    with pytest.raises(ValueError, match=name):
        (S.make_pair if make == "pair" else S.make_scene)(scenario, **kwargs)


def test_t_syn_04_time_grid_errors():
    with pytest.raises(ValueError, match="duration must be positive"):
        S.cfr_times(duration=-1.0)
    with pytest.raises(ValueError, match="fps must be positive"):
        S.cfr_times(duration=2.0, fps=0.0)
    with pytest.raises(ValueError, match="rng"):
        S.vfr_times(2.0, jitter_frac=0.2)
    t = S.vfr_times(4.0, 30.0, step_down_at=2.0, fps_second=10.0)
    assert t[0] == 0.0 and np.all(np.diff(t) > 0) and t[-1] <= 4.0 and abs(np.diff(t)[0] - 1 / 30) < 1e-12
    with pytest.raises(ValueError, match="facing"):
        S.neutral_pose(facing="sideways")


# --- speed_at: the speed truth at any time, not only at the frames (P5.06) -----------------------------------------
def test_t_syn_02_speed_at_equals_the_speed_truth_at_the_frames_of_syn05_and_syn07():
    for scenario in ("SYN-05", "SYN-07"):
        seq = S.make_sequence(scenario, seed=4)
        got = S.speed_at(seq, seq.t_sec)
        assert set(got) == set(GROUPS)
        for g in GROUPS:
            assert got[g].dtype == np.float64 and got[g].shape == seq.t_sec.shape
            assert np.allclose(got[g], seq.truth["speed"][g], rtol=0, atol=1e-12), (scenario, g)


def test_t_syn_02_speed_at_between_the_frames_is_the_derivative_of_the_continuous_model():
    seq = S.make_sequence("SYN-05", seed=5, duration=5.0, pauses=PAUSES, ramp_s=0.2)
    dense = dense_motion(duration=5.0, pauses=PAUSES, ramp_s=0.2)
    rng = np.random.default_rng(11)
    idx = rng.integers(150, int(5.0 * DENSE_FPS) - 150, size=300)
    idx = idx[idx % 100 != 0]  # a frame of the 30 fps clip is a multiple of 100 dense rows: these are between frames
    t = idx / DENSE_FPS
    assert np.allclose(dense.t_sec[idx], t)
    got = S.speed_at(seq, t)
    for g in GROUPS:
        assert np.allclose(got[g], dense_group_speed(dense, idx, g), atol=3e-3), g
    assert got["hands"].max() > 0.3  # not a vector of zeros


def test_t_syn_02_speed_at_is_exactly_zero_inside_a_pause_even_between_frames():
    seq = S.make_sequence("SYN-07", seed=6)  # default: one pause from 1.0 to 1.5 s
    got = S.speed_at(seq, np.array([1.0123, 1.2, 1.2999, 1.4999]))
    for g in GROUPS:
        assert np.all(got[g] == 0.0), g


@pytest.mark.parametrize(
    ("times", "message"),
    [
        (np.array([-0.01, 1.0]), "duration"),
        (np.array([1.0, 4.01]), "duration"),
        (np.array([np.nan]), "finite"),
        (np.zeros((2, 2)), "one-dimensional"),
    ],
)
def test_t_syn_02_speed_at_refuses_times_outside_the_sequence_or_not_a_list_of_times(times, message):
    with pytest.raises(ValueError, match=message):
        S.speed_at(S.make_sequence("SYN-07", seed=1), times)


def test_t_syn_02_speed_at_refuses_a_scenario_that_has_no_tempo_motion():
    with pytest.raises(ValueError, match="SYN-02"):
        S.speed_at(S.make_sequence("SYN-02", seed=1), np.array([1.0]))


# --- slow_intervals: where the continuous group speed is below a threshold (P5.07) ----------------------------------
def dense_group_speed_of(seq, group: str) -> tuple[np.ndarray, np.ndarray]:
    """``(t, V)``: the group speed by a 3000 fps central difference of the float64 positions of the continuous model
    (``truth_at``), not of the float32 ones of a sequence (their rounding would flicker at a threshold) and not of the
    analytic derivative that ``speed_at`` gives."""
    h = 1.0 / DENSE_FPS
    t = np.arange(1, int(round(seq.params["duration"] * DENSE_FPS)) - 1) * h
    v = (S.truth_at(seq, t + h) - S.truth_at(seq, t - h)) / (2.0 * h)
    speed = np.hypot(v[..., 0], v[..., 1]) / seq.truth["scale_px"]
    return t, np.median(speed[:, list(GROUPS[group])], axis=1)


def dense_slow_intervals(seq, group: str, tau: float) -> list[tuple[float, float]]:
    """The stretches below ``tau`` of that dense central-difference speed, as ``(first time, last time)``."""
    t, v = dense_group_speed_of(seq, group)
    out, start = [], None
    for k, flag in enumerate(v < tau):
        if flag and start is None:
            start = float(t[k])
        if not flag and start is not None:
            out.append((start, float(t[k - 1])))
            start = None
    if start is not None:
        out.append((start, float(t[-1])))
    return out


def test_t_syn_02_slow_intervals_at_a_very_small_tau_are_the_exact_pauses_and_the_apex_of_the_movement():
    seq = S.make_sequence("SYN-05", seed=1, duration=5.0, pauses=PAUSES, ramp_s=0.2)
    got = S.slow_intervals(seq, "hands", 1e-7)
    assert len(got) == 3  # the two pauses, and between them the apex, where the speed is 0 for an instant (2.5 s)
    for (t0, t1), (p0, p1) in zip((got[0], got[2]), PAUSES, strict=True):
        assert p0 - 5e-4 < t0 <= p0 and p1 <= t1 < p1 + 5e-4  # the ramps leave the speed under 1e-7 a little outside
    assert 2.5 - 1e-5 < got[1][0] <= 2.5 <= got[1][1] < 2.5 + 1e-5  # the apex: phi = 0.5, the speed crosses 0


@pytest.mark.parametrize("group", ["hands", "hips"])
def test_t_syn_02_slow_intervals_equal_the_stretches_of_a_dense_numerical_derivative(group):
    seq = S.make_sequence("SYN-05", seed=2, duration=5.0, pauses=PAUSES, ramp_s=0.2)
    tau = 0.10 * float(dense_group_speed_of(seq, group)[1].max())
    want = dense_slow_intervals(seq, group, tau)
    got = S.slow_intervals(seq, group, tau)
    assert len(want) == 3 and len(got) == 3  # the two pauses and the turning point of the movement between them
    for (g0, g1), (w0, w1) in zip(got, want, strict=True):
        assert abs(g0 - w0) < 2e-3 and abs(g1 - w1) < 2e-3, (g0, g1, w0, w1)
    assert got == tuple(sorted(got)) and all(a1 < b0 for (_, a1), (b0, _) in zip(got, got[1:], strict=False))


def test_t_syn_02_slow_intervals_agree_with_speed_at_at_random_times_away_from_their_edges():
    seq = S.make_sequence("SYN-07", seed=3)
    tau = 0.1 * float(S.speed_at(seq, np.linspace(0.0, 4.0, 4001))["hands"].max())
    got = S.slow_intervals(seq, "hands", tau)
    t = np.random.default_rng(5).uniform(0.0, 4.0, size=2000)
    edges = np.array([e for interval in got for e in interval])
    t = t[np.min(np.abs(t[:, None] - edges[None, :]), axis=1) > 1e-6]
    inside = np.array([any(a <= x <= b for a, b in got) for x in t])
    assert np.array_equal(inside, S.speed_at(seq, t)["hands"] < tau)
    assert 0 < inside.sum() < len(t)  # both outcomes are exercised


def test_t_syn_02_slow_intervals_edges_are_exact_to_a_microsecond_not_to_the_scan_step():
    seq = S.make_sequence("SYN-05", seed=1)
    tau = 0.10 * float(S.speed_at(seq, np.linspace(0.0, 5.0, 5001))["hands"].max())
    got = S.slow_intervals(seq, "hands", tau)
    assert len(got) == 3
    for t0, t1 in got:  # inside the interval the speed is below tau, a microsecond outside it is not (0.2 ms scan)
        inside = S.speed_at(seq, np.array([t0 + 2e-6, t1 - 2e-6]))["hands"] < tau
        outside = S.speed_at(seq, np.array([t0 - 2e-6, t1 + 2e-6]))["hands"] < tau
        assert inside.all() and not outside.any()


def test_t_syn_02_slow_intervals_above_the_peak_are_the_whole_clip_and_the_group_decides():
    seq = S.make_sequence("SYN-05", seed=1)
    peak = float(S.speed_at(seq, np.linspace(0.0, 5.0, 5001))["hands"].max())
    assert S.slow_intervals(seq, "hands", 10 * peak) == ((0.0, 5.0),)
    hips = S.slow_intervals(seq, "hips", 0.5 * peak)  # the hips move at a twentieth of the hands: below it all along
    assert hips == ((0.0, 5.0),)
    assert S.slow_intervals(seq, "feet", 1e-9) == ((0.0, 5.0),)  # the feet never move: 0 is below any tau


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"group": "arms"}, "group"),
        ({"tau": 0.0}, "tau"),
        ({"tau": -1.0}, "tau"),
        ({"tau": float("nan")}, "tau"),
        ({"tau": float("inf")}, "tau"),
        ({"tau": True}, "tau"),
        ({"tau": "0.1"}, "tau"),
    ],
)
def test_t_syn_02_slow_intervals_refuses_a_bad_group_or_threshold(kwargs, message):
    args = {"group": "hands", "tau": 0.1}
    args.update(kwargs)
    with pytest.raises(ValueError, match=message):
        S.slow_intervals(S.make_sequence("SYN-05", seed=1), args["group"], args["tau"])


def test_t_syn_02_slow_intervals_refuses_a_scenario_that_has_no_tempo_motion():
    with pytest.raises(ValueError, match="SYN-02"):
        S.slow_intervals(S.make_sequence("SYN-02", seed=1), "hands", 0.1)
