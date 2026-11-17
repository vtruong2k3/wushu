"""One process per detector for the comparison of P3.09: speed and memory, then the detections on the labelled
frames and the clips. A fresh process per detector, so that the memory arena of one never counts for the other.

The job (JSON) names the detector (``shipping``: the YOLOX of the registry through ONNX Runtime; ``yolo11``: a
YOLO-format ONNX file), the video files and their rotation, and three sets of frames:

* **S** (speed): the first ``n_speed_frames`` frames of a clip, decoded once and held in memory;
* **R** (labelled frames): ``(id, video, t_sec)``: the frame nearest to ``t_sec``;
* **C** (clips): ``(clip, video, start_s, end_s)``: every frame of the clip, streamed.

Result JSON: the providers, the load time, the VRAM phases (NVML, as in P3.07), the timings (model only and end to end,
per repeat) and the counts. The detections go to an ``.npz`` (``r_*`` and ``c_<clip>_*`` arrays: ids or times,
offsets, the detections ``(n, 5)`` in the original picture); for YOLO11 also the detections with the second NMS
limit (``*_alt``).
Only labels (``d20-vN``) and times are written, never a path of a video.

Offline tooling: the product does not import this module (a guard test checks it).
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from taiji_ai.bench import BenchError
from taiji_ai.bench.gpu import VramSampler, try_open_nvml, vram_unavailable
from taiji_ai.bench.timing import percentiles
from taiji_ai.bench.yolo_onnx import ShippingDetector, YoloOnnx, decode_yolo
from taiji_ai.io.frames import iter_frames
from taiji_ai.store.artifacts import atomic_save_npz

log = logging.getLogger(__name__)

DETECTORS = ("shipping", "yolo11")


@dataclass
class Stages:
    """The three stages of a detector, so that they can be timed apart: ``pre(frame) -> ctx``, ``run(ctx) -> raw``,
    ``post(raw, ctx, image_shape) -> detections``; ``post_alt`` gives the second NMS limit (YOLO11 only)."""

    pre: Callable[[np.ndarray], Any]
    run: Callable[[Any], Any]
    post: Callable[[Any, Any, tuple[int, int]], np.ndarray]
    post_alt: Callable[[Any, Any, tuple[int, int]], np.ndarray] | None = None


def build_stages(
    kind: str, model_path: Path | str, device: str, score: float, nms_iou: float, nms_iou_alt: float
) -> Stages:
    if kind == "shipping":
        ship = ShippingDetector(model_path, device=device, score_limit=score)
        return Stages(
            pre=ship.preprocess,
            run=lambda ctx: ship.run(ctx[0]),
            post=lambda raw, ctx, shape: ship.postprocess(raw, ctx[1]),
        )
    if kind == "yolo11":
        yolo = YoloOnnx(model_path, device=device, conf=score, iou=nms_iou)
        return Stages(
            pre=yolo.preprocess,
            run=lambda ctx: yolo.run(ctx[0]),
            post=lambda raw, ctx, shape: yolo.postprocess(raw, ctx[1], ctx[2], shape),
            post_alt=lambda raw, ctx, shape: decode_yolo(raw, ctx[1], ctx[2], shape, score, nms_iou_alt),
        )
    raise BenchError(f"unknown detector {kind!r}; the detectors are {list(DETECTORS)}")


def pack(arrays: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Offsets ``(n + 1,)`` and the detections stacked ``(m, 5)``; frame ``i`` is the rows from ``offsets[i]`` up to
    (not including) ``offsets[i + 1]``."""
    offsets = np.zeros(len(arrays) + 1, dtype=np.int64)
    offsets[1:] = np.cumsum([len(a) for a in arrays])
    rows = np.concatenate([a.reshape(-1, 5) for a in arrays], axis=0) if arrays else np.empty((0, 5), np.float32)
    return offsets, rows.astype(np.float32, copy=False)


