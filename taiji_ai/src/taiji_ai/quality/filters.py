"""Filters of the quality layer (W6): the Hampel outlier flag now (P4.03); the Butterworth filter comes with P4.05.

**Hampel.** A pose keypoint sometimes jumps for a frame or two and comes back (the ``flicker`` of P3.08). For every
observed cell of a joint, ``hampel_outliers`` compares each coordinate with the median of its neighbours; a cell that
is further from that median than ``n_sigma`` robust standard deviations in x or in y is an **outlier**: it is set to
NaN and gets the reason ``outlier`` (``mask.OUTLIER``). The only change this stage makes is that: nothing is smoothed,
clipped or invented (AGENTS.md section 5.1). The hole an outlier leaves is bridged, if it is short, by
``interpolate_gaps`` (P4.02), flagged ``interpolated``; the order of the stages is mask, Hampel, gaps, resampling,
filter, so Hampel never sees a bridged value (DEC-0046).

The rule for one coordinate of one joint:

1. The **window** of a cell is the ``window`` rows centred on it (rows beyond the ends of the series are absent). A row
   counts only if its cell is observed (``reason == ok``) **and** its time is within ``max_half_span_s`` of the
   centre's time (plus 1e-9 s), so a stall or a long loss in the middle of a window cuts it: the window is a number of
   rows, real seconds only cut it, and no frame rate is assumed (AGENTS.md section 5.2).
2. The cell is **judged** only if it is observed itself and at least ``min_observed`` cells of the window count (itself
   included). A cell that is not judged is never flagged; the first and last rows of a series have a short window.
3. ``m`` is the median of the counted values, ``MAD`` the median of ``|value - m|`` over them, and
   ``sigma = max(1.4826 x MAD, scale_floor_px)``; 1.4826 makes the MAD of Gaussian noise its standard deviation.
4. The cell is an outlier if ``|value - m| > n_sigma x sigma`` (strictly: equal is kept) in x or in y. With ``MAD = 0``
   and no floor any deviation counts and an identical value does not: a spike in a window that is otherwise constant
   is found, and a joint that stands still is not touched.

All cells are judged against the **original** values of their windows (one pass, no iteration). Up to three spiked
rows in a window of seven can be found, because the median stays with the good rows; the spike has to be large against
the spread of the good rows, for with three spikes the MAD is the largest deviation of a good row. A good cell next to
a spike is never flagged because of it. A run of four or more spiked rows is the majority of the window and is not an
outlier, and neither is a persistent error (a joint that stays wrong for many frames, a left/right swap): every sample
of the window shows it, so the median follows it (P4.06 looks for swaps).

**The defaults (DEC-0046).** The MAD of seven numbers is a noisy estimate: on pure Gaussian noise with no spike in it
the rule of W6 flags about 4.8 % of the coordinates (10.8 % without the 1.4826), and on the real footage of M-QLT-03
(D20, four videos) it flagged 7.1 % of the observed cells, 6.9 % of those of frames that a person had confirmed right:
a joint that stays still for a few frames has a MAD near 0 and any jitter counts. A floor under sigma keeps pixel jitter
from counting. With ``scale_floor_px = 2`` the same footage gives 0.49 % and 1.1 %, and the share of the named wrong
joints that are found goes from 39.8 % to 34.8 %. So the defaults are the window and the 3 sigma of W6 with a floor of
2 px (the maintainer chose them with that table; ``Docs/tasks/P4.03.md``). The floor is in pixels, about 1 % of the
197 px torso of that footage: a camera at another distance or resolution needs the floor scaled, and ``torso_length_px``
measures the torso for it (P4.07 decides how the stages are wired). With ``scale_floor_px = 0`` the rule is exactly
the one written in W6.

Units and coordinates: positions are pixels of the upright image, x to the right, y down; times are seconds from the
stream start (real PTS). Inputs are not changed; the result arrays are new and read-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from taiji_ai.pose.skeleton import IDX, NUM_JOINTS
from taiji_ai.quality import QualityError
from taiji_ai.quality._checks import check_layer, frozen, is_int, is_real
from taiji_ai.quality.mask import OK, OUTLIER, MaskedTrack

MAD_TO_SIGMA: Final = 1.4826  # the MAD of Gaussian noise times this is its standard deviation
DEFAULT_SCALE_FLOOR_PX: Final = 2.0  # [px] chosen with the numbers of M-QLT-03 (DEC-0046)
DEFAULT_BLOCK_ROWS: Final = 4096
TORSO_JOINTS: Final = (IDX["LShoulder"], IDX["RShoulder"], IDX["LHip"], IDX["RHip"])

_EPS_S: Final = 1e-9  # a row exactly at the time limit counts: the boundary must not depend on float rounding


@dataclass(frozen=True)
class HampelParams:
    """The parameters of the Hampel stage. ``window`` and ``n_sigma`` are the values of W6; ``min_observed`` and
    ``max_half_span_s`` are the proposals of the plan of P4.03; ``scale_floor_px`` was chosen with the numbers of
    M-QLT-03 (see the module docstring and DEC-0046). Wrong values raise ``QualityError``."""

    window: int = 7  # an odd whole number of rows, at least 3, centred on the cell
    n_sigma: float = 3.0  # finite and above 0: how many robust standard deviations make an outlier
    # at least this many cells of the window must count for a cell to be judged;
    # ``None`` is ``window // 2 + 2`` (5 of 7)
    min_observed: int | None = None
    max_half_span_s: float = 0.25  # [s] finite and above 0: rows further than this from the centre are left out
    # [px] finite, 0 or more: sigma is never smaller than this; 0 is the rule of W6 as written
    scale_floor_px: float = DEFAULT_SCALE_FLOOR_PX

    def __post_init__(self) -> None:
        window = self.window
        if not (is_int(window) and window >= 3 and window % 2 == 1):
            raise QualityError(f"window must be an odd whole number of rows, at least 3, got {window!r}")
        if not (is_real(self.n_sigma) and np.isfinite(self.n_sigma) and self.n_sigma > 0.0):
            raise QualityError(f"n_sigma must be a finite number above 0, got {self.n_sigma!r}")
        minimum = window // 2 + 2 if self.min_observed is None else self.min_observed
        if not (is_int(minimum) and 3 <= minimum <= window):
            raise QualityError(f"min_observed must be a whole number from 3 to the window ({window}), got {minimum!r}")
        span = self.max_half_span_s
        if not (is_real(span) and np.isfinite(span) and span > 0.0):
            raise QualityError(f"max_half_span_s must be a finite number of seconds above 0, got {span!r}")
        floor = self.scale_floor_px
        if not (is_real(floor) and np.isfinite(floor) and floor >= 0.0):
            raise QualityError(f"scale_floor_px must be a finite number of pixels, 0 or more, got {floor!r}")
        object.__setattr__(self, "window", int(window))
        object.__setattr__(self, "n_sigma", float(self.n_sigma))
        object.__setattr__(self, "min_observed", int(minimum))
        object.__setattr__(self, "max_half_span_s", float(span))
        object.__setattr__(self, "scale_floor_px", float(floor))


@dataclass(frozen=True, eq=False)
class HampelResult:
    """The outlier layer of ``T`` frames; every array is new and read-only (``T`` may be 0)."""

    keypoints: np.ndarray  # (T, 26, 2) the input dtype; the input, with the outlier cells NaN
    reason: np.ndarray  # (T, 26) uint8; the input's, with ``OUTLIER`` where a cell was flagged
    outlier: np.ndarray  # (T, 26) bool; the cell was observed and is now NaN with the reason ``outlier``
    # (T, 26) bool; the cell was observed and had enough counted neighbours: it could have been flagged
    judged: np.ndarray
    params: HampelParams


def hampel_outliers(
    keypoints: np.ndarray,
    reason: np.ndarray,
    t_sec: np.ndarray,
    params: HampelParams | None = None,
    *,
    block_rows: int = DEFAULT_BLOCK_ROWS,
) -> HampelResult:
    """Flag the outliers of a mask layer; see the module docstring for the rule.

    ``keypoints`` ``(T, 26, 2)`` float (pixels) with NaN exactly where ``reason`` (``(T, 26)`` uint8, the codes of
    ``quality/mask.py``) is not ``ok``; ``t_sec`` ``(T,)`` float seconds, finite and strictly increasing.
    ``block_rows`` is a memory knob (the windows are built for that many rows at a time): the answer does not depend on
    it. The inputs are not changed. Raises ``QualityError`` for anything else.
    """
    params = HampelParams() if params is None else params
    if not (is_int(block_rows) and block_rows >= 1):
        raise QualityError(f"block_rows must be a whole number of rows, at least 1, got {block_rows!r}")
    kp, rs, t = check_layer(keypoints, reason, t_sec)
    n = kp.shape[0]
    half = params.window // 2
    observed = rs == OK
    values = kp.astype(np.float64)
    judged = np.zeros((n, NUM_JOINTS), dtype=bool)
    outlier = np.zeros((n, NUM_JOINTS), dtype=bool)
    for a in range(0, n, block_rows):
        b = min(a + block_rows, n)
        rows = np.arange(a - half, b + half)  # the block and ``half`` rows of overlap on each side
        inside = (rows >= 0) & (rows < n)
        at = np.clip(rows, 0, n - 1)
        block_values = np.where(inside[:, None, None], values[at], np.nan)  # (rows, 26, 2)
        block_observed = np.where(inside[:, None], observed[at], False)  # (rows, 26)
        block_t = np.where(inside, t[at], np.nan)  # (rows,)
        window_values = sliding_window_view(block_values, params.window, axis=0)  # (b - a, 26, 2, window)
        window_observed = sliding_window_view(block_observed, params.window, axis=0)  # (b - a, 26, window)
        window_t = sliding_window_view(block_t, params.window, axis=0)  # (b - a, window)
        with np.errstate(invalid="ignore"):  # a row beyond the series has no time: the comparison is False
            near = np.abs(window_t - t[a:b, None]) <= params.max_half_span_s + _EPS_S
        counted = window_observed & near[:, None, :]  # (b - a, 26, window)
        judged_here = observed[a:b] & (counted.sum(axis=-1) >= params.min_observed)
        frame, joint = np.nonzero(judged_here)
        if frame.size:
            picked = np.where(counted[frame, joint][:, None, :], window_values[frame, joint], np.nan)  # (K, 2, window)
            median = np.nanmedian(picked, axis=-1)  # at least min_observed >= 3 counted values in every slice
            mad = np.nanmedian(np.abs(picked - median[..., None]), axis=-1)
            sigma = np.maximum(MAD_TO_SIGMA * mad, params.scale_floor_px)
            flagged = (np.abs(picked[..., half] - median) > params.n_sigma * sigma).any(axis=-1)
            outlier[a + frame[flagged], joint[flagged]] = True
        judged[a:b] = judged_here
    out = np.array(kp, copy=True)
    out[outlier] = np.nan
    out_reason = np.array(rs, copy=True)
    out_reason[outlier] = OUTLIER
    return HampelResult(
        keypoints=frozen(out),
        reason=frozen(out_reason),
        outlier=frozen(outlier),
        judged=frozen(judged),
        params=params,
    )


def hampel_track(
    masked: MaskedTrack, params: HampelParams | None = None, *, block_rows: int = DEFAULT_BLOCK_ROWS
) -> HampelResult:
    """The outliers of a masked ``TargetTrack``: its keypoints, reasons and real timestamps, margins included.

    The frames that are not the target's are ``not_tracked`` in the mask: they are not observed, do not count in a
    window and are never flagged. The timeline stays in ``masked``; the rows are the same.
    """
    return hampel_outliers(masked.mask.keypoints, masked.mask.reason, masked.t_sec, params, block_rows=block_rows)


def torso_length_px(keypoints: np.ndarray, reason: np.ndarray) -> float:
    """The length of the torso in pixels, the scale that a floor in pixels is read against.

    It is the median, over the frames in which the four torso joints (both shoulders, both hips) are observed
    (``reason == ok``), of the distance between the middle of the shoulders and the middle of the hips; a frame in which
    that distance is 0 is left out. The result is ``NaN`` when no frame qualifies: nothing is guessed. ``keypoints`` and
    ``reason`` are a layer as for ``hampel_outliers`` (pixels of the upright image; NaN exactly where ``reason`` is not
    ``ok``); the same checks apply and the times play no part. The inputs are not changed.
    """
    given = np.asarray(keypoints)
    kp, _, _ = check_layer(keypoints, reason, np.arange(given.shape[0] if given.ndim else 0, dtype=np.float64))
    l_shoulder, r_shoulder, l_hip, r_hip = TORSO_JOINTS
    values = kp.astype(np.float64)
    # a joint that is not observed is NaN (the contract of a layer), so a frame without all four has no length (NaN)
    length = np.linalg.norm(
        (values[:, l_shoulder] + values[:, r_shoulder]) / 2.0 - (values[:, l_hip] + values[:, r_hip]) / 2.0, axis=-1
    )
    usable = length[length > 0.0]  # NaN is not above 0; a frame with the shoulders on the hips is left out too
    return float(np.median(usable)) if usable.size else float("nan")
