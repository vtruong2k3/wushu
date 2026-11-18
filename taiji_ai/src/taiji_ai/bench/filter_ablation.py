"""P5.08: the ablation of the Butterworth cut-off (4, 6, 8 Hz) on the pauses and the hip amplitude.

A run (a chunk of video pose, a Kinect file, a generated clip) goes through the quality chain once per cut-off; only
``ButterworthParams.cutoff_hz`` changes (``NO_FILTER_HZ`` is above Nyquist for every grid of the project, so the filter
is skipped: the reference of "what the filter does"). The filter copies ``reason`` and ``interpolated`` cell by cell, so
**the grid, the reasons, the flags and the segment must be the same at every cut-off**: ``check_invariants`` raises if
they are not (that would be a bug of the filter stage, not a number to report).

``measure_layer`` takes the numbers of one layer: the quantiles of the speed of each group (P5.06), the pauses of
each ``(tau, d_min)`` cell of a grid (P5.07) and the hip range of variant B (P5.04; variant A with a reference layer,
P5.03). The grid is a **sensitivity grid**: no cell is a value of a metric record (AGENTS.md 5.5), and the whole segment
is taken as the stable interval of the hip (an explicit convention of the ablation: nobody confirmed a stable height).

``agree`` compares a cut-off with the reference (6 Hz) on one run, in rows of the shared grid: the paused share, the
row-level agreement of the paused rows (their intersection over their union, on the rows measured in both), the count
and whether it equals the reference count, and the pauses matched one to one by overlap (a pair needs an overlap of at
least half of the shorter pause; the largest overlap first, the earlier pause on a tie) with the shift of their start
and of their end in steps. ``aggregate`` pools the numerators and denominators over the runs (a long run weighs more
than a short one) and ``render_tables`` writes the markdown: numbers and the names the caller gives, nothing else.

This module measures; it never changes a result and nothing in the product reads it.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np

from taiji_ai.bench import BenchError
from taiji_ai.metrics.hip_height import hip_height_a, hip_height_b
from taiji_ai.metrics.series import MetricResult
from taiji_ai.metrics.tempo import Pause, find_pauses, group_speed
from taiji_ai.quality.chain import QualityParams, QualityResult, run_quality, run_quality_arrays
from taiji_ai.quality.layers_io import PoseFiltered, pose_filtered_from_result
from taiji_ai.schemas.quality_layers import DataSource
from taiji_ai.store.artifacts import atomic_write_text
from taiji_ai.track.state import TargetTrack

CUTOFFS_HZ: Final = (4.0, 6.0, 8.0)  # Appendix B3
NO_FILTER_HZ: Final = 1000.0  # above Nyquist at any frame rate used here: the filter is skipped (`above_nyquist`)
REFERENCE_HZ: Final = 6.0  # the default of W6: every difference is from it
ALL_CUTOFFS: Final = (*CUTOFFS_HZ, NO_FILTER_HZ)
# (tau in body lengths per second, d_min in seconds): a sensitivity grid, not the values of a record
PAUSE_GRID: Final = ((0.1, 0.3), (0.2, 0.3), (0.3, 0.3), (0.5, 0.3), (0.2, 0.5))
GROUPS: Final = ("hands", "hips", "feet")
INVARIANT_ARRAYS: Final = ("t_grid", "reason", "interpolated", "grid_in_segment")
_CAMERA: Final = "camA"  # the metrics want a camera and a view; the ablation reads neither
_VIEW: Final = "front"
Cell = tuple[float, float]
CSV_COLUMNS: Final = (
    "source", "cutoff_hz", "group", "tau", "d_min_s", "runs", "rows_measured", "pauses", "paused_rows", "paused_share",
    "iou", "same_count", "matched", "lost", "extra", "shifts_n", "shift_median", "shift_p95", "shift_max",
)  # fmt: skip


class AblationError(BenchError):
    """An input of the ablation is wrong or a layer breaks an invariant; the message says which."""


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float | np.integer | np.floating) and not isinstance(value, bool)


def _positive(value: Any, name: str) -> float:
    if not _is_number(value) or not math.isfinite(float(value)) or float(value) <= 0.0:
        raise AblationError(f"{name} must be a finite number above 0, got {value!r}")
    return float(value)


def _cutoffs(cutoffs: Any) -> tuple[float, ...]:
    if isinstance(cutoffs, str) or not isinstance(cutoffs, Sequence) or len(cutoffs) == 0:
        raise AblationError(f"cutoffs must be a non-empty list of cut-offs in hertz, got {cutoffs!r}")
    out = tuple(_positive(hz, "cutoffs") for hz in cutoffs)
    if len(set(out)) != len(out):
        raise AblationError(f"cutoffs must be distinct, got {list(out)}")
    if REFERENCE_HZ not in out:
        raise AblationError(f"cutoffs must include the reference {REFERENCE_HZ:g} Hz, got {list(out)}")
    return out


def _grid(grid: Any) -> tuple[Cell, ...]:
    if isinstance(grid, str) or not isinstance(grid, Sequence) or len(grid) == 0:
        raise AblationError(f"grid must be a non-empty list of (tau, d_min) cells, got {grid!r}")
    out: list[Cell] = []
    for cell in grid:
        if isinstance(cell, str) or not isinstance(cell, Sequence) or len(cell) != 2:
            raise AblationError(f"grid must hold (tau, d_min) pairs, got {cell!r}")
        out.append((_positive(cell[0], "grid tau"), _positive(cell[1], "grid d_min")))
    if len(set(out)) != len(out):
        raise AblationError(f"grid cells must be distinct, got {out}")
    return tuple(out)


# --- the layers of one run at several cut-offs ----------------------------------------------------------------------
def check_invariants(layers: Mapping[float, PoseFiltered]) -> None:
    """Raise ``AblationError`` unless every layer has the grid, reasons, flags and segment of the 6 Hz layer."""
    reference = layers.get(REFERENCE_HZ)
    if reference is None:
        raise AblationError(f"the layers need the reference cut-off {REFERENCE_HZ:g} Hz to be compared with")
    for hz, layer in layers.items():
        for name in INVARIANT_ARRAYS:
            a, b = np.asarray(getattr(layer, name)), np.asarray(getattr(reference, name))
            if a.shape != b.shape or not np.array_equal(a, b):
                raise AblationError(f"the layer at {hz:g} Hz differs from the layer at {REFERENCE_HZ:g} Hz in {name}")


def _params_at(base: QualityParams | None, hz: float) -> QualityParams:
    base = QualityParams() if base is None else base
    return dataclasses.replace(base, filter=dataclasses.replace(base.filter, cutoff_hz=hz))


def layers_at_cutoffs(
    keypoints: np.ndarray,
    scores: np.ndarray,
    t_sec: np.ndarray,
    *,
    recording_id: str,
    frame_index: np.ndarray,
    tracked: np.ndarray | None = None,
    in_segment: np.ndarray | None = None,
    data_sources: Sequence[DataSource] = (),
    cutoffs: Sequence[float] = ALL_CUTOFFS,
    base: QualityParams | None = None,
) -> dict[float, PoseFiltered]:
    """The final layer of one run at each cut-off: ``run_quality_arrays`` with ``base`` (the defaults) and only
    ``filter.cutoff_hz`` changed, in the order of ``cutoffs``. Raises ``AblationError`` for a bad list of cut-offs
    (finite, above 0, distinct, with 6 Hz in it) or a broken invariant (``check_invariants``)."""
    hz_list = _cutoffs(cutoffs)
    results = {
        hz: run_quality_arrays(
            keypoints, scores, t_sec, tracked=tracked, in_segment=in_segment, params=_params_at(base, hz)
        )
        for hz in hz_list
    }
    return _layers(results, recording_id, frame_index, data_sources)


def layers_of_track(
    track: TargetTrack,
    *,
    recording_id: str,
    data_sources: Sequence[DataSource] = (),
    cutoffs: Sequence[float] = ALL_CUTOFFS,
    base: QualityParams | None = None,
) -> dict[float, PoseFiltered]:
    """``layers_at_cutoffs`` for a ``TargetTrack`` (``run_quality``: the margins are in the layers)."""
    hz_list = _cutoffs(cutoffs)
    results = {hz: run_quality(track, _params_at(base, hz)) for hz in hz_list}
    return _layers(results, recording_id, track.frame_index, data_sources)


def _layers(
    results: Mapping[float, QualityResult],
    recording_id: str,
    frame_index: np.ndarray,
    data_sources: Sequence[DataSource],
) -> dict[float, PoseFiltered]:
    layers = {
        hz: pose_filtered_from_result(
            result, recording_id=recording_id, frame_index=frame_index, data_sources=data_sources
        )
        for hz, result in results.items()
    }
    check_invariants(layers)
    return layers


# --- the measures of a layer -----------------------------------------------------------------------------------------
@dataclass(frozen=True, eq=False)
class GroupMeasure:
    """One group of one layer over the rows of its segment.

    ``measured`` ``(n_rows,)`` bool: the rows with a speed; ``v_p50``, ``v_p95`` the quantiles of the speed over them
    (body lengths per second; ``None`` with no measured row); ``pauses`` the pauses of each ``(tau, d_min)`` cell.
    """

    n_rows: int
    measured: np.ndarray
    v_p50: float | None
    v_p95: float | None
    pauses: Mapping[Cell, tuple[Pause, ...]]

    def __post_init__(self) -> None:
        measured = np.array(self.measured, dtype=bool)
        if measured.ndim != 1 or len(measured) != self.n_rows:
            raise AblationError(f"measured must have {self.n_rows} rows, got shape {measured.shape}")
        measured.setflags(write=False)
        object.__setattr__(self, "measured", measured)

    @property
    def n_measured(self) -> int:
        return int(self.measured.sum())

    def paused_mask(self, cell: Cell) -> np.ndarray:
        """``(n_rows,)`` bool: the rows inside a pause of the cell."""
        if cell not in self.pauses:
            raise AblationError(f"cell {cell} was not measured; the cells are {list(self.pauses)}")
        mask = np.zeros(self.n_rows, dtype=bool)
        for pause in self.pauses[cell]:
            mask[pause.first_row : pause.last_row + 1] = True
        return mask


@dataclass(frozen=True)
class HipMeasure:
    """The hip range of one variant: ``range`` in trunk lengths, or ``None`` and the ``reason`` there is no evidence."""

    range: float | None
    reason: str | None


@dataclass(frozen=True, eq=False)
class RunMeasure:
    """What is measured on one layer: the groups, and the hip range of variant B (and A with a reference layer)."""

    groups: Mapping[str, GroupMeasure]
    hip_b: HipMeasure
    hip_a: HipMeasure | None = None


def _hip(result: MetricResult) -> HipMeasure:
    (stat,) = [s for s in result.summary.statistics if s.name == "hip_height_range"]
    return HipMeasure(range=stat.value, reason=result.summary.insufficient_reason)


def measure_layer(
    layer: PoseFiltered, *, grid: Sequence[Cell] = PAUSE_GRID, reference: PoseFiltered | None = None
) -> RunMeasure:
    """The speed quantiles and the pauses of each cell of ``grid`` for the three groups, and the hip range of variant B
    (variant A too with ``reference``, the layer of a standing segment of the same recording), of one final layer.

    The whole segment is the stable interval of the hip. A metric with no evidence is ``None`` with its reason, never
    a 0. Raises ``AblationError`` naming the argument.
    """
    if not isinstance(layer, PoseFiltered):
        raise AblationError(f"layer must be a PoseFiltered, got {type(layer).__name__}")
    if reference is not None and not isinstance(reference, PoseFiltered):
        raise AblationError(f"reference must be a PoseFiltered or None, got {type(reference).__name__}")
    cells = _grid(grid)
    groups: dict[str, GroupMeasure] = {}
    for name in GROUPS:
        result = group_speed(layer, group=name, flags={}, camera_id=_CAMERA, view_category=_VIEW)  # type: ignore[arg-type]
        series = result.series
        measured = np.asarray(series.reason) == 0
        values = np.asarray(series.values)[measured]
        groups[name] = GroupMeasure(
            n_rows=len(measured),
            measured=measured,
            v_p50=float(np.median(values)) if len(values) else None,
            v_p95=float(np.percentile(values, 95)) if len(values) else None,
            pauses={cell: find_pauses(series, tau=cell[0], min_pause_s=cell[1]) for cell in cells},
        )
    whole = [(float(layer.t_grid[0]) - 1.0, float(layer.t_grid[-1]) + 1.0)]
    common: dict[str, Any] = {"stable_intervals": whole, "flags": {}, "camera_id": _CAMERA, "view_category": _VIEW}
    hip_b = _hip(hip_height_b(layer, **common))
    hip_a = None if reference is None else _hip(hip_height_a(layer, reference=reference, **common))
    return RunMeasure(groups=groups, hip_b=hip_b, hip_a=hip_a)


# --- the agreement of a cut-off with the reference -------------------------------------------------------------------
@dataclass(frozen=True)
class Agreement:
    """One group and cell of one run, a cut-off against the reference (see the module docstring)."""

    n_measured: int
    paused_rows: int
    paused_share: float | None
    intersection_rows: int
    union_rows: int
    count: int
    ref_count: int
    matched: int
    lost: int  # pauses of the reference with no match in this cut-off
    extra: int  # pauses of this cut-off with no match in the reference
    shifts: tuple[tuple[int, int], ...]  # (start, end) in rows (= steps of the grid) of each matched pair

    @property
    def iou(self) -> float | None:
        return None if self.union_rows == 0 else self.intersection_rows / self.union_rows

    @property
    def count_equal(self) -> bool:
        return self.count == self.ref_count


def _matches(this: Sequence[Pause], ref: Sequence[Pause]) -> list[tuple[int, int]]:
    """``(i, j)`` pairs, one to one: the largest overlap first, then the earlier pause; an overlap of at least half of
    the shorter pause is needed."""
    pairs = []
    for i, p in enumerate(this):
        for j, q in enumerate(ref):
            overlap = min(p.last_row, q.last_row) - max(p.first_row, q.first_row) + 1
            shorter = min(p.last_row - p.first_row, q.last_row - q.first_row) + 1
            if overlap > 0 and 2 * overlap >= shorter:
                pairs.append((-overlap, i, j))
    taken_i: set[int] = set()
    taken_j: set[int] = set()
    out = []
    for _, i, j in sorted(pairs):
        if i not in taken_i and j not in taken_j:
            taken_i.add(i)
            taken_j.add(j)
            out.append((i, j))
    return sorted(out)


def agree(measure: RunMeasure, reference: RunMeasure, group: str, cell: Cell) -> Agreement:
    """A cut-off against the reference for one ``group`` and ``cell`` of one run. Raises ``AblationError`` for a group
    or a cell that was not measured or for runs of different length."""
    if group not in measure.groups or group not in reference.groups:
        raise AblationError(f"group must be one of {list(reference.groups)}, got {group!r}")
    a, b = measure.groups[group], reference.groups[group]
    if a.n_rows != b.n_rows:
        raise AblationError(f"the two runs do not have the same rows: {a.n_rows} and {b.n_rows}")
    pa, pb = a.paused_mask(cell), b.paused_mask(cell)
    both = a.measured & b.measured
    paused_rows = int((pa & a.measured).sum())
    matches = _matches(a.pauses[cell], b.pauses[cell])
    shifts = tuple(
        (
            abs(a.pauses[cell][i].first_row - b.pauses[cell][j].first_row),
            abs(a.pauses[cell][i].last_row - b.pauses[cell][j].last_row),
        )
        for i, j in matches
    )
    return Agreement(
        n_measured=a.n_measured,
        paused_rows=paused_rows,
        paused_share=None if a.n_measured == 0 else paused_rows / a.n_measured,
        intersection_rows=int((pa & pb & both).sum()),
        union_rows=int(((pa | pb) & both).sum()),
        count=len(a.pauses[cell]),
        ref_count=len(b.pauses[cell]),
        matched=len(matches),
        lost=len(b.pauses[cell]) - len(matches),
        extra=len(a.pauses[cell]) - len(matches),
        shifts=shifts,
    )


# --- the aggregation over runs ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SpeedSummary:
    """The median over the runs of each run's median and P95 of the speed of a group at a cut-off."""

    runs: int  # runs with at least one measured row
    v_p50: float | None
    v_p95: float | None


