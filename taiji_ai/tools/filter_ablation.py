"""P5.08: the ablation of the Butterworth cut-off (4, 6, 8 Hz and no filter) on real recordings, numbers only.

Two sources, reported apart (AGENTS.md 9.4.4): ``d20`` the pose chunks of the D20 lesson videos (``pose_raw/1`` files of
the P3.08 pass; the performer is the one ``taiji_ai.audit.analyse.target_track`` follows) and ``umons`` the 111
Kinect files of UMONS-TAICHI (D12, CC BY-NC-SA 4.0, local, never in git). Each run goes through the quality chain once
per cut-off, only ``cutoff_hz`` changing (``taiji_ai.bench.filter_ablation``), and the speed quantiles, the pauses of a
grid of ``(tau, d_min)`` cells and the hip range are compared with the 6 Hz run. The grid is a sensitivity grid, not the
value of a record; real data has no label of a pause and no hip height truth, so the numbers are differences, never
errors.

Writes into ``--out`` (ignored by git) ``per_run.csv`` (one row per run, cut-off, group and cell: counts only) and
``cells.csv`` (the pooled numbers); with ``--report FILE`` the markdown tables. A run that cannot be made (no performer,
a file that does not parse, a broken invariant) is an error row, not a skip. Only run ids (``d20-v1_000``,
``P01T01C03``) and numbers are printed or written: no path, no image, no value of a file.

Usage (from ``taiji_ai/``; about 35 s for the 22 D20 chunks and 150 s for the 111 UMONS files)::

    python tools/filter_ablation.py d20 --pose data/reports/p3_08/pose --out data/reports/p5_08/d20
    python tools/filter_ablation.py umons --umons ../datasets/taiji/umons --out data/reports/p5_08/umons

Exit codes: 0 all runs ran, 1 the run finished and at least one failed (an error row is in the CSV), 2 the run could not
start (a folder that is not there or holds nothing to run, an id that is not in it, a bad option).
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from taiji_ai.audit.analyse import target_track
from taiji_ai.bench import BenchError
from taiji_ai.bench.filter_ablation import (
    ALL_CUTOFFS,
    PAUSE_GRID,
    AblationSummary,
    RunMeasure,
    aggregate,
    layers_at_cutoffs,
    layers_of_track,
    measure_layer,
    render_tables,
    write_cells_csv,
)
from taiji_ai.bench.umons import UmonsError, find_umons, load_kinect
from taiji_ai.logs import configure_logging
from taiji_ai.metrics import MetricError
from taiji_ai.pose.raw_io import PoseRawError, load_pose_raw
from taiji_ai.quality import QualityError
from taiji_ai.schemas.quality_layers import DataSource
from taiji_ai.store.artifacts import atomic_write_text
from taiji_ai.track.state import TargetStateError

_RECORDING_UMONS = "6f1c2a90-3b5d-4e7a-8c14-0d9e5a2b7f31"  # the layers need a recording id: one fixed id per source
_SOURCES = {
    "d20": (DataSource(dataset_id="D20", license="internal use, no verified terms"),),
    "umons": (DataSource(dataset_id="D12", license="CC BY-NC-SA 4.0"),),
}
_FAILURES = (BenchError, QualityError, MetricError, PoseRawError, TargetStateError, ValueError)


@dataclass(frozen=True)
class Outcome:
    """The result of one run: its measures at every cut-off, or the name of the error."""

    run_id: str
    measures: dict[float, RunMeasure] | None
    error: str | None


def _measure(layers) -> dict[float, RunMeasure]:
    return {hz: measure_layer(layer) for hz, layer in layers.items()}


def _umons_runs(root: Path, only: Sequence[str] | None) -> list[tuple[str, Callable[[], dict[float, RunMeasure]]]]:
    folder = find_umons(root)
    files = {f.stem: f for f in sorted(folder.glob("P*T*C*.txt"))}
    ids = list(files) if only is None else list(only)
    unknown = [i for i in ids if i not in files]
    if unknown:
        raise BenchError(f"not a sequence of the dataset: {', '.join(unknown)}")

    def make(sid: str) -> Callable[[], dict[float, RunMeasure]]:
        def run() -> dict[float, RunMeasure]:
            seq = load_kinect(files[sid])
            layers = layers_at_cutoffs(
                seq.keypoints,
                seq.scores,
                seq.t_sec,
                tracked=seq.tracked,
                recording_id=_RECORDING_UMONS,
                frame_index=np.arange(len(seq.t_sec), dtype=np.int64),
                data_sources=_SOURCES["umons"],
            )
            return _measure(layers)

        return run

    return [(sid, make(sid)) for sid in ids]


def _d20_runs(folder: Path, only: Sequence[str] | None) -> list[tuple[str, Callable[[], dict[float, RunMeasure]]]]:
    if not folder.is_dir():
        raise BenchError("the pose folder does not exist")
    files = {f.stem: f for f in sorted(folder.glob("*.npz"))}
    if not files:
        raise BenchError("the pose folder holds no pose file (*.npz)")
    ids = list(files) if only is None else list(only)
    unknown = [i for i in ids if i not in files]
    if unknown:
        raise BenchError(f"not a pose file of the folder: {', '.join(unknown)}")

    def make(sid: str) -> Callable[[], dict[float, RunMeasure]]:
        def run() -> dict[float, RunMeasure]:
            raw = load_pose_raw(files[sid])
            track = target_track(raw)  # the P3.08 review rule: the most persistent large person of the chunk
            if track is None:
                raise BenchError("no performer can be chosen in the chunk")
            layers = layers_of_track(track, recording_id=raw.recording_id, data_sources=_SOURCES["d20"])
            return _measure(layers)

        return run

    return [(sid, make(sid)) for sid in ids]


def _run_all(runs: list[tuple[str, Callable[[], dict[float, RunMeasure]]]]) -> list[Outcome]:
    out = []
    for run_id, run in runs:
        try:
            out.append(Outcome(run_id, run(), None))
        except _FAILURES as exc:
            out.append(Outcome(run_id, None, f"{type(exc).__name__}: {exc}"))
    return out


def per_run_csv(source: str, outcomes: Sequence[Outcome]) -> str:
    """One row per run, cut-off, group and cell (counts and quantiles only); an error row has only the error."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        ["source", "run_id", "cutoff_hz", "group", "tau", "d_min_s", "n_rows", "n_measured", "v_p50", "v_p95", "pauses",
         "paused_rows", "hip_b_range", "hip_b_reason", "error"]
    )  # fmt: skip
    for o in outcomes:
        if o.measures is None:
            writer.writerow([source, o.run_id] + [""] * 12 + [o.error])
            continue
        for hz, m in o.measures.items():
            for group, g in m.groups.items():
                for cell in g.pauses:
                    head = [source, o.run_id, hz, group, cell[0], cell[1], g.n_rows, g.n_measured, g.v_p50, g.v_p95]
                    tail = [len(g.pauses[cell]), int(g.paused_mask(cell).sum()), m.hip_b.range, m.hip_b.reason, ""]
                    writer.writerow(head + tail)  # a missing number (None) is an empty field
    return buffer.getvalue()


