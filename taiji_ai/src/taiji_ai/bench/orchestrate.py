"""Run the pose benchmark end to end (P3.07): ingest the clips, one worker per N, compare the runs, apply the rule.

``run_benchmark`` ingests the D20 videos it needs into a **throwaway data folder** (a test participant, never the
project data), writes the plan, starts ``python -m taiji_ai.bench.worker`` once per N, loads the ``PoseRaw`` each
worker saved, compares every N with N = 1 (``compare_runs``, ``downstream_summary``), applies the written rule
(``recommend_n``) and returns one JSON-ready dict with every number. Nothing here prints; the tool
``tools/bench_pose.py`` writes the dict and the tables of ``taiji_ai.bench.report`` and deletes the throwaway folder
(the recordings hold copies of the videos).
"""

from __future__ import annotations

import dataclasses
import datetime
import importlib.metadata
import json
import logging
import os
import shutil
import stat
import statistics
import subprocess
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from taiji_ai.bench import BenchError
from taiji_ai.bench.clips import CLIPS, D20_VIDEOS, SEGMENT_S, PlanEntry, find_videos, write_plan
from taiji_ai.bench.compare import (
    Downstream,
    RunComparison,
    TargetComparison,
    compare_runs,
    compare_target_tracks,
    downstream_summary,
    pool_comparisons,
    pool_target_comparisons,
    same_target,
)
from taiji_ai.bench.decision import DecisionRule, NStats, recommend_n
from taiji_ai.bench.timing import fps_equivalent_rtf, percentiles
from taiji_ai.config import PROJECT_ROOT, Settings
from taiji_ai.io.ingest import IngestError, ingest_recording
from taiji_ai.pose.raw_io import load_pose_raw
from taiji_ai.schemas._base import read_manifest
from taiji_ai.schemas.recording import RecordingManifest
from taiji_ai.store.db import connect
from taiji_ai.store.participants import register_participant

log = logging.getLogger(__name__)


def ingest_throwaway(videos: dict[str, Path], work: Path) -> dict[str, Path]:
    """Ingest the videos into a throwaway data folder with an invented test participant; label -> recording folder."""
    # The longest D20 video lasts 43 minutes; the limit of the product (30 minutes) does not apply to a throwaway copy.
    settings = Settings(data_dir=work / "data", max_source_duration_s=7200.0)
    conn = connect(settings.db_path, settings.migrations_dir)
    try:
        register_participant(
            conn, "P03", "CONSENT-2026-011", analysis=True, train=False, share=False, retention_until=None,
            actor="cli:O",
        )  # fmt: skip
    finally:
        conn.close()
    folders: dict[str, Path] = {}
    for k, (label, path) in enumerate(sorted(videos.items()), start=1):
        meta = {"participant_id": "P03", "session_id": "S01", "take_id": f"S01-P03-T{k:02d}", "camera_id": "camA"}
        try:
            result = ingest_recording(path, meta, settings)
        except IngestError as exc:
            raise BenchError(f"the ingest of {label} failed: {exc}") from exc
        folders[label] = settings.data_dir / "recordings" / result.manifest.recording_id
        log.info("ingested %s", label)
    return folders


def _comparison_dict(c: RunComparison) -> dict[str, Any]:
    def stats(s: Any) -> dict[str, float] | None:
        return None if s is None else {"median": s.median, "p95": s.p95, "p99": s.p99, "max": s.max, "n": s.n}

    return {
        "n_frames": c.n_frames,
        "count_agreement": c.count_agreement,
        "n_ref_persons": c.n_ref_persons,
        "n_other_persons": c.n_other_persons,
        "n_pairs": c.n_pairs,
        "n_missed": c.n_missed,
        "n_extra": c.n_extra,
        "n_uncomparable_ref": c.n_uncomparable_ref,
        "n_uncomparable_other": c.n_uncomparable_other,
        "entry_delay_frames": {
            "n": len(c.entry_delays),
            "mean": float(np.mean(c.entry_delays)) if c.entry_delays else None,
            "max": max(c.entry_delays) if c.entry_delays else None,
        },
        "n_tracks_never_matched": c.n_tracks_never_matched,
        "px": stats(c.px),
        "norm": stats(c.norm),
        "group_p95_norm": c.group_p95,
    }


