"""From the two passes to the frames to look at (P3.08): signals, selection, sheets, the review file, the report tables.

``analyse`` reads the pose files of the pass at N = 1 (``out/``) and at N = 5 (``out/n5/``), follows the target in
every chunk (the default rule at the chunk start, then ``resolve_target``), computes the measures of
``taiji_ai.audit.signals`` on the target of the N = 1 pass, the difference between the two cadences, chooses the
frames (``taiji_ai.audit.select``), decodes them from the stored recordings and writes, under ``out/``:
``sheets/sheet_NN.png`` (12 frames each, both skeletons: N = 1 thick, N = 5 thin and light), ``sheets/strips_NN.png``
(three consecutive frames of each ``jump`` candidate), ``candidates.json``, ``signals.json`` and an empty
``review.csv``. It **refuses to overwrite** a review file (``force=True`` does) because that file is filled by hand.

``report`` reads the review file and writes ``summary.json`` and ``report_tables.md``. The score of a wrong joint is
taken from the cadence that is wrong: the N = 5 skeleton when the label says ``n5_only``, the N = 1 skeleton
otherwise.

Everything here is local: pictures, pose files and candidate lists hold frames and keypoints of the videos and are never
committed; only the tables go to the report.
"""

from __future__ import annotations

import json
import logging
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from taiji_ai.audit import AuditError
from taiji_ai.audit.labels import final_label, read_review, write_template
from taiji_ai.audit.render import caption_text, contact_sheet, strip, tile
from taiji_ai.audit.scan import chunk_frame_mask, load_chunk, read_pass
from taiji_ai.audit.select import Candidate, Rule, select_frames
from taiji_ai.audit.signals import RULE_HIGHER_IS_WORSE, TAU_KP, cadence_difference, compute_signals
from taiji_ai.audit.summary import render_tables, summarise
from taiji_ai.io.frames import iter_frames
from taiji_ai.pose.runner import PoseRaw
from taiji_ai.schemas._base import read_manifest
from taiji_ai.schemas.recording import RecordingManifest
from taiji_ai.track.associate import associate_tracks
from taiji_ai.track.state import TRACKED, TargetStateError, TargetTrack, resolve_target
from taiji_ai.track.target import TargetSelectionError, select_target

log = logging.getLogger(__name__)

SIGNAL_RULES = (
    "low_essential", "structure", "jump", "bone", "swap_pair", "find_back", "find_one_leg", "find_rotation",
    "find_occlusion",
)  # fmt: skip
PER_SHEET = 12
STRIPS_PER_IMAGE = 4


@dataclass
class Pool:
    """Every kept frame of one pass, in the order video, chunk, frame; arrays have one entry per frame."""

    video: list[str] = field(default_factory=list)
    chunk: np.ndarray = field(default_factory=lambda: np.empty(0, np.int64))  # index of the chunk in its video
    pos: np.ndarray = field(
        default_factory=lambda: np.empty(0, np.int64)
    )  # position of the frame in its chunk's pose file
    frame_index: np.ndarray = field(default_factory=lambda: np.empty(0, np.int64))
    t_sec: np.ndarray = field(default_factory=lambda: np.empty(0))
    tracked: np.ndarray = field(default_factory=lambda: np.empty(0, bool))
    kp: np.ndarray = field(default_factory=lambda: np.empty((0, 26, 2), np.float32))
    scores: np.ndarray = field(default_factory=lambda: np.empty((0, 26), np.float32))
    valid: np.ndarray = field(default_factory=lambda: np.empty((0, 26), bool))
    ref_height: np.ndarray = field(default_factory=lambda: np.empty(0))  # the median body height of the frame's chunk
    event: np.ndarray = field(
        default_factory=lambda: np.empty(0)
    )  # 1.0 at a frame with an event of the target, else NaN
    signals: dict[str, np.ndarray] = field(default_factory=dict)
    no_target: list[tuple[str, int]] = field(default_factory=list)  # (video, chunk) with no target at all


