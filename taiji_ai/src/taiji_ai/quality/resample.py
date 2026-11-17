"""Resampling of the gap layer onto a uniform grid (W6, P4.04, X.31): a regular clock for the filter, the way back kept.

The Butterworth filter of P4.05 needs samples on a regular clock; a video with a variable frame rate has rows at
irregular real times (``pts.parquet``). ``resample_layer`` takes the gap layer of ``quality/gaps.py`` and puts it on a
uniform grid by **linear interpolation in real time**; ``GridMap`` keeps the map between the grid and the source rows
so that a layer on the grid can be brought back to the source timestamps (``to_source``). The order of the stages is
mask, Hampel, gaps, resampling, filter (DEC-0046); the decisions of this module are DEC-0047, amended by DEC-0052
(X.31).

**The timeline decides** (rule 1). The plan of the grid looks at ``t_sec`` only: it fits the least-squares straight
line through the row times, and if every row is within ``uniform_tol_s`` (0.001 s, +1e-9 s) of it the timeline is
*uniform* and the stage is the **identity**: the grid is the rows, nothing is touched, ``resampled`` is false (every
constant frame rate video; 1 ms covers the rounding of a time base of 1 ms, 0.5 ms at most, and a dropped frame is 33
ms off). An explicit ``grid_hz`` always resamples. No frame rate is assumed anywhere (AGENTS.md section 5.2).

**Otherwise a regular grid** (rules 2 to 4), ``t_grid[j] = phase + j x step`` for the integers ``j`` whose time lies
in ``[t_0 - snap, t_last + snap]``: nothing is extrapolated beyond the tolerance. *The lattice of the clock*
(DEC-0052): with no ``grid_hz`` the step and the phase are **fitted to the row times**. An interval is *regular* if it
is at least half of the median interval and at most ``max_step_s`` (0.150 s, the limit of the gap layer; plus 1e-9 s);
a *run* is a stretch of rows joined by regular intervals (a pause, or a burst of rows finer than the clock, ends a run
and is outside the fit). An interval spans ``max(1, round(interval / step))`` frames (a dropped frame is one frame
more, not a longer step), the frame index of a row counts from the start of its run, and the step is the least-squares
slope of the row times against that index with one phase per run; the phase of the grid is the one of the longest run
(the first on a tie). A clock in whole milliseconds with dropped frames gets its true step (33.333 ms, not the median
33 ms nor a mean dragged up by the drops) and the phase of its lattice (not that of a first row that may be off it).
No run of two rows: the median interval and the first row, as in DEC-0047. An explicit ``grid_hz`` gives step ``1 /
grid_hz`` anchored at the first row.

**A grid time that is a row** (rule 3). ``snap = min(uniform_tol_s, step / 4) + 1e-9 s``: the same 1 ms that decides a
uniform clock, the precision of a time stamp. A grid time whose nearest row (the earlier on a tie) is within ``snap``
*is* that row: value, reason and flag are copied bit for bit and ``mixed`` is false; the value is then at most
``snap`` away from its grid time (that is the price, and it is measured in ``Docs/tasks/X.31.md``). ``uniform_tol_s =
0`` leaves only 1e-9 s, the exact rule. A grid time between rows ``l`` and ``l + 1`` and farther than ``snap`` from
both has the weight ``w = (g - t_l) / (t_{l+1} - t_l)``; if ``w > 0`` and the interval between the two rows is more
than ``max_step_s`` the grid time is a **stall**: a pause in the timestamps is not bridged, every cell is NaN with the
reason ``no_frame`` (``mask.NO_FRAME``).

**The cells** (rules 5 to 7): between two usable cells (finite: observed or bridged) a cell is the linear mix ``a + w
(b - a)`` in float64, x and y apart, cast to the input dtype; its flag ``interpolated`` is the OR of the parents' (a
value built on a bridged value is not observed), its reason is ``ok`` if both parents are, else the reason of the
parent that is not (the nearer one, the left one on a tie within 1e-9, if both are not). A cell next to an unusable
cell is **NaN, never filled**, with the reason of the unusable parent (the nearer if both); it is not
``interpolated``. A grid time that is a row copies value, reason and flag of that row bit for bit. ``mixed`` is a row
flag: the grid time is not a source row, so its values are linear mixes and not measurements. The result obeys the
same contract as the input (``check_gap_layer``).

**The way back** (rule 8): ``GridMap.to_source(values)`` takes values on the grid and gives values on the source rows:
a row within ``snap`` of a grid time (the nearest) is a copy, otherwise the linear mix of the two grid values around
it if both are finite, else NaN; a row before the first grid time (``before``) or after the last (``beyond``), and not
within ``snap`` of one, has no neighbour on one side and is NaN: at most the rows of one step at each end of a clip. A
usable source row next to a hole may lose its value (one of its grid neighbours lies in the hole): on a
variable-frame-rate clip a hole costs the rows within about one step of it; a uniform clock (the identity) loses
nothing. ``GridLayer.to_source`` also gives no value to a source cell that was not usable at the source: a grid
coarser than the rows could otherwise make one up. The reasons of a layer on the source lattice are assigned by the
stage that owns it.

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
UNIFORM_TOL_S: Final = 0.001  # [s] a timeline within this of a line is uniform; a row this near a grid time is it
SNAP_STEP_FRACTION: Final = 0.25  # the tolerance of a row on a grid time is at most this share of the grid step

_EPS_S: Final = 1e-9  # a grid time within this of a row is that row: the boundary must not depend on float rounding


@dataclass(frozen=True)
class ResampleParams:
    """The parameters of the resampling; the defaults are DEC-0047. Wrong values raise ``QualityError``."""

    grid_hz: float | None = None  # None, or finite and above 0: the grid rate; None = the median interval of the clip
    max_step_s: float = MAX_STEP_S  # [s] finite and above 0: a longer pause between two rows is not bridged
    uniform_tol_s: float = UNIFORM_TOL_S  # [s] finite, 0 or more: how far a row may be off a straight clock or the grid

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


def values_on_rows(
    values: np.ndarray, back_left: np.ndarray, back_weight: np.ndarray, outside: np.ndarray
) -> np.ndarray:
    """Values on the grid (``(G, ...)`` float) as values on the ``T`` source rows (a new array of the same dtype).

    The formula of ``GridMap.to_source``, given the map: row ``i`` is ``values[back_left[i]]`` if ``back_weight[i]``
    is 0, else the linear mix of ``values[back_left[i]]`` and the next grid value with that weight (NaN if either is
    NaN); a row that is ``outside`` the grid is NaN. Computed in float64, cast back to the dtype of ``values``. The map
    is taken as it is (``GridMap`` has it from the plan, ``pose_filtered.npz`` stores it): nothing is checked here.
    """
    rows = values.shape[0]
    w = back_weight.reshape((len(back_left),) + (1,) * (values.ndim - 1))
    left = back_left.astype(np.int64)
    a = values[left].astype(np.float64)
    b = values[np.minimum(left + 1, rows - 1)].astype(np.float64)
    with np.errstate(invalid="ignore"):  # inf times 0 in a value that the caller passed
        mixed = a + w * (b - a)
    out = np.where(w > 0.0, mixed, a)
    out[outside] = np.nan
    return out.astype(values.dtype)


@dataclass(frozen=True, eq=False)
class GridMap:
    """The timing of a grid against its source rows (``T`` rows, ``G`` grid times); every array is read-only."""

    t_source: np.ndarray  # (T,) float64 [s]; the real row times
    t_grid: np.ndarray  # (G,) float64 [s]; the grid times (the row times for the identity)
    step_s: float  # [s] the regular interval that the filter uses; NaN for fewer than two rows
    snap_s: float  # [s] a grid time within this of a row is that row (0 for the identity)
    left: np.ndarray  # (G,) int32; a copy: its row (the nearest within ``snap_s``); else the row before the grid time
    weight: np.ndarray  # (G,) float64 in [0, 1); how far from row ``left`` to ``left + 1``; 0 = the grid time is a row
    stall: np.ndarray  # (G,) bool; between rows more than ``max_step_s`` apart: not bridged
    identity: bool  # the timeline is uniform: the grid is the rows
    back_left: np.ndarray  # (T,) int32; a copy: its grid time (nearest within ``snap_s``); else the one before the row
    back_weight: np.ndarray  # (T,) float64 in [0, 1); how far from grid time ``back_left`` to the next; 0 = a grid time
    before: np.ndarray  # (T,) bool; the row is before the first grid time and not on it: no left neighbour, no value
    beyond: np.ndarray  # (T,) bool; the row is after the last grid time and not on it: no right neighbour, no value

    @property
    def resampled(self) -> bool:
        """The manifest entry of W6: the layer on the grid is not the layer on the rows."""
        return not self.identity

    def to_source(self, values: np.ndarray) -> np.ndarray:
        """Values on the grid (``(G, ...)`` float) as values on the source rows (``(T, ...)``, a new read-only array).

        A row within ``snap_s`` of a grid time is a copy of its value (a NaN too); otherwise the linear mix of the two
        grid values around it if both are finite, else NaN; a row before the first grid time or after the last (and not
        on it) is NaN. Computed in float64, cast back to the input dtype.
        """
        v = np.asarray(values)
        rows = len(self.t_grid)
        if v.dtype.kind != "f" or v.ndim < 1 or v.shape[0] != rows:
            raise QualityError(
                f"values must be a floating-point array with {rows} rows (one per grid time), got {v.dtype} {v.shape}"
            )
        if self.identity:
            return frozen(np.array(v, copy=True))
        return frozen(values_on_rows(v, self.back_left, self.back_weight, self.before | self.beyond))


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
        snap_s=0.0,
        left=frozen(index.copy()),
        weight=frozen(np.zeros(n)),
        stall=frozen(np.zeros(n, dtype=bool)),
        identity=True,
        back_left=frozen(index.copy()),
        back_weight=frozen(np.zeros(n)),
        before=frozen(np.zeros(n, dtype=bool)),
        beyond=frozen(np.zeros(n, dtype=bool)),
    )


def _fit_lattice(t: np.ndarray, max_step_s: float) -> tuple[float, float] | None:
    """The step and the phase of the lattice that the row times follow (DEC-0052), or None if they follow none.

    ``t`` (``n >= 2``, finite, strictly increasing) in seconds. Returns ``(step_s, phase_s)``: ``phase_s + j x step_s``
    are the lattice times (``phase_s`` is the lattice time of the first row of the longest run). None when no interval
    is regular (every interval is a pause or a burst) or the fit is not a finite step above 0.
    """
    d = np.diff(t)
    nominal = float(np.median(d))
    regular = (d >= 0.5 * nominal) & (d <= max_step_s + _EPS_S)
    if not regular.any():
        return None
    run = np.concatenate(([0], np.cumsum(~regular))).astype(np.int64)  # (n,) the run of each row
    first = np.concatenate(([0], np.flatnonzero(~regular) + 1))  # (runs,) the first row of each run
    rows = np.bincount(run)
    step = nominal
    for _ in range(2):  # the second pass counts the frames of the intervals with the step found by the first
        frames = np.where(regular, np.maximum(1.0, np.round(d / step)), 0.0)
        cumulated = np.concatenate(([0.0], np.cumsum(frames)))
        index = cumulated - cumulated[first][run]  # the frame index of a row, from the start of its run
        index_mean = np.bincount(run, weights=index) / rows
        time_mean = np.bincount(run, weights=t) / rows
        dk, dt = index - index_mean[run], t - time_mean[run]
        spread = float(np.dot(dk, dk))
        if spread <= 0.0:
            return None
        step = float(np.dot(dk, dt)) / spread  # a common slope, one intercept per run
        if not (np.isfinite(step) and step > 0.0):
            return None
    longest = int(np.argmax(rows))
    return step, float(time_mean[longest] - step * index_mean[longest])


def _window(t: np.ndarray, phase: float, step: float, snap: float) -> tuple[int, int]:
    """The first and last lattice index whose time lies in ``[t_0 - snap, t_last + snap]``."""
    return int(np.ceil((t[0] - snap - phase) / step)), int(np.floor((t[-1] + snap - phase) / step))


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
    if params.grid_hz is not None:
        step, phase = 1.0 / params.grid_hz, float(t[0])
    else:
        fit = _fit_lattice(t, params.max_step_s)
        step, phase = fit if fit is not None else (float(np.median(np.diff(t))), float(t[0]))
    snap = min(params.uniform_tol_s, SNAP_STEP_FRACTION * step) + _EPS_S
    j0, j1 = _window(t, phase, step, snap)
    if j1 < j0:  # the fitted lattice has no time inside the clip: the first row anchors the grid (index 0 is inside)
        phase = float(t[0])
        j0, j1 = _window(t, phase, step, snap)
    grid = phase + np.arange(j0, j1 + 1, dtype=np.float64) * step
    count = len(grid)
    # grid time -> row: the nearest row within ``snap`` is a copy (the earlier one on a tie); else the rows around it
    last_row = np.searchsorted(t, grid, side="right").astype(np.int64) - 1  # the last row at or before the time
    lo, hi = np.clip(last_row, 0, n - 1), np.clip(last_row + 1, 0, n - 1)
    d_lo, d_hi = np.abs(grid - t[lo]), np.abs(grid - t[hi])
    # a grid time at or past an end row is that row (the window is within ``snap`` of the ends: float rounding at its
    # edge must not make a mix with a weight outside [0, 1))
    copy = (np.minimum(d_lo, d_hi) <= snap) | (grid <= t[0]) | (grid >= t[-1])
    left = np.where(copy, np.where(d_hi < d_lo, hi, lo), lo)  # a mix has its two rows: the window ends are copies
    gap = t[np.minimum(left + 1, n - 1)] - t[left]
    weight = np.zeros(count)
    np.divide(grid - t[left], gap, out=weight, where=~copy)
    stall = ~copy & (gap > params.max_step_s + _EPS_S)
    # row -> grid time: the nearest grid time within ``snap`` is a copy; a row outside the grid has no value
    last_grid = np.searchsorted(grid, t, side="right").astype(np.int64) - 1  # the last grid time at or before the row
    lo, hi = np.clip(last_grid, 0, count - 1), np.clip(last_grid + 1, 0, count - 1)
    d_lo, d_hi = np.abs(t - grid[lo]), np.abs(t - grid[hi])
    on = np.minimum(d_lo, d_hi) <= snap
    before = ~on & (last_grid < 0)
    beyond = ~on & (last_grid >= count - 1)
    back = np.where(on, np.where(d_hi < d_lo, hi, lo), lo)
    back_weight = np.zeros(n)
    between = ~(on | before | beyond)
    back_weight[between] = (t[between] - grid[back[between]]) / step
    return GridMap(
        t_source=frozen(np.array(t, copy=True)),
        t_grid=frozen(grid),
        step_s=step,
        snap_s=snap,
        left=frozen(left.astype(np.int32)),
        weight=frozen(weight),
        stall=frozen(stall),
        identity=False,
        back_left=frozen(back.astype(np.int32)),
        back_weight=frozen(back_weight),
        before=frozen(before),
        beyond=frozen(beyond),
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
        nearer = np.where((w <= 0.5 + _EPS_S)[:, None], a_rs, b_rs)  # the left parent on the tie (within 1e-9)
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