def _target_dict(t: TargetComparison | None) -> dict[str, Any] | None:
    if t is None:
        return None

    def stats(s: Any) -> dict[str, float] | None:
        return None if s is None else {"median": s.median, "p95": s.p95, "p99": s.p99, "max": s.max, "n": s.n}

    return {
        "n_frames": t.n_frames,
        "n_both_tracked": t.n_both_tracked,
        "n_ref_only": t.n_ref_only,
        "n_other_only": t.n_other_only,
        "n_uncomparable_frames": t.n_uncomparable_frames,
        "px": stats(t.px),
        "norm": stats(t.norm),
    }


def _downstream_dict(d: Downstream) -> dict[str, Any]:
    return {
        "target_found": d.target_found,
        "error": d.error,
        "selection_frame_pos": d.selection_frame_pos,
        "share_tracked": d.share_tracked,
        "share_lost": d.share_lost,
        "share_target_lost": d.share_target_lost,
        "share_before_target": d.share_before_target,
        "events": d.events,
        "needs_reselect": d.needs_reselect,
        "reselect_reason": d.reselect_reason,
    }


def summarise_worker(worker: dict[str, Any]) -> dict[str, Any]:
    """The numbers derived from one worker's passes: medians per clip, pooled latencies, windows, phases."""
    per_clip: dict[str, Any] = {}
    series: list[float] = []
    windows: list[float] = []
    for clip_id, c in worker["clips"].items():
        passes = c["passes"]
        med = statistics.median
        elapsed = [p["elapsed_s"] for p in passes]
        rtfs = [p["rtf"] for p in passes]
        per_clip[clip_id] = {
            "n_frames": c["n_frames"],
            "span_s": passes[0]["span_s"],
            "n_passes": len(passes),
            "elapsed_median_s": med(elapsed),
            "elapsed_min_s": min(elapsed),
            "elapsed_max_s": max(elapsed),
            "rtf_median": med(rtfs),
            "rtf_min": min(rtfs),
            "rtf_max": max(rtfs),
            "ms_per_frame_median": med(p["ms_per_frame"] for p in passes),
            "detect_s_median": med(p["detect_s"] for p in passes),
            "estimate_s_median": med(p["estimate_s"] for p in passes),
            "decode_s_median": med(d["decode_s"] for d in c["decode"]),
            "post_s_median": med(p["post_s"] for p in c["post"]),
            "spread": c["spread"],
            "noisy": c["noisy"],
            "extra_passes": c["extra_passes"],
            "all_identical": c["all_identical"],
        }
        per_clip[clip_id]["end_to_end_s"] = per_clip[clip_id]["elapsed_median_s"] + per_clip[clip_id]["post_s_median"]
        for p in passes:
            series.extend(p["latency_ms"])
            windows.extend(p["window_rtf"])
    elapsed_total = sum(c["elapsed_median_s"] for c in per_clip.values())
    frames_total = sum(c["n_frames"] for c in per_clip.values())
    span_total = sum(c["span_s"] for c in per_clip.values())
    ms_per_frame = 1000.0 * elapsed_total / frames_total
    phases = {
        key: sum(c[f"{key}_median"] for c in per_clip.values())
        for key in ("detect_s", "estimate_s", "decode_s", "post_s")
    }
    phases["other_s"] = elapsed_total - phases["detect_s"] - phases["estimate_s"] - phases["decode_s"]
    return {
        "per_clip": per_clip,
        "elapsed_median_s": elapsed_total,  # one pass over all the clips
        "n_frames": frames_total,
        "span_s": span_total,
        "rtf": elapsed_total / span_total,
        "ms_per_frame": ms_per_frame,
        "rtf_at_30_fps": fps_equivalent_rtf(ms_per_frame, 30.0),
        "rtf_at_60_fps": fps_equivalent_rtf(ms_per_frame, 60.0),
        "phases_s": phases,
        "frame_latency_ms": {str(q): v for q, v in percentiles(series).items()},
        "window_rtf": {str(q): v for q, v in percentiles(windows, (50, 95)).items()},
        "n_windows": len(windows),
    }


