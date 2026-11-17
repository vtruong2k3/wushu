"""Synthetic HALPE_26 skeleton generator F-SYN for test scenarios (task P0.07, version ``syn/2``).

Test-only: lives under ``tests/helpers/``, is never imported by ``src/taiji_ai`` and never writes a file. Every
object carries ``synthetic=True`` and ``generator_version``.

Conventions
-----------
- Image pixels, x right, **y down**. ``kp`` float32 ``(T, 26, 2)``, ``score`` float32 ``(T, 26)``, ``t_sec`` float64
  ``(T,)`` strictly increasing from 0. NaN = not observed. Joint order = ``taiji_ai.pose.skeleton.JOINTS``.
- The default body faces the camera: the person's left joints (L*) appear on the image right.
- Trunk length ``L`` = |mid-shoulder - mid-hip| = ``scale_px`` in every frame of every scenario except SYN-09
  (camera depth). Adult proportions: hip-to-ankle = 1.7 L, toes 1.82 L below the hip.
- Angles in degrees; theta follows TECH_WORKFLOW Appendix B2: ``atan2(x_S - x_H, y_H - y_S)``, positive when the top
  of the trunk leans to the image right. Camera roll beta uses the same sign.
- Units of truth values: px (image), Lambda (trunk lengths), Lambda/s, s, degrees, m (SYN-09 only).

Truth
-----
The truth comes from the **continuous model** (closed-form phase, analytic velocity, pinhole projection, analytic time
warp), never from the sampled output, so a consumer test cannot pass by repeating the same sampling. The tests check
every truth independently (Appendix B formulas on ``kp_true``, a 3000 fps numerical derivative, pose equality).
``kp_true`` is the noise-free, gap-free, swap-free position. Truth containers are read-only: mappings are
``MappingProxyType``, sequences are tuples (intervals are tuples of tuples), arrays are non-writeable.

Randomness: one ``np.random.default_rng(seed)`` per call, split with ``Generator.spawn``; the global ``numpy`` and
``random`` states are neither read nor changed. Unknown parameters raise ``TypeError`` (no silent default).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

import numpy as np

from taiji_ai.pose.skeleton import GROUND_CANDIDATES, GROUPS, IDX, JOINTS, LR_PAIRS, NUM_JOINTS

SYNTH_VERSION: Final = "syn/2"
DEFAULT_FPS: Final = 30.0
IMAGE_SIZE: Final = (1920, 1080)  # width, height in pixels
SCALE_PX: Final = 200.0  # trunk length (mid-shoulder to mid-hip) in pixels
GROUND_Y_PX: Final = 900.0  # image row of the toes of a person standing on the ground line
FOOT_DROP: Final = 1.82  # toes below the mid-hip, in trunk lengths
TRUNK_M: Final = 0.5  # physical trunk length used by the pinhole scenario, metres
SHORT_GAP_S: Final = 0.150  # plan W6: gaps up to 150 ms are bridged by interpolation
ACTIONS: Final = ("raise_lower", "open_close")

# Tolerances for downstream tests (IMPLEMENTATION_PLAN §14.3; decision DEC-0013). Changing one needs a reason in the PR.
TOLERANCES: Final[dict[str, Any]] = {
    "SYN-02": {"range_relative_error": 0.05},
    "SYN-03": {"median_theta_error_deg": 0.5},
    "SYN-04": {"median_theta_error_deg": 0.5},
    "SYN-05": {"max_boundary_error_frames": 1},
    "SYN-06": {"short_gap_max_error_px": 2.0, "long_gap_all_nan": True},
    "SYN-07": {"median_speed_relative_error": 0.05},
    "SYN-08": {"exact_swap_flags": True},
    # SYN-09: the metric must reproduce the truth of BOTH variants; which one is smaller depends on the camera
    # geometry and is a measured outcome, not an assumption (BUG-0022, P0.07 §9).
    "SYN-09": {"range_abs_error_lambda": 0.02, "variant_order_asserted": False},
    "SYN-10": {"shape_distance_max": 0.02, "median_rate_k_relative_error": 0.10},
    "SYN-11": {"variant_closer_ratio": 2.0},
    "SYN-12": {"identity_swaps": 0, "max_boundary_error_frames": 1},
}


# --- helpers: freezing, validation -------------------------------------------------------------------------------
def _freeze(obj: Any) -> Any:
    """Deep read-only copy: arrays non-writeable, mappings read-only, lists to tuples, numpy scalars to Python."""
    if isinstance(obj, np.ndarray):
        arr = obj.copy()
        arr.flags.writeable = False
        return arr
    if isinstance(obj, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in obj.items()})
    if isinstance(obj, list | tuple):
        return tuple(_freeze(v) for v in obj)
    if isinstance(obj, np.floating | np.integer | np.bool_):
        return obj.item()
    return obj


def _freeze_fields(obj: Any, arrays: Sequence[str]) -> None:
    for name in arrays:
        getattr(obj, name).flags.writeable = False
    for name in ("truth", "params"):
        object.__setattr__(obj, name, _freeze(getattr(obj, name)))


def _num(p: Mapping[str, Any], name: str) -> float:
    v = p[name]
    if isinstance(v, bool) or not isinstance(v, int | float | np.integer | np.floating) or not math.isfinite(v):
        raise ValueError(f"{name} must be a finite number, got {v!r}")
    return float(v)


def _positive(p: Mapping[str, Any], name: str) -> float:
    v = _num(p, name)
    if v <= 0:
        raise ValueError(f"{name} must be positive, got {v}")
    return v


def _pair(p: Mapping[str, Any], name: str) -> tuple[float, float]:
    v = p[name]
    if not isinstance(v, Sequence) or isinstance(v, str) or len(v) != 2:
        raise ValueError(f"{name} must be a pair of numbers, got {v!r}")
    return float(v[0]), float(v[1])


def _check_common(p: Mapping[str, Any], fps_name: str = "fps") -> None:
    _positive(p, "duration")
    _positive(p, fps_name)
    _positive(p, "scale_px")
    if _num(p, "noise_px") < 0:
        raise ValueError(f"noise_px must be >= 0, got {p['noise_px']}")
    if not 0.0 <= _num(p, "score_base") <= 1.0:
        raise ValueError(f"score_base must be in [0, 1], got {p['score_base']}")
    if p["facing"] not in ("camera", "away"):
        raise ValueError(f"facing must be 'camera' or 'away', got {p['facing']!r}")


def _require_in_image(kp: np.ndarray, scenario: str) -> None:
    x, y = kp[..., 0], kp[..., 1]
    if np.nanmin(x) < 0 or np.nanmax(x) > IMAGE_SIZE[0] or np.nanmin(y) < 0 or np.nanmax(y) > IMAGE_SIZE[1]:
        raise ValueError(
            f"{scenario}: the chosen parameters put joints outside the image ({IMAGE_SIZE[0]}x{IMAGE_SIZE[1]} px); "
            "reduce scale_px, amplitude or the camera height"
        )


def _rngs(seed: int, n: int) -> list[np.random.Generator]:
    return list(np.random.default_rng(seed).spawn(n))


# --- output types -----------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SynthSequence:
    """One synthetic sequence with its ground truth (all arrays read-only)."""

    kp: np.ndarray  # (T, 26, 2) float32 image px, y down; NaN = not observed
    score: np.ndarray  # (T, 26) float32 in [0, 1]
    t_sec: np.ndarray  # (T,) float64, strictly increasing, t_sec[0] == 0
    truth: Mapping[str, Any]  # scenario answer (units in the module docstring and SCENARIOS)
    kp_true: np.ndarray  # (T, 26, 2) float32 noise-free, gap-free, swap-free positions
    scenario: str
    seed: int
    params: Mapping[str, Any]
    generator_version: str = SYNTH_VERSION
    synthetic: bool = True

    def __post_init__(self) -> None:
        _freeze_fields(self, ("kp", "score", "t_sec", "kp_true"))


@dataclass(frozen=True)
class SynthPair:
    """Reference and query sequences for comparison tests (SYN-10, SYN-11)."""

    ref: SynthSequence
    query: SynthSequence
    truth: Mapping[str, Any]
    scenario: str
    seed: int
    params: Mapping[str, Any]
    generator_version: str = SYNTH_VERSION
    synthetic: bool = True

    def __post_init__(self) -> None:
        _freeze_fields(self, ())


@dataclass(frozen=True)
class SynthScene:
    """Several people per frame in shuffled detection order (SYN-12)."""

    kp: np.ndarray  # (T, N, 26, 2) float32; NaN in empty slots
    score: np.ndarray  # (T, N, 26) float32; 0 in empty slots
    bbox: np.ndarray  # (T, N, 4) float32 xyxy px; NaN in empty slots
    t_sec: np.ndarray  # (T,) float64
    truth: Mapping[str, Any]
    scenario: str
    seed: int
    params: Mapping[str, Any]
    generator_version: str = SYNTH_VERSION
    synthetic: bool = True

    def __post_init__(self) -> None:
        _freeze_fields(self, ("kp", "score", "bbox", "t_sec"))


@dataclass(frozen=True)
class ScenarioSpec:
    kind: str  # "sequence", "pair" or "scene"
    builder: Callable[[int, Mapping[str, Any]], Any]
    default_params: Mapping[str, Any]  # every accepted parameter name with its default
    truth_keys: tuple[str, ...]
    doc: str


# --- body template -----------------------------------------------------------------------------------------------
_UPPER_NAMES: Final = (
    "Nose", "LEye", "REye", "LEar", "REar", "LShoulder", "RShoulder", "LElbow", "RElbow", "LWrist", "RWrist",
    "Head", "Neck", "Hip", "LHip", "RHip",
)  # fmt: skip
_UPPER_IDX: Final = tuple(sorted(IDX[n] for n in _UPPER_NAMES))
_LEAN_IDX: Final = tuple(i for i in _UPPER_IDX if i not in (IDX["Hip"], IDX["LHip"], IDX["RHip"]))


def _template(facing: str) -> np.ndarray:
    """Neutral standing pose in trunk lengths: origin at the mid-hip, x right, y down (float64)."""
    pts = np.zeros((NUM_JOINTS, 2))

    def put(name: str, x: float, y: float) -> None:
        pts[IDX[name]] = (x, y)

    put("Hip", 0.0, 0.0)
    put("Neck", 0.0, -1.05)
    put("Nose", 0.0, -1.25)
    put("Head", 0.0, -1.35)
    for side, s in (("L", 1.0), ("R", -1.0)):
        put(f"{side}Hip", 0.20 * s, 0.0)
        put(f"{side}Shoulder", 0.35 * s, -1.00)
        put(f"{side}Eye", 0.06 * s, -1.28)
        put(f"{side}Ear", 0.14 * s, -1.26)
        put(f"{side}Elbow", 0.40 * s, -0.40)
        put(f"{side}Wrist", 0.42 * s, 0.14)
        put(f"{side}Knee", 0.20 * s, 0.85)
        put(f"{side}Ankle", 0.20 * s, 1.70)
        put(f"{side}Heel", 0.20 * s, 1.80)
        put(f"{side}BigToe", 0.20 * s, FOOT_DROP)
        put(f"{side}SmallToe", 0.25 * s, FOOT_DROP)
    if facing == "away":
        pts[:, 0] *= -1.0
    return pts


def neutral_pose(
    scale_px: float = SCALE_PX,
    origin: tuple[float, float] | None = None,
    facing: str = "camera",
) -> np.ndarray:
    """Neutral standing pose, float64 ``(26, 2)`` image px (y down); ``origin`` is the mid-hip.

    The trunk length is exactly ``scale_px``. Default origin: x = 960, feet on the ground line ``GROUND_Y_PX``.
    ``facing="camera"``: the person's left joints appear on the image right; ``"away"`` mirrors the body.
    """
    if facing not in ("camera", "away"):
        raise ValueError(f"facing must be 'camera' or 'away', got {facing!r}")
    if scale_px <= 0:
        raise ValueError(f"scale_px must be positive, got {scale_px}")
    ox, oy = origin if origin is not None else (IMAGE_SIZE[0] / 2.0, GROUND_Y_PX - FOOT_DROP * scale_px)
    return _template(facing) * float(scale_px) + np.array([ox, oy], dtype=np.float64)


# --- time grids -------------------------------------------------------------------------------------------------
def cfr_times(duration: float, fps: float = DEFAULT_FPS) -> np.ndarray:
    """Constant-frame-rate timestamps ``k / fps`` for ``round(duration * fps)`` frames, starting at 0."""
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    return np.arange(max(int(round(duration * fps)), 1), dtype=np.float64) / float(fps)


def vfr_times(
    duration: float,
    fps_nominal: float = DEFAULT_FPS,
    *,
    step_down_at: float | None = None,
    fps_second: float = 10.0,
    jitter_frac: float = 0.0,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Variable-frame-rate timestamps from 0 to at most ``duration`` (strictly increasing).

    ``step_down_at``: the rate drops from ``fps_nominal`` to ``fps_second`` after that time (like the F-VID video).
    ``jitter_frac``: each interval is multiplied by ``1 + U(-j, j)`` (needs ``rng``).
    """
    if duration <= 0 or fps_nominal <= 0 or fps_second <= 0:
        raise ValueError("duration, fps_nominal and fps_second must be positive")
    if not 0.0 <= jitter_frac < 1.0:
        raise ValueError(f"jitter_frac must be in [0, 1), got {jitter_frac}")
    if step_down_at is not None:
        if not 0.0 < step_down_at < duration:
            raise ValueError(f"step_down_at must be inside (0, duration={duration}), got {step_down_at}")
        n1 = max(int(round(step_down_at * fps_nominal)), 1)
        t1 = np.arange(n1, dtype=np.float64) / fps_nominal
        n2 = int(math.floor((duration - t1[-1]) * fps_second + 1e-9))
        t = np.concatenate([t1, t1[-1] + np.arange(1, n2 + 1, dtype=np.float64) / fps_second])
    else:
        t = cfr_times(duration, fps_nominal)
    if jitter_frac > 0:
        if rng is None:
            raise ValueError("jitter_frac > 0 needs an rng (pass np.random.default_rng(seed))")
        dt = np.diff(t) * (1.0 + rng.uniform(-jitter_frac, jitter_frac, size=len(t) - 1))
        t = np.concatenate([[0.0], np.cumsum(dt)])
        t = t[t <= duration]
    return t


