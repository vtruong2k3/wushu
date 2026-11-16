"""P3.08: the failure review of the pose on the D20 videos.

``pose`` finds the four videos by size and SHA-256 (never by name), ingests them into a work folder (kept until the
review is closed: the sheets and the reruns decode frames from it; it holds copies of the videos and is ignored by
git), and runs the pose over all of them in chunks of 300 s at the cadence ``--n`` (the reference is N = 1). It is
resumable. ``analyse`` chooses the frames to look at from the two passes (N = 1 in ``--out``, N = 5 in ``--out/n5``),
draws the contact sheets and writes an empty ``review.csv``; ``report`` reads the finished review and writes the
tables.

Usage (from ``taiji_ai/``, with the GPU free of other jobs; about 2 hours at N = 1 and 35 minutes at N = 5)::

    python tools/pose_audit.py pose --video-dir ../video --out data/reports/p3_08 --work-dir data/bench/p3_08 --n 1
    python tools/pose_audit.py pose --video-dir ../video --out data/reports/p3_08/n5 --work-dir data/bench/p3_08 --n 5
    python tools/pose_audit.py analyse
    python tools/pose_audit.py report

Only labels (``d20-v1`` to ``d20-v4``) are printed. Images and pose files stay under ``--out`` and ``--work-dir``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from taiji_ai.audit import AuditError
from taiji_ai.audit.analyse import analyse, report
from taiji_ai.audit.scan import run_pose_pass
from taiji_ai.bench import BenchError
from taiji_ai.bench.clips import D20_VIDEOS, find_videos
from taiji_ai.bench.orchestrate import ingest_throwaway
from taiji_ai.config import PROJECT_ROOT, get_settings
from taiji_ai.logs import configure_logging


def _recordings(video_dir: Path, work: Path) -> dict[str, Path]:
    """label -> recording folder; ingest once, then reuse (a stop and a restart must not ingest again)."""
    index = work / "recordings.json"
    if index.exists():
        ids = json.loads(index.read_text(encoding="utf-8"))
        folders = {label: work / "data" / "recordings" / rec_id for label, rec_id in ids.items()}
        if set(folders) == set(D20_VIDEOS) and all(f.is_dir() for f in folders.values()):
            return folders
    videos = find_videos(video_dir, D20_VIDEOS)
    work.mkdir(parents=True, exist_ok=True)
    folders = ingest_throwaway(videos, work)
    index.write_text(json.dumps({label: folder.name for label, folder in folders.items()}), encoding="utf-8")
    return folders


def _pose(args: argparse.Namespace) -> int:
    from taiji_ai.pose.registry import ModelRegistry
    from taiji_ai.pose.rtm import PoseEstimator

    settings = get_settings()
    if not settings.registry_path.exists():
        raise AuditError("the model registry is missing: run tools/fetch_models.py first")
    folders = _recordings(args.video_dir, args.work_dir)
    estimator = PoseEstimator(ModelRegistry(settings.registry_path), device=settings.device)
    manifest = run_pose_pass(folders, args.out, estimator, n=args.n, chunk_s=args.chunk_s)
    for label, video in manifest["videos"].items():
        sys.stdout.write(f"{label}: {len(video['chunks'])} chunks, {video['n_frames']} frames\n")
    sys.stdout.write("pose pass done\n")
    return 0


def _analyse(args: argparse.Namespace) -> int:
    result = analyse(args.out, args.work_dir, n5_dir=args.n5_dir, force=args.force, progress=None)
    sys.stdout.write(
        f"{result['n_candidates']} candidate frames, {result['n_sheets']} sheets, {result['n_strips']} strips\n"
    )
    for name, rule in result["signals"]["per_rule"].items():
        sys.stdout.write(f"  {name}: {rule['taken']} taken of {rule['eligible']} eligible frames\n")
    sys.stdout.write("fill review.csv (the a_* columns first, then the h_* columns) and run report\n")
    return 0


def _report(args: argparse.Namespace) -> int:
    summary = report(args.out)
    sys.stdout.write(
        f"{summary['n_rows']} frames, {summary['n_failures']} failures, blind rate {summary['blind']['rate']}\n"
    )
    sys.stdout.write("wrote summary.json and report_tables.md\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    pose = sub.add_parser("pose", help="run the pose over the four videos in chunks")
    pose.add_argument("--video-dir", required=True, type=Path)
    pose.add_argument("--out", type=Path, default=PROJECT_ROOT / "data" / "reports" / "p3_08")
    pose.add_argument("--work-dir", type=Path, default=PROJECT_ROOT / "data" / "bench" / "p3_08")
    pose.add_argument("--n", type=int, default=1, help="detector cadence of the pass (N = 1 is the reference)")
    pose.add_argument("--chunk-s", type=float, default=300.0)
    pose.set_defaults(func=_pose)
    an = sub.add_parser("analyse", help="signals, selection, sheets and an empty review file from the two passes")
    an.add_argument("--out", type=Path, default=PROJECT_ROOT / "data" / "reports" / "p3_08")
    an.add_argument("--work-dir", type=Path, default=PROJECT_ROOT / "data" / "bench" / "p3_08")
    an.add_argument("--n5-dir", type=Path, default=None, help="the pass at N = 5 (default: <out>/n5)")
    an.add_argument("--force", action="store_true", help="overwrite an existing review.csv")
    an.set_defaults(func=_analyse)
    rp = sub.add_parser("report", help="read review.csv and write the tables")
    rp.add_argument("--out", type=Path, default=PROJECT_ROOT / "data" / "reports" / "p3_08")
    rp.set_defaults(func=_report)
    args = parser.parse_args(argv)
    configure_logging()
    try:
        return int(args.func(args))
    except (AuditError, BenchError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
