"""P3.09: compare the shipping detector (YOLOX of rtmlib) with YOLO11 on the D20 footage. Measurement only: nothing
of the stack changes.

YOLO11 and its weights are AGPL-3.0 (Ultralytics). They are used **offline, for this one measurement**: the ONNX file is
exported in an isolated environment by the vendor's command line, outside this repository; nothing here imports
Ultralytics, nothing registers the file in ``models/registry.json`` (DEC-0043, ``Docs/tasks/P3.09.md``).

``run`` finds the four videos by size and SHA-256 (never by name), ingests them into a throwaway folder, runs one worker
process per detector (speed and memory, the 250 labelled frames of P3.08, the five clips of P3.07), computes the numbers
and draws the frames where only one detector finds a person. ``sheets`` builds the page for the review of those frames.
``report`` reads the reviewed labels, applies the rule written before the measurement, and writes the tables.

Usage (from ``taiji_ai/``, the GPU free of other jobs)::

    python tools/detector_compare.py run --video-dir ../video --yolo11 data/bench/p3_09/models/yolo11m.onnx
    python tools/detector_compare.py sheets
    python tools/detector_compare.py report

Only labels (``d20-v1`` to ``d20-v4``), clip names and times are printed. Exit code 2 for what the tool cannot do.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from taiji_ai.bench import BenchError
from taiji_ai.bench.clips import CLIPS, D20_VIDEOS, SEGMENT_S, find_videos
from taiji_ai.bench.detector_compare import (
    SCORE_LIMITS,
    iou_profile,
    pick_sample,
    recall_by_limit,
    render_tables,
    speed_summary,
    summarise_c,
    summarise_r,
)
from taiji_ai.bench.detector_metrics import CReview, DetectorRule, PairedRecall, decide, reference_box
from taiji_ai.bench.detector_worker import frame_near, unpack
from taiji_ai.bench.orchestrate import _remove_tree, ingest_throwaway
from taiji_ai.bench.yolo_onnx import check_layout, read_shapes
from taiji_ai.config import PROJECT_ROOT, get_settings
from taiji_ai.logs import configure_logging
from taiji_ai.store.artifacts import sha256_file

OUT_DEFAULT = PROJECT_ROOT / "data" / "bench" / "p3_09"
P308_DEFAULT = PROJECT_ROOT / "data" / "reports" / "p3_08"
NEGATIVE_IDS = ("fc-210", "fc-250")  # the two frames of P3.08 without a person (a title card and a black frame)
SPEED_CLIP = "c1"
SAMPLE_SIZE = 60
NMS_IOU_ALT = 0.7  # the default of Ultralytics, reported as a side line


def _check_options(args: argparse.Namespace) -> None:
    if args.repeats < 1:
        raise BenchError("repeats must be at least 1")
    if args.warmup < 0:
        raise BenchError("warmup must be 0 or more")
    if not 0.0 < args.score < 1.0:
        raise BenchError("score must be above 0 and below 1")
    if not 0.0 < args.nms_iou <= 1.0:
        raise BenchError("nms-iou must be above 0 and at most 1")


def _labelled_frames(p308: Path) -> list[dict[str, Any]]:
    """The 250 frames of P3.08 with what is known about the performer: a reference box from the skeleton that was
    confirmed right (an ``ok`` frame), a negative (no person), or neither (a failure: no reference)."""
    from taiji_ai.audit.analyse import collect_pass
    from taiji_ai.audit.labels import final_label, read_review

    try:
        records = json.loads((p308 / "candidates.json").read_text(encoding="utf-8"))
        rows = {r.cid: r for r in read_review(p308 / "review.csv", expected_ids=[c["id"] for c in records])}
    except (OSError, ValueError) as exc:
        raise BenchError("the review files of P3.08 are missing or unreadable") from exc
    if not all(n in rows for n in NEGATIVE_IDS):
        raise BenchError("the labelled frames of P3.08 do not hold the two frames without a person")
    pool = collect_pass(p308)
    where = {(v, int(f)): i for i, (v, f) in enumerate(zip(pool.video, pool.frame_index, strict=True))}
    entries = []
    for c in records:
        label = final_label(rows[c["id"]])
        negative = c["id"] in NEGATIVE_IDS
        reference = None
        if label.verdict == "ok" and not negative:
            pos = where[(c["video"], int(c["frame_index"]))]
            reference = reference_box(pool.kp[pos], pool.scores[pos])
        entries.append(
            {
                "id": c["id"],
                "video": c["video"],
                "t_sec": float(c["t_sec"]),
                "reference": reference,
                "negative": negative,
            }
        )
    return entries


def _sources(recordings: dict[str, Path]) -> dict[str, dict[str, Any]]:
    from taiji_ai.schemas._base import read_manifest
    from taiji_ai.schemas.recording import RecordingManifest

    out = {}
    for label, rec in recordings.items():
        info = read_manifest(rec / "recording.json", RecordingManifest)
        out[label] = {"path": str(rec / f"source{info.source_ext}"), "rotation": info.display_rotation}
    return out


def _run_worker(kind: str, job: dict[str, Any], out_dir: Path) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    job_path, result_path = out_dir / f"job_{kind}.json", out_dir / f"worker_{kind}.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")
    done = subprocess.run(
        [sys.executable, "-m", "taiji_ai.bench.detector_worker", "--job", str(job_path), "--out", str(result_path)],
        cwd=PROJECT_ROOT,
        check=False,
    )
    if done.returncode != 0:
        raise BenchError(f"the worker of {kind} failed (exit {done.returncode})")
    arrays = np.load(result_path.with_suffix(".npz"))
    return json.loads(result_path.read_text(encoding="utf-8")), {k: arrays[k] for k in arrays.files}


def _draw(image: np.ndarray, boxes_a: np.ndarray, boxes_b: np.ndarray, caption: str) -> np.ndarray:
    """Both detectors' boxes on the frame (1 green, 2 magenta: the order is not the order of the detectors' names)."""
    img = image.copy()
    for rows, colour in ((boxes_a, (0, 200, 0)), (boxes_b, (200, 0, 200))):
        for x1, y1, x2, y2, score in np.asarray(rows).reshape(-1, 5):
            cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), colour, max(2, img.shape[0] // 270))
            cv2.putText(img, f"{score:.2f}", (int(x1) + 4, int(y1) + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, colour, 2)
    h, w = img.shape[:2]
    scale = 760.0 / max(h, w)
    small = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    bar = np.zeros((26, small.shape[1], 3), np.uint8)
    cv2.putText(bar, caption, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return np.vstack([bar, small])


def run(args: argparse.Namespace) -> int:
    _check_options(args)
    if not Path(args.video_dir).is_dir():
        raise BenchError("the video folder does not exist")
    if not Path(args.yolo11).is_file():
        raise BenchError("the YOLO11 file does not exist")
    check_layout(*read_shapes(args.yolo11))
    videos = find_videos(args.video_dir, D20_VIDEOS)
    settings = get_settings()
    if not settings.registry_path.exists():
        raise BenchError("the model registry is missing: run tools/fetch_models.py first")
    from taiji_ai.pose.registry import ModelRegistry

    shipping = ModelRegistry(settings.registry_path).by_role("det")
    entries = _labelled_frames(args.p308)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    recordings = ingest_throwaway(videos, work)
    try:
        sources = _sources(recordings)
        clips = [
            {"clip": cid, "video": c.video_label, "start_s": c.start_s, "end_s": c.start_s + SEGMENT_S}
            for cid, c in CLIPS.items()
        ]
        base = {
            "sources": sources,
            "score": args.score,
            "nms_iou": args.nms_iou,
            "nms_iou_alt": NMS_IOU_ALT,
            "repeats": args.repeats,
            "warmup": args.warmup,
            "n_speed_frames": args.frames,
            "baseline_s": 3.0,
            "device": "cuda",
            "set_s": {"video": CLIPS[SPEED_CLIP].video_label, "start_s": CLIPS[SPEED_CLIP].start_s},
            "set_r": [{"id": e["id"], "video": e["video"], "t_sec": e["t_sec"]} for e in entries],
            "set_c": clips,
        }
        wa, na = _run_worker("shipping", {**base, "detector": "shipping", "model_path": str(shipping.path)}, out)
        wb, nb = _run_worker("yolo11", {**base, "detector": "yolo11", "model_path": str(args.yolo11)}, out)
        heights = {**wa["image_shapes"], **wb["image_shapes"]}
        for e in entries:
            e["image_height"] = float(heights[e["video"]][0])

        r_a, r_b = unpack(na["r_offsets"], na["r_dets"]), unpack(nb["r_offsets"], nb["r_dets"])
        r_b_alt = unpack(nb["r_offsets_alt"], nb["r_dets_alt"])
        c_in: dict[str, dict[str, Any]] = {}
        for cl in clips:
            k = f"c_{cl['clip']}"
            c_in[cl["clip"]] = {
                "t_sec": na[f"{k}_t_sec"],
                "dets_a": unpack(na[f"{k}_offsets"], na[f"{k}_dets"]),
                "dets_b": unpack(nb[f"{k}_offsets"], nb[f"{k}_dets"]),
                "image_height": float(heights[cl["video"]][0]),
            }
        c = summarise_c(c_in, args.score)
        sample = pick_sample(c["runs"], SAMPLE_SIZE)
        d_dir = out / "discordant"
        d_dir.mkdir(exist_ok=True)
        clip_video = {cl["clip"]: cl["video"] for cl in clips}
        for item in sample:
            frames = c_in[item["clip"]]
            i = int(np.argmin(np.abs(frames["t_sec"] - item["t_sec"])))
            src = sources[clip_video[item["clip"]]]
            image = frame_near(src["path"], int(src["rotation"]), float(item["t_sec"]))
            tile = _draw(
                image, frames["dets_a"][i], frames["dets_b"][i], f"{item['id']}  {item['clip']}  {item['t_sec']:.2f} s"
            )
            cv2.imwrite(str(d_dir / f"{item['id']}.jpg"), tile, [cv2.IMWRITE_JPEG_QUALITY, 88])
        result = {
            "schema": "p3_09_detector/1",
            "settings": {k: getattr(args, k) for k in ("score", "nms_iou", "repeats", "warmup", "frames")}
            | {"nms_iou_alt": NMS_IOU_ALT},
            "weights": {"shipping_sha256": shipping.sha256, "yolo11_onnx_sha256": sha256_file(args.yolo11)},
            "providers": {"a": wa.get("providers"), "b": wb.get("providers")},
            "speed": {"a": speed_summary(wa), "b": speed_summary(wb)},
            "r": summarise_r(entries, r_a, r_b, args.score),
            "r_alt_nms": summarise_r(entries, r_a, r_b_alt, args.score),
            "r_by_limit": recall_by_limit(entries, r_a, r_b, SCORE_LIMITS),
            "r_iou": iou_profile(entries, r_a, r_b, args.score),
            "c": c,
            "sample": sample,
        }
        (out / "detector.json").write_text(json.dumps(result, allow_nan=False, indent=1), encoding="utf-8")
        (out / "discordant.json").write_text(json.dumps(sample, allow_nan=False, indent=1), encoding="utf-8")
        (out / "detector_tables.md").write_text(render_tables(result), encoding="utf-8")
    finally:
        if not args.keep_work:
            _remove_tree(work)
    r = result["r"]
    sys.stdout.write(
        f"recall on {r['n_positive']} labelled frames: A {r['paired']['recall_a']:.3f}, "
        f"B {r['paired']['recall_b']:.3f} (only A {r['paired']['only_a']}, only B {r['paired']['only_b']}, "
        f"McNemar p {r['mcnemar_p']:.4f})\n"
        f"clips: runs with only A {c['runs_only_a']}, only B {c['runs_only_b']}; "
        f"{len(sample)} frames drawn for the review\n"
    )
    return 0


def _load_result(out: Path) -> dict[str, Any]:
    try:
        return json.loads((out / "detector.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except (OSError, ValueError) as exc:
        raise BenchError("no result yet: run first") from exc


def _read_labels(out: Path) -> dict[str, str]:
    """``id -> yes | no | unsure``; the maintainer's file wins over the agent's, row by row."""
    labels: dict[str, str] = {}
    for name in ("dc_labels_agent.json", "dc_labels_h.json"):
        path = out / name
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise BenchError(f"{name} is not valid JSON") from exc
            for k, v in data.items():
                if v not in ("yes", "no", "unsure"):
                    raise BenchError(f"{name}: {k} must be yes, no or unsure")
                labels[k] = v
    return labels


def sheets(args: argparse.Namespace) -> int:
    out = Path(args.out)
    result = _load_result(out)
    items = [
        {"id": s["id"], "clip": s["clip"], "t_sec": s["t_sec"]} for s in result["sample"]
    ]  # the direction stays hidden
    template = Path(__file__).with_name("detector_review_page.html")
    page = (
        template.read_text(encoding="utf-8")
        .replace("__DATA__", json.dumps(items))
        .replace("__LABELS__", json.dumps(_read_labels(out)))
    )
    (out / "dc_review.html").write_text(page, encoding="utf-8")
    sys.stdout.write(f"{len(items)} frames in the review page\n")
    return 0


def report(args: argparse.Namespace) -> int:
    out = Path(args.out)
    result = _load_result(out)
    labels = _read_labels(out)
    sample = result["sample"]
    reviewed = [s for s in sample if s["id"] in labels]
    b_better = a_better = unsure = 0
    for s in reviewed:
        answer = labels[s["id"]]
        if answer == "unsure":
            unsure += 1
        elif (s["direction"] == "only_b") == (
            answer == "yes"
        ):  # B has the box and a person is there, or A has it and none is
            b_better += 1
        else:
            a_better += 1
    runs = result["c"]["runs"]
    review = CReview(n_discordant=len(runs), n_reviewed=len(reviewed), b_better=b_better, a_better=a_better)
    pairs = result["r"]["paired"]
    recall = PairedRecall(result["r"]["n_positive"], pairs["both"], pairs["only_a"], pairs["only_b"])
    stab = result["c"]["stability"]

    def p95(key: str) -> float | None:
        d = stab[key]["one_minus_iou"]
        return None if d is None else float(d["p95"])

    decision = decide(DetectorRule(), recall, review, (p95("a"), p95("b")))  # decide() refuses an unreviewed C
    result["review"] = {
        "n_discordant": len(runs),
        "n_reviewed": len(reviewed),
        "b_better": b_better,
        "a_better": a_better,
        "unsure": unsure,
    }
    result["decision"] = {"outcome": decision.outcome, "criterion": decision.criterion, "reasons": decision.reasons}
    (out / "detector.json").write_text(json.dumps(result, allow_nan=False, indent=1), encoding="utf-8")
    (out / "detector_tables.md").write_text(render_tables(result), encoding="utf-8")
    sys.stdout.write(
        f"decision: {decision.outcome}" + (f" ({decision.criterion})" if decision.criterion else "") + "\n"
    )
    for line in decision.reasons:
        sys.stdout.write(f"  {line}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="measure both detectors and draw the frames where they disagree")
    p.add_argument("--video-dir", required=True, type=Path)
    p.add_argument(
        "--yolo11", required=True, type=Path, help="the YOLO11 ONNX file exported offline (640, 80 classes, no NMS)"
    )
    p.add_argument("--out", type=Path, default=OUT_DEFAULT)
    p.add_argument("--p308", type=Path, default=P308_DEFAULT, help="the folder of the P3.08 review")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--warmup", type=int, default=30)
    p.add_argument("--frames", type=int, default=300, help="frames of the speed set")
    p.add_argument("--score", type=float, default=0.3, help="the score limit of both detectors")
    p.add_argument(
        "--nms-iou",
        type=float,
        default=DetectorRule().matched_nms_iou,
        help="the NMS limit given to YOLO11 (default %(default)s: the limit inside the shipping YOLOX graph)",
    )
    p.add_argument("--keep-work", action="store_true", help="keep the throwaway ingest (copies of the videos)")
    p.set_defaults(func=run)
    s = sub.add_parser("sheets", help="the page for the review of the frames where only one detector finds a person")
    s.add_argument("--out", type=Path, default=OUT_DEFAULT)
    s.set_defaults(func=sheets)
    r = sub.add_parser("report", help="apply the rule to the reviewed labels and write the tables")
    r.add_argument("--out", type=Path, default=OUT_DEFAULT)
    r.set_defaults(func=report)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging()
    try:
        return int(args.func(args))
    except (BenchError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