@dataclass(frozen=True)
class CellSummary:
    """A cut-off, a group and a ``(tau, d_min)`` cell over the runs: pooled numerators and denominators."""

    runs: int  # runs with at least one measured row
    rows_measured: int
    pauses: int
    paused_rows: int
    paused_share: float | None  # paused rows over measured rows, pooled
    iou: float | None  # intersection over union with the reference, pooled
    same_count: float | None  # the share of the runs whose count equals the reference count
    matched: int
    lost: int
    extra: int
    shifts_n: int  # the shifts of the starts and the ends of the matched pairs, in steps, pooled
    shift_median: float | None
    shift_p95: float | None
    shift_max: int | None


@dataclass(frozen=True)
class HipSummary:
    """The hip range of one variant at a cut-off, as the absolute relative difference from the reference, in percent."""

    runs: int  # runs
    n: int  # runs with a range at this cut-off and a non-zero one at the reference
    abs_diff_median: float | None
    abs_diff_p95: float | None
    abs_diff_max: float | None


@dataclass(frozen=True)
class AblationSummary:
    """The ablation of one source of runs."""

    runs: int
    cutoffs: tuple[float, ...]
    grid: tuple[Cell, ...]
    groups: tuple[str, ...]
    speed: Mapping[tuple[float, str], SpeedSummary]
    cells: Mapping[tuple[float, str, Cell], CellSummary]
    hip: Mapping[tuple[float, str], HipSummary]


