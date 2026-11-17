"""P4.08: run the quality chain over the UMONS-TAICHI Kinect recordings and write the numbers.

Reads the 111 Kinect files of the dataset (D12, CC BY-NC-SA 4.0, local, never in git) through the adapter
``taiji_ai.bench.umons`` (the plane (y, -z) in mm, 17 of the 26 HALPE joints, a repeated timestamp is two bodies and not
tracked), runs ``run_quality_arrays`` with the default parameters, and writes into ``--out`` (ignored by git)
``per_file.csv``: one row per file, counts only. With ``--grid-hz H`` it runs a second time with that grid rate and
writes ``per_file_grid.csv``. With ``--report FILE`` it writes the tables of ``Docs/reports/p4_umons_quality.md``.
Only sequence ids (``P01T01C03``) are printed; no value of a file ever is.

Usage (from ``taiji_ai/``; about 30 s for the 111 files, 703,146 rows)::

    python tools/umons_adapter.py run --umons ../datasets/taiji/umons --out data/reports/p4_08 \\
        --grid-hz 30 --report data/reports/p4_08/report_tables.md

Exit codes: 0 all files ran, 1 the run finished and at least one file failed (an error row is in the CSV), 2 the run
could not start (a folder that is not the dataset, a name that is not a sequence id, a bad option).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from taiji_ai.bench import BenchError
from taiji_ai.bench.umons import UmonsSummary, aggregate, find_umons, render_tables, run_folder, write_per_file_csv
from taiji_ai.logs import configure_logging
from taiji_ai.quality import QualityError
from taiji_ai.quality.chain import QualityParams
from taiji_ai.quality.resample import ResampleParams
from taiji_ai.store.artifacts import atomic_write_text


def _share(part: int, whole: int) -> str:
    return f"{100 * part / whole:.2f} %" if whole else "n/a"


def _line(label: str, s: UmonsSummary) -> str:
    return (
        f"{label}: files run: {s.files}, files failed: {len(s.errors)}, rows {s.rows:,}, grid rows {s.grid_rows:,}, "
        f"usable frames {_share(s.usable_frames, s.grid_rows)}, "
        f"the 17 provided joints observed {_share(s.provided_observed, s.provided_cells)}, {s.seconds:.1f} s"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the chain over the Kinect files and write the numbers")
    run.add_argument(
        "--umons", required=True, type=Path, help="the dataset root, its extracted folder or the Kinect folder"
    )
    run.add_argument("--out", required=True, type=Path, help="folder for per_file.csv (ignored by git)")
    run.add_argument(
        "--grid-hz", type=float, default=None, help="also run with this grid rate [Hz] (per_file_grid.csv)"
    )
    run.add_argument("--only", nargs="+", default=None, metavar="ID", help="sequence ids to run (default: all)")
    run.add_argument("--report", type=Path, default=None, help="write the Markdown tables to this file")
    args = parser.parse_args(argv)
    configure_logging(level="WARNING")  # the chain logs one line per file at INFO
    try:
        folder = find_umons(args.umons)
        side_params = None if args.grid_hz is None else QualityParams(resample=ResampleParams(grid_hz=args.grid_hz))
        baseline = run_folder(folder, None, args.only)
        side = None if side_params is None else run_folder(folder, side_params, args.only)
    except (BenchError, QualityError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    runs = {"default": aggregate(baseline)}
    write_per_file_csv(args.out / "per_file.csv", baseline)
    if side is not None:
        runs[f"grid {args.grid_hz:g} Hz"] = aggregate(side)
        write_per_file_csv(args.out / "per_file_grid.csv", side)
    if args.report is not None:
        atomic_write_text(args.report, render_tables(runs))
    for label, summary in runs.items():
        sys.stdout.write(_line(label, summary) + "\n")
        for sid, message in summary.errors:
            sys.stdout.write(f"  failed {sid}: {message}\n")
    return 1 if any(s.errors for s in runs.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
