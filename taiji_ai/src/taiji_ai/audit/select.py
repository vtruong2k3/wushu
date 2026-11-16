"""Which frames to look at (P3.08): rank-based, spaced in time, one blind random sample, overlaps merged.

The frames of all the clips are pooled in arrays of length ``N`` (``t_sec``, ``video``, ``frame_index``, ``tracked``).
Each ``Rule`` gives a score per frame (NaN: the frame is not eligible for that rule) and a direction. A rule takes its
``k`` worst frames, **at least ``min_gap_s`` of real time apart within the same video** (the spacing is inclusive),
ties broken by one seeded random order, so that a rule whose score is constant does not always pick the start of the
first video. A frame that two rules take appears once with both tags; every rule still has its own ``k`` frames, which
keeps the precision of each rule measurable over the same number of frames. No threshold is used (AGENTS.md section
5.5). Each video has its share of the ``k`` frames of a rule (by the time it covers, or ``video_share``); a video
with too few eligible frames hands its slots to the others.

The **blind sample** is drawn by a seeded weighted random order among the tracked frames that no rule took and that
are not within ``min_gap_s`` of a taken frame or of an earlier blind frame (same video): it is the base rate of
failures that the rules do not point at. ``weight`` (default 1 per frame) lets the caller draw uniformly in time
rather than in frames. Fewer eligible frames than asked give fewer frames, never a duplicate. The result is
deterministic for a seed.
"""

from __future__ import annotations

import bisect
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from taiji_ai.audit import AuditError

_EPS = 1e-9
BLIND = "blind"


@dataclass(frozen=True)
class Rule:
    name: str
    score: np.ndarray  # (N,) float; NaN = not eligible for this rule
    higher_is_worse: bool = True


@dataclass(frozen=True)
class Candidate:
    cid: str  # fc-001, in order of video then time
    video: str
    frame_index: int  # row of the frame in pts.parquet
    pos: int  # position in the pooled arrays
    t_sec: float
    tags: tuple[str, ...]  # the rules that took the frame (in the order of the rules), or ("blind",)
    scores: dict[str, float]  # the score each tagging rule gave this frame


class _Spacing:
    """The accepted times of each video, to ask whether a new frame is far enough from all of them."""

    def __init__(self, min_gap_s: float):
        self._gap = min_gap_s
        self._times: dict[str, list[float]] = {}

    def free(self, video: str, t: float) -> bool:
        times = self._times.get(video, [])
        i = bisect.bisect_left(times, t)
        near = [times[j] for j in (i - 1, i) if 0 <= j < len(times)]
        return all(abs(t - other) >= self._gap - _EPS for other in near)

    def add(self, video: str, t: float) -> None:
        bisect.insort(self._times.setdefault(video, []), t)