def _median_or_none(values: Sequence[float]) -> float | None:
    return float(np.median(values)) if len(values) else None


def _cell_summary(rows: Sequence[tuple[GroupMeasure, Agreement]]) -> CellSummary:
    used = [(g, a) for g, a in rows if g.n_measured > 0]
    shifts = [s for _, a in used for pair in a.shifts for s in pair]
    measured = sum(a.n_measured for _, a in used)
    paused = sum(a.paused_rows for _, a in used)
    union = sum(a.union_rows for _, a in used)
    return CellSummary(
        runs=len(used),
        rows_measured=measured,
        pauses=sum(a.count for _, a in used),
        paused_rows=paused,
        paused_share=None if measured == 0 else paused / measured,
        iou=None if union == 0 else sum(a.intersection_rows for _, a in used) / union,
        same_count=None if not used else sum(a.count_equal for _, a in used) / len(used),
        matched=sum(a.matched for _, a in used),
        lost=sum(a.lost for _, a in used),
        extra=sum(a.extra for _, a in used),
        shifts_n=len(shifts),
        shift_median=float(np.median(shifts)) if shifts else None,
        shift_p95=float(np.percentile(shifts, 95)) if shifts else None,
        shift_max=max(shifts) if shifts else None,
    )


def _range_a(measure: RunMeasure) -> float | None:
    return None if measure.hip_a is None else measure.hip_a.range