def _effect(
    ref_raws: dict[str, Any],
    ref_down: dict[str, Downstream],
    raws: dict[str, Any],
    downs: dict[str, Downstream],
) -> tuple[dict[str, Any], RunComparison, float | None, int]:
    """Comparison of one N with N = 1: per clip and pooled; returns the dict, the pooled comparison, the loss of the
    tracked share in percentage points (None if no clip has a target in both) and the new ``needs_reselect`` count."""
    per_clip: dict[str, Any] = {}
    comparisons: list[RunComparison] = []
    target_comparisons: list[TargetComparison] = []
    both_frames = 0
    ref_tracked = other_tracked = 0.0
    new_reselect = 0
    for clip_id, raw in raws.items():
        comparison = compare_runs(ref_raws[clip_id], raw)
        comparisons.append(comparison)
        a, b = ref_down[clip_id], downs[clip_id]
        target = compare_target_tracks(a, b, raw.params.min_score)
        if target is not None:
            target_comparisons.append(target)
        per_clip[clip_id] = {
            "comparison": _comparison_dict(comparison),
            "downstream": _downstream_dict(b),
            "same_target": same_target(a, b),
            "target": _target_dict(target),
        }
        if a.target_found and b.target_found:
            assert a.share_tracked is not None and b.share_tracked is not None
            both_frames += comparison.n_frames
            ref_tracked += a.share_tracked * comparison.n_frames
            other_tracked += b.share_tracked * comparison.n_frames
        if b.needs_reselect and not a.needs_reselect:
            new_reselect += 1
    pooled = pool_comparisons(comparisons)
    loss = 100.0 * (ref_tracked - other_tracked) / both_frames if both_frames else None
    return (
        {
            "pooled": _comparison_dict(pooled),
            "target_pooled": _target_dict(pool_target_comparisons(target_comparisons) if target_comparisons else None),
            "per_clip": per_clip,
            "tracked_loss_points": loss,
            "new_needs_reselect": new_reselect,
        },
        pooled,
        loss,
        new_reselect,
    )


def _environment(workers: dict[int, dict[str, Any]]) -> dict[str, Any]:
    import av
    import numpy

    first = next(iter(workers.values()))
    vram = first["vram"]
    first_clip = next(iter(first["clips"].values()))
    return {
        "date": datetime.date.today().isoformat(),
        "python": sys.version.split()[0],
        "onnxruntime_gpu": importlib.metadata.version("onnxruntime-gpu"),
        "rtmlib": importlib.metadata.version("rtmlib"),
        "av": av.__version__,
        "numpy": numpy.__version__,
        "gpu": vram.get("device") if vram.get("measured") else None,
        "driver": vram.get("driver") if vram.get("measured") else None,
        "gpu_total_mib": vram.get("total_mib") if vram.get("measured") else None,
        "providers": first_clip["providers"],
        "utilisation_before_pct": {str(n): w["utilisation_before_pct"] for n, w in workers.items()},
    }