def _time_share(t: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    """The share of each video in the time the pooled frames cover (a video of one frame counts one second)."""
    spans = {}
    for label in dict.fromkeys(str(v) for v in labels):
        times = t[labels == label]
        spans[label] = float(times.max() - times.min()) if times.size > 1 else 1.0
    total = sum(spans.values())
    return {label: span / total for label, span in spans.items()} if total > 0 else {}


def _quotas(k: int, share: Mapping[str, float]) -> dict[str, int]:
    """``k`` split over the videos by their share (largest remainder), the sum is exactly ``k``."""
    total = sum(share.values())
    if not share or not (total > 0.0):
        return {}
    raw = {label: k * s / total for label, s in share.items()}
    quota = {label: int(math.floor(x)) for label, x in raw.items()}
    for label in sorted(share, key=lambda v: (-(raw[v] - quota[v]), v))[: k - sum(quota.values())]:
        quota[label] += 1
    return quota


def select_frames(
    rules: Sequence[Rule],
    *,
    t_sec: np.ndarray,
    video: Sequence[str],
    frame_index: np.ndarray,
    tracked: np.ndarray,
    k: int = 20,
    min_gap_s: float = 2.0,
    blind_k: int = 40,
    seed: int = 20261116,
    weight: np.ndarray | None = None,
    video_share: Mapping[str, float] | None = None,
) -> list[Candidate]:
    """The frames of the review: the ``k`` worst of every rule and ``blind_k`` blind ones; see the module docstring.

    ``video_share`` is the share of each video in the ``k`` frames of a rule (default: its share of the time the frames
    cover); a video with too few eligible frames hands its slots to the others.
    """
    n = len(t_sec)
    if not (len(video) == len(frame_index) == len(tracked) == n):
        raise AuditError("t_sec, video, frame_index and tracked must have the same length")
    if k < 0 or blind_k < 0 or not (math.isfinite(min_gap_s) and min_gap_s >= 0.0):
        raise AuditError("k and blind_k must be >= 0 and min_gap_s a finite number >= 0")
    if len({r.name for r in rules}) != len(rules) or BLIND in {r.name for r in rules}:
        raise AuditError(f"rule names must be distinct and not '{BLIND}'")
    t = np.asarray(t_sec, dtype=np.float64)
    labels = np.asarray(video)
    rng = np.random.default_rng(seed)
    tiebreak = rng.permutation(n)
    quota = _quotas(k, video_share if video_share is not None else _time_share(t, labels))
    taken: dict[int, list[str]] = {}
    scores: dict[int, dict[str, float]] = {}
    for rule in rules:
        score = np.asarray(rule.score, dtype=np.float64)
        if score.shape != (n,):
            raise AuditError(f"rule {rule.name!r} has {score.size} scores for {n} frames")
        values = score if rule.higher_is_worse else -score
        eligible = np.flatnonzero(np.isfinite(values))
        order = eligible[np.lexsort((tiebreak[eligible], -values[eligible]))]
        spacing = _Spacing(min_gap_s)
        own: set[int] = set()
        per_video: Counter[str] = Counter()
        for stage in ("quota", "fill"):  # the share of each video first, then what is left by the global rank
            for pos in order:
                if len(own) >= k:
                    break
                video_of = str(labels[pos])
                if int(pos) in own or (stage == "quota" and per_video[video_of] >= quota.get(video_of, 0)):
                    continue
                if not spacing.free(video_of, float(t[pos])):
                    continue
                spacing.add(video_of, float(t[pos]))
                own.add(int(pos))
                per_video[video_of] += 1
                taken.setdefault(int(pos), []).append(rule.name)
                scores.setdefault(int(pos), {})[rule.name] = float(score[pos])

    if blind_k > 0:
        around = _Spacing(min_gap_s)
        for pos in taken:
            around.add(str(labels[pos]), float(t[pos]))
        w = np.ones(n) if weight is None else np.asarray(weight, dtype=np.float64)
        if w.shape != (n,) or np.any(w < 0) or not np.all(np.isfinite(w)):
            raise AuditError("weight must be n finite numbers >= 0")
        pool = np.flatnonzero(np.asarray(tracked, dtype=bool) & (w > 0))
        pool = np.array([p for p in pool if int(p) not in taken], dtype=np.int64)
        if pool.size:
            # weighted draw without replacement: ascending -log(u) / w is a weighted random order
            keys = -np.log(rng.random(pool.size)) / w[pool]
            picked = 0
            for pos in pool[np.argsort(keys, kind="stable")]:
                if picked >= blind_k:
                    break
                if not around.free(str(labels[pos]), float(t[pos])):
                    continue
                around.add(str(labels[pos]), float(t[pos]))
                taken.setdefault(int(pos), []).append(BLIND)
                scores.setdefault(int(pos), {})[BLIND] = float("nan")
                picked += 1

    order_names = {r.name: i for i, r in enumerate(rules)}
    ordered = sorted(taken, key=lambda p: (str(labels[p]), float(t[p])))
    return [
        Candidate(
            cid=f"fc-{i:03d}",
            video=str(labels[pos]),
            frame_index=int(frame_index[pos]),
            pos=pos,
            t_sec=float(t[pos]),
            tags=tuple(sorted(taken[pos], key=lambda name: order_names.get(name, len(order_names)))),
            scores=scores[pos],
        )
        for i, pos in enumerate(ordered, start=1)
    ]