def _hip_summary(pairs: Sequence[tuple[float | None, float | None]], runs: int) -> HipSummary:
    diffs = [abs(x / ref - 1.0) * 100.0 for x, ref in pairs if x is not None and ref]
    return HipSummary(
        runs=runs,
        n=len(diffs),
        abs_diff_median=float(np.median(diffs)) if diffs else None,
        abs_diff_p95=float(np.percentile(diffs, 95)) if diffs else None,
        abs_diff_max=max(diffs) if diffs else None,
    )


def aggregate(
    runs: Sequence[Mapping[float, RunMeasure]],
    *,
    cutoffs: Sequence[float] = ALL_CUTOFFS,
    grid: Sequence[Cell] = PAUSE_GRID,
) -> AblationSummary:
    """Pool the runs: each is the ``RunMeasure`` of the same run at every cut-off. Raises ``AblationError`` for no run,
    a run that lacks a cut-off, or cutoffs without 6 Hz."""
    hz_list, cell_list = _cutoffs(cutoffs), _grid(grid)
    if isinstance(runs, str) or not isinstance(runs, Sequence) or len(runs) == 0:
        raise AblationError("runs must be a non-empty list of runs")
    for k, run in enumerate(runs):
        for hz in hz_list:
            if hz not in run:
                raise AblationError(f"run {k} has no measure at {hz:g} Hz")
    groups = tuple(g for g in GROUPS if all(g in run[REFERENCE_HZ].groups for run in runs))
    speed: dict[tuple[float, str], SpeedSummary] = {}
    cells: dict[tuple[float, str, Cell], CellSummary] = {}
    for hz in hz_list:
        for group in groups:
            measures = [run[hz].groups[group] for run in runs]
            p50 = [m.v_p50 for m in measures if m.v_p50 is not None]
            p95 = [m.v_p95 for m in measures if m.v_p95 is not None]
            speed[(hz, group)] = SpeedSummary(runs=len(p50), v_p50=_median_or_none(p50), v_p95=_median_or_none(p95))
            for cell in cell_list:
                rows = [
                    (m, agree(run[hz], run[REFERENCE_HZ], group, cell)) for m, run in zip(measures, runs, strict=True)
                ]
                cells[(hz, group, cell)] = _cell_summary(rows)
    hip: dict[tuple[float, str], HipSummary] = {}
    for hz in hz_list:
        hip[(hz, "B")] = _hip_summary([(r[hz].hip_b.range, r[REFERENCE_HZ].hip_b.range) for r in runs], len(runs))
        if any(r[hz].hip_a is not None for r in runs):
            hip[(hz, "A")] = _hip_summary([(_range_a(r[hz]), _range_a(r[REFERENCE_HZ])) for r in runs], len(runs))
    return AblationSummary(
        runs=len(runs), cutoffs=hz_list, grid=cell_list, groups=groups, speed=speed, cells=cells, hip=hip
    )


