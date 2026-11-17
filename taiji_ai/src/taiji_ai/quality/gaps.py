"""Short-gap interpolation of the mask layer (W6, P4.02): bridge the holes that are short in real time, and say so.

The mask layer (``quality/mask.py``) has holes: joints that are NaN, each with a reason. A **gap** is a maximal run of
unobserved frames of one joint (``reason != ok``). ``interpolate_gaps`` looks at every gap and applies the rule below;
a gap that is bridged is filled with a straight line in time and every cell of it is flagged ``interpolated``.

The rule, in this order; the first that applies names the outcome of the gap (``OUTCOME_NAMES``):

1. **open** (``open_start``, ``open_end``, ``open_both``): no observed frame before it, after it, or both. A line
   needs two ends; anything else is extrapolation, and nothing is extrapolated.
2. **never fill**: a cell of the gap has a reason in ``GapParams.never_fill``, by default ``not_tracked`` (the frame is
   not the target's: the tracker had lost the performer or had not found them yet). A line drawn across an absence
   could join two different people.
3. **blocked**: a cell of the gap, or one of the two anchors, is marked in the optional ``blocked`` mask. This is the
   place for "do not bridge across a suspected turning point" (W6): the detector of those points is P4.06's.
4. **too long**: the bridged span ``t[after] - t[before]`` (from the last observed frame before to the first observed
   frame after) is more than ``max_gap_s`` plus 1e-9 s. ``max_gap_s`` is 0.150 s (W6). The span is measured on the
   real timestamps, never in frames, so the same number of missing frames is bridged at 60 fps and not at 15 fps; a
   span of exactly 150 ms is bridged (the 1e-9 s absorbs ``0.15000000000000002``). At 30 fps up to 3 missing frames
   are bridged.
5. otherwise **filled**: ``p(t) = p_before + w (p_after - p_before)`` with
   ``w = (t - t_before) / (t_after - t_before)``, for x and y separately and with the real times, so the bridge is
   exact for a movement that is linear in time.

Nothing is held, repeated, extrapolated or set to zero (AGENTS.md section 5.1). Every value of the result is one of
three things: the input value at the same place (observed), a bridged value with ``interpolated`` set and an observed
anchor on both sides, or NaN with the mask's reason. The input is not changed (section 5.3); the result is new and
read-only; the mask's ``reason`` is kept for every cell, a bridged one included, so that the coverage can report what
made the hole. A bridge is only as good as its anchors: ``interpolated`` says "not observed", not "right". An
interpolated cell has no score (the model never saw it): scores are not part of this layer.

Units and coordinates: positions are pixels of the upright image, x to the right, y down (as in the raw layer); times
are seconds from the stream start (real PTS). The decisions of this module are DEC-0045.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import numpy as np

from taiji_ai.pose.skeleton import NUM_JOINTS
from taiji_ai.quality import QualityError
from taiji_ai.quality._checks import check_layer, frozen, is_real
from taiji_ai.quality.mask import NOT_TRACKED, OK, MaskedTrack

MAX_GAP_S: Final = 0.150  # W6: a hole of at most this many seconds, anchor to anchor, may be bridged

FILLED: Final = 0
TOO_LONG: Final = 1
NEVER_FILL: Final = 2
BLOCKED: Final = 3
OPEN_START: Final = 4
OPEN_END: Final = 5
OPEN_BOTH: Final = 6
OUTCOME_NAMES: Final = ("filled", "too_long", "never_fill", "blocked", "open_start", "open_end", "open_both")  # = code

_EPS_S: Final = 1e-9  # a span of 0.15 s is not an exact float: the boundary must not depend on it


def _is_code(value: Any) -> bool:
    return bool(isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)) and 0 <= value <= 255)


@dataclass(frozen=True)
class GapParams:
    """The parameters of the gap layer; the defaults are the values of W6. Wrong values raise ``QualityError``."""

    # [s] finite and above 0: the longest bridged span, anchor to anchor
    max_gap_s: float = MAX_GAP_S
    # reason codes (0..255), distinct: a gap that has a cell with one of them is not bridged
    never_fill: tuple[int, ...] = (NOT_TRACKED,)

    def __post_init__(self) -> None:
        limit = self.max_gap_s
        if not (is_real(limit) and np.isfinite(limit) and limit > 0.0):
            raise QualityError(f"max_gap_s must be a finite number of seconds above 0, got {limit!r}")
        try:
            codes = tuple(self.never_fill)
        except TypeError as exc:
            raise QualityError(f"never_fill must be a sequence of reason codes, got {self.never_fill!r}") from exc
        if not all(_is_code(c) for c in codes) or len(set(codes)) != len(codes):
            raise QualityError(f"never_fill must hold distinct reason codes in [0, 255], got {codes!r}")
        object.__setattr__(self, "max_gap_s", float(limit))
        object.__setattr__(self, "never_fill", tuple(int(c) for c in codes))


@dataclass(frozen=True, eq=False)
class GapTable:
    """One row per gap, ordered by joint and then by first frame; every array is new and read-only (``G`` rows)."""

    joint: np.ndarray  # (G,) int16; joint index (halpe26/1)
    start: np.ndarray  # (G,) int32; first frame (row of the arrays) of the gap
    end: np.ndarray  # (G,) int32; last frame of the gap, inclusive
    missing_s: np.ndarray  # (G,) float64 [s]; frames in the gap x the median frame interval (NaN if there is one frame)
    bridge_s: np.ndarray  # (G,) float64 [s]; ``t[end + 1] - t[start - 1]``; NaN when the gap is open
    outcome: np.ndarray  # (G,) uint8; index into ``OUTCOME_NAMES``

    def __len__(self) -> int:
        return int(self.joint.shape[0])


@dataclass(frozen=True, eq=False)
class GapResult:
    """The gap layer of ``T`` frames; every array is new and read-only (``T`` may be 0)."""

    keypoints: np.ndarray  # (T, 26, 2) the input dtype; observed values, bridged values, NaN elsewhere
    interpolated: np.ndarray  # (T, 26) bool; the cell was NaN in the mask and is a bridged value here
    observed: np.ndarray  # (T, 26) bool; ``reason == ok``
    reason: np.ndarray  # (T, 26) uint8; the mask's reason, unchanged: why the cell was missing, a bridged one too
    gaps: GapTable
    params: GapParams

    @property
    def usable(self) -> np.ndarray:
        """``(T, 26)`` bool: the cell has a value, observed or bridged."""
        return self.observed | self.interpolated


def _check(keypoints: Any, reason: Any, t_sec: Any, blocked: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, Any]:
    kp, rs, t = check_layer(keypoints, reason, t_sec)
    if blocked is not None:
        n = kp.shape[0]
        blocked = np.asarray(blocked)
        if blocked.dtype != np.bool_ or blocked.shape != (n, NUM_JOINTS):
            raise QualityError(
                f"blocked must be a bool array of shape ({n}, {NUM_JOINTS}), got {blocked.dtype} {blocked.shape}"
            )
    return kp, rs, t, blocked


def interpolate_gaps(
    keypoints: np.ndarray,
    reason: np.ndarray,
    t_sec: np.ndarray,
    params: GapParams | None = None,
    blocked: np.ndarray | None = None,
) -> GapResult:
    """Bridge the short gaps of a mask layer; see the module docstring for the rule.

    ``keypoints`` ``(T, 26, 2)`` float (pixels) with NaN exactly where ``reason`` (``(T, 26)`` uint8, the codes of
    ``quality/mask.py``) is not ``ok``; ``t_sec`` ``(T,)`` float seconds, finite and strictly increasing; ``blocked``
    ``(T, 26)`` bool or ``None``. The inputs are not changed. Raises ``QualityError`` for anything else.
    """
    params = GapParams() if params is None else params
    kp, rs, t, block = _check(keypoints, reason, t_sec, blocked)
    n = kp.shape[0]
    unobserved = rs != OK
    never = np.isin(rs, params.never_fill)
    out = np.array(kp, copy=True)
    flagged = np.zeros(rs.shape, dtype=bool)
    dt = float(np.median(np.diff(t))) if n > 1 else float("nan")

    # The runs of every joint at once: a rise of the padded mask starts a run, a fall ends it (``stop`` is exclusive).
    padded = np.zeros((NUM_JOINTS, n + 2), dtype=np.int8)
    padded[:, 1:-1] = unobserved.T
    edges = np.diff(padded, axis=1)
    runs = zip(np.argwhere(edges == 1), np.argwhere(edges == -1), strict=True)

    joints: list[int] = []
    starts: list[int] = []
    ends: list[int] = []
    missing: list[float] = []
    bridge: list[float] = []
    outcomes: list[int] = []
    for (j, first), (_, stop) in runs:
        before, after = int(first) - 1, int(stop)
        span = float("nan")
        if before < 0 and after >= n:
            outcome = OPEN_BOTH
        elif before < 0:
            outcome = OPEN_START
        elif after >= n:
            outcome = OPEN_END
        else:
            span = float(t[after] - t[before])
            if never[first:stop, j].any():
                outcome = NEVER_FILL
            elif block is not None and (block[first:stop, j].any() or block[before, j] or block[after, j]):
                outcome = BLOCKED
            elif span > params.max_gap_s + _EPS_S:
                outcome = TOO_LONG
            else:
                outcome = FILLED
                weight = (t[first:stop] - t[before]) / span
                anchor_before, anchor_after = out[before, j].astype(np.float64), out[after, j].astype(np.float64)
                out[first:stop, j] = anchor_before + weight[:, None] * (anchor_after - anchor_before)
                flagged[first:stop, j] = True
        joints.append(int(j))
        starts.append(int(first))
        ends.append(int(stop) - 1)
        missing.append((int(stop) - int(first)) * dt)
        bridge.append(span)
        outcomes.append(outcome)

    table = GapTable(
        joint=frozen(np.array(joints, dtype=np.int16)),
        start=frozen(np.array(starts, dtype=np.int32)),
        end=frozen(np.array(ends, dtype=np.int32)),
        missing_s=frozen(np.array(missing, dtype=np.float64)),
        bridge_s=frozen(np.array(bridge, dtype=np.float64)),
        outcome=frozen(np.array(outcomes, dtype=np.uint8)),
    )
    return GapResult(
        keypoints=frozen(out),
        interpolated=frozen(flagged),
        observed=frozen(~unobserved),
        reason=frozen(np.array(rs, copy=True)),
        gaps=table,
        params=params,
    )


def interpolate_track(
    masked: MaskedTrack, params: GapParams | None = None, blocked: np.ndarray | None = None
) -> GapResult:
    """The gap layer of a masked ``TargetTrack``: its keypoints, reasons and real timestamps, margins included.

    The frames that are not the target's are ``not_tracked`` in the mask and are never bridged (default ``never_fill``).
    The timeline (``frame_index``, ``in_segment``, ``status``) stays in ``masked``; the rows are the same.
    """
    return interpolate_gaps(masked.mask.keypoints, masked.mask.reason, masked.t_sec, params, blocked)