def _line(source: str, outcomes: Sequence[Outcome], summary: AblationSummary | None, seconds: float) -> str:
    failed = sum(o.measures is None for o in outcomes)
    rows = 0 if summary is None else summary.cells[(6.0, summary.groups[0], PAUSE_GRID[0])].rows_measured
    return (
        f"{source}: runs {len(outcomes)}, failed {failed}, measured rows of the first group {rows:,}, {seconds:.1f} s"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    d20 = sub.add_parser("d20", help="the D20 pose chunks")
    d20.add_argument("--pose", required=True, type=Path, help="the folder of the pose_raw/1 chunk files")
    umons = sub.add_parser("umons", help="the UMONS Kinect files")
    umons.add_argument("--umons", required=True, type=Path, help="the dataset root, its extracted folder or Kinect")
    for p in (d20, umons):
        p.add_argument("--out", required=True, type=Path, help="folder for per_run.csv and cells.csv (ignored by git)")
        p.add_argument("--only", nargs="+", default=None, metavar="ID", help="run ids to run (default: all)")
        p.add_argument("--report", type=Path, default=None, help="write the Markdown tables to this file")
    args = parser.parse_args(argv)
    configure_logging(level="WARNING")
    try:
        if args.command == "d20":
            runs = _d20_runs(args.pose, args.only)
        else:
            runs = _umons_runs(args.umons, args.only)
    except (BenchError, UmonsError, QualityError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    started = time.perf_counter()
    outcomes = _run_all(runs)
    good = [o.measures for o in outcomes if o.measures is not None]
    summary = aggregate(good, cutoffs=ALL_CUTOFFS, grid=PAUSE_GRID) if good else None
    args.out.mkdir(parents=True, exist_ok=True)
    atomic_write_text(args.out / "per_run.csv", per_run_csv(args.command, outcomes))
    if summary is not None:
        write_cells_csv(args.out / "cells.csv", {args.command: summary})
        if args.report is not None:
            atomic_write_text(args.report, render_tables({args.command: summary}))
    sys.stdout.write(_line(args.command, outcomes, summary, time.perf_counter() - started) + "\n")
    for o in outcomes:
        if o.error is not None:
            sys.stdout.write(f"  failed {o.run_id}: {o.error}\n")
    return 1 if any(o.error is not None for o in outcomes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