# --- the tables ------------------------------------------------------------------------------------------------------
def _label(hz: float) -> str:
    return f"{hz:g} Hz"


def _num(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _pct(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{100.0 * value:.{digits}f} %"


def render_tables(summaries: Mapping[str, AblationSummary]) -> str:
    """The markdown tables of the sources (in the order of the mapping): numbers and the names the caller gave. A
    missing number is written ``n/a``. Deterministic: the same summaries give the same text."""
    out: list[str] = []
    for name, s in summaries.items():
        out += [f"## {name}", "", f"Runs: {s.runs}. Reference: {REFERENCE_HZ:g} Hz.", ""]
        head = "| cut-off | " + " | ".join(f"{g} p50 | {g} p95" for g in s.groups) + " |"
        out += ["Speed of the groups, body lengths per second (median over the runs of the run's quantile):", "", head]
        out.append("|" + "---|" * (1 + 2 * len(s.groups)))
        for hz in s.cutoffs:
            cols = [f"{_num(s.speed[(hz, g)].v_p50)} | {_num(s.speed[(hz, g)].v_p95)}" for g in s.groups]
            out.append(f"| {_label(hz)} | " + " | ".join(cols) + " |")
        for tau, d_min in s.grid:
            out += ["", f"Pauses, tau {tau:g}, d_min {d_min:g} s:", ""]
            out.append(
                "| cut-off | group | runs | rows measured | pauses | same count | paused share "
                "| agreement with the reference | shift median | shift p95 | shift max |"
            )
            out.append("|" + "---|" * 11)
            for hz in s.cutoffs:
                for g in s.groups:
                    c = s.cells[(hz, g, (tau, d_min))]
                    out.append(
                        f"| {_label(hz)} | {g} | {c.runs} | {c.rows_measured} | {c.pauses} | {_pct(c.same_count)} "
                        f"| {_pct(c.paused_share)} | {_num(c.iou)} | {_num(c.shift_median, 1)} "
                        f"| {_num(c.shift_p95, 1)} | {'n/a' if c.shift_max is None else c.shift_max} |"
                    )
        out += ["", "Hip range, absolute difference from the reference, percent of the reference value:", ""]
        out.append("| cut-off | variant | runs | pairs | median | p95 | max |")
        out.append("|" + "---|" * 7)
        for (hz, variant), h in s.hip.items():
            out.append(
                f"| {_label(hz)} | {variant} | {h.runs} | {h.n} | {_num(h.abs_diff_median, 2)} "
                f"| {_num(h.abs_diff_p95, 2)} | {_num(h.abs_diff_max, 2)} |"
            )
        out.append("")
    return "\n".join(out) + "\n"


def cells_csv(summaries: Mapping[str, AblationSummary]) -> str:
    """One CSV row per source, cut-off, group and cell: the numbers of ``CellSummary`` (counts and ratios only)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for name, s in summaries.items():
        for (hz, group, cell), c in s.cells.items():
            row = [name, hz, group, cell[0], cell[1]]
            row += [getattr(c, field) for field in CSV_COLUMNS[5:]]
            writer.writerow(row)  # a missing number (None) is an empty field
    return buffer.getvalue()


def write_cells_csv(path: str | Path, summaries: Mapping[str, AblationSummary]) -> Path:
    """Write ``cells_csv`` atomically and return the path."""
    target = Path(path)
    atomic_write_text(target, cells_csv(summaries))
    return target
