"""Resampling of the gap layer onto a uniform grid (W6, P4.04): a regular clock for the filter, the way back kept.

The Butterworth filter of P4.05 needs samples on a regular clock; a video with a variable frame rate has rows at
irregular real times (``pts.parquet``). ``resample_layer`` takes the gap layer of ``quality/gaps.py`` and puts it on a
uniform grid by **linear interpolation in real time**; ``GridMap`` keeps the map between the grid and the source rows so
that a layer on the grid can be brought back to the source timestamps (``to_source``). The order of the stages is mask,
Hampel, gaps, resampling, filter (DEC-0046); the decisions of this module are DEC-0047.

**The timeline decides** (rule 1). The plan of the grid looks at ``t_sec`` only: it fits the least-squares straight line
through the row times, and if every row is within ``uniform_tol_s`` (0.001 s, +1e-9 s) of it the timeline is *uniform*
and the stage is the **identity**: the grid is the rows, nothing is touched, ``resampled`` is false (every constant
frame rate video; 1 ms covers the rounding of a time base of 1 ms, 0.5 ms at most, and a dropped frame is 33 ms off). An
explicit ``grid_hz`` always resamples. No frame rate is assumed anywhere (AGENTS.md section 5.2).

**Otherwise a regular grid** (rules 2 to 4), anchored at the first real row time: step = ``1 / grid_hz`` or the **median
interval** of the clip, ``t_grid[k] = t_0 + k x step`` up to the last row (never beyond it: nothing is extrapolated). A
grid time between rows ``l`` and ``l + 1`` has the weight ``w = (g - t_l) / (t_{l+1} - t_l)``; within 1e-9 s of a row it
*is* that row (``w = 0``, a copy). If ``w > 0`` and the interval between the two rows is more than ``max_step_s``
(0.150 s, the limit of the gap layer; plus 1e-9 s) the grid time is a **stall**: a pause in the timestamps is not
bridged, every cell is NaN with the reason ``no_frame`` (``mask.NO_FRAME``).

**The cells** (rules 5 to 7): between two usable cells (finite: observed or bridged) a cell is the linear mix
``a + w (b - a)`` in float64, x and y apart, cast to the input dtype; its flag ``interpolated`` is the OR of the
parents' (a value built on a bridged value is not observed), its reason is ``ok`` if both parents are, else the reason
of the parent that is not (the nearer one, the left one on a tie, if both are not). A cell next to an unusable cell is
**NaN, never filled**, with the reason of the unusable parent (the nearer if both are); it is not ``interpolated``. A
grid time that is a row copies value, reason and flag of that row bit for bit. ``mixed`` is a row flag: the grid time is
not a source row, so its values are linear mixes and not measurements. The result obeys the same contract as the input
(``check_gap_layer``).

**The way back** (rule 8): ``GridMap.to_source(values)`` takes values on the grid and gives values on the source rows: a
row that is a grid time is a copy, otherwise the linear mix of the two grid values around it if both are finite, else
NaN; a row after the last grid time (``beyond``, less than one step) is NaN. A usable source row next to a hole may lose
its value (one of its grid neighbours lies in the hole): on a variable-frame-rate clip a hole costs the rows within
about one step of it; a uniform clock (the identity) loses nothing. ``GridLayer.to_source`` also gives no value to a
source cell that was not usable at the source: a grid coarser than the rows could otherwise make one up. The reasons of
a layer on the source lattice are assigned by the stage that owns it.

Units and coordinates: positions are pixels of the upright image, x right, y down; times are seconds from the stream
start (real PTS). Inputs are not changed; the result arrays are new and read-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

from taiji_ai.pose.skeleton import NUM_JOINTS
from taiji_ai.quality import QualityError
from taiji_ai.quality._checks import check_gap_layer, check_times, frozen, is_real
from taiji_ai.quality.gaps import MAX_GAP_S, GapResult
from taiji_ai.quality.mask import NO_FRAME, OK

MAX_STEP_S: Final = MAX_GAP_S  # a pause in the timestamps longer than this is not bridged (the limit of the gap layer)
UNIFORM_TOL_S: Final = 0.001  # [s] a timeline within this of a straight line is uniform

_EPS_S: Final = 1e-9  # a grid time within this of a row is that row: the boundary must not depend on float rounding


@dataclass(frozen=True)
class ResampleParams:
    """The parameters of the resampling; the defaults are DEC-0047. Wrong values raise ``QualityError``."""

    grid_hz: float | None = None  # None, or finite and above 0: the grid rate; None = the median interval of the clip
    max_step_s: float = MAX_STEP_S  # [s] finite and above 0: a longer pause between two rows is not bridged
    uniform_tol_s: float = UNIFORM_TOL_S  # [s] finite, 0 or more: how far a row may be off a straight clock

    def __post_init__(self) -> None:
        hz = self.grid_hz
        if hz is not None and not (is_real(hz) and np.isfinite(hz) and hz > 0.0):
            raise QualityError(f"grid_hz must be None or a finite number of hertz above 0, got {hz!r}")
        step = self.max_step_s
        if not (is_real(step) and np.isfinite(step) and step > 0.0):
            raise QualityError(f"max_step_s must be a finite number of seconds above 0, got {step!r}")
        tol = self.uniform_tol_s
        if not (is_real(tol) and np.isfinite(tol) and tol >= 0.0):
            raise QualityError(f"uniform_tol_s must be a finite number of seconds, 0 or more, got {tol!r}")
        object.__setattr__(self, "grid_hz", None if hz is None else float(hz))
        object.__setattr__(self, "max_step_s", float(step))
        object.__setattr__(self, "uniform_tol_s", float(tol))


@dataclass(frozen=True, eq=False)
class GridMap:
    """The timing of a grid against its source rows (``T`` rows, ``G`` grid times); every array is read-only."""

    t_source: np.ndarray  # (T,) float64 [s]; the real row times
    t_grid: np.ndarray  # (G,) float64 [s]; the grid times (the row times for the identity)
    step_s: float  # [s] the regular interval that the filter uses; NaN for fewer than two rows
    left: np.ndarray  # (G,) int32; the grid time lies between rows ``left`` and ``left + 1``
    weight: np.ndarray  # (G,) float64 in [0, 1); how far from row ``left`` to ``left + 1``; 0 = the grid time is a row
    stall: np.ndarray  # (G,) bool; between rows more than ``max_step_s`` apart: not bridged
    identity: bool  # the timeline is uniform: the grid is the rows
    back_left: np.ndarray  # (T,) int32; the row lies between grid times ``back_left`` and ``back_left + 1``
    back_weight: np.ndarray  # (T,) float64 in [0, 1); how far from grid time ``back_left`` to the next; 0 = a grid time
    beyond: np.ndarray  # (T,) bool; the row is after the last grid time: no right neighbour, no value

    @property
    def resampled(self) -> bool:
        """The manifest entry of W6: the layer on the grid is not the layer on the rows."""
        return not self.identity

    def to_source(self, values: np.ndarray) -> np.ndarray:
        """Values on the grid (``(G, ...)`` float) as values on the source rows (``(T, ...)``, a new read-only array).

        A row that is a grid time is a copy (a NaN too); otherwise the linear mix of the two grid values around it if
        both are finite, else NaN; a row after the last grid time is NaN. Computed in float64, cast back to the input
        dtype.
        """
        v = np.asarray(values)
        rows = len(self.t_grid)
        if v.dtype.kind != "f" or v.ndim < 1 or v.shape[0] != rows:
            raise QualityError(
                f"values must be a floating-point array with {rows} rows (one per grid time), got {v.dtype} {v.shape}"
            )
        if self.identity:
            return frozen(np.array(v, copy=True))
        n = len(self.t_source)
        w = self.back_weight.reshape((n,) + (1,) * (v.ndim - 1))
        left = self.back_left.astype(np.int64)
        a = v[left].astype(np.float64)
        b = v[np.minimum(left + 1, rows - 1)].astype(np.float64)
        with np.errstate(invalid="ignore"):  # inf times 0 in a value that the caller passed
            mixed = a + w * (b - a)
        out = np.where(w > 0.0, mixed, a)
        out[self.beyond] = np.nan
        return frozen(out.astype(v.dtype))


@dataclass(frozen=True, eq=False)
class GridLayer:
    """The gap layer on the grid (``G`` grid times); every array is new and read-only. Same contract as the input."""

    keypoints: np.ndarray  # (G, 26, 2) the input dtype; copies, linear mixes, or NaN
    reason: np.ndarray  # (G, 26) uint8; the reason of the cell (rules 5 and 6), ``no_frame`` in a stall
    interpolated: np.ndarray  # (G, 26) bool; the cell is a bridged value or was built on one
    mixed: np.ndarray  # (G,) bool; the grid time is not a source row: the values are linear mixes, not measurements
    source_usable: np.ndarray  # (T, 26) bool; the source cell had a value (observed or bridged)
    gridmap: GridMap
    params: ResampleParams

    @property
    def usable(self) -> np.ndarray:
        """``(G, 26)`` bool: the cell has a value."""
        return ~np.isnan(self.keypoints[..., 0])

    @property
    def observed(self) -> np.ndarray:
        """``(G, 26)`` bool: ``reason == ok``: every parent is an observed cell (a mixed cell is still a mix)."""
        return self.reason == OK

    def to_source(self, values: np.ndarray) -> np.ndarray:
        """``GridMap.to_source`` with no value for a source cell that was not usable at the source."""
        out = np.array(self.gridmap.to_source(values), copy=True)
        if out.ndim < 2 or out.shape[1] != NUM_JOINTS:
            raise QualityError(f"values must have shape (G, {NUM_JOINTS}, ...) like a layer, got {np.shape(values)}")
        keep = self.source_usable.reshape(self.source_usable.shape + (1,) * (out.ndim - 2))
        out[~np.broadcast_to(keep, out.shape)] = np.nan
        return frozen(out)


def _identity_map(t: np.ndarray, step_s: float) -> GridMap:
    n = len(t)
    index = np.arange(n, dtype=np.int32)
    return GridMap(
        t_source=frozen(np.array(t, copy=True)),
        t_grid=frozen(np.array(t, copy=True)),
        step_s=step_s,
        left=frozen(index.copy()),
        weight=frozen(np.zeros(n)),
        stall=frozen(np.zeros(n, dtype=bool)),
        identity=True,
        back_left=frozen(index.copy()),
        back_weight=frozen(np.zeros(n)),
        beyond=frozen(np.zeros(n, dtype=bool)),
    )


def plan_grid(t_sec: np.ndarray, params: ResampleParams | None = None) -> GridMap:
    """The grid for the real row times ``t_sec`` (finite, strictly increasing seconds): rules 1 to 4 and the map back.

    Zero or one row is the identity. The map depends on the times only.
    """
    params = ResampleParams() if params is None else params
    given = np.asarray(t_sec)
    if given.ndim != 1:
        raise QualityError(f"t_sec must be a one-dimensional array of seconds, got shape {given.shape}")
    t = np.asarray(check_times(given, given.shape[0]), dtype=np.float64)
    n = len(t)
    if n <= 1:
        return _identity_map(t, float("nan"))
    index = np.arange(n, dtype=np.float64)
    centred = index - index.mean()
    slope = float(np.dot(centred, t - t.mean()) / np.dot(centred, centred))  # least-squares line through the times
    deviation = float(np.abs(t - (t.mean() + slope * centred)).max())
    if deviation <= params.uniform_tol_s + _EPS_S and params.grid_hz is None:
        return _identity_map(t, slope)
    step = 1.0 / params.grid_hz if params.grid_hz is not None else float(np.median(np.diff(t)))
    count = int(np.floor((t[-1] - t[0] + _EPS_S) / step)) + 1
    grid = t[0] + np.arange(count, dtype=np.float64) * step
    left = np.searchsorted(t, grid + _EPS_S, side="right").astype(np.int64) - 1  # the last row at or before the time
    gap = t[np.minimum(left + 1, n - 1)] - t[left]
    with np.errstate(invalid="ignore", divide="ignore"):
        weight = np.where(gap > 0.0, (grid - t[left]) / gap, 0.0)  # the last row has no right neighbour: gap is 0
    weight = np.where(np.abs(grid - t[left]) <= _EPS_S, 0.0, weight)
    stall = (weight > 0.0) & (gap > params.max_step_s + _EPS_S)
    back = np.searchsorted(grid, t + _EPS_S, side="right").astype(np.int64) - 1
    back_weight = np.where(np.abs(t - grid[back]) <= _EPS_S, 0.0, (t - grid[back]) / step)
    return GridMap(
        t_source=frozen(np.array(t, copy=True)),
        t_grid=frozen(grid),
        step_s=step,
        left=frozen(left.astype(np.int32)),
        weight=frozen(weight),
        stall=frozen(stall),
        identity=False,
        back_left=frozen(back.astype(np.int32)),
        back_weight=frozen(back_weight),
        beyond=frozen((back == count - 1) & (back_weight > 0.0)),
    )


def resample_layer(
    keypoints: np.ndarray,
    reason: np.ndarray,
    interpolated: np.ndarray,
    t_sec: np.ndarray,
    params: ResampleParams | None = None,
) -> GridLayer:
    """Put a gap layer on a uniform grid; see the module docstring for the rules.

    ``keypoints`` ``(T, 26, 2)`` float (pixels), ``reason`` ``(T, 26)`` uint8, ``interpolated`` ``(T, 26)`` bool: the
    arrays of ``GapResult``; ``t_sec`` ``(T,)`` real seconds, finite and strictly increasing. The inputs are not
    changed. Raises ``QualityError`` for anything else.
    """
    params = ResampleParams() if params is None else params
    kp, rs, flag, t = check_gap_layer(keypoints, reason, interpolated, t_sec)
    gridmap = plan_grid(t, params)
    source_usable = ~np.isnan(kp[..., 0])
    if gridmap.identity:
        out_kp, out_rs, out_flag = np.array(kp, copy=True), np.array(rs, copy=True), np.array(flag, copy=True)
        mixed = np.zeros(len(t), dtype=bool)
    else:
        left = gridmap.left.astype(np.int64)
        right = np.minimum(left + 1, len(t) - 1)
        w = gridmap.weight
        copy = (w == 0.0)[:, None]
        stall = gridmap.stall[:, None]
        a_kp, b_kp = kp[left].astype(np.float64), kp[right].astype(np.float64)
        a_ok, b_ok = source_usable[left], source_usable[right]
        a_rs, b_rs = rs[left], rs[right]
        both = a_ok & b_ok & ~stall  # the cell is a mix of two usable cells
        mix = a_kp + w[:, None, None] * (b_kp - a_kp)
        out_kp = np.where(copy[..., None], a_kp, np.where(both[..., None], mix, np.nan)).astype(kp.dtype)
        nearer = np.where((w <= 0.5)[:, None], a_rs, b_rs)  # the left parent on the tie
        of_pair = np.where(
            (a_rs == OK) & (b_rs == OK), OK, np.where(a_rs == OK, b_rs, np.where(b_rs == OK, a_rs, nearer))
        )
        of_hole = np.where(a_ok, b_rs, np.where(b_ok, a_rs, nearer))  # the unusable parent, the nearer if both
        out_rs = np.where(copy, a_rs, np.where(stall, NO_FRAME, np.where(a_ok & b_ok, of_pair, of_hole))).astype(
            np.uint8
        )
        out_flag = np.where(copy, flag[left], both & (flag[left] | flag[right]))
        mixed = (w > 0.0) & ~gridmap.stall
    return GridLayer(
        keypoints=frozen(out_kp),
        reason=frozen(out_rs),
        interpolated=frozen(out_flag),
        mixed=frozen(mixed),
        source_usable=frozen(source_usable),
        gridmap=gridmap,
        params=params,
    )


def resample_gaps(result: GapResult, t_sec: np.ndarray, params: ResampleParams | None = None) -> GridLayer:
    """The grid layer of a ``GapResult`` (``interpolate_gaps`` or ``interpolate_track``) and its real timestamps."""
    return resample_layer(result.keypoints, result.reason, result.interpolated, t_sec, params)