def truth_at(seq: SynthSequence, t: np.ndarray) -> np.ndarray:
    """The noise-free positions (float64, ``(len(t), 26, 2)``) of a SYN-05 or SYN-07 sequence's motion at any times.

    The motion is analytic in time (``_motion``), so the truth exists between the rows too: the check of a resampling
    needs it at grid times that are not rows. ``t`` must lie inside ``[0, duration]`` of the sequence.
    """
    times = np.asarray(t, dtype=np.float64)
    return _motion(times, seq.params, pauses=seq.params["pauses"])[0]


_TEMPO_SCENARIOS: Final = ("SYN-05", "SYN-06", "SYN-07", "SYN-08")  # the scenarios that share ``_motion``


def speed_at(seq: SynthSequence, t: np.ndarray) -> dict[str, np.ndarray]:
    """The analytic group speed truth (Appendix B3: the median over the joints of ``|v| / Lambda``, Lambda/s) of a
    SYN-05 to SYN-08 sequence's motion at any times ``t`` in ``[0, duration]``, as ``{group: (len(t),) float64}``.

    ``seq.truth["speed"]`` is the same truth at the frames; this gives it where there is no frame, for example at the
    times of the uniform grid that a variable-frame-rate video is resampled to. The speed is exactly 0 inside a pause.
    """
    if seq.scenario not in _TEMPO_SCENARIOS:
        raise ValueError(f"speed_at needs a tempo scenario {_TEMPO_SCENARIOS}, got {seq.scenario}")
    times = np.asarray(t, dtype=np.float64)
    if times.ndim != 1 or not np.isfinite(times).all():
        raise ValueError(f"t must be a one-dimensional array of finite times, got shape {times.shape}")
    duration = float(seq.params["duration"])
    if times.size and (times.min() < -1e-9 or times.max() > duration + 1e-9):
        raise ValueError(f"t must lie inside [0, duration] = [0, {duration}] s, got [{times.min()}, {times.max()}]")
    speed = _motion(np.clip(times, 0.0, duration), seq.params, pauses=seq.params["pauses"])[1]["speed"]
    return {group: np.array(values, dtype=np.float64) for group, values in speed.items()}


