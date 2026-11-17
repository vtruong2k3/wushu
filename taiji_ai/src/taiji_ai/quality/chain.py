"""The quality chain of the pose (W6, P4.07): the stages wired in their order, and the report of what they kept.

``run_quality_arrays`` (arrays) and ``run_quality`` (a ``TargetTrack`` of W5) run the six stages in the order that
DEC-0046 and DEC-0049 fixed and return **every layer** (they stay apart, AGENTS.md section 5.3) with the report:

1. the **mask** (``quality/mask.py``): a keypoint under ``tau_kp`` or not finite, a frame that is not the target's or
   has too few essential joints, is NaN with a reason;
2. the **torso** of the mask layer (``torso_length_px``), the scale of the swap flag and of the Hampel floor;
3. the **swap flag** (``quality/lr_swap.py``) on the mask layer: a warning, no value or label is changed;
4. **Hampel** (``quality/filters.py``) on the mask layer (not on the layer after the swap flag): an outlier is NaN with
   the reason ``outlier``; its floor is ``hampel_floor_fraction`` x the torso in pixels (1 %: 2 px at the 197 px torso
   on which the 2 px was chosen), or the floor of ``HampelParams`` as it is when the fraction is ``None`` or the torso
   cannot be measured (the warning ``torso_unmeasured`` says so);
5. the **gap layer** (``quality/gaps.py``) on the Hampel layer, the swap mask as ``blocked``: a short gap is bridged,
   flagged;
6. the **uniform grid** (``quality/resample.py``): the identity for a constant frame rate;
7. the **Butterworth low-pass** (``quality/filters.py``) run by run on the grid layer.

The result of a stage is never fed back into an earlier one. The layers and the report are read-only (the arrays) or
frozen (the models); nothing that was passed in is changed. A ``QualityError`` of a stage is re-raised with the name of
the stage in front (``mask``, ``torso``, ``lr_swap``, ``hampel``, ``gaps``, ``resample``, ``filter``).

The report (``taiji_ai.schemas.quality.QualityReport``, ``quality.json`` through ``quality/quality_io.py``) is the
coverage of ``quality/coverage.py`` over the grid lattice plus the clock, the parameters as used and the warnings. The
final layer on the rows of the video, for an overlay, is ``QualityResult.filtered_on_source()`` (no loss on a uniform
clock; about 0.07 % of the cells on a variable one, at the edges of holes).

Units and coordinates: pixels of the upright image (x right, y down), times in seconds from the stream start.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

import numpy as np

from taiji_ai.quality import QualityError
from taiji_ai.quality._checks import frozen, is_real
from taiji_ai.quality.coverage import compute_coverage, parse_intervals, swap_warnings
from taiji_ai.quality.filters import (
    ButterworthParams,
    FilterResult,
    HampelParams,
    HampelResult,
    hampel_outliers,
    lowpass_grid,
    torso_length_px,
)
from taiji_ai.quality.gaps import GapParams, GapResult, interpolate_gaps
from taiji_ai.quality.lr_swap import SwapParams, SwapResult, detect_lr_swaps
from taiji_ai.quality.mask import MaskParams, MaskResult, apply_mask, mask_track
from taiji_ai.quality.resample import GridLayer, ResampleParams, resample_gaps
from taiji_ai.schemas.quality import (
    FilterParamsRecord,
    GapParamsRecord,
    HampelParamsRecord,
    MaskParamsRecord,
    QualityParamsRecord,
    QualityReport,
    ResampleParamsRecord,
    SwapParamsRecord,
    Timeline,
)
from taiji_ai.track.state import TargetTrack

log = logging.getLogger(__name__)

DEFAULT_FLOOR_FRACTION = 0.01  # the Hampel floor as a share of the torso (Q3 of P4.07, DEC-0050)


@dataclass(frozen=True)
class QualityParams:
    """The parameters of every stage and the rule of the Hampel floor; the defaults are those of the stages.

    ``hampel_floor_fraction``: ``None`` or a finite number, 0 or more. A number makes the floor of Hampel that share of
    the torso of the mask layer (``hampel.scale_floor_px`` is then not used); ``None`` uses ``hampel.scale_floor_px`` as
    it is. Wrong values raise ``QualityError``.
    """

    mask: MaskParams = field(default_factory=MaskParams)
    swap: SwapParams = field(default_factory=SwapParams)
    hampel: HampelParams = field(default_factory=HampelParams)
    hampel_floor_fraction: float | None = DEFAULT_FLOOR_FRACTION
    gaps: GapParams = field(default_factory=GapParams)
    resample: ResampleParams = field(default_factory=ResampleParams)
    filter: ButterworthParams = field(default_factory=ButterworthParams)

    def __post_init__(self) -> None:
        for name, cls in (
            ("mask", MaskParams),
            ("swap", SwapParams),
            ("hampel", HampelParams),
            ("gaps", GapParams),
            ("resample", ResampleParams),
            ("filter", ButterworthParams),
        ):
            value = getattr(self, name)
            if not isinstance(value, cls):
                raise QualityError(f"{name} must be a {cls.__name__}, got {value!r}")
        fraction = self.hampel_floor_fraction
        if fraction is not None:
            if not (is_real(fraction) and np.isfinite(fraction) and fraction >= 0.0):
                raise QualityError(
                    f"hampel_floor_fraction must be None or a finite number, at least 0, got {fraction!r}"
                )
            object.__setattr__(self, "hampel_floor_fraction", float(fraction))


@dataclass(frozen=True, eq=False)
class QualityResult:
    """The layers of the chain, side by side, and the report; every array is read-only (``T`` rows, ``G`` grid rows)."""

    mask: MaskResult  # (T, ...) the mask layer
    swap: SwapResult  # (T, ...) the swap flag, read from the mask layer
    hampel: HampelResult  # (T, ...) the mask layer with the outliers taken out
    gaps: GapResult  # (T, ...) the Hampel layer with the short gaps bridged, flagged
    grid: GridLayer  # (G, ...) the gap layer on the uniform grid (the rows themselves for a uniform clock)
    filtered: FilterResult  # (G, ...) the final layer: the low-passed grid layer
    t_sec: np.ndarray  # (T,) float64 [s] the real row times
    in_segment: np.ndarray  # (T,) bool the rows of the segment (all rows when none was given)
    torso_px: float  # [px] the median torso of the mask layer; NaN when it could not be measured
    params: QualityParams  # as used: the Hampel floor is in pixels
    report: QualityReport

    def filtered_on_source(self) -> np.ndarray:
        """The final keypoints ``(T, 26, 2)`` on the rows of the video: NaN where the grid cannot give a value."""
        return self.grid.to_source(self.filtered.keypoints)


def _stage[R](name: str, fn: Callable[..., R], *args: Any, **kwargs: Any) -> R:
    """Run a stage; a ``QualityError`` is re-raised with the name of the stage in front."""
    try:
        return fn(*args, **kwargs)
    except QualityError as exc:
        raise QualityError(f"{name}: {exc}") from exc


def _check_in_segment(in_segment: Any, n: int) -> np.ndarray:
    if in_segment is None:
        return np.ones(n, dtype=bool)
    given = np.asarray(in_segment)
    if given.dtype != np.bool_ or given.shape != (n,):
        raise QualityError(f"in_segment must be a bool array of shape ({n},), got {given.dtype} {given.shape}")
    return np.array(given, copy=True)


def _finite_or_none(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def _params_record(used: QualityParams) -> QualityParamsRecord:
    hampel = used.hampel
    return QualityParamsRecord(
        mask=MaskParamsRecord(
            tau_kp=used.mask.tau_kp,
            essential=used.mask.essential,
            min_essential_fraction=used.mask.min_essential_fraction,
        ),
        swap=SwapParamsRecord(
            min_jump=used.swap.min_jump,
            max_cross_ratio=used.swap.max_cross_ratio,
            max_dt_s=used.swap.max_dt_s,
            max_swap_s=used.swap.max_swap_s,
            pairs=used.swap.pairs,
        ),
        hampel=HampelParamsRecord(
            window=hampel.window,
            n_sigma=hampel.n_sigma,
            min_observed=cast(int, hampel.min_observed),  # ``HampelParams.__post_init__`` resolves ``None`` to an int
            max_half_span_s=hampel.max_half_span_s,
            scale_floor_px=hampel.scale_floor_px,
            floor_fraction=used.hampel_floor_fraction,
        ),
        gaps=GapParamsRecord(max_gap_s=used.gaps.max_gap_s, never_fill=used.gaps.never_fill),
        resample=ResampleParamsRecord(
            grid_hz=used.resample.grid_hz,
            max_step_s=used.resample.max_step_s,
            uniform_tol_s=used.resample.uniform_tol_s,
        ),
        filter=FilterParamsRecord(cutoff_hz=used.filter.cutoff_hz, order=used.filter.order, padlen=used.filter.padlen),
    )


def _run(
    mask: MaskResult,
    t_sec: Any,
    in_segment: np.ndarray,
    params: QualityParams,
    intervals: Mapping[str, tuple[float, float]] | None,
) -> QualityResult:
    torso = _stage("torso", torso_length_px, mask.keypoints, mask.reason)
    measured = bool(np.isfinite(torso))
    swap = _stage(
        "lr_swap",
        detect_lr_swaps,
        mask.keypoints,
        mask.reason,
        t_sec,
        params.swap,
        torso_px=torso if measured else None,
    )
    hampel_params = params.hampel
    if params.hampel_floor_fraction is not None and measured:
        hampel_params = dataclasses.replace(hampel_params, scale_floor_px=params.hampel_floor_fraction * torso)
    hampel = _stage("hampel", hampel_outliers, mask.keypoints, mask.reason, t_sec, hampel_params)
    blocked = swap.blocked
    gaps = _stage("gaps", interpolate_gaps, hampel.keypoints, hampel.reason, t_sec, params.gaps, blocked)
    grid = _stage("resample", resample_gaps, gaps, t_sec, params.resample)
    filtered = _stage("filter", lowpass_grid, grid, params.filter)

    t = frozen(np.array(t_sec, dtype=np.float64, copy=True))
    seg = frozen(np.array(in_segment, copy=True))
    used = dataclasses.replace(params, hampel=hampel_params)
    coverage = compute_coverage(
        t_sec=t,
        in_segment=seg,
        gaps=gaps,
        suspect=swap.suspect,
        blocked=blocked,
        grid=grid,
        filtered=filtered,
        essential=params.mask.essential,
        min_essential_fraction=params.mask.min_essential_fraction,
        intervals=intervals,
    )
    hz = filtered.sampling_hz
    warnings = swap_warnings(t, seg, blocked)
    if not measured:
        warnings.append("torso_unmeasured")
    if grid.gridmap.resampled:
        warnings.append("grid_resampled")
    if np.isfinite(hz) and params.filter.cutoff_hz >= hz / 2.0:
        warnings.append("filter_skipped_above_nyquist")
    report = QualityReport(
        schema_version="quality/1",
        skeleton="halpe26/1",
        params=_params_record(used),
        timeline=Timeline(
            rows=len(t),
            grid_rows=len(grid.keypoints),
            resampled=grid.gridmap.resampled,
            step_s=_finite_or_none(grid.gridmap.step_s),
            sampling_hz=_finite_or_none(hz),
            torso_px=_finite_or_none(torso),
        ),
        intervals=coverage,
        warnings=tuple(warnings),
    )
    log.info("quality chain: %d rows, %d grid rows, %d warnings", len(t), len(grid.keypoints), len(warnings))
    return QualityResult(
        mask=mask,
        swap=swap,
        hampel=hampel,
        gaps=gaps,
        grid=grid,
        filtered=filtered,
        t_sec=t,
        in_segment=seg,
        torso_px=float(torso),
        params=used,
        report=report,
    )


def _check_params(params: QualityParams | None) -> QualityParams:
    if params is None:
        return QualityParams()
    if not isinstance(params, QualityParams):
        raise QualityError(f"params must be a QualityParams, got {params!r}")
    return params


def run_quality_arrays(
    keypoints: np.ndarray,
    scores: np.ndarray,
    t_sec: np.ndarray,
    *,
    tracked: np.ndarray | None = None,
    in_segment: np.ndarray | None = None,
    params: QualityParams | None = None,
    intervals: Mapping[str, tuple[float, float]] | None = None,
) -> QualityResult:
    """The chain over arrays: ``keypoints`` ``(T, 26, 2)`` float (pixels), ``scores`` ``(T, 26)``, ``t_sec`` ``(T,)``
    finite strictly increasing seconds, ``tracked`` ``(T,)`` bool (``None``: every row is the target's), ``in_segment``
    ``(T,)`` bool (``None``: every row), ``intervals`` the named intervals of the report (name to ``(start, end)`` in
    seconds, half-open). Nothing passed in is changed. Raises ``QualityError`` for anything that is wrong, naming the
    stage.
    """
    params = _check_params(params)
    parse_intervals(intervals)  # a wrong interval costs nothing: refused before any stage runs
    mask = _stage("mask", apply_mask, keypoints, scores, tracked, params.mask)
    seg = _check_in_segment(in_segment, mask.keypoints.shape[0])
    return _run(mask, t_sec, seg, params, intervals)


def run_quality(
    track: TargetTrack,
    params: QualityParams | None = None,
    intervals: Mapping[str, tuple[float, float]] | None = None,
) -> QualityResult:
    """The chain over a ``TargetTrack`` (W5): its keypoints, scores, real timestamps and ``in_segment`` (the 1 s margins
    are in the layers and not in the coverage); a frame is the target's when its status is ``tracked``."""
    params = _check_params(params)
    parse_intervals(intervals)
    masked = _stage("mask", mask_track, track, params.mask)
    return _run(masked.mask, masked.t_sec, _check_in_segment(masked.in_segment, len(masked.t_sec)), params, intervals)