def unpack(offsets: np.ndarray, rows: np.ndarray) -> list[np.ndarray]:
    return [rows[int(offsets[i]) : int(offsets[i + 1])] for i in range(len(offsets) - 1)]


def frame_near(source: Path | str, rotation: int, t_sec: float, window_s: float = 0.05) -> np.ndarray:
    """The decoded frame nearest to ``t_sec`` (by real PTS)."""
    best: tuple[float, np.ndarray] | None = None
    for frame in iter_frames(source, max(0.0, t_sec - window_s), t_sec + window_s, rotation_deg=rotation):
        gap = abs(frame.t_sec - t_sec)
        if best is None or gap < best[0]:
            best = (gap, frame.image)
    if best is None:
        raise BenchError(f"no frame near {t_sec:.3f} s: the stored video does not match the plan")
    return best[1]


def _spread(values_ms: list[float]) -> dict[str, float]:
    p = percentiles(values_ms, (50, 95, 99))
    return {"p50": p[50], "p95": p[95], "p99": p[99], "mean": float(np.mean(values_ms))}


def measure_speed(stages: Stages, frames: list[np.ndarray], warmup: int, repeats: int) -> dict[str, Any]:
    """Per repeat: model-only and end-to-end time per frame in ms (percentiles), and the medians of pre and post."""
    if not frames:
        raise BenchError("no frames to measure the speed on")
    for i in range(warmup):  # not counted: cuDNN algorithm search and arena growth
        frame = frames[i % len(frames)]
        ctx = stages.pre(frame)
        stages.post(stages.run(ctx), ctx, frame.shape[:2])  # type: ignore[arg-type]
    runs = []
    for _ in range(repeats):
        pre, run, post = [], [], []
        for frame in frames:
            t0 = time.perf_counter()
            ctx = stages.pre(frame)
            t1 = time.perf_counter()
            raw = stages.run(ctx)
            t2 = time.perf_counter()
            stages.post(raw, ctx, frame.shape[:2])  # type: ignore[arg-type]
            t3 = time.perf_counter()
            pre.append(1000.0 * (t1 - t0))
            run.append(1000.0 * (t2 - t1))
            post.append(1000.0 * (t3 - t2))
        runs.append(
            {
                "model_ms": _spread(run),
                "end_to_end_ms": _spread([a + b + c for a, b, c in zip(pre, run, post, strict=True)]),
                "pre_ms_median": float(statistics.median(pre)),
                "post_ms_median": float(statistics.median(post)),
            }
        )
    return {"n_frames": len(frames), "warmup": warmup, "repeats": runs}


def detect_frames(stages: Stages, frames: Any) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """The detections of each frame of an iterable of images; the second list is empty if the detector has no alt
    NMS."""
    main: list[np.ndarray] = []
    alt: list[np.ndarray] = []
    for image in frames:
        ctx = stages.pre(image)
        raw = stages.run(ctx)
        main.append(stages.post(raw, ctx, image.shape[:2]))
        if stages.post_alt is not None:
            alt.append(stages.post_alt(raw, ctx, image.shape[:2]))
    return main, alt


