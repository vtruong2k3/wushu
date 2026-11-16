"""P3.07: measure the speed, the GPU memory and the effect of the detector cadence N of the pose stage.

Finds the four D20 videos in a folder by size and SHA-256 (never by name), ingests the ones the five clips need into a
throwaway data folder (deleted at the end unless ``--keep``), runs one worker process per N, compares every N with N =
1, applies the written rule for N and writes two files into ``--out`` (ignored by git): ``bench.json`` (every number)
and ``report_tables.md`` (the tables of ``Docs/reports/p3_pose_benchmark.md``). Only clip IDs and ``d20-v1..v4`` are
printed.

Usage (from ``taiji_ai/``, with the GPU free of other jobs)::

    python tools/bench_pose.py --video-dir ../video --out data/reports/p3_07

About 25 minutes of GPU time for the default five clips, N = 1, 5, 10 and three measured passes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from taiji_ai.bench import BenchError
from taiji_ai.bench.orchestrate import run_benchmark
from taiji_ai.bench.report import render_tables
from taiji_ai.config import PROJECT_ROOT
from taiji_ai.logs import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--video-dir", required=True, type=Path, help="folder that holds the D20 videos")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "data" / "reports" / "p3_07")
    parser.add_argument("--ns", default="1,5,10", help="values of N, comma separated; 1 is required")
    parser.add_argument("--repeats", type=int, default=3, help="measured passes per clip and N")
    parser.add_argument("--clips", default="", help="clip IDs, comma separated (default: all five)")
    parser.add_argument("--segment-s", type=float, default=30.0, help="seconds of each clip (30 for the real run)")
    parser.add_argument("--baseline-s", type=float, default=3.0, help="seconds of VRAM baseline before the models load")
    parser.add_argument("--work-dir", type=Path, default=None, help="throwaway folder (default: data/bench/<id>)")
    parser.add_argument("--keep", action="store_true", help="keep the throwaway folder (it holds copies of the videos)")
    args = parser.parse_args(argv)
    configure_logging()
    try:
        ns = [int(v) for v in args.ns.split(",") if v.strip()]
        clips = [c.strip() for c in args.clips.split(",") if c.strip()] or None
        result = run_benchmark(
            args.video_dir, ns=ns, repeats=args.repeats, clip_ids=clips, baseline_s=args.baseline_s,
            segment_s=args.segment_s,
            work_dir=args.work_dir, keep=args.keep,
        )  # fmt: skip
    except (BenchError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "bench.json").write_text(json.dumps(result, allow_nan=False, indent=1), encoding="utf-8")
    (args.out / "report_tables.md").write_text(render_tables(result), encoding="utf-8")
    rec = result["recommendation"]
    sys.stdout.write(f"recommended N: {rec['n']}\n")
    for n in result["ns"]:
        s = result["runs"][str(n)]["summary"]
        sys.stdout.write(f"N = {n}: RTF {s['rtf']:.3f}, {s['ms_per_frame']:.1f} ms per frame\n")
    sys.stdout.write("wrote bench.json and report_tables.md\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