_SLOW_SCAN_S: Final = 2e-4  # the scan of ``slow_intervals``: a stretch shorter than this can be missed
_SLOW_BISECTIONS: Final = 45  # 2e-4 s halved 45 times is far below a nanosecond


def slow_intervals(seq: SynthSequence, group: str, tau: float) -> tuple[tuple[float, float], ...]:
    """The maximal intervals ``(t0, t1)`` of ``[0, duration]`` where the analytic group speed is below ``tau``.

    The truth of a pause (Appendix B3: ``V_G < tau``) for a SYN-05 to SYN-08 sequence: it is the stretches of
    ``speed_at(seq, t)[group] < tau`` of the continuous motion, not the generator's exact pauses (``pause_intervals``,
    where the speed is 0), which are shorter by the ramps and which leave out the turning point of the movement.
    ``tau`` is in Lambda/s. The speed is scanned every 0.2 ms and each edge is refined by bisection, so an edge is
    exact to far below a nanosecond; a stretch shorter than the scan (a threshold the speed barely goes under) can be
    missed. An interval that reaches the start or the end of the clip ends there.
    """
    if group not in GROUPS:
        raise ValueError(f"group must be one of {tuple(GROUPS)}, got {group!r}")
    if isinstance(tau, bool) or not isinstance(tau, int | float) or not math.isfinite(tau) or tau <= 0:
        raise ValueError(f"tau must be a finite number above 0, got {tau!r}")

    def below(times: np.ndarray) -> np.ndarray:
        return speed_at(seq, times)[group] < tau

    duration = float(seq.params["duration"])
    grid = np.linspace(0.0, duration, int(math.ceil(duration / _SLOW_SCAN_S)) + 1)
    flags = below(grid)
    crossing = np.flatnonzero(flags[1:] != flags[:-1])  # the edge lies between grid[i] and grid[i + 1]
    lo, hi, was_below = grid[crossing].copy(), grid[crossing + 1].copy(), flags[crossing]
    for _ in range(_SLOW_BISECTIONS):
        middle = 0.5 * (lo + hi)
        same = below(middle) == was_below  # still on the side of ``lo``
        lo, hi = np.where(same, middle, lo), np.where(same, hi, middle)
    edges = 0.5 * (lo + hi)
    out: list[tuple[float, float]] = []
    start: float | None = 0.0 if flags[0] else None
    for edge, leaves in zip(edges, was_below, strict=True):
        if leaves:  # the speed was below and now is not: an interval ends
            out.append((float(start), float(edge)))  # type: ignore[arg-type]
            start = None
        else:
            start = float(edge)
    if start is not None:
        out.append((start, duration))
    return tuple(out)


# --- modifiers --------------------------------------------------------------------------------------------------
def add_noise(kp: np.ndarray, sigma_px: float, rng: np.random.Generator) -> np.ndarray:
    """Add i.i.d. Gaussian noise (px) to every finite coordinate; NaN stays NaN. Returns a float64 copy."""
    out = np.array(kp, dtype=np.float64, copy=True)
    if sigma_px > 0:
        out += np.where(np.isfinite(out), rng.normal(0.0, sigma_px, size=out.shape), 0.0)
    return out