def run_job(job: dict[str, Any], out_npz: Path) -> dict[str, Any]:
    kind = job["detector"]
    if kind not in DETECTORS:
        raise BenchError(f"unknown detector {kind!r}; the detectors are {list(DETECTORS)}")
    for key in ("repeats", "warmup", "n_speed_frames"):
        if int(job[key]) < 0 or (key != "warmup" and int(job[key]) < 1):
            raise BenchError(f"{key} must be a whole number of at least {0 if key == 'warmup' else 1}")
    sources: dict[str, dict[str, Any]] = job["sources"]

    nvml, nvml_reason = try_open_nvml()
    sampler = VramSampler(nvml) if nvml is not None else None
    if sampler is not None:
        sampler.phase("baseline")
        sampler.sample_once()
        sampler.start()
        time.sleep(float(job.get("baseline_s", 3.0)))
        sampler.phase("load")
    arrays: dict[str, np.ndarray] = {}
    result: dict[str, Any] = {"detector": kind, "image_shapes": {}}
    try:
        started = time.perf_counter()
        stages = build_stages(
            kind,
            job["model_path"],
            job.get("device", "cuda"),
            float(job["score"]),
            float(job["nms_iou"]),
            float(job["nms_iou_alt"]),
        )
        result["load_s"] = time.perf_counter() - started
        if sampler is not None:
            sampler.phase("warmup")

        speed_set = job.get("set_s")
        if speed_set is not None:
            src = sources[speed_set["video"]]
            frames = []
            start = float(speed_set["start_s"])
            for frame in iter_frames(src["path"], start, start + 30.0, rotation_deg=int(src["rotation"])):
                frames.append(frame.image)
                if len(frames) >= int(job["n_speed_frames"]):
                    break
            if sampler is not None:
                sampler.phase("measured")
            result["speed"] = measure_speed(stages, frames, int(job["warmup"]), int(job["repeats"]))
            result["speed"]["image_shape"] = list(frames[0].shape[:2])
        elif sampler is not None:
            sampler.phase("measured")

        labelled = job.get("set_r") or []
        if labelled:
            images = (
                frame_near(sources[e["video"]]["path"], int(sources[e["video"]]["rotation"]), float(e["t_sec"]))
                for e in labelled
            )
            main, alt = detect_frames(stages, images)
            offsets, rows = pack(main)
            arrays.update(r_ids=np.array([e["id"] for e in labelled]), r_offsets=offsets, r_dets=rows)
            if alt:
                o2, r2 = pack(alt)
                arrays.update(r_offsets_alt=o2, r_dets_alt=r2)
            result["r"] = {"n_frames": len(labelled)}

        result["c"] = {}
        for clip in job.get("set_c") or []:
            src = sources[clip["video"]]
            times: list[float] = []

            def stream(clip: dict[str, Any] = clip, src: dict[str, Any] = src, times: list[float] = times) -> Any:
                for frame in iter_frames(
                    src["path"], float(clip["start_s"]), float(clip["end_s"]), rotation_deg=int(src["rotation"])
                ):
                    times.append(frame.t_sec)
                    result["image_shapes"][clip["video"]] = list(frame.image.shape[:2])
                    yield frame.image

            main, alt = detect_frames(stages, stream())
            offsets, rows = pack(main)
            name = f"c_{clip['clip']}"
            arrays.update({f"{name}_t_sec": np.array(times), f"{name}_offsets": offsets, f"{name}_dets": rows})
            if alt:
                o2, r2 = pack(alt)
                arrays.update({f"{name}_offsets_alt": o2, f"{name}_dets_alt": r2})
            result["c"][clip["clip"]] = {"n_frames": len(times)}
        result["providers"] = (
            ["CUDAExecutionProvider"] if job.get("device", "cuda") == "cuda" else ["CPUExecutionProvider"]
        )
        if sampler is not None:
            sampler.stop()
            result["vram"] = sampler.summary()
        else:
            result["vram"] = vram_unavailable(nvml_reason)
    finally:
        if sampler is not None:
            try:
                sampler.stop()
            except BenchError:
                log.warning("the VRAM sampler had failed")
        if nvml is not None:
            nvml.close()
    out_npz.parent.mkdir(parents=True, exist_ok=True)
    atomic_save_npz(out_npz, **arrays)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m taiji_ai.bench.detector_worker", description=__doc__)
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="the result JSON; the detections go next to it as .npz")
    args = parser.parse_args(argv)
    from taiji_ai.logs import configure_logging

    configure_logging()
    try:
        job = json.loads(args.job.read_text(encoding="utf-8"))
        result = run_job(job, args.out.with_suffix(".npz"))
    except (BenchError, OSError, ValueError, KeyError) as exc:
        log.error("the detector worker could not measure: %s", exc)
        return 2
    args.out.write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
