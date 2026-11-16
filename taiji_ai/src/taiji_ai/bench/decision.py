"""The written rule that recommends the detector cadence N (P3.07).

The rule was fixed before the measurement (task file P3.07, section 1, point 8) and is an engineering choice for a
parameter, not a metric threshold (AGENTS.md section 5.5). Against N = 1 (the detector on every frame), pooled over the
clips, N is **acceptable** when all of these hold:

* the person-count agreement is at least ``min_count_agreement`` (0.99);
* the keypoint distance p95 is at most ``max_p95_norm`` (0.01 body height) and p99 at most ``max_p99_norm`` (0.03);
* the ``tracked`` share of the target is not lower than N = 1's by more than ``max_tracked_loss_points`` (0.5
  percentage points);
* no clip gets ``needs_reselect`` that N = 1 does not have.

The recommendation is the largest acceptable N, with one brake: after the first acceptable N, a larger one is adopted
only if it is at least ``min_speed_gain`` (0.15) faster in median elapsed time than the previous one. The search stops
at the first N that is not acceptable, so if N = 5 is not acceptable the answer is N = 1 whatever N = 10 looks like.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from taiji_ai.bench import BenchError


@dataclass(frozen=True)
class DecisionRule:
    min_count_agreement: float = 0.99
    max_p95_norm: float = 0.01  # body heights
    max_p99_norm: float = 0.03  # body heights
    max_tracked_loss_points: float = 0.5  # percentage points
    min_speed_gain: float = 0.15  # share of the time of the previous N

    def __post_init__(self) -> None:
        if not (math.isfinite(self.min_count_agreement) and 0.0 < self.min_count_agreement <= 1.0):
            raise ValueError(f"min_count_agreement must be in (0, 1], got {self.min_count_agreement!r}")
        if not (math.isfinite(self.max_p95_norm) and self.max_p95_norm >= 0.0):
            raise ValueError(f"max_p95_norm must be a finite number >= 0, got {self.max_p95_norm!r}")
        if not (math.isfinite(self.max_p99_norm) and self.max_p99_norm >= self.max_p95_norm):
            raise ValueError(f"max_p99_norm must be finite and not below max_p95_norm, got {self.max_p99_norm!r}")
        if not (math.isfinite(self.max_tracked_loss_points) and self.max_tracked_loss_points >= 0.0):
            raise ValueError(
                f"max_tracked_loss_points must be a finite number >= 0, got {self.max_tracked_loss_points!r}"
            )
        if not (math.isfinite(self.min_speed_gain) and 0.0 <= self.min_speed_gain < 1.0):
            raise ValueError(f"min_speed_gain must be in [0, 1), got {self.min_speed_gain!r}")


@dataclass(frozen=True)
class NStats:
    """What was measured for one N, against N = 1 (for N = 1 itself: the reference values)."""

    n: int
    count_agreement: float  # share of frames with the same number of persons as N = 1
    p95_norm: float | None  # keypoint distance, body heights; None when no pair of persons was compared
    p99_norm: float | None
    # (N = 1 tracked share - this tracked share) in percentage points, > 0 is worse; None: no clip had a target in both
    tracked_loss_points: float | None
    new_needs_reselect: int  # clips with needs_reselect that N = 1 does not have
    elapsed_median_s: float  # median elapsed seconds of one pass over the clips


@dataclass(frozen=True)
class Recommendation:
    n: int
    acceptable: dict[int, bool]  # for every N above 1
    reasons: dict[int, list[str]]  # why each N above 1 is not acceptable (empty list: acceptable)
    speed_gain_vs_previous: dict[int, float] = field(default_factory=dict)  # for every N above 1: vs the next smaller N


def speed_gain(slow_s: float, fast_s: float) -> float:
    """Share of the slower time that the faster one saves (negative if it is slower)."""
    if not (math.isfinite(slow_s) and slow_s > 0.0 and math.isfinite(fast_s) and fast_s >= 0.0):
        raise BenchError(f"times must be finite, the slower one above 0: {slow_s!r}, {fast_s!r}")
    return 1.0 - fast_s / slow_s


def _reasons(s: NStats, rule: DecisionRule) -> list[str]:
    out: list[str] = []
    if s.count_agreement < rule.min_count_agreement:
        out.append(f"person-count agreement {s.count_agreement:.4f} is below {rule.min_count_agreement}")
    if s.p95_norm is None or s.p99_norm is None:
        out.append("no keypoint pairs were compared, so the distance is unknown")
    else:
        if s.p95_norm > rule.max_p95_norm:
            out.append(f"p95 distance {s.p95_norm:.5f} body heights is above {rule.max_p95_norm}")
        if s.p99_norm > rule.max_p99_norm:
            out.append(f"p99 distance {s.p99_norm:.5f} body heights is above {rule.max_p99_norm}")
    if s.tracked_loss_points is None:
        out.append("the tracked share of the target could not be compared (no clip has a target in both runs)")
    elif s.tracked_loss_points > rule.max_tracked_loss_points:
        out.append(
            f"the tracked share of the target fell by {s.tracked_loss_points:.2f} points "
            f"(limit {rule.max_tracked_loss_points})"
        )
    if s.new_needs_reselect > 0:
        out.append(f"needs_reselect appeared in {s.new_needs_reselect} clip(s) where N = 1 has none")
    return out


def recommend_n(stats: Sequence[NStats], rule: DecisionRule | None = None) -> Recommendation:
    """Apply the rule to the measurements of N = 1 (reference) and of the larger N; see the module docstring."""
    rule = rule or DecisionRule()
    by_n: dict[int, NStats] = {}
    for s in stats:
        if s.n in by_n:
            raise BenchError(f"N = {s.n} was measured twice")
        by_n[s.n] = s
    if 1 not in by_n:
        raise BenchError("the measurement of N = 1 is needed as the reference")
    ordered = sorted(by_n)
    acceptable: dict[int, bool] = {}
    reasons: dict[int, list[str]] = {}
    gains: dict[int, float] = {}
    for previous, n in zip(ordered, ordered[1:], strict=False):
        reasons[n] = _reasons(by_n[n], rule)
        acceptable[n] = not reasons[n]
        gains[n] = speed_gain(by_n[previous].elapsed_median_s, by_n[n].elapsed_median_s)
    best = 1
    for n in ordered[1:]:
        if not acceptable[n]:
            break
        if best != 1 and gains[n] < rule.min_speed_gain:
            break
        best = n
    return Recommendation(best, acceptable, reasons, gains)