def run_benchmark(
    video_dir: Path | str,
    *,
    ns: Sequence[int] = (1, 5, 10),
    repeats: int = 3,
    clip_ids: Sequence[str] | None = None,
    baseline_s: float = 3.0,
    segment_s: float = SEGMENT_S,
    rule: DecisionRule | None = None,
    work_dir: Path | str | None = None,
    keep: bool = False,
) -> dict[str, Any]:
    """Measure and compare; see the module docstring. Raises ``BenchError`` when something cannot be measured."""
    ns = sorted(set(ns))
    if 1 not in ns:
        raise BenchError("N = 1 is the reference of the comparison and must be among the values of N")
    if any(n < 1 for n in ns) or repeats < 1 or segment_s <= 0:
        raise BenchError("N and repeats must be at least 1 and the segment longer than 0 s")
    chosen = list(clip_ids) if clip_ids else list(CLIPS)
    unknown = [c for c in chosen if c not in CLIPS]
    if unknown:
        raise BenchError(f"unknown clip(s) {unknown}; the clips are {list(CLIPS)}")
    labels = sorted({CLIPS[c].video_label for c in chosen})
    videos = find_videos(video_dir, {label: D20_VIDEOS[label] for label in labels})
    root = Path(work_dir) if work_dir is not None else PROJECT_ROOT / "data" / "bench" / uuid.uuid4().hex[:8]
    root.mkdir(parents=True, exist_ok=True)
    try:
        folders = ingest_throwaway(videos, root)
        plan = [
            PlanEntry(c, str(folders[CLIPS[c].video_label]), CLIPS[c].start_s, CLIPS[c].start_s + segment_s)
            for c in chosen
        ]
        write_plan(root / "plan.json", plan)
        workers: dict[int, dict[str, Any]] = {}
        for n in ns:
            out = root / f"worker_n{n}.json"
            log.info("measuring N = %d", n)
            done = subprocess.run(
                [
                    sys.executable, "-m", "taiji_ai.bench.worker", "--plan", str(root / "plan.json"), "--n", str(n),
                    "--repeats", str(repeats), "--baseline-s", str(baseline_s), "--work-dir", str(root / f"w{n}"),
                    "--out", str(out),
                ],
                capture_output=True, text=True, cwd=PROJECT_ROOT, check=False,
            )  # fmt: skip
            if done.returncode != 0:
                tail = "\n".join(done.stderr.strip().splitlines()[-15:])
                raise BenchError(f"the worker for N = {n} failed (exit {done.returncode}):\n{tail}")
            workers[n] = json.loads(out.read_text(encoding="utf-8"))

        raws = {n: {c: load_pose_raw(root / f"w{n}" / f"pose_n{n}_{c}.npz") for c in chosen} for n in ns}
        downs = {n: {c: downstream_summary(raws[n][c]) for c in chosen} for n in ns}
        summaries = {n: summarise_worker(workers[n]) for n in ns}
        effects: dict[int, dict[str, Any]] = {}
        stats = [NStats(1, 1.0, 0.0, 0.0, 0.0, 0, summaries[1]["elapsed_median_s"])]
        for n in ns:
            if n == 1:
                continue
            effect, pooled, loss, new_reselect = _effect(raws[1], downs[1], raws[n], downs[n])
            effects[n] = effect
            norm = pooled.norm
            stats.append(
                NStats(
                    n=n,
                    count_agreement=pooled.count_agreement,
                    p95_norm=None if norm is None else norm.p95,
                    p99_norm=None if norm is None else norm.p99,
                    tracked_loss_points=loss,
                    new_needs_reselect=new_reselect,
                    elapsed_median_s=summaries[n]["elapsed_median_s"],
                )
            )
        rule = rule or DecisionRule()
        recommendation = recommend_n(stats, rule)

        clip_info: dict[str, Any] = {}
        for entry in plan:
            manifest = read_manifest(Path(entry.recording_dir) / "recording.json", RecordingManifest)
            info = workers[ns[0]]["clips"][entry.clip_id]
            clip_info[entry.clip_id] = {
                "video": CLIPS[entry.clip_id].video_label,
                "start_s": entry.start_s,
                "end_s": entry.end_s,
                "codec": manifest.codec,
                "nominal_fps": manifest.nominal_fps,
                "width": manifest.width,
                "height": manifest.height,
                "n_frames": info["n_frames"],
                "persons_per_frame": info["persons_per_frame"],
            }
        return {
            "schema": "p3_07/1",
            "environment": _environment(workers),
            "rule": dataclasses.asdict(rule),
            "clips": clip_info,
            "ns": ns,
            "repeats": repeats,
            "runs": {str(n): {"worker": workers[n], "summary": summaries[n]} for n in ns},
            "reference": {c: _downstream_dict(downs[1][c]) for c in chosen},
            "effect": {str(n): effects[n] for n in effects},
            "n_stats": [dataclasses.asdict(s) for s in stats],
            "recommendation": {
                "n": recommendation.n,
                "acceptable": {str(k): v for k, v in recommendation.acceptable.items()},
                "reasons": {str(k): v for k, v in recommendation.reasons.items()},
                "speed_gain_vs_previous": {str(k): v for k, v in recommendation.speed_gain_vs_previous.items()},
            },
        }
    finally:
        if not keep:
            _remove_tree(root)


def _make_writable_and_retry(func: Any, path: str, _exc: BaseException) -> None:
    os.chmod(path, stat.S_IWRITE)  # ingest leaves the stored source read-only, which Windows will not delete
    func(path)


def _remove_tree(path: Path) -> None:
    """Delete the throwaway folder (it holds copies of the videos); a failure is reported, never hidden."""
    try:
        shutil.rmtree(path, onexc=_make_writable_and_retry)
    except OSError:
        log.warning("the throwaway benchmark folder could not be removed completely: remove it by hand")