def apply_gaps(
    kp: np.ndarray,
    score: np.ndarray,
    gaps: Sequence[tuple[Sequence[int | str], float, float]],
    t_sec: np.ndarray,
    mode: str = "nan",
    short_gap_s: float = SHORT_GAP_S,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """Remove joints for a time span. ``gaps``: ``(joints, t_start_s, duration_s)`` with names or indices.

    ``mode="nan"``: coordinates NaN, score 0 (exercises gap filling, P4.02). ``"low_score"``: score 0.05 (< tau_kp 0.3)
    and coordinates jittered by 15 px (exercises the mask, P4.01; needs ``rng``).
    Each gap is reported with both duration definitions (D2): ``missing_s`` = missing frames x median dt and
    ``bridge_s`` = time from the last valid frame before to the first valid frame after. A gap at the first or last
    frame cannot be bridged: ``bridgeable=False``, ``bridge_s=None``, ``kind="unbridgeable"``.
    """
    if mode not in ("nan", "low_score"):
        raise ValueError(f"gap_mode must be 'nan' or 'low_score', got {mode!r}")
    if mode == "low_score" and rng is None:
        raise ValueError("gap_mode 'low_score' needs an rng")
    if short_gap_s <= 0:
        raise ValueError(f"short_gap_s must be positive, got {short_gap_s}")
    kp_out, score_out = np.array(kp, copy=True), np.array(score, copy=True)
    dt = float(np.median(np.diff(t_sec))) if len(t_sec) > 1 else 1.0 / DEFAULT_FPS
    out: list[dict[str, Any]] = []
    for joint_spec, t0, dur in gaps:
        if not 0.0 <= t0 <= t_sec[-1]:
            raise ValueError(f"gap start t0={t0} s is outside the clip [0, {t_sec[-1]:.4f}] s")
        if dur <= 0:
            raise ValueError(f"gap duration must be positive, got {dur}")
        joints: list[int] = []
        for j in joint_spec:
            idx = IDX.get(j) if isinstance(j, str) else (int(j) if 0 <= int(j) < NUM_JOINTS else None)
            if idx is None:
                raise ValueError(f"unknown joint {j!r} in gap at t0={t0} s")
            joints.append(idx)
        mask = (t_sec >= t0 - 1e-9) & (t_sec < t0 + dur - 1e-9)
        frames = np.flatnonzero(mask)
        if len(frames) == 0:
            raise ValueError(f"gap at t0={t0} s (duration {dur} s) contains no frame")
        i0, i1 = int(frames[0]), int(frames[-1])
        for j in joints:
            if mode == "nan":
                kp_out[mask, j, :] = np.nan
                score_out[mask, j] = 0.0
            else:
                assert rng is not None
                kp_out[mask, j, :] = kp_out[mask, j, :] + rng.normal(0.0, 15.0, size=(len(frames), 2))
                score_out[mask, j] = 0.05
        missing_s = len(frames) * dt
        bridgeable = i0 > 0 and i1 < len(t_sec) - 1
        bridge_s = float(t_sec[i1 + 1] - t_sec[i0 - 1]) if bridgeable else None
        out.append(
            {
                "joints": tuple(JOINTS[j] for j in joints),
                "frames": (i0, i1),
                "n_missing": len(frames),
                "missing_s": missing_s,
                "bridge_s": bridge_s,
                "bridgeable": bridgeable,
                "kind": ("short" if bridge_s <= short_gap_s else "long") if bridge_s is not None else "unbridgeable",
                "kind_missing": "short" if missing_s <= short_gap_s else "long",
                "t0": float(t0),
                "dur": float(dur),
            }
        )
    return kp_out, score_out, out


def apply_lr_swap(kp: np.ndarray, score: np.ndarray, swap_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Exchange the two sides of every ``LR_PAIRS`` pair (keypoints and scores) in the frames of ``swap_mask``."""
    perm = np.arange(NUM_JOINTS)
    for a, b in LR_PAIRS:
        perm[a], perm[b] = b, a
    kp_out, score_out = np.array(kp, copy=True), np.array(score, copy=True)
    kp_out[swap_mask] = kp_out[swap_mask][:, perm]
    score_out[swap_mask] = score_out[swap_mask][:, perm]
    return kp_out, score_out


def apply_roll(kp: np.ndarray, beta_deg: float, centre: tuple[float, float]) -> np.ndarray:
    """Rotate image coordinates by ``beta_deg`` about ``centre`` (px, y down): positive moves the top to the right."""
    theta = math.radians(beta_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    out = np.array(kp, dtype=np.float64, copy=True)
    x, y = out[..., 0] - centre[0], out[..., 1] - centre[1]
    out[..., 0] = centre[0] + x * cos_t - y * sin_t
    out[..., 1] = centre[1] + x * sin_t + y * cos_t
    return out


# --- continuous motion model ------------------------------------------------------------------------------------
# Motion = pose(phi(t)). phi is the normalised integral of a speed factor s(t) that is exactly 0 inside the pauses and
# follows cosine ramps before and after them. The integral has a closed form, so poses, velocities and speeds do not
# depend on the sampling grid (frame rate, VFR). Pose and velocity are analytic in phi.
def _check_pauses(pauses: Sequence[Sequence[float]], ramp_s: float, duration: float) -> tuple[tuple[float, float], ...]:
    if ramp_s < 0:
        raise ValueError(f"ramp_s must be >= 0, got {ramp_s}")
    clean: list[tuple[float, float]] = []
    for item in pauses:
        if len(item) != 2:
            raise ValueError(f"pauses must be (start, end) pairs, got {item!r}")
        p0, p1 = float(item[0]), float(item[1])
        if not p0 < p1:
            raise ValueError(f"pauses: start must be before end, got ({p0}, {p1})")
        if p0 - ramp_s < 0 or p1 + ramp_s > duration:
            raise ValueError(f"pauses: ({p0}, {p1}) with ramp_s={ramp_s} does not fit in the clip [0, {duration}] s")
        clean.append((p0, p1))
    clean.sort()
    for (_, e0), (s1, _) in zip(clean, clean[1:], strict=False):
        if s1 - ramp_s < e0 + ramp_s:
            raise ValueError(f"pauses: the ramps of consecutive pauses overlap ({e0} -> {s1}, ramp_s={ramp_s})")
    return tuple(clean)


def _lost(t: np.ndarray, p0: float, p1: float, r: float) -> np.ndarray:
    """Progress lost to one pause up to time t: the integral of (1 - s) from 0 to t (closed form)."""
    out = np.zeros_like(t)
    half = 0.5 * r
    m = (t > p0 - r) & (t <= p0)
    x = (t[m] - (p0 - r)) / r if r > 0 else t[m]
    out[m] = half * (x - np.sin(np.pi * x) / np.pi)
    m = (t > p0) & (t <= p1)
    out[m] = half + (t[m] - p0)
    m = (t > p1) & (t <= p1 + r)
    u = (t[m] - p1) / r if r > 0 else t[m]
    out[m] = half + (p1 - p0) + half * (u + np.sin(np.pi * u) / np.pi)
    out[t > p1 + r] = r + (p1 - p0)
    return out


def _progress(t: np.ndarray, pauses: Sequence[tuple[float, float]], r: float) -> np.ndarray:
    """F(t) = integral of the speed factor; bit-identical for every t inside a pause."""
    t_eff = np.array(t, dtype=np.float64, copy=True)
    for p0, p1 in pauses:
        t_eff[(t > p0) & (t <= p1)] = p0
    f = t_eff.copy()
    for p0, p1 in pauses:
        f -= _lost(t_eff, p0, p1, r)
    return f


def _speed_factor(t: np.ndarray, pauses: Sequence[tuple[float, float]], r: float) -> np.ndarray:
    s = np.ones_like(t, dtype=np.float64)
    for p0, p1 in pauses:
        s[(t >= p0) & (t <= p1)] = 0.0
        if r > 0:
            m = (t > p0 - r) & (t < p0)
            s[m] = 0.5 * (1.0 - np.cos(np.pi * (p0 - t[m]) / r))
            m = (t > p1) & (t < p1 + r)
            s[m] = 0.5 * (1.0 - np.cos(np.pi * (t[m] - p1) / r))
    return s


def _phase(
    t: np.ndarray, pauses: Sequence[tuple[float, float]], ramp_s: float, duration: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(phi, dphi/dt, s)`` at the times ``t``; phi runs from 0 to just below 1 over ``duration``."""
    f_total = float(_progress(np.array([duration]), pauses, ramp_s)[0])
    if f_total <= 0.05 * duration:
        raise ValueError(f"pauses leave no time for motion (moving time {f_total:.3f} s of {duration} s)")
    s = _speed_factor(t, pauses, ramp_s)
    return _progress(t, pauses, ramp_s) / f_total, s / f_total, s


def _displacements(action: str, facing: str) -> np.ndarray:
    """Displacement of every joint per unit ``psi = sin(pi * phi)``, in trunk lengths, ``(26, 2)``."""
    d = np.zeros((NUM_JOINTS, 2))
    if action == "raise_lower":  # arms rise in front, the body sinks a little, knees bend; the trunk stays rigid
        for n in _UPPER_NAMES:
            d[IDX[n], 1] += 0.08
        for n in ("LKnee", "RKnee"):
            d[IDX[n], 1] += 0.04
        for n in ("LWrist", "RWrist"):
            d[IDX[n], 1] -= 1.10
        for n in ("LElbow", "RElbow"):
            d[IDX[n], 1] -= 0.55
    elif action == "open_close":  # arms open sideways (outward whichever way the body faces) and close
        sign = 1.0 if facing == "camera" else -1.0
        d[IDX["LWrist"], 0] += 0.60 * sign
        d[IDX["RWrist"], 0] -= 0.60 * sign
        d[IDX["LElbow"], 0] += 0.30 * sign
        d[IDX["RElbow"], 0] -= 0.30 * sign
    else:
        raise ValueError(f"action must be one of {ACTIONS}, got {action!r}")
    return d


def _pose_from_phase(
    phi: np.ndarray, *, action: str, scale_px: float, facing: str, origin: tuple[float, float] | None = None
) -> np.ndarray:
    """Positions (px, float64) ``(T, 26, 2)`` at the motion phases ``phi``: the one pose function of the module."""
    base = neutral_pose(scale_px, origin, facing)
    psi = np.sin(np.pi * np.asarray(phi, dtype=np.float64))
    return base[None] + psi[:, None, None] * (_displacements(action, facing) * scale_px)[None]


def _velocity_from_phase(
    phi: np.ndarray, phi_dot: np.ndarray, *, action: str, scale_px: float, facing: str
) -> np.ndarray:
    """Analytic joint velocity (px/s) ``(T, 26, 2)``: d pose / d phi times dphi/dt."""
    gain = np.pi * np.cos(np.pi * np.asarray(phi, dtype=np.float64)) * phi_dot
    return gain[:, None, None] * (_displacements(action, facing) * scale_px)[None]


def _group_speeds(vel: np.ndarray, scale_px: float) -> dict[str, np.ndarray]:
    """Appendix B3 group speed: median over the joints of the group of |v| / Lambda (Lambda = trunk length)."""
    speed = np.hypot(vel[..., 0], vel[..., 1]) / scale_px
    return {g: np.median(speed[:, list(idx)], axis=1) for g, idx in GROUPS.items()}


def _motion(
    t: np.ndarray, p: Mapping[str, Any], *, pauses: Sequence[Sequence[float]]
) -> tuple[np.ndarray, dict[str, Any]]:
    """Noise-free positions (float64) and the tempo truth of the motion sampled at ``t``."""
    ramp_s, duration, scale_px = float(p["ramp_s"]), float(p["duration"]), float(p["scale_px"])
    clean = _check_pauses(pauses, ramp_s, duration)
    phi, phi_dot, s = _phase(t, clean, ramp_s, duration)
    kw = {"action": p["action"], "scale_px": scale_px, "facing": p["facing"]}
    kp = _pose_from_phase(phi, **kw)
    speed = _group_speeds(_velocity_from_phase(phi, phi_dot, **kw), scale_px)
    pause_frames = []
    for p0, p1 in clean:
        frames = np.flatnonzero((t >= p0 - 1e-9) & (t <= p1 + 1e-9))
        if len(frames):
            pause_frames.append((int(frames[0]), int(frames[-1])))
    truth = {
        "pause_intervals": clean,
        "pause_frames": tuple(pause_frames),
        "n_pauses": len(clean),
        "speed": speed,
        "speed_profile": s,
        "phase": phi,
        "scale_px": scale_px,
    }
    return kp, truth


def _sequence(
    scenario: str,
    seed: int,
    p: Mapping[str, Any],
    t: np.ndarray,
    kp_true: np.ndarray,
    truth: dict[str, Any],
    kp: np.ndarray | None = None,
    score: np.ndarray | None = None,
) -> SynthSequence:
    _require_in_image(kp_true, scenario)
    if score is None:
        score = np.full((len(t), NUM_JOINTS), float(p["score_base"]), dtype=np.float32)
    return SynthSequence(
        kp=(kp_true if kp is None else kp).astype(np.float32),
        score=score.astype(np.float32),
        t_sec=np.asarray(t, dtype=np.float64),
        truth=truth,
        kp_true=kp_true.astype(np.float32),
        scenario=scenario,
        seed=seed,
        params=dict(p),
    )


# --- scenario builders ------------------------------------------------------------------------------------------
def build_syn_01(seed: int, p: Mapping[str, Any]) -> SynthSequence:
    """SYN-01: standing still + i.i.d. noise. Truth: no motion at all, hence one pause over the whole clip."""
    _check_common(p)
    (noise_rng,) = _rngs(seed, 1)
    t = cfr_times(p["duration"], p["fps"])
    kp_true = np.tile(neutral_pose(p["scale_px"], facing=p["facing"]), (len(t), 1, 1))
    truth = {
        "hip_range": 0.0,
        "speed": {g: np.zeros(len(t)) for g in GROUPS},
        "pause_intervals": ((0.0, float(t[-1])),),
        "pause_frames": ((0, len(t) - 1),),
        "n_pauses": 1,
        "scale_px": float(p["scale_px"]),
    }
    return _sequence("SYN-01", seed, p, t, kp_true, truth, add_noise(kp_true, p["noise_px"], noise_rng))


def build_syn_02(seed: int, p: Mapping[str, Any]) -> SynthSequence:
    """SYN-02: upper body and hips oscillate vertically by ``A * Lambda * sin(2 pi f t)`` (feet fixed, knees half)."""
    _check_common(p)
    (noise_rng,) = _rngs(seed, 1)
    t = cfr_times(p["duration"], p["fps"])
    amp, freq, scale = _num(p, "amplitude"), _positive(p, "freq"), float(p["scale_px"])
    dy = -amp * scale * np.sin(2.0 * np.pi * freq * t)  # negative = up (y down)
    kp_true = np.tile(neutral_pose(scale, facing=p["facing"]), (len(t), 1, 1))
    kp_true[:, list(_UPPER_IDX), 1] += dy[:, None]
    kp_true[:, [IDX["LKnee"], IDX["RKnee"]], 1] += 0.5 * dy[:, None]
    truth = {
        "A": amp,
        "f": freq,
        "nominal_range": 2.0 * abs(amp),
        # P95 - P5 of A sin(.) over whole periods is 2 A sin(0.45 pi), not 2 A
        "expected_range_p95_p5": 2.0 * abs(amp) * math.sin(0.45 * math.pi),
        "hip_y": neutral_pose(scale, facing=p["facing"])[IDX["Hip"], 1] + dy,
        "scale_px": scale,
    }
    return _sequence("SYN-02", seed, p, t, kp_true, truth, add_noise(kp_true, p["noise_px"], noise_rng))


def _lean(t: np.ndarray, p: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Body with the upper joints rotated about the mid-hip by theta(t); returns positions and theta (degrees)."""
    scale = float(p["scale_px"])
    if p["theta_deg"] is not None:
        theta = np.full(len(t), _num(p, "theta_deg"))
    else:
        theta = _num(p, "theta_from") + (_num(p, "theta_to") - _num(p, "theta_from")) * t / float(p["duration"])
    base = neutral_pose(scale, facing=p["facing"])
    hip = 0.5 * (base[IDX["LHip"]] + base[IDX["RHip"]])
    c, s = np.cos(np.radians(theta))[:, None], np.sin(np.radians(theta))[:, None]
    rel = base[list(_LEAN_IDX)] - hip
    kp = np.tile(base, (len(t), 1, 1))
    kp[:, list(_LEAN_IDX), 0] = hip[0] + rel[:, 0] * c - rel[:, 1] * s  # clockwise in image space: top goes right
    kp[:, list(_LEAN_IDX), 1] = hip[1] + rel[:, 0] * s + rel[:, 1] * c
    return kp, theta


def build_syn_03(seed: int, p: Mapping[str, Any]) -> SynthSequence:
    """SYN-03: known trunk lean theta(t): constant (``theta_deg``) or linear in time (from/to)."""
    _check_common(p)
    (noise_rng,) = _rngs(seed, 1)
    t = cfr_times(p["duration"], p["fps"])
    kp_true, theta = _lean(t, p)
    truth = {"theta_deg": theta, "median_theta_deg": float(np.median(theta)), "scale_px": float(p["scale_px"])}
    return _sequence("SYN-03", seed, p, t, kp_true, truth, add_noise(kp_true, p["noise_px"], noise_rng))


def build_syn_04(seed: int, p: Mapping[str, Any]) -> SynthSequence:
    """SYN-04: the SYN-03 body, then the whole image rotated by the camera roll beta about ``centre``."""
    _check_common(p)
    beta = _num(p, "roll_deg")
    if abs(beta) > 45.0:
        raise ValueError(f"roll_deg must be within +-45 degrees, got {beta}")
    centre = _pair(p, "centre")
    (noise_rng,) = _rngs(seed, 1)
    t = cfr_times(p["duration"], p["fps"])
    body, theta = _lean(t, p)
    kp_true = apply_roll(body, beta, centre)
    line = apply_roll(np.array([[centre[0], centre[1] - 200.0], [centre[0], centre[1] + 200.0]]), beta, centre)
    truth = {
        "roll_deg": beta,
        "theta_body_deg": theta,
        "theta_raw_deg": theta + beta,  # what a metric without roll correction measures
        "vertical_line": line,  # two image points (top, bottom) of a true vertical line
        "scale_px": float(p["scale_px"]),
    }
    return _sequence("SYN-04", seed, p, t, kp_true, truth, add_noise(kp_true, p["noise_px"], noise_rng))


def build_syn_05(seed: int, p: Mapping[str, Any]) -> SynthSequence:
    """SYN-05: an action driven by a speed profile with exact zero-speed pauses and cosine ramps."""
    _check_common(p)
    (noise_rng,) = _rngs(seed, 1)
    t = cfr_times(p["duration"], p["fps"])
    kp_true, truth = _motion(t, p, pauses=p["pauses"])
    return _sequence("SYN-05", seed, p, t, kp_true, truth, add_noise(kp_true, p["noise_px"], noise_rng))


def build_syn_06(seed: int, p: Mapping[str, Any]) -> SynthSequence:
    """SYN-06: the SYN-05 motion with joint gaps (short and long by default, both inside the motion)."""
    _check_common(p)
    noise_rng, gap_rng = _rngs(seed, 2)
    t = cfr_times(p["duration"], p["fps"])
    kp_true, truth = _motion(t, p, pauses=p["pauses"])
    kp, score, gaps = apply_gaps(
        add_noise(kp_true, p["noise_px"], noise_rng),
        np.full((len(t), NUM_JOINTS), float(p["score_base"])),
        [(tuple(g[0]), float(g[1]), float(g[2])) for g in p["gaps"]],
        t,
        mode=p["gap_mode"],
        short_gap_s=_positive(p, "short_gap_s"),
        rng=gap_rng,
    )
    truth["gaps"] = gaps
    return _sequence("SYN-06", seed, p, t, kp_true, truth, kp, score)


def build_syn_07(seed: int, p: Mapping[str, Any]) -> SynthSequence:
    """SYN-07: the SYN-05 motion sampled at variable-frame-rate timestamps (the motion does not depend on them)."""
    _check_common(p, "fps_nominal")
    _positive(p, "fps_second")
    noise_rng, time_rng = _rngs(seed, 2)
    t = vfr_times(
        p["duration"],
        p["fps_nominal"],
        step_down_at=p["step_down_at"],
        fps_second=p["fps_second"],
        jitter_frac=_num(p, "jitter_frac"),
        rng=time_rng,
    )
    kp_true, truth = _motion(t, p, pauses=p["pauses"])
    dt = np.diff(t)
    truth["dt"] = dt
    truth["is_vfr"] = bool(len(dt) > 1 and np.std(dt) / np.median(dt) > 0.01)
    return _sequence("SYN-07", seed, p, t, kp_true, truth, add_noise(kp_true, p["noise_px"], noise_rng))


def build_syn_08(seed: int, p: Mapping[str, Any]) -> SynthSequence:
    """SYN-08: the SYN-05 motion with all left/right pairs exchanged in the given frame ranges (half-open)."""
    _check_common(p)
    (noise_rng,) = _rngs(seed, 1)
    t = cfr_times(p["duration"], p["fps"])
    kp_true, truth = _motion(t, p, pauses=p["pauses"])
    mask = np.zeros(len(t), dtype=bool)
    ranges = []
    for item in p["swap_ranges"]:
        s0, s1 = int(item[0]), int(item[1])
        if not 0 <= s0 < s1 <= len(t):
            raise ValueError(f"swap_ranges: ({s0}, {s1}) must satisfy 0 <= start < end <= {len(t)} frames")
        mask[s0:s1] = True
        ranges.append((s0, s1))
    kp, score = apply_lr_swap(
        add_noise(kp_true, p["noise_px"], noise_rng), np.full((len(t), NUM_JOINTS), float(p["score_base"])), mask
    )
    truth.update(lr_swap_mask=mask, lr_swap_intervals=tuple(ranges), n_pairs_swapped=len(LR_PAIRS))
    return _sequence("SYN-08", seed, p, t, kp_true, truth, kp, score)


def _p95_p5(h: np.ndarray) -> float:
    return float(np.subtract(*np.percentile(h, [95, 5])))


def build_syn_09(seed: int, p: Mapping[str, Any]) -> SynthSequence:
    """SYN-09: a person walks away from a fixed pinhole camera; the physical hip height never changes.

    Camera: horizontal axis, height ``cam_height_m``, principal point at the image centre, focal length chosen so the
    trunk is ``scale_px`` long at the reference depth ``z0_m``. The person stands still for ``reference_s``, then walks
    to ``z0_m * depth_ratio`` at constant speed. Truth (Appendix B1 formulas on the continuous model, Lambda units):
    ``expected_hA = y_H / Lambda_take``, ``expected_hB = (lowest ankle/heel y - y_H) / Lambda_segment``.
    """
    _check_common(p)
    z0, trunk_m = _positive(p, "z0_m"), _positive(p, "trunk_m")
    ratio, cam_h, ref_s = _positive(p, "depth_ratio"), _positive(p, "cam_height_m"), _positive(p, "reference_s")
    if not ref_s < p["duration"]:
        raise ValueError(f"reference_s must be shorter than the duration, got {ref_s}")
    (noise_rng,) = _rngs(seed, 1)
    t = cfr_times(p["duration"], p["fps"])
    walk = np.clip((t - ref_s) / (float(p["duration"]) - ref_s), 0.0, 1.0)
    z = z0 + (z0 * ratio - z0) * walk  # depth in metres
    focal = float(p["scale_px"]) * z0 / trunk_m
    cx, cy = IMAGE_SIZE[0] / 2.0, IMAGE_SIZE[1] / 2.0
    tpl = _template(p["facing"])
    hip_h = FOOT_DROP * trunk_m  # metres above the ground
    height = hip_h - tpl[:, 1] * trunk_m  # joint height above the ground, metres
    kp_true = np.stack(
        [cx + focal * (tpl[:, 0] * trunk_m)[None] / z[:, None], cy + focal * (cam_h - height)[None] / z[:, None]], -1
    )
    scale_t = focal * trunk_m / z  # trunk length in the image
    y_hip = cy + focal * (cam_h - hip_h) / z
    ground = cy + focal * (cam_h - height[list(GROUND_CANDIDATES)].min()) / z
    lam_take, lam_seg = float(np.median(scale_t[t < ref_s])), float(np.median(scale_t))
    h_a, h_b = y_hip / lam_take, (ground - y_hip) / lam_seg
    truth = {
        "scale_px": scale_t,
        "depth_m": z,
        "reference_s": ref_s,
        "reference_interval": (0.0, ref_s),
        "lambda_take": lam_take,
        "lambda_segment": lam_seg,
        "expected_hA": h_a,
        "expected_hB": h_b,
        "range_A": _p95_p5(h_a),
        "range_B": _p95_p5(h_b),
        "true_hip_height_m": hip_h,
        "true_hip_height_range_m": 0.0,
    }
    return _sequence("SYN-09", seed, p, t, kp_true, truth, add_noise(kp_true, p["noise_px"], noise_rng))


def _warp_times(t_query: np.ndarray, duration: float, k0: float, k1: float) -> np.ndarray:
    """Reference time of each query time for ``d t_query / d t_ref = k0 + (k1 - k0) t_ref / duration`` (closed form)."""
    a = (k1 - k0) / (2.0 * duration)
    if abs(a) < 1e-12:
        return t_query / k0
    return (-k0 + np.sqrt(k0 * k0 + 4.0 * a * t_query)) / (2.0 * a)


def build_syn_10(seed: int, p: Mapping[str, Any]) -> SynthPair:
    """SYN-10: the query is the reference re-timed by a monotone warp ``t_query = W(t_ref)`` (can be shifted/scaled).

    Both sequences sample ONE continuous pose function, so the query pose at ``t_q`` is exactly the reference pose at
    ``t_ref_of_query(t_q)``. ``rate_k = d t_query / d t_ref`` (Appendix C.4) is analytic.
    """
    _check_common(p)
    k0, k1 = _positive(p, "k_start"), _positive(p, "k_end")
    q_scale = _positive(p, "query_scale")
    shift = _pair(p, "query_shift_px")
    ref_rng, query_rng = _rngs(seed, 2)
    duration, fps, scale = float(p["duration"]), float(p["fps"]), float(p["scale_px"])
    t_ref = cfr_times(duration, fps)
    phi_ref = t_ref / duration
    ref_kp = _pose_from_phase(phi_ref, action="raise_lower", scale_px=scale, facing=p["facing"])
    d_query = duration * (k0 + k1) / 2.0
    t_q = cfr_times(d_query, fps)
    t_ref_of_q = _warp_times(t_q, duration, k0, k1)
    origin = (IMAGE_SIZE[0] / 2.0 + shift[0], GROUND_Y_PX - FOOT_DROP * scale + shift[1])
    q_kp = _pose_from_phase(
        t_ref_of_q / duration, action="raise_lower", scale_px=scale * q_scale, facing=p["facing"], origin=origin
    )
    rate_k = k0 + (k1 - k0) * t_ref_of_q / duration
    ref = _sequence(
        "SYN-10/ref", seed, p, t_ref, ref_kp, {"role": "reference", "phase": phi_ref},
        add_noise(ref_kp, p["noise_px"], ref_rng),
    )  # fmt: skip
    query = _sequence(
        "SYN-10/query", seed, p, t_q, q_kp, {"role": "query", "t_ref_of_query": t_ref_of_q, "rate_k": rate_k},
        add_noise(q_kp, p["noise_px"], query_rng),
    )  # fmt: skip
    truth = {
        "t_ref_of_query": t_ref_of_q,
        "rate_k": rate_k,
        "same_shape": True,
        "k_start": k0,
        "k_end": k1,
        "query_scale": q_scale,
        "query_shift_px": shift,
        "query_duration": d_query,
    }
    return SynthPair(ref, query, truth, "SYN-10", seed, dict(p))


def build_syn_11(seed: int, p: Mapping[str, Any]) -> SynthPair:
    """SYN-11: two different actions, plus a same-action variant of the reference (small warp + noise)."""
    _check_common(p)
    v0, v1 = _pair(p, "variant_k")
    if v0 <= 0 or v1 <= 0:
        raise ValueError(f"variant_k must be positive, got {(v0, v1)}")
    if _num(p, "variant_noise_px") < 0:
        raise ValueError(f"variant_noise_px must be >= 0, got {p['variant_noise_px']}")
    ref_rng, query_rng, var_rng = _rngs(seed, 3)
    duration, fps, scale, facing = float(p["duration"]), float(p["fps"]), float(p["scale_px"]), p["facing"]
    t = cfr_times(duration, fps)
    phi = t / duration
    ref_kp = _pose_from_phase(phi, action="raise_lower", scale_px=scale, facing=facing)
    other_kp = _pose_from_phase(phi, action="open_close", scale_px=scale, facing=facing)
    t_var = cfr_times(duration * (v0 + v1) / 2.0, fps)
    var_kp = _pose_from_phase(
        _warp_times(t_var, duration, v0, v1) / duration, action="raise_lower", scale_px=scale, facing=facing
    )
    # each sequence names its action in its own params so that a consumer can tell them apart
    ref = _sequence(
        "SYN-11/ref", seed, {**p, "action": "raise_lower"}, t, ref_kp, {"role": "reference"},
        add_noise(ref_kp, p["noise_px"], ref_rng),
    )  # fmt: skip
    other = _sequence(
        "SYN-11/query", seed, {**p, "action": "open_close"}, t, other_kp, {"role": "query"},
        add_noise(other_kp, p["noise_px"], query_rng),
    )  # fmt: skip
    variant = _sequence(
        "SYN-11/variant", seed, {**p, "action": "raise_lower"}, t_var, var_kp, {"role": "variant"},
        add_noise(var_kp, p["variant_noise_px"], var_rng),
    )  # fmt: skip
    truth = {"action_ref": "raise_lower", "action_query": "open_close", "same_action": False, "variant": variant}
    return SynthPair(ref, other, truth, "SYN-11", seed, dict(p))


def _boxes(kp: np.ndarray, pad: float = 20.0) -> np.ndarray:
    """Tight keypoint boxes xyxy padded by ``pad`` px; ``kp`` is ``(T, 26, 2)``."""
    return np.concatenate([kp.min(axis=1) - pad, kp.max(axis=1) + pad], axis=-1)


def build_syn_12(seed: int, p: Mapping[str, Any]) -> SynthScene:
    """SYN-12: target + distractor (+ bystander); the target leaves and re-enters, the distractor crosses it first.

    Detections are an unordered list: per frame the present people are placed in the first slots in a seeded random
    order, ``truth["person_id"]`` (T, N) gives the true identity of every slot (-1 = empty).
    """
    _check_common(p)
    n_people = p["n_people"]
    if n_people not in (2, 3):
        raise ValueError(f"n_people must be 2 or 3, got {n_people!r}")
    a0, a1 = _pair(p, "absent_s")
    duration = float(p["duration"])
    if not 0.0 < a0 < a1 <= duration:
        raise ValueError(f"absent_s must satisfy 0 < start < end <= duration ({duration}), got {(a0, a1)}")
    cross_s, walk = _positive(p, "cross_s"), _positive(p, "walk_px_s")
    x0, offset = _num(p, "target_x0_px"), _num(p, "return_offset_px")
    noise_rng, shuffle_rng = _rngs(seed, 2)
    t = cfr_times(duration, p["fps"])
    n_t = len(t)
    scales = [float(p["scale_px"]) * f for f in (1.0, 0.95, 0.90)][:n_people]
    xs = [
        x0 + 15.0 * np.sin(t) + np.where(t >= a1, offset, 0.0),  # target: slight sway, returns shifted by `offset`
        np.maximum(300.0, x0 + walk * (cross_s - t)),  # distractor: walks left through the target's place at cross_s
        np.full(n_t, 1500.0),  # bystander: stands still
    ][:n_people]
    present = np.ones((n_t, n_people), dtype=bool)
    present[:, 0] = ~((t >= a0) & (t < a1))
    by_person = np.full((n_t, n_people, NUM_JOINTS, 2), np.nan)
    box = np.full((n_t, n_people, 4), np.nan)
    for i in range(n_people):
        base = neutral_pose(scales[i], origin=(0.0, GROUND_Y_PX - FOOT_DROP * scales[i]), facing=p["facing"])
        kp_i = np.tile(base, (n_t, 1, 1))
        kp_i[..., 0] += xs[i][:, None]
        by_person[present[:, i], i] = kp_i[present[:, i]]
        box[present[:, i], i] = _boxes(kp_i[present[:, i]])
    _require_in_image(by_person, "SYN-12")

    f_absent = np.flatnonzero(~present[:, 0])
    if len(f_absent) == 0:
        raise ValueError(f"absent_s: the interval {(a0, a1)} contains no frame")
    overlap = present[:, 0] & present[:, 1]
    overlap &= np.minimum(box[:, 0, 2], box[:, 1, 2]) > np.maximum(box[:, 0, 0], box[:, 1, 0])
    overlap &= np.minimum(box[:, 0, 3], box[:, 1, 3]) > np.maximum(box[:, 0, 1], box[:, 1, 1])
    if not overlap.any():
        raise ValueError("cross_s: the distractor never overlaps the target while both are visible")
    if overlap[max(int(f_absent[0]) - 1, 0)]:
        raise ValueError("cross_s: the crossing is still going on when the target leaves; lower cross_s or absent_s")
    crossing_frames = (int(np.flatnonzero(overlap)[0]), int(np.flatnonzero(overlap)[-1]))

    kp = np.full((n_t, n_people, NUM_JOINTS, 2), np.nan)
    score = np.zeros((n_t, n_people, NUM_JOINTS))
    bbox = np.full((n_t, n_people, 4), np.nan)
    person_id = np.full((n_t, n_people), -1, dtype=np.int32)
    for ti in range(n_t):
        for slot, ident in enumerate(shuffle_rng.permutation(np.flatnonzero(present[ti]))):
            kp[ti, slot], bbox[ti, slot], person_id[ti, slot] = by_person[ti, ident], box[ti, ident], ident
            score[ti, slot] = float(p["score_base"])
    truth = {
        "target_id": 0,
        "n_people": n_people,
        "person_id": person_id,
        "kp_by_person": by_person.astype(np.float32),
        "absent_intervals": ((a0, a1),),
        "absent_frames": ((int(f_absent[0]), int(f_absent[-1])),),
        "crossing_interval": (float(t[crossing_frames[0]]), float(t[crossing_frames[1]])),
        "crossing_frames": crossing_frames,
        "return_offset_px": offset,
        "target_x0_px": x0,
    }
    return SynthScene(
        kp=add_noise(kp, p["noise_px"], noise_rng).astype(np.float32),
        score=score.astype(np.float32),
        bbox=bbox.astype(np.float32),
        t_sec=t,
        truth=truth,
        scenario="SYN-12",
        seed=seed,
        params=dict(p),
    )


def expected_target_lost(
    scene_or_truth: SynthScene | Mapping[str, Any], max_lost_s: float
) -> tuple[tuple[float, float], ...]:
    """Intervals (s) in which a tracker with ``max_lost`` must report ``target_lost``: from ``start + max_lost`` to the
    return of the target, for every absence longer than ``max_lost_s``. Boundaries are meant within one frame."""
    if max_lost_s < 0:
        raise ValueError(f"max_lost_s must be >= 0, got {max_lost_s}")
    truth = scene_or_truth.truth if isinstance(scene_or_truth, SynthScene) else scene_or_truth
    return tuple((a0 + max_lost_s, a1) for a0, a1 in truth["absent_intervals"] if a1 - a0 > max_lost_s)


# --- registry and public API ------------------------------------------------------------------------------------
def _common(duration: float, **extra: Any) -> dict[str, Any]:
    return {
        "duration": duration,
        "fps": DEFAULT_FPS,
        "scale_px": SCALE_PX,
        "noise_px": 0.0,
        "score_base": 0.95,
        "facing": "camera",
        **extra,
    }


def _vfr_defaults() -> dict[str, Any]:
    """SYN-07 samples at ``fps_nominal`` / ``fps_second``: it has no ``fps`` (an accepted but unused name is a trap)."""
    d = _common(4.0, pauses=((1.0, 1.5),), step_down_at=2.0, fps_second=10.0, jitter_frac=0.0, **_MOTION)
    d["fps_nominal"] = d.pop("fps")
    return d


_MOTION: Final = {"action": "raise_lower", "ramp_s": 0.2}
_TEMPO_TRUTH: Final = ("pause_intervals", "pause_frames", "n_pauses", "speed", "speed_profile", "phase", "scale_px")
_DEFAULT_PAUSES: Final = ((1.0, 1.6), (2.8, 3.4))

SCENARIOS: Final[dict[str, ScenarioSpec]] = {
    "SYN-01": ScenarioSpec(
        "sequence", build_syn_01, _common(3.0, noise_px=1.0),
        ("hip_range", "speed", "pause_intervals", "pause_frames", "n_pauses", "scale_px"),
        "Still performer with Gaussian noise (zero motion; the whole clip is one pause)",
    ),
    "SYN-02": ScenarioSpec(
        "sequence", build_syn_02, _common(4.0, amplitude=0.15, freq=0.5),
        ("A", "f", "nominal_range", "expected_range_p95_p5", "hip_y", "scale_px"),
        "Vertical hip sine oscillation (hip-height range truth, Lambda units)",
    ),
    "SYN-03": ScenarioSpec(
        "sequence", build_syn_03, _common(3.0, theta_deg=None, theta_from=0.0, theta_to=15.0),
        ("theta_deg", "median_theta_deg", "scale_px"),
        "Known trunk lean theta(t) in degrees (Appendix B2 sign)",
    ),
    "SYN-04": ScenarioSpec(
        "sequence", build_syn_04,
        _common(3.0, theta_deg=None, theta_from=0.0, theta_to=15.0, roll_deg=5.0, centre=(960.0, 540.0)),
        ("roll_deg", "theta_body_deg", "theta_raw_deg", "vertical_line", "scale_px"),
        "Body lean seen through a camera rolled by beta (roll-correction truth)",
    ),
    "SYN-05": ScenarioSpec(
        "sequence", build_syn_05, _common(5.0, pauses=_DEFAULT_PAUSES, **_MOTION),
        _TEMPO_TRUTH,
        "Action with exact zero-speed pauses and cosine ramps (tempo truth from the continuous model)",
    ),
    "SYN-06": ScenarioSpec(
        "sequence", build_syn_06,
        _common(
            5.0, pauses=_DEFAULT_PAUSES, gaps=((("LWrist", "RWrist"), 2.0, 0.100), (("LWrist", "RWrist"), 0.3, 0.300)),
            gap_mode="nan", short_gap_s=SHORT_GAP_S, **_MOTION,
        ),
        (*_TEMPO_TRUTH, "gaps"),
        "SYN-05 motion with a short (100 ms) and a long (300 ms) gap, both during motion",
    ),
    "SYN-07": ScenarioSpec(
        "sequence", build_syn_07,
        _vfr_defaults(),
        (*_TEMPO_TRUTH, "dt", "is_vfr"),
        "SYN-05 motion sampled at variable-frame-rate timestamps",
    ),
    "SYN-08": ScenarioSpec(
        "sequence", build_syn_08, _common(5.0, pauses=_DEFAULT_PAUSES, swap_ranges=((20, 23), (50, 53)), **_MOTION),
        (*_TEMPO_TRUTH, "lr_swap_mask", "lr_swap_intervals", "n_pairs_swapped"),
        "SYN-05 motion with left/right swaps in known frames",
    ),
    "SYN-09": ScenarioSpec(
        "sequence", build_syn_09,
        _common(4.0, z0_m=4.0, depth_ratio=1.5, cam_height_m=1.0, trunk_m=TRUNK_M, reference_s=1.0),
        (
            "scale_px", "depth_m", "reference_s", "reference_interval", "lambda_take", "lambda_segment",
            "expected_hA", "expected_hB", "range_A", "range_B", "true_hip_height_m", "true_hip_height_range_m",
        ),
        "Person walking away from a pinhole camera; hip-height variants A and B by the Appendix B formulas",
    ),
    "SYN-10": ScenarioSpec(
        "pair", build_syn_10,
        _common(4.0, k_start=0.8, k_end=1.25, query_scale=1.0, query_shift_px=(0.0, 0.0)),
        (
            "t_ref_of_query", "rate_k", "same_shape", "k_start", "k_end", "query_scale", "query_shift_px",
            "query_duration",
        ),
        "Query = reference re-timed by a monotone warp (shape distance 0, known local rate)",
    ),
    "SYN-11": ScenarioSpec(
        "pair", build_syn_11, _common(3.0, variant_k=(0.97, 1.03), variant_noise_px=1.5),
        ("action_ref", "action_query", "same_action", "variant"),
        "Two different actions and a same-action variant (action discrimination)",
    ),
    "SYN-12": ScenarioSpec(
        "scene", build_syn_12,
        _common(
            4.0, score_base=0.9, n_people=3, absent_s=(1.5, 2.5), cross_s=0.8, walk_px_s=400.0, target_x0_px=700.0,
            return_offset_px=0.0,
        ),
        (
            "target_id", "n_people", "person_id", "kp_by_person", "absent_intervals", "absent_frames",
            "crossing_interval", "crossing_frames", "return_offset_px", "target_x0_px",
        ),
        "People in shuffled detection order; the target leaves and re-enters after a crossing",
    ),
}  # fmt: skip


def _make(kind: str, scenario: str, seed: Any, params: Mapping[str, Any]) -> Any:
    spec = SCENARIOS.get(scenario)
    if spec is None:
        valid = ", ".join(k for k, v in SCENARIOS.items() if v.kind == kind)
        raise ValueError(f"Unknown scenario {scenario!r}; valid {kind} IDs: {valid}")
    if spec.kind != kind:
        raise ValueError(f"Scenario {scenario!r} is of kind {spec.kind!r}; use make_{spec.kind}() instead")
    if isinstance(seed, bool) or not isinstance(seed, int | np.integer) or seed < 0:
        raise ValueError(f"seed must be a non-negative integer, got {seed!r}")
    unknown = sorted(set(params) - set(spec.default_params))
    if unknown:
        raise TypeError(f"unknown parameter(s) for {scenario}: {unknown}; accepted: {sorted(spec.default_params)}")
    return spec.builder(int(seed), {**spec.default_params, **params})


def make_sequence(scenario: str, *, seed: int = 0, **params: Any) -> SynthSequence:
    """One synthetic sequence (SYN-01 .. SYN-09). Unknown parameters raise ``TypeError``."""
    return _make("sequence", scenario, seed, params)


def make_pair(scenario: str, *, seed: int = 0, **params: Any) -> SynthPair:
    """A reference/query pair (SYN-10, SYN-11). Unknown parameters raise ``TypeError``."""
    return _make("pair", scenario, seed, params)


def make_scene(scenario: str, *, seed: int = 0, **params: Any) -> SynthScene:
    """A multi-person scene (SYN-12). Unknown parameters raise ``TypeError``."""
    return _make("scene", scenario, seed, params)
