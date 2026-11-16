"""The process that measures one detector cadence N (P3.07): ``python -m taiji_ai.bench.worker --plan ... --n N``.

One fresh process per N, because ONNX Runtime keeps its GPU memory arena: a peak measured after another N would be the
peak of the largest run. The worker builds the estimator from the verified registry, samples the device memory in
phases (baseline, load, warm-up, measured), runs one warm-up pass (not counted: cuDNN algorithm search, arena growth)
and then ``repeats`` measured passes over the clips (all clips once per repeat, so a drift of the machine spreads over
the clips). A clip whose elapsed times spread by more than 10 % of their median gets up to two more passes and is
marked noisy if it stays above. After the GPU work it times the decode alone, the stages after ``run_pose``
(association, target, resolution, saving) and writes the ``PoseRaw`` of the first measured pass of every clip next to
the JSON, for the comparison between runs. Everything printed or written names clips by their ID; the recording
folders are throwaway.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

from taiji_ai.bench import BenchError
from taiji_ai.bench.clips import PlanEntry, read_plan
from taiji_ai.bench.gpu import VramSampler, try_open_nvml, vram_unavailable
from taiji_ai.bench.timing import FrameClock, TimedModel, ms_per_frame, rtf, video_span_s, window_rtf
from taiji_ai.config import get_settings
from taiji_ai.io.frames import iter_frames
from taiji_ai.pose.raw_io import save_pose_raw
from taiji_ai.pose.runner import PoseRaw, PoseRunError, PoseRunParams, run_pose
from taiji_ai.schemas._base import read_manifest
from taiji_ai.schemas.recording import RecordingManifest
from taiji_ai.track.associate import associate_tracks
from taiji_ai.track.state import resolve_target
from taiji_ai.track.target import TargetSelectionError, select_target
from taiji_ai.track.track_io import save_track

log = logging.getLogger(__name__)

SPREAD_LIMIT = 0.10  # (max - min) / median of the elapsed times of a clip above which it is measured again
MAX_EXTRA_PASSES = 2


def _spread(values: list[float]) -> float:
    median = statistics.median(values)
    return (max(values) - min(values)) / median if median > 0 else 0.0


def _one_pass(
    entry: PlanEntry, timed: TimedModel, clock: FrameClock, params: PoseRunParams
) -> tuple[dict[str, Any], PoseRaw]:
    timed.reset()
    clock.start()
    raw = run_pose(entry.recording_dir, entry.start_s, entry.end_s, timed, params=params, on_frame=clock.on_frame)
    stats = raw.stats
    if timed.n_detect != stats.n_detector_calls or timed.n_estimate != stats.n_pose_calls:
        raise BenchError(
            f"clip {entry.clip_id}: the timed calls ({timed.n_detect} detector, {timed.n_estimate} pose) do not match "
            f"the counts of the run ({stats.n_detector_calls}, {stats.n_pose_calls})"
        )
    if clock.n_frames != raw.n_frames or not np.array_equal(clock.t_sec, raw.t_sec):
        raise BenchError(f"clip {entry.clip_id}: the frame callbacks do not match the frames of the run")
    assert stats.elapsed_s is not None  # a fresh run always has its wall clock
    span = video_span_s(raw.t_sec)
    latency = clock.latencies()
    windows = window_rtf(latency, raw.t_sec)
    return (
        {
            "elapsed_s": stats.elapsed_s,
            "n_frames": raw.n_frames,
            "span_s": span,
            "rtf": rtf(stats.elapsed_s, span),
            "ms_per_frame": ms_per_frame(stats.elapsed_s, raw.n_frames),
            "detect_s": timed.detect_s,
            "estimate_s": timed.estimate_s,
            "n_detect": timed.n_detect,
            "n_estimate": timed.n_estimate,
            "latency_ms": [round(1000.0 * float(v), 4) for v in latency],
            "window_rtf": windows.values.tolist(),
            "n_empty_windows": windows.n_empty_windows,
            "n_dropped_frames": windows.n_dropped_frames,
            "identical_to_first": None,
        },
        raw,
    )


def _decode_only(entry: PlanEntry, raw: PoseRaw) -> dict[str, float]:
    manifest = read_manifest(Path(entry.recording_dir) / "recording.json", RecordingManifest)
    source = Path(entry.recording_dir) / f"source{manifest.source_ext}"
    started = time.perf_counter()
    n = 0
    for _ in iter_frames(source, float(raw.t_sec[0]), float(raw.t_sec[-1]), rotation_deg=manifest.display_rotation):
        n += 1
    seconds = time.perf_counter() - started
    if n != raw.n_frames:
        raise BenchError(f"clip {entry.clip_id}: the decode-only pass gave {n} frames, the run {raw.n_frames}")
    return {"decode_s": seconds, "n_frames": n}


def _post_stages(raw: PoseRaw, tmp: Path) -> dict[str, Any]:
    """Time what follows ``run_pose``: association, target, resolution, saving the pose and the track."""
    marks: dict[str, float] = {}
    t = time.perf_counter()
    tracks = associate_tracks(raw)
    marks["associate_s"] = time.perf_counter() - t
    t = time.perf_counter()
    try:
        selection = select_target(raw)
    except TargetSelectionError:
        selection = None
    marks["select_s"] = time.perf_counter() - t
    t = time.perf_counter()
    track = resolve_target(raw, tracks, selection) if selection is not None else None
    marks["resolve_s"] = time.perf_counter() - t
    t = time.perf_counter()
    save_pose_raw(tmp / "pose_raw.npz", raw)
    marks["save_pose_s"] = time.perf_counter() - t
    t = time.perf_counter()
    if track is not None:
        save_track(tmp / "track.parquet", track)
    marks["save_track_s"] = time.perf_counter() - t
    marks["post_s"] = sum(marks.values())
    marks["target_found"] = selection is not None  # type: ignore[assignment]
    return marks


def _persons_per_frame(raw: PoseRaw) -> dict[str, float]:
    counts = raw.n_persons
    shares = {str(k): float((counts == k).mean()) for k in range(4)}
    shares["4+"] = float((counts >= 4).mean())
    return shares


def run_worker(plan: list[PlanEntry], n: int, repeats: int, baseline_s: float, work_dir: Path) -> dict[str, Any]:
    """Measure the clips of ``plan`` with a detector cadence of ``n``; the result is a JSON-ready dict."""
    if n < 1 or repeats < 1 or baseline_s < 0.0:
        raise BenchError("n and repeats must be at least 1 and baseline_s not negative")
    settings = get_settings()
    if not settings.registry_path.exists():
        raise BenchError("the model registry is missing: run tools/fetch_models.py first")
    from taiji_ai.pose.registry import ModelRegistry
    from taiji_ai.pose.rtm import PoseEstimator

    work_dir.mkdir(parents=True, exist_ok=True)
    nvml, nvml_reason = try_open_nvml()
    sampler = VramSampler(nvml) if nvml is not None else None
    utilisation_before = nvml.utilisation_pct() if nvml is not None else None
    if sampler is not None:
        sampler.phase("baseline")
        sampler.sample_once()  # at least one baseline sample, even with a baseline of 0 s
        sampler.start()
        time.sleep(baseline_s)
        sampler.phase("load")
    try:
        started = time.perf_counter()
        estimator = PoseEstimator(ModelRegistry(settings.registry_path), device=settings.device)
        load_s = time.perf_counter() - started
        timed, clock, params = TimedModel(estimator), FrameClock(), PoseRunParams(detect_every_n=n)

        if sampler is not None:
            sampler.phase("warmup")
        warm, _ = _one_pass(plan[0], timed, clock, params)  # not counted in any RTF
        if sampler is not None:
            sampler.phase("measured")
        passes: dict[str, list[dict[str, Any]]] = {e.clip_id: [] for e in plan}
        first: dict[str, PoseRaw] = {}
        for repeat in range(repeats):
            for entry in plan:
                result, raw = _one_pass(entry, timed, clock, params)
                if repeat == 0:
                    first[entry.clip_id] = raw
                    save_pose_raw(work_dir / f"pose_n{n}_{entry.clip_id}.npz", raw)
                else:
                    result["identical_to_first"] = raw.equals(first[entry.clip_id])
                passes[entry.clip_id].append(result)
        extra_passes: dict[str, int] = {}
        for entry in plan:
            extra = 0
            while _spread([p["elapsed_s"] for p in passes[entry.clip_id]]) > SPREAD_LIMIT and extra < MAX_EXTRA_PASSES:
                result, raw = _one_pass(entry, timed, clock, params)
                result["identical_to_first"] = raw.equals(first[entry.clip_id])
                passes[entry.clip_id].append(result)
                extra += 1
            extra_passes[entry.clip_id] = extra
        if sampler is not None:
            sampler.stop()
            vram = sampler.summary()
        else:
            vram = vram_unavailable(nvml_reason)
    finally:
        if sampler is not None:
            try:
                sampler.stop()
            except BenchError:
                log.warning("the VRAM sampler had failed")
        if nvml is not None:
            nvml.close()

    clips: dict[str, Any] = {}
    for entry in plan:
        raw = first[entry.clip_id]
        elapsed = [p["elapsed_s"] for p in passes[entry.clip_id]]
        decode = [_decode_only(entry, raw) for _ in range(repeats)]
        post = []
        for _ in range(repeats):
            with tempfile.TemporaryDirectory(dir=work_dir) as tmp:
                post.append(_post_stages(raw, Path(tmp)))
        clips[entry.clip_id] = {
            "start_s": entry.start_s,
            "end_s": entry.end_s,
            "n_frames": raw.n_frames,
            "image_size": list(raw.image_size),
            "providers": raw.providers,
            "persons_per_frame": _persons_per_frame(raw),
            "passes": passes[entry.clip_id],
            "spread": _spread(elapsed),
            "noisy": _spread(elapsed) > SPREAD_LIMIT,
            "extra_passes": extra_passes[entry.clip_id],
            "all_identical": all(p["identical_to_first"] in (None, True) for p in passes[entry.clip_id]),
            "decode": decode,
            "post": post,
        }
    return {
        "n": n,
        "repeats": repeats,
        "load_s": load_s,
        "warmup": warm,
        "utilisation_before_pct": utilisation_before,
        "vram": vram,
        "clips": clips,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m taiji_ai.bench.worker", description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--n", required=True, type=int)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--baseline-s", type=float, default=3.0)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    from taiji_ai.logs import configure_logging

    configure_logging()
    try:
        result = run_worker(read_plan(args.plan), args.n, args.repeats, args.baseline_s, args.work_dir)
    except (BenchError, PoseRunError) as exc:
        log.error("the worker could not measure: %s", exc)
        return 2
    args.out.write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