def target_track(raw: PoseRaw) -> TargetTrack | None:
    """The performer of a chunk, followed by ``resolve_target``; ``None`` if nobody can be chosen.

    For this review the performer is the **most persistent large person of the chunk**: the track with the largest sum
    of box areas (a long track of a large person), chosen at the middle of that track with the box of its person. The
    default rule of the product (the largest person near the centre at the start of a segment) is wrong on a lesson
    that opens with a title card or a different shot, which would leave a chunk without a target; the product asks the
    user, the review has no user.
    """
    tracks = associate_tracks(raw)
    if tracks.n_tracks == 0:
        return None
    area = (raw.bboxes[:, 2] - raw.bboxes[:, 0]).astype(np.float64) * (raw.bboxes[:, 3] - raw.bboxes[:, 1])
    mass = np.bincount(
        tracks.track_id[tracks.track_id >= 0], weights=area[tracks.track_id >= 0], minlength=tracks.n_tracks
    )
    best = int(np.argmax(mass))
    rows = np.flatnonzero(tracks.track_id == best)
    row = int(rows[len(rows) // 2])
    frame = int(np.searchsorted(raw.person_offsets, row, side="right") - 1)
    try:
        x0, y0, x1, y1 = (float(v) for v in raw.bboxes[row])
        selection = select_target(raw, bbox=(x0, y0, x1, y1), at_t_sec=float(raw.t_sec[frame]))
        return resolve_target(raw, tracks, selection)
    except (TargetSelectionError, TargetStateError):
        return None


def collect_pass(out_dir: Path | str, tau: float = TAU_KP) -> Pool:
    """Load every chunk of a pass, follow the target, compute the signals; the margins of ``run_pose`` are dropped."""
    manifest = read_pass(out_dir)
    pool = Pool()
    parts: dict[str, list[Any]] = {
        k: [] for k in ("chunk", "pos", "frame_index", "t_sec", "tracked", "kp", "scores", "valid", "ref", "event")
    }
    sig_parts: dict[str, list[np.ndarray]] = {}
    for label in sorted(manifest["videos"]):
        chunks = manifest["videos"][label]["chunks"]
        for c in chunks:
            raw = load_chunk(out_dir, label, c["index"])
            track = target_track(raw)
            keep = chunk_frame_mask(
                raw.t_sec, c["start_s"], c["end_s"], first=c["index"] == 0, last=c["index"] == len(chunks) - 1
            )
            n = raw.n_frames
            event = np.full(n, np.nan)
            if track is None:
                pool.no_target.append((label, c["index"]))
                kp, sc = np.full((n, 26, 2), np.nan, np.float32), np.full((n, 26), np.nan, np.float32)
                tracked = np.zeros(n, dtype=bool)
            else:
                kp, sc, tracked = track.keypoints, track.scores, track.status == TRACKED
                for e in track.meta.events:
                    event[e.frame_pos] = 1.0
            sig = compute_signals(kp, sc, raw.t_sec, tracked, tau)
            parts["chunk"].append(np.full(int(keep.sum()), c["index"]))
            parts["pos"].append(np.flatnonzero(keep))
            parts["frame_index"].append(raw.frame_index[keep])
            parts["t_sec"].append(raw.t_sec[keep])
            parts["tracked"].append(tracked[keep])
            parts["kp"].append(kp[keep])
            parts["scores"].append(sc[keep])
            parts["valid"].append(sig["valid"][keep])
            parts["ref"].append(np.full(int(keep.sum()), float(sig["ref_height"])))
            parts["event"].append(event[keep])
            for name, values in sig.items():
                if values.ndim == 1 and name != "ref_height":
                    sig_parts.setdefault(name, []).append(values[keep])
            pool.video.extend([label] * int(keep.sum()))
            log.info(
                "%s chunk %d: %d frames kept, target %s",
                label,
                c["index"],
                int(keep.sum()),
                "found" if track else "not found",
            )
    pool.chunk, pool.pos = np.concatenate(parts["chunk"]), np.concatenate(parts["pos"])
    pool.frame_index, pool.t_sec = np.concatenate(parts["frame_index"]), np.concatenate(parts["t_sec"])
    pool.tracked, pool.kp = np.concatenate(parts["tracked"]), np.concatenate(parts["kp"])
    pool.scores, pool.valid = np.concatenate(parts["scores"]), np.concatenate(parts["valid"])
    pool.ref_height, pool.event = np.concatenate(parts["ref"]), np.concatenate(parts["event"])
    pool.signals = {name: np.concatenate(chunks) for name, chunks in sig_parts.items()}
    return pool


def _check_aligned(a: Pool, b: Pool) -> None:
    if not (a.video == b.video and np.array_equal(a.frame_index, b.frame_index) and np.array_equal(a.t_sec, b.t_sec)):
        raise AuditError("the passes at N = 1 and N = 5 do not cover the same frames: run both over the same chunks")


def _frame_weights(pool: Pool) -> np.ndarray:
    """The frame interval of each frame's video (so that the blind sample is drawn uniformly in time, not in frames)."""
    weights = np.ones(len(pool.video))
    labels = np.asarray(pool.video)
    for label in dict.fromkeys(pool.video):
        mask = labels == label
        weights[mask] = float(np.median(np.diff(pool.t_sec[mask]))) if mask.sum() > 1 else 1.0
    return weights


def _clean(value: Any) -> Any:
    """JSON-safe: NaN and infinity become ``None``, numpy numbers plain numbers."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return _clean(value.tolist())
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    return value


class _Frames:
    """Decode one frame of a stored recording by time (the nearest frame to ``t_sec``)."""

    def __init__(self, work_dir: Path, manifest: dict[str, Any]):
        self._sources: dict[str, tuple[Path, int]] = {}
        for label, video in manifest["videos"].items():
            rec = work_dir / "data" / "recordings" / video["recording_id"]
            info = read_manifest(rec / "recording.json", RecordingManifest)
            self._sources[label] = (rec / f"source{info.source_ext}", info.display_rotation)

    def get(self, label: str, t_sec: float) -> np.ndarray:
        source, rotation = self._sources[label]
        best: tuple[float, np.ndarray] | None = None
        for frame in iter_frames(source, max(0.0, t_sec - 0.05), t_sec + 0.05, rotation_deg=rotation):
            gap = abs(frame.t_sec - t_sec)
            if best is None or gap < best[0]:
                best = (gap, frame.image)
        if best is None:
            raise AuditError(f"no frame of {label} near {t_sec:.3f} s: the stored recording does not match the pass")
        return best[1]


class _RawCache:
    """The last few ``PoseRaw`` chunks, to read the boxes of the other persons of a frame."""

    def __init__(self, out_dir: Path, size: int = 3):
        self._out, self._size = out_dir, size
        self._items: OrderedDict[tuple[str, int], PoseRaw] = OrderedDict()

    def boxes(self, label: str, chunk: int, pos: int) -> list[np.ndarray]:
        key = (label, chunk)
        if key not in self._items:
            self._items[key] = load_chunk(self._out, label, chunk)
            while len(self._items) > self._size:
                self._items.popitem(last=False)
        raw = self._items[key]
        return [raw.bboxes[r] for r in range(int(raw.person_offsets[pos]), int(raw.person_offsets[pos + 1]))]


def analyse(
    out_dir: Path | str,
    work_dir: Path | str,
    *,
    n5_dir: Path | str | None = None,
    tau: float = TAU_KP,
    k: int = 20,
    blind_k: int = 40,
    min_gap_s: float = 2.0,
    seed: int = 20261116,
    tile_size: int = 380,
    force: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Choose the frames and write the sheets, the candidates and an empty review file; see the module docstring."""
    out, work = Path(out_dir), Path(work_dir)
    n5 = Path(n5_dir) if n5_dir is not None else out / "n5"
    review = out / "review.csv"
    if review.exists() and not force:
        raise AuditError("review.csv exists and may hold a review: use force to start again (it would be overwritten)")
    manifest = read_pass(out)
    p1, p5 = collect_pass(out, tau), collect_pass(n5, tau)
    _check_aligned(p1, p5)

    cadence = cadence_difference(p1.kp, p1.valid, p5.kp, p5.valid, p1.ref_height)
    # a frame without the target is not a candidate of a pose rule (``low_essential`` counts it as all joints missing)
    rules = [
        Rule(name, np.where(p1.tracked, p1.signals[name], np.nan), RULE_HIGHER_IS_WORSE[name]) for name in SIGNAL_RULES
    ]
    rules += [Rule("target_event", p1.event), Rule("cadence_diff", cadence)]
    candidates = select_frames(
        rules, t_sec=p1.t_sec, video=p1.video, frame_index=p1.frame_index, tracked=p1.tracked, k=k, min_gap_s=min_gap_s,
        blind_k=blind_k, seed=seed, weight=_frame_weights(p1),
    )  # fmt: skip

    frames, raws = _Frames(work, manifest), _RawCache(out)
    sheets_dir = out / "sheets"
    sheets_dir.mkdir(parents=True, exist_ok=True)

    def one(pos: int, caption: str) -> np.ndarray:
        label = p1.video[pos]
        image = frames.get(label, float(p1.t_sec[pos]))
        boxes = raws.boxes(label, int(p1.chunk[pos]), int(p1.pos[pos]))
        skeletons = [(p1.kp[pos], p1.scores[pos], False), (p5.kp[pos], p5.scores[pos], True)]
        return tile(image, skeletons, caption, size=tile_size, tau=tau, boxes=boxes)

    tiles: list[np.ndarray] = []
    strips: list[np.ndarray] = []
    records = []
    for c in candidates:
        tiles.append(one(c.pos, caption_text(c.cid, c.video, c.t_sec, c.tags)))
        strip_name = None
        if "jump" in c.tags:
            around = [p for p in (c.pos - 1, c.pos, c.pos + 1) if 0 <= p < len(p1.video) and p1.video[p] == c.video]
            strips.append(
                strip([one(p, f"{c.cid} {'prev' if p < c.pos else 'next' if p > c.pos else 'this'}") for p in around])
            )
            strip_name = f"strips_{(len(strips) - 1) // STRIPS_PER_IMAGE + 1:02d}.png"
        slot = len(tiles) - 1
        records.append(
            _record(c, p1, p5, cadence, sheet=slot // PER_SHEET + 1, slot=slot % PER_SHEET, strip=strip_name)
        )
        if progress:
            progress(f"{c.cid} done")
    for number, start in enumerate(range(0, len(tiles), PER_SHEET), start=1):
        cv2.imwrite(
            str(sheets_dir / f"sheet_{number:02d}.png"), contact_sheet(tiles[start : start + PER_SHEET], columns=4)
        )
    for number, start in enumerate(range(0, len(strips), STRIPS_PER_IMAGE), start=1):
        cv2.imwrite(
            str(sheets_dir / f"strips_{number:02d}.png"),
            contact_sheet(strips[start : start + STRIPS_PER_IMAGE], columns=1),
        )

    signals = _signals_summary(p1, p5, cadence, rules, candidates)
    (out / "candidates.json").write_text(json.dumps(_clean(records), allow_nan=False, indent=1), encoding="utf-8")
    (out / "signals.json").write_text(json.dumps(_clean(signals), allow_nan=False, indent=1), encoding="utf-8")
    write_template(review, [(c.cid, c.video, c.frame_index, c.t_sec, c.tags) for c in candidates])
    return {
        "n_candidates": len(candidates),
        "n_sheets": -(-len(tiles) // PER_SHEET),
        "n_strips": len(strips),
        "signals": signals,
    }


def _record(
    c: Candidate, p1: Pool, p5: Pool, cadence: np.ndarray, *, sheet: int, slot: int, strip: str | None
) -> dict[str, Any]:
    return {
        "id": c.cid, "video": c.video, "chunk": int(p1.chunk[c.pos]), "frame_index": c.frame_index, "t_sec": c.t_sec,
        "tags": list(c.tags), "rule_scores": c.scores, "cadence_diff": float(cadence[c.pos]),
        "scores_n1": p1.scores[c.pos], "scores_n5": p5.scores[c.pos], "sheet": sheet, "slot": slot, "strip": strip,
    }  # fmt: skip


def _signals_summary(
    p1: Pool, p5: Pool, cadence: np.ndarray, rules: list[Rule], candidates: list[Candidate]
) -> dict[str, Any]:
    labels = np.asarray(p1.video)
    per_video = {}
    for label in dict.fromkeys(p1.video):
        mask = labels == label
        per_video[label] = {
            "frames": int(mask.sum()),
            "tracked_n1": int(p1.tracked[mask].sum()),
            "tracked_n5": int(p5.tracked[mask].sum()),
        }
    per_rule = {}
    for rule in rules:
        finite = np.isfinite(rule.score)
        per_rule[rule.name] = {
            "eligible": int(finite.sum()),
            "taken": sum(rule.name in c.tags for c in candidates),
            "min": float(rule.score[finite].min()) if finite.any() else None,
            "median": float(np.median(rule.score[finite])) if finite.any() else None,
            "max": float(rule.score[finite].max()) if finite.any() else None,
        }
    return {
        "frames": len(p1.video),
        "per_video": per_video,
        "per_rule": per_rule,
        "blind_taken": sum(c.tags == ("blind",) for c in candidates),
        "chunks_without_target_n1": [list(x) for x in p1.no_target],
        "chunks_without_target_n5": [list(x) for x in p5.no_target],
        "cadence_diff_p95": float(np.nanpercentile(cadence, 95)) if np.isfinite(cadence).any() else None,
        "cadence_diff_max": float(np.nanmax(cadence)) if np.isfinite(cadence).any() else None,
    }


def report(out_dir: Path | str, tau: float = TAU_KP) -> dict[str, Any]:
    """Read the finished review, write ``summary.json`` and ``report_tables.md`` and return the summary."""
    out = Path(out_dir)
    try:
        records = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AuditError("candidates.json is missing: run analyse first") from exc
    rows = read_review(out / "review.csv", expected_ids=[r["id"] for r in records])
    scores: dict[str, np.ndarray] = {}
    for r in rows:
        record = next(x for x in records if x["id"] == r.cid)
        key = "scores_n5" if final_label(r).cadence == "n5_only" else "scores_n1"
        scores[r.cid] = np.array([np.nan if v is None else v for v in record[key]], dtype=np.float64)
    summary = summarise(rows, scores, tau)
    (out / "summary.json").write_text(json.dumps(_clean(summary), allow_nan=False, indent=1), encoding="utf-8")
    (out / "report_tables.md").write_text(render_tables(summary), encoding="utf-8")
    return summary
