"""The numbers and the tables of the detector comparison (P3.09), from the detections of the two workers.

A is the shipping YOLOX, B the candidate YOLO11. Everything here is computed from arrays and dicts, with no model and no
video, so it is tested on made-up detections. The rule that reads these numbers is ``detector_metrics.decide``
(DEC-0043, written before any measurement).

* Set **R** (labelled frames): ``entries`` say which frames have a reference box (a person known to be there) and which
  are negatives (no person); recall of both detectors, paired, and the false alarms on the negatives.
* Set **C** (clips): the frames in which each detector has a performer-sized box (at least 20 % of the image height),
  the agreement of the two, the **runs** of consecutive frames in which exactly one of them has it (the unit of the
  review: one representative frame per run, so that near-identical frames are not counted many times), the stability of
  the box and the dropouts in seconds.
* Speed: the medians over the repeats of the percentiles of the model-only and the end-to-end time, and the VRAM.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from taiji_ai.bench.detector_metrics import (
    box_iou,
    dropout_runs,
    finds,
    mcnemar_exact,
    performer_box,
    recall_paired,
    stability,
)

MIN_HEIGHT_FRAC = 0.2
BOX_GAP = 3  # frames without a box put between clips when they are pooled: nothing is paired across a clip boundary
SCORE_LIMITS = (0.3, 0.5, 0.7)


def above(detections: np.ndarray, limit: float) -> np.ndarray:
    """The detections with a score strictly above ``limit`` (the detections are stored at the lowest limit, 0.3)."""
    rows = np.asarray(detections, dtype=np.float32).reshape(-1, 5)
    return rows[rows[:, 4] > limit]


def summarise_r(
    entries: Sequence[Mapping[str, Any]],
    dets_a: Sequence[np.ndarray],
    dets_b: Sequence[np.ndarray],
    limit: float = 0.3,
) -> dict[str, Any]:
    """Recall on the labelled frames. ``entries[i]``: ``id``, ``reference`` (a box or ``None``), ``negative`` (bool),
    ``image_height``. A frame with no reference that is not a negative is counted apart (``no_reference``)."""
    if not (len(entries) == len(dets_a) == len(dets_b)):
        raise ValueError("entries, dets_a and dets_b must have the same length")
    pos = [i for i, e in enumerate(entries) if not e["negative"] and e["reference"] is not None]
    neg = [i for i, e in enumerate(entries) if e["negative"]]
    found_a = [finds(above(dets_a[i], limit), entries[i]["reference"]) for i in pos]
    found_b = [finds(above(dets_b[i], limit), entries[i]["reference"]) for i in pos]
    paired = recall_paired(found_a, found_b)

    def false_alarm(dets: Sequence[np.ndarray], i: int) -> bool:
        return performer_box(above(dets[i], limit), float(entries[i]["image_height"]), MIN_HEIGHT_FRAC) is not None

    return {
        "limit": limit,
        "n_positive": len(pos),
        "paired": paired,
        "mcnemar_p": mcnemar_exact(paired["only_b"], paired["only_a"]),
        "negatives": {
            "n": len(neg),
            "false_alarms_a": sum(false_alarm(dets_a, i) for i in neg),
            "false_alarms_b": sum(false_alarm(dets_b, i) for i in neg),
        },
        "no_reference": sum(1 for e in entries if not e["negative"] and e["reference"] is None),
        "missed_ids_a": [entries[i]["id"] for i, f in zip(pos, found_a, strict=True) if not f],
        "missed_ids_b": [entries[i]["id"] for i, f in zip(pos, found_b, strict=True) if not f],
    }


def recall_by_limit(
    entries: Sequence[Mapping[str, Any]],
    dets_a: Sequence[np.ndarray],
    dets_b: Sequence[np.ndarray],
    limits: Sequence[float] = SCORE_LIMITS,
) -> list[dict[str, Any]]:
    """Recall of each detector when its score limit is raised (the detections were kept at the lowest one)."""
    out = []
    for limit in limits:
        r = summarise_r(entries, dets_a, dets_b, limit)
        out.append(
            {
                "limit": limit,
                "recall_a": r["paired"]["recall_a"],
                "recall_b": r["paired"]["recall_b"],
                "n": r["n_positive"],
            }
        )
    return out


IOU_LIMITS = (0.3, 0.5, 0.7)


def iou_profile(
    entries: Sequence[Mapping[str, Any]],
    dets_a: Sequence[np.ndarray],
    dets_b: Sequence[np.ndarray],
    limit: float = 0.3,
    iou_limits: Sequence[float] = IOU_LIMITS,
) -> dict[str, Any]:
    """How well the boxes agree with the reference box (the hull of a confirmed skeleton), apart from the rule.

    The best IoU of each detector per labelled frame (0 when it has no box above the score limit), and the recall at
    other IoU limits. The rule uses 0.5; a detector with looser boxes loses frames at 0.5 that it still finds at 0.3.
    """
    pos = [i for i, e in enumerate(entries) if not e["negative"] and e["reference"] is not None]

    def best(dets: Sequence[np.ndarray]) -> np.ndarray:
        out = []
        for i in pos:
            boxes = above(dets[i], limit)
            out.append(max((box_iou(b[:4], entries[i]["reference"]) for b in boxes), default=0.0))
        return np.array(out, dtype=np.float64)

    a, b = best(dets_a), best(dets_b)

    def spread(v: np.ndarray) -> dict[str, float] | None:
        if len(v) == 0:
            return None
        return {"p10": float(np.percentile(v, 10)), "p25": float(np.percentile(v, 25)), "p50": float(np.median(v))}

    return {
        "n": len(pos),
        "a": spread(a),
        "b": spread(b),
        "recall_at": [
            {
                "iou_min": lim,
                "recall_a": float((a >= lim).mean()) if len(a) else None,
                "recall_b": float((b >= lim).mean()) if len(b) else None,
            }
            for lim in iou_limits
        ],
    }


def _runs(has_a: np.ndarray, has_b: np.ndarray, t: np.ndarray, clip: str) -> list[dict[str, Any]]:
    """Runs of consecutive frames in which exactly one detector has the performer (same direction throughout)."""
    only_a, only_b = has_a & ~has_b, has_b & ~has_a
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 0.0
    runs: list[dict[str, Any]] = []
    for direction, mask in (("only_a", only_a), ("only_b", only_b)):
        i = 0
        while i < len(mask):
            if not mask[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(mask) and mask[j + 1]:
                j += 1
            end = float(t[j + 1]) if j + 1 < len(t) else float(t[j]) + dt
            mid = (i + j) // 2
            runs.append(
                {
                    "clip": clip,
                    "direction": direction,
                    "start_index": i,
                    "end_index": j,
                    "frames": j - i + 1,
                    "seconds": end - float(t[i]),
                    "t_sec": float(t[mid]),
                }
            )
            i = j + 1
    runs.sort(key=lambda r: r["start_index"])
    return runs


def _pool(parts: list[list[np.ndarray | None]]) -> list[np.ndarray | None]:
    """The boxes of several clips in one list, with ``BOX_GAP`` frames without a box between clips."""
    boxes: list[np.ndarray | None] = []
    for part in parts:
        if boxes:
            boxes += [None] * BOX_GAP
        boxes += part
    return boxes


def summarise_c(clips: Mapping[str, Mapping[str, Any]], limit: float = 0.3) -> dict[str, Any]:
    """The clips. ``clips[name]``: ``t_sec`` (n,), ``dets_a`` and ``dets_b`` (a list of ``(k, 5)`` per frame),
    ``image_height``."""
    per_clip: dict[str, Any] = {}
    runs: list[dict[str, Any]] = []
    pooled: dict[str, list[list[np.ndarray | None]]] = {"a": [], "b": []}
    drop: dict[str, list[float]] = {"a": [], "b": []}
    totals = {"frames": 0, "both": 0, "only_a": 0, "only_b": 0, "neither": 0}
    for name, clip in clips.items():
        t = np.asarray(clip["t_sec"], dtype=np.float64)
        height = float(clip["image_height"])
        boxes_a = [performer_box(above(d, limit), height, MIN_HEIGHT_FRAC) for d in clip["dets_a"]]
        boxes_b = [performer_box(above(d, limit), height, MIN_HEIGHT_FRAC) for d in clip["dets_b"]]
        if not (len(boxes_a) == len(boxes_b) == len(t)):
            raise ValueError(f"clip {name}: the two detectors and the times must cover the same frames")
        has_a = np.array([b is not None for b in boxes_a], bool)
        has_b = np.array([b is not None for b in boxes_b], bool)
        counts = recall_paired(has_a, has_b)
        per_clip[name] = {k: counts[k] for k in ("n", "both", "only_a", "only_b", "neither")}
        totals["frames"] += counts["n"]
        for k in ("both", "only_a", "only_b", "neither"):
            totals[k] += counts[k]
        runs += _runs(has_a, has_b, t, name)
        for key, boxes in (("a", boxes_a), ("b", boxes_b)):
            pooled[key].append(boxes)
        drop["a"] += dropout_runs(has_a, has_b, t)
        drop["b"] += dropout_runs(has_b, has_a, t)
    stab: dict[str, Any] = {}
    for key in ("a", "b"):
        boxes = _pool(pooled[key])
        stab[key] = stability(boxes, np.arange(len(boxes), dtype=np.float64))  # only the length of the times is used

    def drops(values: list[float]) -> dict[str, Any]:
        return {
            "count": len(values),
            "total_s": float(sum(values)),
            "longest_s": float(max(values)) if values else None,
            "over_half_second": sum(v > 0.5 for v in values),
        }

    return {
        "limit": limit,
        "totals": totals,
        "per_clip": per_clip,
        "runs": runs,
        "runs_only_a": sum(r["direction"] == "only_a" for r in runs),
        "runs_only_b": sum(r["direction"] == "only_b" for r in runs),
        "stability": stab,
        "dropouts": {"a_loses_what_b_has": drops(drop["a"]), "b_loses_what_a_has": drops(drop["b"])},
    }


def pick_sample(runs: Sequence[Mapping[str, Any]], k: int = 60, seed: int = 20261116) -> list[dict[str, Any]]:
    """All the runs if there are ``k`` or fewer, else a seeded sample of ``k``; ordered by clip and position,
    with an ID."""
    ordered = sorted(runs, key=lambda r: (r["clip"], r["start_index"]))
    if len(ordered) > k:
        keep = sorted(np.random.default_rng(seed).choice(len(ordered), size=k, replace=False).tolist())
        ordered = [ordered[i] for i in keep]
    return [{**dict(r), "id": f"dc-{n:03d}"} for n, r in enumerate(ordered, start=1)]


def speed_summary(worker: Mapping[str, Any]) -> dict[str, Any]:
    """The median over the repeats of each percentile, for the model alone and for the whole detection; the VRAM above
    the baseline. ``n/a`` (None) when the worker has no speed section or no VRAM reading."""
    speed = worker.get("speed")
    out: dict[str, Any] = {}
    if speed:
        reps = speed["repeats"]
        for key in ("model_ms", "end_to_end_ms"):
            out[key] = {p: float(np.median([r[key][p] for r in reps])) for p in ("p50", "p95", "p99")}
        out["pre_ms_median"] = float(np.median([r["pre_ms_median"] for r in reps]))
        out["post_ms_median"] = float(np.median([r["post_ms_median"] for r in reps]))
        out["n_frames"] = speed["n_frames"]
        out["repeats"] = len(reps)
    vram = worker.get("vram") or {}
    out["vram_peak_delta_mib"] = vram.get("peak_delta_mib") if vram.get("measured") else None
    out["vram_baseline_mib"] = vram.get("baseline_mib") if vram.get("measured") else None
    out["load_s"] = worker.get("load_s")
    return out


def _f(x: float | None, digits: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100.0 * x:.1f} %"


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows])


def render_tables(result: Mapping[str, Any]) -> str:
    """Markdown tables of the comparison; a value that does not exist is ``n/a``, never 0."""
    out: list[str] = []

    def section(title: str, body: str) -> None:
        out.append(f"#### {title}\n\n{body}\n")

    sp_a, sp_b = result["speed"]["a"], result["speed"]["b"]
    rows = []
    for name, s in (("YOLOX (shipping)", sp_a), ("YOLO11m", sp_b)):
        m, e = s.get("model_ms"), s.get("end_to_end_ms")
        rows.append(
            [
                name,
                _f(m and m["p50"]), _f(m and m["p95"]), _f(e and e["p50"]), _f(e and e["p95"]), _f(e and e["p99"]),
                _f(s.get("vram_peak_delta_mib"), 0),
            ]
        )  # fmt: skip
    section(
        "Speed and memory (median over the repeats, ms per frame, 640 x 640, batch 1, fp32, CUDA)",
        _table(
            ["Detector", "Model p50", "Model p95", "End-to-end p50", "p95", "p99", "VRAM above baseline [MiB]"], rows
        ),
    )
    r = result["r"]
    p = r["paired"]
    section(
        f"Recall of the performer on the labelled frames (score limit {r['limit']:g}; "
        f"{r['n_positive']} frames with a reference box)",
        _table(
            ["Recall A", "Recall B", "Both", "Only A", "Only B", "Neither", "McNemar p (exact)"],
            [
                [
                    _pct(p["recall_a"]),
                    _pct(p["recall_b"]),
                    str(p["both"]),
                    str(p["only_a"]),
                    str(p["only_b"]),
                    str(p["neither"]),
                    _f(r["mcnemar_p"], 4),
                ]
            ],
        )
        + f"\n\nNegative frames (no person): {r['negatives']['n']}; false alarms A {r['negatives']['false_alarms_a']}, "
        f"B {r['negatives']['false_alarms_b']}. Frames without a usable reference box: {r['no_reference']}.",
    )
    section(
        "Recall when the score limit is raised",
        _table(
            ["Score limit", "Frames", "Recall A", "Recall B"],
            [[f"{x['limit']:g}", str(x["n"]), _pct(x["recall_a"]), _pct(x["recall_b"])] for x in result["r_by_limit"]]
            or [["n/a", "0", "n/a", "n/a"]],
        ),
    )
    prof = result.get("r_iou")
    if prof is not None:
        section(
            "Box agreement with the reference box (best IoU per labelled frame; the rule uses IoU 0.5)",
            _table(
                ["Detector", "IoU p10", "p25", "median"],
                [
                    [name, _f(s and s["p10"]), _f(s and s["p25"]), _f(s and s["p50"])]
                    for name, s in (("YOLOX (shipping)", prof["a"]), ("YOLO11m", prof["b"]))
                ],
            )
            + "\n\n"
            + _table(
                ["IoU limit", "Recall A", "Recall B"],
                [[f"{x['iou_min']:g}", _pct(x["recall_a"]), _pct(x["recall_b"])] for x in prof["recall_at"]]
                or [["n/a", "n/a", "n/a"]],
            ),
        )
    c = result["c"]
    t = c["totals"]
    section(
        "The clips: frames with a performer-sized box (at least 20 % of the image height)",
        _table(
            ["Clip", "Frames", "Both", "Only A", "Only B", "Neither"],
            [
                [n, str(v["n"]), str(v["both"]), str(v["only_a"]), str(v["only_b"]), str(v["neither"])]
                for n, v in c["per_clip"].items()
            ]
            + [["all", str(t["frames"]), str(t["both"]), str(t["only_a"]), str(t["only_b"]), str(t["neither"])]],
        )
        + "\n\nRuns of frames where only one detector has the performer: "
        f"only A {c['runs_only_a']}, only B {c['runs_only_b']}. Frames where both miss cannot be seen by this method.",
    )
    srows = []
    for name, key in (("YOLOX (shipping)", "a"), ("YOLO11m", "b")):
        s = c["stability"][key]
        d, h = s["one_minus_iou"], s["height_change"]
        srows.append(
            [
                name,
                str(s["pairs"]),
                str(s["jumps"]),
                _f(d and d["p50"], 4),
                _f(d and d["p95"], 4),
                _f(d and d["p99"], 4),
                _f(h and h["p95"], 4),
            ]
        )
    section(
        "Stability of the performer's box (consecutive frames)",
        _table(["Detector", "Pairs", "Jumps (IoU < 0.5)", "1 - IoU p50", "p95", "p99", "Height change p95"], srows),
    )
    dr = c["dropouts"]
    section(
        "Dropouts: seconds in which one detector loses the performer while the other has them",
        _table(
            ["Detector that loses", "Runs", "Total [s]", "Longest [s]", "Runs over 0.5 s"],
            [
                [name, str(v["count"]), _f(v["total_s"], 2), _f(v["longest_s"], 2), str(v["over_half_second"])]
                for name, v in (("YOLOX (shipping)", dr["a_loses_what_b_has"]), ("YOLO11m", dr["b_loses_what_a_has"]))
            ],
        ),
    )
    rev = result.get("review")
    if rev is not None:
        section(
            "The reviewed runs of the clips (one representative frame per run)",
            _table(
                ["Runs", "Reviewed", "B right, A wrong", "A right, B wrong", "Unsure"],
                [
                    [
                        str(rev["n_discordant"]),
                        str(rev["n_reviewed"]),
                        str(rev["b_better"]),
                        str(rev["a_better"]),
                        str(rev.get("unsure", 0)),
                    ]
                ],
            ),
        )
    dec = result.get("decision")
    if dec is not None:
        section(
            "The decision by the rule written before the measurement (DEC-0043)",
            f"**{dec['outcome']}**"
            + (f" (criterion {dec['criterion']})" if dec["criterion"] else "")
            + "\n\n"
            + "\n".join(f"- {x}" for x in dec["reasons"]),
        )
    return "\n".join(out)
